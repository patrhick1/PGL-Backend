# podcast_outreach/services/enrichment/data_merger.py

import logging
from typing import Dict, Any, Optional
from pydantic import HttpUrl, ValidationError

from podcast_outreach.database.models.media_models import EnrichedPodcastProfile
from podcast_outreach.database.models.llm_outputs import GeminiPodcastEnrichment
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

class DataMergerService:
    """
    Merges data from various enrichment sources into a standardized EnrichedPodcastProfile.
    This service uses a confidence-based approach to ensure that high-quality, manually
    entered data is not overwritten by lower-quality automated discoveries.
    """

    # --- Confidence Scores for Data Sources ---
    # Higher score means more trustworthy.
    CONFIDENCE_MANUAL = 1.00
    CONFIDENCE_API_PRIMARY = 0.90  # Data from ListenNotes/Podscan initial fetch
    CONFIDENCE_SOCIAL_SCRAPE = 0.80  # Data from Apify scrapers
    CONFIDENCE_LLM_DISCOVERY = 0.60  # Data inferred by an LLM (e.g., Gemini/Tavily search)

    def __init__(self):
        logger.info("DataMergerService initialized with confidence-based merging logic.")

    def _clean_initial_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean initial data to fix common validation issues."""
        cleaned_data = data.copy()
        
        # Fix emails being stored in URL fields
        url_fields = [
            'podcast_twitter_url', 'podcast_linkedin_url', 'podcast_instagram_url',
            'podcast_facebook_url', 'podcast_youtube_url', 'podcast_tiktok_url',
            'podcast_other_social_url', 'website', 'image_url', 'rss_feed_url'
        ]
        
        for field in url_fields:
            if field in cleaned_data and cleaned_data[field]:
                value = str(cleaned_data[field]).strip()
                # Check if it's an email (contains @ but not a valid URL)
                if '@' in value and not value.startswith(('http://', 'https://')):
                    logger.warning(f"Found email '{value}' in URL field '{field}', moving to primary_email")
                    # Move email to primary_email field if it's not already set
                    if not cleaned_data.get('primary_email'):
                        cleaned_data['primary_email'] = value
                    # Clear the URL field
                    cleaned_data[field] = None
        
        return cleaned_data

    def _normalize_url(self, url: Optional[str]) -> Optional[HttpUrl]:
        """Validates and normalizes a URL string to a Pydantic HttpUrl or None."""
        if not url or not isinstance(url, str) or url.lower() in ['null', 'n/a', 'none']:
            return None
        url = url.strip()
        if not url:
            return None
        
        # Filter out specific URLs that the LLM is hallucinating/cross-contaminating
        # These are legitimate URLs but are being incorrectly assigned to wrong podcasts
        problematic_urls = [
            'twitter.com/masterofnonepod',
            'linkedin.com/company/none-of-your-business-podcast',
            'youtube.com/@noonecanknowaboutthispodca',
            'example.com',
            'placeholder',
            'generic',
            'sample',
            'test'
        ]
        
        url_lower = url.lower()
        for pattern in problematic_urls:
            if pattern in url_lower:
                logger.warning(f"Rejecting cross-contaminated URL that doesn't belong to this podcast: {url}")
                return None
        
        if '://' not in url:
            url = "https://" + url
        try:
            return HttpUrl(url)
        except ValidationError:
            logger.debug(f"Failed to validate URL: {url}. Returning None.")
            return None

    def _safe_int_cast(self, value: Any) -> Optional[int]:
        """Safely casts a value to an integer, returning None on failure."""
        if value is None: return None
        try: return int(value)
        except (ValueError, TypeError): return None

    def _safe_float_cast(self, value: Any) -> Optional[float]:
        """Safely casts a value to a float, returning None on failure."""
        if value is None: return None
        try: return float(value)
        except (ValueError, TypeError): return None

    def _merge_field(
        self,
        profile: EnrichedPodcastProfile,
        field_name: str,
        new_value: Any,
        new_source: str,
        new_confidence: float
    ):
        """
        Intelligently merges a new value for a field based on confidence scores.
        It will not overwrite manually entered data.
        """
        source_field = f"{field_name}_source"
        confidence_field = f"{field_name}_confidence"

        # Check if the model has source and confidence fields for this field
        has_source_field = hasattr(profile, source_field)
        has_confidence_field = hasattr(profile, confidence_field)

        # Safely get current values from the Pydantic model
        existing_source = getattr(profile, source_field, None) if has_source_field else None
        existing_confidence = getattr(profile, confidence_field, 0.0) if has_confidence_field else 0.0

        # Rule 1: Never overwrite manually entered data
        if existing_source == 'manual':
            logger.debug(f"Skipping update for '{field_name}'; existing data is manually entered.")
            return

        # Rule 2: Only update if the new data has higher or equal confidence
        if new_value is not None and new_confidence >= (existing_confidence or 0.0):
            # Always update the main field if it exists
            if hasattr(profile, field_name):
                setattr(profile, field_name, new_value)
                
                # Only set source/confidence fields if they exist in the model
                if has_source_field:
                    setattr(profile, source_field, new_source)
                if has_confidence_field:
                    setattr(profile, confidence_field, new_confidence)
                    
                logger.debug(f"Updated '{field_name}' with new value from '{new_source}' (confidence: {new_confidence}).")
            else:
                logger.warning(f"Field '{field_name}' does not exist in EnrichedPodcastProfile model")
        else:
            logger.debug(f"Skipping update for '{field_name}'; new confidence ({new_confidence}) is not higher than existing ({existing_confidence}).")

    def merge_podcast_data(
        self,
        initial_db_data: Dict[str, Any], 
        gemini_enrichment: Optional[GeminiPodcastEnrichment] = None,
        social_media_results: Optional[Dict[str, Optional[Dict[str, Any]]]] = None
    ) -> Optional[EnrichedPodcastProfile]:
        """
        Merges initial database data with various enrichment data sources into a standardized
        EnrichedPodcastProfile, ready for database update.
        """
        if not initial_db_data or not isinstance(initial_db_data, dict):
            logger.error("DataMergerService: Initial database data is missing or invalid.")
            return None

        api_id = initial_db_data.get('api_id') or initial_db_data.get('media_id')
        logger.info(f"Merging data for podcast ID: {api_id or 'Unknown'} (Name: {initial_db_data.get('name', 'N/A')})")

        try:
            # Clean the initial data before validation
            cleaned_data = self._clean_initial_data(initial_db_data)
            # Initialize the profile with data from the database
            profile = EnrichedPodcastProfile(**cleaned_data)
        except ValidationError as ve:
            logger.error(f"Pydantic validation error initializing EnrichedPodcastProfile for {api_id}: {ve}")
            return None

        # --- Merge Gemini Enrichment Data ---
        if gemini_enrichment:
            logger.debug(f"Merging Gemini data for {api_id}...")
            self._merge_field(profile, 'host_names', gemini_enrichment.host_names, 'llm_discovery', self.CONFIDENCE_LLM_DISCOVERY)
            self._merge_field(profile, 'podcast_twitter_url', self._normalize_url(gemini_enrichment.podcast_twitter_url), 'llm_discovery', self.CONFIDENCE_LLM_DISCOVERY)
            self._merge_field(profile, 'podcast_linkedin_url', self._normalize_url(gemini_enrichment.podcast_linkedin_url), 'llm_discovery', self.CONFIDENCE_LLM_DISCOVERY)
            self._merge_field(profile, 'podcast_instagram_url', self._normalize_url(gemini_enrichment.podcast_instagram_url), 'llm_discovery', self.CONFIDENCE_LLM_DISCOVERY)
            self._merge_field(profile, 'podcast_facebook_url', self._normalize_url(gemini_enrichment.podcast_facebook_url), 'llm_discovery', self.CONFIDENCE_LLM_DISCOVERY)
            self._merge_field(profile, 'podcast_youtube_url', self._normalize_url(gemini_enrichment.podcast_youtube_url), 'llm_discovery', self.CONFIDENCE_LLM_DISCOVERY)
            self._merge_field(profile, 'podcast_tiktok_url', self._normalize_url(gemini_enrichment.podcast_tiktok_url), 'llm_discovery', self.CONFIDENCE_LLM_DISCOVERY)

        # --- Merge Social Scraper Data ---
        if social_media_results:
            logger.debug(f"Merging social media scraping results for {api_id}...")
            
            twitter_data = social_media_results.get('podcast_twitter')
            if twitter_data:
                self._merge_field(profile, 'twitter_followers', self._safe_int_cast(twitter_data.get('followers_count')), 'apify_scrape', self.CONFIDENCE_SOCIAL_SCRAPE)
                self._merge_field(profile, 'twitter_following', self._safe_int_cast(twitter_data.get('following_count')), 'apify_scrape', self.CONFIDENCE_SOCIAL_SCRAPE)
                self._merge_field(profile, 'is_twitter_verified', twitter_data.get('is_verified'), 'apify_scrape', self.CONFIDENCE_SOCIAL_SCRAPE)

            instagram_data = social_media_results.get('podcast_instagram')
            if instagram_data:
                self._merge_field(profile, 'instagram_followers', self._safe_int_cast(instagram_data.get('followers_count')), 'apify_scrape', self.CONFIDENCE_SOCIAL_SCRAPE)

            tiktok_data = social_media_results.get('podcast_tiktok')
            if tiktok_data:
                self._merge_field(profile, 'tiktok_followers', self._safe_int_cast(tiktok_data.get('followers_count')), 'apify_scrape', self.CONFIDENCE_SOCIAL_SCRAPE)
            
            # youtube_data = social_media_results.get('podcast_youtube')
            # if youtube_data:
            #     self._merge_field(profile, 'youtube_subscribers', self._safe_int_cast(youtube_data.get('subscriber_count')), 'apify_scrape', self.CONFIDENCE_SOCIAL_SCRAPE)

            # facebook_data = social_media_results.get('podcast_facebook')
            # if facebook_data:
            #     self._merge_field(profile, 'facebook_likes', self._safe_int_cast(facebook_data.get('likes_count')), 'apify_scrape', self.CONFIDENCE_SOCIAL_SCRAPE)
            
            linkedin_company_data = social_media_results.get('podcast_linkedin_company')
            if linkedin_company_data:
                # Note: The 'media' table does not have a dedicated linkedin_followers column.
                # This data could be stored in a generic JSONB field or a new column if needed.
                # For now, we'll log it but not merge it into a specific field.
                li_followers = self._safe_int_cast(linkedin_company_data.get('followers_count'))
                if li_followers is not None:
                    logger.debug(f"LinkedIn Company followers found ({li_followers}), but no target field on EnrichedPodcastProfile.")

        # --- Final Consolidations ---
        # Consolidate primary_email: prefer direct contact_email from DB, then rss_owner_email
        self._merge_field(profile, 'contact_email', profile.rss_owner_email, 'rss_feed', 0.7)

        # Add social stats timestamp if we processed any social media data
        if social_media_results and any(social_media_results.values()):
            from datetime import datetime, timezone
            # Set social_stats_last_fetched_at since we just fetched social data
            if hasattr(profile, 'social_stats_last_fetched_at'):
                setattr(profile, 'social_stats_last_fetched_at', datetime.now(timezone.utc))
                logger.debug(f"Set social_stats_last_fetched_at timestamp for {profile.api_id}")

        logger.info(f"Successfully merged data for podcast: {profile.api_id} - {getattr(profile, 'name', None) or getattr(profile, 'title', None) or 'Unknown'}")
        return profile