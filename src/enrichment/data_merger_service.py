import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

from pydantic import HttpUrl, ValidationError

# Assuming models are in src.models - adjust path if needed
from ..models.podcast_profile_models import EnrichedPodcastProfile, EpisodeInfo # EpisodeInfo for recent_episodes typing
from ..models.llm_output_models import GeminiPodcastEnrichment

logger = logging.getLogger(__name__)

class DataMergerService:
    """Merges data from various enrichment sources into a standardized EnrichedPodcastProfile."""

    def __init__(self):
        logger.info("DataMergerService initialized.")

    def _normalize_url(self, url: Optional[str]) -> Optional[HttpUrl]:
        """Validates and normalizes a URL string to HttpUrl or None."""
        if not url or not isinstance(url, str):
            return None
        url = url.strip()
        if not url:
            return None
        
        # Ensure scheme is present for Pydantic validation
        if '://' not in url:
            url = "https://" + url
        try:
            return HttpUrl(url)
        except ValidationError:
            logger.debug(f"Failed to validate URL: {url}. Returning None.")
            return None

    def _safe_int_cast(self, value: Any) -> Optional[int]:
        if value is None: return None
        try: return int(value)
        except (ValueError, TypeError): return None

    def _safe_float_cast(self, value: Any) -> Optional[float]:
        if value is None: return None
        try: return float(value)
        except (ValueError, TypeError): return None

    def _merge_social_media_data(
        self, 
        profile: EnrichedPodcastProfile, 
        social_results: Dict[str, Optional[Dict[str, Any]]],
        platform_map: Dict[str, Dict[str,str]]
    ):
        """Helper to merge social media data from Apify results into the profile."""
        # platform_map: e.g., {'twitter': {'url_field': 'podcast_twitter_url', 'followers_field': 'twitter_followers', ...}}
        
        for platform_key, apify_data in social_results.items(): # platform_key e.g., 'podcast_twitter', 'host_linkedin'
            if not apify_data or not isinstance(apify_data, dict):
                continue

            # Determine which fields on EnrichedPodcastProfile to update based on platform_key
            # This requires a mapping or more complex logic if host social data isn't directly on EnrichedPodcastProfile
            # For now, assuming direct mapping for podcast's own social profiles
            
            # Example: if platform_key is 'podcast_twitter' from SocialDiscoveryService results
            if platform_key == 'podcast_twitter' and platform_map.get('twitter'):
                map_info = platform_map['twitter']
                profile.podcast_twitter_url = self._normalize_url(apify_data.get('profile_url')) or profile.podcast_twitter_url
                profile.twitter_followers = self._safe_int_cast(apify_data.get('followers_count')) or profile.twitter_followers
                profile.twitter_following = self._safe_int_cast(apify_data.get('following_count')) or profile.twitter_following
                profile.is_twitter_verified = apify_data.get('is_verified') if isinstance(apify_data.get('is_verified'), bool) else profile.is_twitter_verified
            
            elif platform_key == 'podcast_instagram' and platform_map.get('instagram'):
                map_info = platform_map['instagram']
                profile.podcast_instagram_url = self._normalize_url(apify_data.get('profile_url')) or profile.podcast_instagram_url
                profile.instagram_followers = self._safe_int_cast(apify_data.get('followers_count')) or profile.instagram_followers

            elif platform_key == 'podcast_tiktok' and platform_map.get('tiktok'):
                map_info = platform_map['tiktok']
                profile.podcast_tiktok_url = self._normalize_url(apify_data.get('profile_url')) or profile.podcast_tiktok_url
                profile.tiktok_followers = self._safe_int_cast(apify_data.get('followers_count')) or profile.tiktok_followers
            
            # Add similar blocks for LinkedIn (company), Facebook, YouTube if their data is fetched for the podcast itself
            # If social_results contains host data (e.g., 'host_linkedin'), that needs to be handled differently,
            # likely by the EnrichmentAgent to update a People record, not EnrichedPodcastProfile directly.
            # For now, this merger focuses on fields directly on EnrichedPodcastProfile.

    def merge_podcast_data(
        self,
        initial_db_data: Dict[str, Any], 
        gemini_enrichment: Optional[GeminiPodcastEnrichment] = None,
        social_media_results: Optional[Dict[str, Optional[Dict[str, Any]]]] = None # e.g. {"podcast_twitter": {...}, "podcast_instagram": {...}}
        # rss_data: Optional[Dict[str, Any]] = None, # Removed direct RSS parsing dependency
    ) -> Optional[EnrichedPodcastProfile]:
        """Merges initial database data with enrichment data sources into an EnrichedPodcastProfile.

        Args:
            initial_db_data: Data fetched from the 'media' table.
            gemini_enrichment: Structured data from GeminiService for social URLs, host names.
            social_media_results: Results from SocialDiscoveryService for various platforms.

        Returns:
            An EnrichedPodcastProfile instance or None if critical data is missing or merging fails.
        """
        if not initial_db_data or not isinstance(initial_db_data, dict):
            logger.error("DataMergerService: Initial database data is missing or invalid.")
            return None

        api_id = initial_db_data.get('api_id') or initial_db_data.get('media_id')
        logger.info(f"Merging data for podcast ID: {api_id or 'Unknown'} (Title: {initial_db_data.get('name', 'N/A')})")

        # Start with data from the database (media table row)
        try:
            profile = EnrichedPodcastProfile(
                # IDs
                api_id=str(api_id) if api_id else None,
                source_api=initial_db_data.get('source_api'), # Assuming 'source_api' comes from DB
                unified_profile_id=initial_db_data.get('media_id', str(uuid.uuid4())), # Use media_id as unified if available
                
                # Core Info
                title=initial_db_data.get('title') or initial_db_data.get('name'),
                description=initial_db_data.get('description'),
                image_url=self._normalize_url(initial_db_data.get('image_url')),
                website=self._normalize_url(initial_db_data.get('website')),
                language=initial_db_data.get('language'),
                podcast_spotify_id=initial_db_data.get('podcast_spotify_id'),
                itunes_id=str(initial_db_data.get('itunes_id')) if initial_db_data.get('itunes_id') is not None else None,
                total_episodes=self._safe_int_cast(initial_db_data.get('total_episodes')),
                last_posted_at=initial_db_data.get('last_posted_at'), # Expects datetime or None
                rss_feed_url=self._normalize_url(initial_db_data.get('rss_url') or initial_db_data.get('rss_feed_url')),
                category=initial_db_data.get('category'),
                
                # Host Info (denormalized from DB)
                host_names=initial_db_data.get('host_names'), # Expects List[str] or None

                # RSS-related fields (from DB if pre-populated)
                rss_owner_name=initial_db_data.get('rss_owner_name'),
                rss_owner_email=initial_db_data.get('rss_owner_email'),
                rss_explicit=initial_db_data.get('rss_explicit'),
                rss_categories=initial_db_data.get('rss_categories'),
                
                # Dates (from DB)
                latest_episode_date=initial_db_data.get('latest_episode_date'),
                first_episode_date=initial_db_data.get('first_episode_date'),
                publishing_frequency_days=self._safe_float_cast(initial_db_data.get('publishing_frequency_days')),

                # Social URLs (from DB)
                podcast_twitter_url=self._normalize_url(initial_db_data.get('podcast_twitter_url')),
                podcast_linkedin_url=self._normalize_url(initial_db_data.get('podcast_linkedin_url')),
                podcast_instagram_url=self._normalize_url(initial_db_data.get('podcast_instagram_url')),
                podcast_facebook_url=self._normalize_url(initial_db_data.get('podcast_facebook_url')),
                podcast_youtube_url=self._normalize_url(initial_db_data.get('podcast_youtube_url')),
                podcast_tiktok_url=self._normalize_url(initial_db_data.get('podcast_tiktok_url')),
                podcast_other_social_url=self._normalize_url(initial_db_data.get('podcast_other_social_url')),

                # Contact (from DB)
                primary_email=initial_db_data.get('contact_email'), # Prioritize direct contact_email

                # Metrics (from DB)
                listen_score=self._safe_float_cast(initial_db_data.get('listen_score')),
                listen_score_global_rank=self._safe_int_cast(initial_db_data.get('listen_score_global_rank')),
                audience_size=self._safe_int_cast(initial_db_data.get('audience_size')),
                itunes_rating_average=self._safe_float_cast(initial_db_data.get('itunes_rating_average')),
                itunes_rating_count=self._safe_int_cast(initial_db_data.get('itunes_rating_count')),
                spotify_rating_average=self._safe_float_cast(initial_db_data.get('spotify_rating_average')),
                spotify_rating_count=self._safe_int_cast(initial_db_data.get('spotify_rating_count')),
                twitter_followers=self._safe_int_cast(initial_db_data.get('twitter_followers')),
                twitter_following=self._safe_int_cast(initial_db_data.get('twitter_following')),
                is_twitter_verified=initial_db_data.get('is_twitter_verified'),
                instagram_followers=self._safe_int_cast(initial_db_data.get('instagram_followers')),
                tiktok_followers=self._safe_int_cast(initial_db_data.get('tiktok_followers')),
                facebook_likes=self._safe_int_cast(initial_db_data.get('facebook_likes')),
                youtube_subscribers=self._safe_int_cast(initial_db_data.get('youtube_subscribers')),
                
                # Quality Score (from DB - will be updated by QualityService later)
                quality_score=self._safe_float_cast(initial_db_data.get('quality_score')),
                
                # Timestamps
                last_enriched_timestamp=initial_db_data.get('last_enriched_timestamp', datetime.utcnow()) # Fallback to now
            )
        except ValidationError as ve:
            logger.error(f"Pydantic validation error initializing EnrichedPodcastProfile for {api_id}: {ve}")
            return None

        # Merge Gemini Enrichment Data (if any)
        if gemini_enrichment:
            logger.debug(f"Merging Gemini data for {api_id}...")
            # Prefer Gemini data for these fields if the profile fields are currently None
            if gemini_enrichment.host_names and not profile.host_names:
                profile.host_names = gemini_enrichment.host_names
            if gemini_enrichment.podcast_twitter_url and not profile.podcast_twitter_url:
                profile.podcast_twitter_url = gemini_enrichment.podcast_twitter_url
            if gemini_enrichment.podcast_linkedin_url and not profile.podcast_linkedin_url:
                profile.podcast_linkedin_url = gemini_enrichment.podcast_linkedin_url
            if gemini_enrichment.podcast_instagram_url and not profile.podcast_instagram_url:
                profile.podcast_instagram_url = gemini_enrichment.podcast_instagram_url
            if gemini_enrichment.podcast_facebook_url and not profile.podcast_facebook_url:
                profile.podcast_facebook_url = gemini_enrichment.podcast_facebook_url
            if gemini_enrichment.podcast_youtube_url and not profile.podcast_youtube_url:
                profile.podcast_youtube_url = gemini_enrichment.podcast_youtube_url
            if gemini_enrichment.podcast_tiktok_url and not profile.podcast_tiktok_url:
                profile.podcast_tiktok_url = gemini_enrichment.podcast_tiktok_url
            # Note: Host-specific social URLs from Gemini (host_linkedin_url, host_twitter_url)
            # are not directly merged into EnrichedPodcastProfile here. 
            # The EnrichmentAgent should handle them by trying to update/create People records.

        # Merge Social Media Scraping Results (if any)
        if social_media_results:
            logger.debug(f"Merging social media scraping results for {api_id}...")
            platform_map = {
                'twitter': {
                    'url_field': 'podcast_twitter_url', 
                    'followers_field': 'twitter_followers', 
                    'following_field': 'twitter_following', 
                    'verified_field': 'is_twitter_verified'
                },
                'instagram': {
                    'url_field': 'podcast_instagram_url',
                    'followers_field': 'instagram_followers'
                },
                'tiktok': {
                    'url_field': 'podcast_tiktok_url',
                    'followers_field': 'tiktok_followers'
                }
                # Add mappings for LinkedIn (company), Facebook, YouTube if scraping for podcast entity itself
            }
            self._merge_social_media_data(profile, social_media_results, platform_map)

        # Consolidate primary_email: prefer direct contact_email from DB, then rss_owner_email
        if not profile.primary_email and profile.rss_owner_email:
            profile.primary_email = profile.rss_owner_email
        
        # Update the timestamp
        profile.last_enriched_timestamp = datetime.utcnow()

        logger.info(f"Successfully merged data for podcast: {profile.api_id} - {profile.title}")
        return profile

# Example Usage (for direct testing of this service module)
if __name__ == '__main__':
    # Mock initial data similar to what would come from db_service_pg.get_media_for_enrichment
    mock_db_media_data = {
        "media_id": 123,
        "api_id": "listennotes_xyz123",
        "name": "Tech Conversations",
        "title": "Tech Conversations Today",
        "description": "Deep dives into the world of technology.",
        "rss_url": "https://example.com/feed.xml",
        "image_url": "https://example.com/image.jpg",
        "website": "https://example.com/podcast",
        "contact_email": "podcast@example.com",
        "host_names": ["Alex The Host"], # Pre-existing in DB
        "podcast_twitter_url": "https://twitter.com/TechConvoDB"
    }

    # Mock Gemini enrichment output
    mock_gemini_data = GeminiPodcastEnrichment(
        podcast_twitter_url=HttpUrl("https://twitter.com/TechConvoGemini"), # Gemini found a different/better one
        host_names=["Alex The Host", "Dr. Gemini Expert"], # Gemini found an additional host
        podcast_instagram_url=HttpUrl("https://instagram.com/TechConvoInsta")
    )

    # Mock Social Media scraping results
    mock_social_results = {
        "podcast_twitter": { # Corresponds to the Gemini URL or an even better one found by agent
            "profile_url": "https://twitter.com/TechConvoGemini",
            "followers_count": 5500,
            "following_count": 100,
            "is_verified": True
        },
        "podcast_instagram": { # Corresponds to the Gemini URL
            "profile_url": "https://instagram.com/TechConvoInsta",
            "followers_count": 1200
        }
    }

    merger = DataMergerService()
    enriched_profile = merger.merge_podcast_data(
        initial_db_data=mock_db_media_data,
        gemini_enrichment=mock_gemini_data,
        social_media_results=mock_social_results
    )

    if enriched_profile:
        print("\n--- Enriched Profile --- ")
        print(enriched_profile.model_dump_json(indent=2, exclude_none=True))
        
        # Verify merging logic:
        # - Twitter URL should be from Gemini (higher precedence in this mock flow if DB one was different)
        # - Host names should include both DB and Gemini if Gemini added new ones
        # - Instagram should be filled from Gemini + Social scraping
        # - Twitter followers should be from social scraping
        print(f"\nTwitter URL: {enriched_profile.podcast_twitter_url}")
        print(f"Host Names: {enriched_profile.host_names}")
        print(f"Instagram URL: {enriched_profile.podcast_instagram_url}")
        print(f"Instagram Followers: {enriched_profile.instagram_followers}")
        print(f"Twitter Followers: {enriched_profile.twitter_followers}")
        print(f"Primary Email: {enriched_profile.primary_email}") # Should be podcast@example.com
        print(f"Last Enriched: {enriched_profile.last_enriched_timestamp}")
    else:
        print("Failed to merge podcast data.") 