# podcast_outreach/services/media/podcast_fetcher.py

import asyncio
import argparse
import uuid
from typing import Optional, List, Dict, Any, Tuple, Set
import concurrent.futures
import html
import functools
import logging
from datetime import datetime, timezone as dt_timezone

# Import modular queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import review_tasks as review_tasks_queries
from podcast_outreach.database.connection import get_db_pool, close_db_pool # For main function

from podcast_outreach.services.ai.openai_client import OpenAIService
from podcast_outreach.integrations.listen_notes import ListenNotesAPIClient
from podcast_outreach.integrations.podscan import PodscanAPIClient
from podcast_outreach.utils.exceptions import APIClientError, RateLimitError
from podcast_outreach.services.ai.utils import generate_genre_ids, generate_podscan_category_ids
from podcast_outreach.utils.data_processor import parse_date
from podcast_outreach.services.media.episode_handler import EpisodeHandlerService # ENSURED IMPORT
from podcast_outreach.services.events.event_bus import get_event_bus, Event, EventType

# --- Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Constants ---
LISTENNOTES_PAGE_SIZE = 10
PODSCAN_PAGE_SIZE = 20
API_CALL_DELAY = 1.2
KEYWORD_PROCESSING_DELAY = 2
ENRICHMENT_FRESHNESS_THRESHOLD_DAYS = 180
MIN_EPISODE_COUNT = 10 # Minimum number of episodes required for podcasts


def _sanitize_numeric_string(value: Any, target_type: type = float) -> Optional[Any]:
    """Convert strings like '10%' or 'N/A' to numbers."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) if target_type == int else value
    s_value = str(value).strip().replace('%', '').replace(',', '')
    if not s_value or s_value.lower() == 'n/a':
        return None
    try:
        return int(float(s_value)) if target_type == int else float(s_value)
    except ValueError:
        logger.warning("Could not convert sanitized string '%s' to %s", s_value, target_type)
        return None


class MediaFetcher:
    """Fetch podcasts from external APIs and store them in PostgreSQL."""

    def __init__(self) -> None:
        self.openai_service = OpenAIService()
        self.listennotes_client = ListenNotesAPIClient()
        self.podscan_client = PodscanAPIClient()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
        self.episode_handler_service = EpisodeHandlerService() # ENSURED INITIALIZATION
        logger.info("MediaFetcher services initialized")

    async def _run_in_executor(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        func_with_args = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(self.executor, func_with_args)

    async def _generate_genre_ids_async(self, keyword: str, campaign_id_str: str) -> Optional[str]:
        try:
            logger.info(f"Generating ListenNotes genre IDs for '{keyword}' (context: {campaign_id_str})")
            genre_ids_output = await generate_genre_ids(self.openai_service, keyword, campaign_id_str)
            
            if isinstance(genre_ids_output, str):
                logger.info(f"Successfully generated ListenNotes genre IDs for '{keyword}': {genre_ids_output}")
                return genre_ids_output
            logger.warning(f"_generate_genre_ids_async: Unexpected type or None from generate_genre_ids for '{keyword}': {type(genre_ids_output)}, value: {genre_ids_output}")
        except Exception as e:  
            logger.error(f"Error in _generate_genre_ids_async for '{keyword}': {e}", exc_info=True)
        return None

    # NEW: Helper for Podscan category IDs
    async def _generate_podscan_category_ids_async(self, keyword: str, campaign_id_str: str) -> Optional[str]:
        try:
            logger.info(f"Generating Podscan category IDs for '{keyword}' (context: {campaign_id_str})")
            category_ids_output = await generate_podscan_category_ids(self.openai_service, keyword, campaign_id_str)
            if isinstance(category_ids_output, str):
                logger.info(f"Successfully generated Podscan category IDs for '{keyword}': {category_ids_output}")
                return category_ids_output
            logger.warning(f"_generate_podscan_category_ids_async: Unexpected type or None from generate_podscan_category_ids for '{keyword}': {type(category_ids_output)}, value: {category_ids_output}")
        except Exception as e:
            logger.error(f"Error in _generate_podscan_category_ids_async for '{keyword}': {e}", exc_info=True)
        return None

    def _extract_social_links(self, socials: List[Dict[str, str]]) -> Dict[str, Optional[str]]:
        social_map: Dict[str, Optional[str]] = {}
        for item in socials or []:
            platform = item.get('platform')
            url = item.get('url')
            if not platform or not url:
                continue
            
            # Validate that the URL is actually a URL and not an email
            url_str = str(url).strip()
            # Skip if it's an email (contains @ but doesn't start with http)
            if '@' in url_str and not url_str.startswith(('http://', 'https://')):
                logger.debug(f"Skipping email address '{url_str}' found in social links for platform '{platform}'")
                continue
            
            # Basic URL validation - must start with http or be a valid domain
            if not url_str.startswith(('http://', 'https://')):
                # Add https:// if it looks like a domain
                if '.' in url_str and not '@' in url_str:
                    url_str = f'https://{url_str}'
                else:
                    logger.debug(f"Skipping invalid URL '{url_str}' for platform '{platform}'")
                    continue
            
            key = {
                'twitter': 'podcast_twitter_url',
                'linkedin': 'podcast_linkedin_url',
                'instagram': 'podcast_instagram_url',
                'facebook': 'podcast_facebook_url',
                'youtube': 'podcast_youtube_url',
                'tiktok': 'podcast_tiktok_url',
            }.get(platform)
            if key:
                social_map[key] = url_str
            else:
                social_map.setdefault('podcast_other_social_url', url_str)
        return social_map

    async def _quick_rss_email_discovery(self, rss_url: str) -> Optional[str]:
        """
        Attempt to extract email from RSS feed XML for email validation.
        Looks for managingEditor, webMaster, or itunes:owner email fields.
        Returns the first valid email found, or None if none found or on error.
        """
        if not rss_url:
            return None
            
        try:
            import aiohttp
            import re
            from bs4 import BeautifulSoup
            
            timeout = aiohttp.ClientTimeout(total=10)  # Quick timeout for discovery
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; PodcastEmailDiscovery/1.0)",
                "Accept": "application/xml,text/xml,application/rss+xml"
            }
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(rss_url, headers=headers) as response:
                    if response.status != 200:
                        logger.debug(f"RSS email discovery failed for {rss_url}: HTTP {response.status}")
                        return None
                        
                    content = await response.text()
                    
            # Parse XML content
            soup = BeautifulSoup(content, 'xml')
            if not soup:
                logger.debug(f"RSS email discovery: Could not parse XML for {rss_url}")
                return None
                
            # Look for various email fields in RSS/iTunes namespace
            email_fields = [
                'managingEditor',
                'webMaster', 
                'itunes:owner',
                'itunes:email'
            ]
            
            for field in email_fields:
                elements = soup.find_all(field)
                for element in elements:
                    if field == 'itunes:owner':
                        # Look for nested email in owner
                        email_elem = element.find('itunes:email')
                        if email_elem and email_elem.get_text():
                            email_text = email_elem.get_text().strip()
                        else:
                            continue
                    else:
                        email_text = element.get_text().strip() if element else ""
                    
                    if email_text:
                        # Extract email using regex
                        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
                        email_match = re.search(email_pattern, email_text)
                        if email_match:
                            found_email = email_match.group(0)
                            logger.debug(f"RSS email discovery: Found email in {field}: {found_email}")
                            return found_email
                            
            logger.debug(f"RSS email discovery: No email found in RSS feed {rss_url}")
            return None
            
        except Exception as e:
            logger.debug(f"RSS email discovery error for {rss_url}: {e}")
            return None

    async def _get_existing_media_by_identifiers(self, initial_data: Dict[str, Any], source_api: str) -> Optional[Dict[str, Any]]:
        rss_url = None
        api_id_val = None
        
        if source_api == "ListenNotes":
            rss_url = initial_data.get('rss')
            api_id_val = str(initial_data.get('id', '')).strip()
        elif source_api == "PodscanFM":
            rss_url = initial_data.get('rss_url')
            api_id_val = str(initial_data.get('podcast_id', '')).strip()

        # Enhanced Logging
        logger.debug(f"_get_existing_media (source: {source_api}): Checking with api_id_val='{api_id_val}', rss_url='{rss_url}'")

        existing_media = None
        if rss_url:
            logger.debug(f"_get_existing_media (source: {source_api}): Attempting fetch by RSS: {rss_url}")
            existing_media = await media_queries.get_media_by_rss_url_from_db(rss_url)
            logger.debug(f"_get_existing_media (source: {source_api}): Result from RSS fetch for '{rss_url}': {'Found (media_id: ' + str(existing_media.get('media_id')) + ')' if existing_media else 'Not Found'}")
        
        if not existing_media and api_id_val and source_api:
            logger.debug(f"_get_existing_media (source: {source_api}): Not found by RSS (or RSS not provided). Attempting fetch by api_id='{api_id_val}'")
            pool = await get_db_pool() 
            async with pool.acquire() as conn:
                query_existing_api = "SELECT * FROM media WHERE api_id = $1 AND source_api = $2;"
                try:
                    row = await conn.fetchrow(query_existing_api, api_id_val, source_api)
                    if row:
                        existing_media = dict(row)
                        logger.debug(f"_get_existing_media (source: {source_api}): Found by api_id. Media ID: {existing_media.get('media_id')}")
                    else:
                        logger.debug(f"_get_existing_media (source: {source_api}): Not found by api_id.")
                except Exception as e:
                    logger.error(f"_get_existing_media (source: {source_api}): DB error fetching by api_id {api_id_val}: {e}")
        
        if not existing_media:
            logger.debug(f"_get_existing_media (source: {source_api}): NO existing media found by any identifier for item based on api_id_val '{api_id_val}' / rss '{rss_url}'.")
        return existing_media

    async def _enrich_podcast_data(self, initial_data: Dict[str, Any], source_api: str, existing_media_from_db: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        enriched: Dict[str, Any] = {}
        current_last_posted_at: Optional[datetime] = None

        if existing_media_from_db:
            enriched = existing_media_from_db.copy()
            # Ensure existing last_posted_at is a datetime object if present
            if isinstance(enriched.get('last_posted_at'), datetime):
                current_last_posted_at = enriched.get('last_posted_at')
            else: # If it's a string or other, try to parse it, or nullify
                current_last_posted_at = parse_date(enriched.get('last_posted_at'))
                enriched['last_posted_at'] = current_last_posted_at # Update with parsed or None
        else:
            enriched = initial_data.copy() # For new items, last_posted_at will be processed fresh below
            # Ensure no stale string date from initial_data.copy() if it's not parsed later
            if 'last_posted_at' in enriched:
                 enriched['last_posted_at'] = None # Will be set by parse_date or remain None

        # Update direct fields from the current API source
        if source_api == "ListenNotes":
            enriched['name'] = html.unescape(str(initial_data.get('title_original', enriched.get('name', '')))).strip()
            enriched['description'] = html.unescape(str(initial_data.get('description_original', enriched.get('description', '')))).strip() or None
            enriched['rss_url'] = initial_data.get('rss') or enriched.get('rss_url')
            enriched['itunes_id'] = str(initial_data.get('itunes_id', enriched.get('itunes_id', ''))).strip() or None
            enriched['website'] = initial_data.get('website') or enriched.get('website')
            enriched['image_url'] = initial_data.get('image') or enriched.get('image_url')
            enriched['contact_email'] = initial_data.get('email') or enriched.get('contact_email') # Prioritize new email? Or existing?
            enriched['language'] = initial_data.get('language') or enriched.get('language')
            enriched['total_episodes'] = initial_data.get('total_episodes') if initial_data.get('total_episodes') is not None else enriched.get('total_episodes')
            enriched['listen_score'] = _sanitize_numeric_string(initial_data.get('listen_score'), int) if initial_data.get('listen_score') is not None else enriched.get('listen_score')
            enriched['listen_score_global_rank'] = _sanitize_numeric_string(initial_data.get('listen_score_global_rank'), int) if initial_data.get('listen_score_global_rank') is not None else enriched.get('listen_score_global_rank')
            parsed_ln_date = parse_date(initial_data.get('latest_pub_date_ms'))
            if parsed_ln_date is not None:
                enriched['last_posted_at'] = parsed_ln_date
                current_last_posted_at = parsed_ln_date
            elif existing_media_from_db is None: # New item and parsing failed
                enriched['last_posted_at'] = None
                current_last_posted_at = None 
            # Else (existing item and parsing failed): current_last_posted_at (from DB or already None) is kept

            if isinstance(initial_data.get('genres'), list) and initial_data['genres']:
                enriched['category'] = initial_data['genres'][0]
            enriched['api_id'] = str(initial_data.get('id', enriched.get('api_id', ''))).strip() # Ensure current source's API ID is set
        elif source_api == "PodscanFM":
            enriched['name'] = html.unescape(str(initial_data.get('podcast_name', enriched.get('name', '')))).strip()
            enriched['description'] = html.unescape(str(initial_data.get('podcast_description', enriched.get('description', '')))).strip() or None
            enriched['rss_url'] = initial_data.get('rss_url') or enriched.get('rss_url')
            enriched['itunes_id'] = str(initial_data.get('podcast_itunes_id', enriched.get('itunes_id', ''))).strip() or None
            enriched['website'] = initial_data.get('podcast_url') or enriched.get('website')
            enriched['image_url'] = initial_data.get('podcast_image_url') or enriched.get('image_url')
            reach = initial_data.get('reach') or {}
            enriched['contact_email'] = reach.get('email') or enriched.get('contact_email') # Prioritize?
            enriched['language'] = initial_data.get('language', enriched.get('language', 'English'))
            enriched['total_episodes'] = _sanitize_numeric_string(initial_data.get('episode_count'), int) if initial_data.get('episode_count') is not None else enriched.get('total_episodes')
            parsed_ps_date = parse_date(initial_data.get('last_posted_at'))
            if parsed_ps_date is not None:
                enriched['last_posted_at'] = parsed_ps_date
                current_last_posted_at = parsed_ps_date
            elif existing_media_from_db is None: # New item and parsing failed
                enriched['last_posted_at'] = None
                current_last_posted_at = None
            # Else (existing item and parsing failed): current_last_posted_at (from DB or already None) is kept
            enriched['podcast_spotify_id'] = initial_data.get('podcast_spotify_id') or enriched.get('podcast_spotify_id')
            enriched['audience_size'] = _sanitize_numeric_string(reach.get('audience_size'), int) if reach.get('audience_size') is not None else enriched.get('audience_size')
            if reach.get('itunes'):
                enriched['itunes_rating_average'] = _sanitize_numeric_string(reach['itunes'].get('itunes_rating_average'), float) if reach['itunes'].get('itunes_rating_average') is not None else enriched.get('itunes_rating_average')
                enriched['itunes_rating_count'] = _sanitize_numeric_string(reach['itunes'].get('itunes_rating_count'), int) if reach['itunes'].get('itunes_rating_count') is not None else enriched.get('itunes_rating_count')
            # (Apply similar logic for spotify ratings and social links from Podscan initial_data)
            enriched['api_id'] = str(initial_data.get('podcast_id', enriched.get('api_id', ''))).strip() # Ensure current source's API ID

        # Ensure source_api is correctly set or overridden by the current source
        enriched['source_api'] = source_api 
        if enriched.get('api_id') and source_api == "ListenNotes":
             enriched['api_id'] = str(initial_data.get('id', enriched.get('api_id', ''))).strip()
        elif enriched.get('api_id') and source_api == "PodscanFM":
            enriched['api_id'] = str(initial_data.get('podcast_id', enriched.get('api_id', ''))).strip()

        perform_cross_api_enrichment = False
        if not existing_media_from_db:
            perform_cross_api_enrichment = True
        else:
            last_enriched_ts_val = enriched.get('last_enriched_timestamp') # Already should be datetime or None from DB
            is_stale = True
            if isinstance(last_enriched_ts_val, datetime):
                now_aware = datetime.now(dt_timezone.utc)
                if (now_aware - last_enriched_ts_val).days < ENRICHMENT_FRESHNESS_THRESHOLD_DAYS:
                    is_stale = False
            if is_stale:
                perform_cross_api_enrichment = True

        if perform_cross_api_enrichment:
            logger.info(f"Performing full cross-API enrichment for {enriched.get('name')}")
            rss_for_cross_enrich = enriched.get('rss_url')
            itunes_id_for_cross_enrich = _sanitize_numeric_string(enriched.get('itunes_id'), int)

            try:
                if source_api == "ListenNotes": # Enrich WITH Podscan
                    match = None
                    if itunes_id_for_cross_enrich:
                        logger.debug(f"Cross-enriching ListenNotes item {enriched.get('name')} with Podscan via iTunes ID: {itunes_id_for_cross_enrich}")
                        await asyncio.sleep(API_CALL_DELAY / 2)
                        match = await self._run_in_executor(self.podscan_client.search_podcast_by_itunes_id, itunes_id_for_cross_enrich)
                    if not match and rss_for_cross_enrich:
                        logger.debug(f"Cross-enriching ListenNotes item {enriched.get('name')} with Podscan via RSS: {rss_for_cross_enrich}")
                        await asyncio.sleep(API_CALL_DELAY / 2)
                        match = await self._run_in_executor(self.podscan_client.search_podcast_by_rss, rss_for_cross_enrich)
                    
                    if match:
                        logger.info(f"Podscan match found for ListenNotes item '{enriched.get('name')}'. Promoting to Podscan as primary source.")
                        # *** PROMOTION LOGIC ***
                        enriched['source_api'] = "PodscanFM"
                        enriched['api_id'] = str(match.get('podcast_id')).strip()
                        # Now merge Podscan data, overwriting ListenNotes data where Podscan is likely better
                        enriched['name'] = html.unescape(str(match.get('podcast_name', enriched.get('name', '')))).strip()
                        enriched['description'] = html.unescape(str(match.get('podcast_description', enriched.get('description', '')))).strip() or None
                        enriched['website'] = match.get('podcast_url') or enriched.get('website')
                        enriched['podcast_spotify_id'] = match.get('podcast_spotify_id') or enriched.get('podcast_spotify_id')
                        reach = match.get('reach') or {}
                        enriched['audience_size'] = _sanitize_numeric_string(reach.get('audience_size'), int) if reach.get('audience_size') is not None else enriched.get('audience_size')
                        if reach.get('email'): enriched['contact_email'] = reach.get('email')
                        for k, v in self._extract_social_links(reach.get('social_links', [])).items():
                            enriched.setdefault(k, v)
                        parsed_cross_ps_date = parse_date(match.get('last_posted_at'))
                        if parsed_cross_ps_date is not None:
                            if current_last_posted_at is None or parsed_cross_ps_date > current_last_posted_at:
                                enriched['last_posted_at'] = parsed_cross_ps_date
                        enriched['image_url'] = match.get('podcast_image_url') or enriched.get('image_url')
                        if match.get('podcast_categories'): enriched['category'] = match['podcast_categories'][0].get('category_name')

                elif source_api == "PodscanFM": # Enrich WITH ListenNotes
                    match = None
                    if itunes_id_for_cross_enrich:
                        logger.debug(f"Cross-enriching PodscanFM item {enriched.get('name')} with ListenNotes via iTunes ID: {itunes_id_for_cross_enrich}")
                        await asyncio.sleep(API_CALL_DELAY / 2)
                        match = await self._run_in_executor(self.listennotes_client.lookup_podcast_by_itunes_id, itunes_id_for_cross_enrich)
                    if not match and rss_for_cross_enrich:
                        logger.debug(f"Cross-enriching PodscanFM item {enriched.get('name')} with ListenNotes via RSS: {rss_for_cross_enrich}")
                        await asyncio.sleep(API_CALL_DELAY / 2)
                        match = await self._run_in_executor(self.listennotes_client.lookup_podcast_by_rss, rss_for_cross_enrich)

                    if match:
                        logger.debug(f"ListenNotes match found for PodscanFM item {enriched.get('name')}: {match.get('title_original')}")
                        enriched.setdefault('listen_score', _sanitize_numeric_string(match.get('listen_score'), int))
                        enriched.setdefault('listen_score_global_rank', _sanitize_numeric_string(match.get('listen_score_global_rank'), int))
                        if match.get('description_original') and not enriched.get('description'): # If Podscan desc was empty
                            enriched['description'] = html.unescape(match['description_original'])
                        enriched.setdefault('language', match.get('language'))
                        enriched.setdefault('total_episodes', match.get('total_episodes'))
                        enriched.setdefault('image_url', match.get('image'))
                        if match.get('genres') and not enriched.get('category'):
                            enriched['category'] = match['genres'][0]
                        if match.get('email') and not enriched.get('contact_email'): # Only set if Podscan email was empty
                            enriched['contact_email'] = match.get('email')
                        parsed_cross_ln_date = parse_date(match.get('latest_pub_date_ms'))
                        if parsed_cross_ln_date is not None:
                            # Update if ListenNotes has a more recent or if current is None
                            if current_last_posted_at is None or parsed_cross_ln_date > current_last_posted_at:
                                enriched['last_posted_at'] = parsed_cross_ln_date
                        if match.get('itunes_id') and not enriched.get('itunes_id'):
                             enriched['itunes_id'] = str(match.get('itunes_id')).strip()
                        enriched.setdefault('website', match.get('website'))
                        # Add other ListenNotes fields to Podscan record if missing or preferred

            except APIClientError as e:
                logger.warning(f"API client error during conditional cross-enrichment for {enriched.get('name')}: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error during conditional cross-enrichment for {enriched.get('name')}: {e}", exc_info=True)
            
            enriched['last_enriched_timestamp'] = datetime.now(dt_timezone.utc)
        
        # Final check to ensure last_posted_at is None if it somehow ended up as an empty string (should not happen with parse_date)
        if enriched.get('last_posted_at') == '':
            enriched['last_posted_at'] = None

        return enriched

    async def merge_and_upsert_media(self, podcast_data: Dict[str, Any], source_api: str,
                                     campaign_uuid: uuid.UUID, keyword: str) -> Optional[int]:
        # Enhanced logging within this function
        media_name_for_log = podcast_data.get('name', '[Name N/A]')
        logger.debug(f"merge_and_upsert_media: Processing '{media_name_for_log}' from source '{source_api}', keyword '{keyword}'.")

        # BUSINESS RULE: Only process podcasts with contact email
        # First check API-provided emails
        contact_email = podcast_data.get('contact_email') or podcast_data.get('rss_owner_email')
        
        # If no API email found, try quick RSS parsing for contact email
        if not contact_email and podcast_data.get('rss_url'):
            logger.debug(f"merge_and_upsert_media: No API email for '{media_name_for_log}', attempting RSS email discovery")
            rss_email = await self._quick_rss_email_discovery(podcast_data.get('rss_url'))
            if rss_email:
                contact_email = rss_email
                podcast_data['rss_owner_email'] = rss_email
                logger.info(f"merge_and_upsert_media: Found email in RSS for '{media_name_for_log}': {rss_email}")
        
        if not contact_email:
            logger.debug(f"merge_and_upsert_media: Skipping '{media_name_for_log}' - no contact email found in API or RSS")
            return None
        
        name_val = str(podcast_data.get('name', '')).strip()
        if not name_val:
            logger.warning(f"merge_and_upsert_media: Skipping upsert for item from '{source_api}' (keyword '{keyword}'), media name is empty. Data snapshot: api_id={podcast_data.get('api_id')}, rss={podcast_data.get('rss_url')}")
            return None
        
        if not podcast_data.get('rss_url') and not podcast_data.get('website'):
            logger.warning(f"merge_and_upsert_media: Skipping upsert for '{media_name_for_log}' from '{source_api}' (keyword '{keyword}'), both RSS and website missing.")
            return None

        try:
            logger.debug(f"merge_and_upsert_media: Calling upsert_media_in_db for '{media_name_for_log}'.")
            media = await media_queries.upsert_media_in_db(podcast_data)
            if media and media.get('media_id'):
                logger.info(f"merge_and_upsert_media: Media upserted/updated: '{media.get('name')}' (ID: {media['media_id']}) from source {podcast_data.get('source_api')}")
                
                # Discovery tracking removed - this is now handled exclusively in fetch_podcasts_for_campaign
                # to respect the max_matches limit properly
                
                return media['media_id']
            else:
                logger.warning(f"merge_and_upsert_media: upsert_media_in_db for '{media_name_for_log}' did not return a valid media record or media_id. Media dict: {media}")
                return None
        except Exception as e:  
            logger.error(f"merge_and_upsert_media: DB error during upsert for '{media_name_for_log}': {e}", exc_info=True)
            return None # Ensure None is returned on DB error

    async def create_match_suggestions(self, media_id: int, campaign_uuid: uuid.UUID, keyword: str) -> bool:
        try:
            existing = await match_queries.get_match_suggestion_by_campaign_and_media_ids(campaign_uuid, media_id)
            if existing:
                logger.info("MatchSuggestion already exists for media %s and campaign %s", media_id, campaign_uuid)
                return False
            suggestion = {
                'campaign_id': campaign_uuid,
                'media_id': media_id,
                'matched_keywords': [keyword],
                'status': 'pending',
            }
            created = await match_queries.create_match_suggestion_in_db(suggestion)
            if created and created.get('match_id'):
                review_task = {
                    'task_type': 'match_suggestion',
                    'related_id': created['match_id'],
                    'campaign_id': campaign_uuid,
                    'status': 'pending',
                }
                await review_tasks_queries.create_review_task_in_db(review_task)
                logger.info("Created ReviewTask for MatchSuggestion %s", created['match_id'])
                return True
            else:
                logger.warning("Could not create ReviewTask for media %s (match suggestion creation failed or returned unexpected)", media_id)
                return False
        except Exception as e:
            logger.error("Error creating match suggestion for media %s: %s", media_id, e, exc_info=True)
            return False

    async def search_listen_notes_for_media(self, keyword: str, genre_ids_str: Optional[str], campaign_uuid: uuid.UUID, # Renamed for clarity
                                            processed_ids_session: set) -> List[int]:
        if not genre_ids_str:
            logger.warning(f"ListenNotes: No genre IDs available for keyword '{keyword}', skipping ListenNotes search.")
            return []
        logger.info(f"ListenNotes: Using genre_ids_str '{genre_ids_str}' for keyword '{keyword}'.")
        
        upserted_media_ids_this_call: List[int] = []
        ln_offset = 0
        ln_has_more = True 

        while ln_has_more:
            try:
                logger.info(f"ListenNotes: Searching '{keyword}', offset {ln_offset}")
                response = await self._run_in_executor(
                    self.listennotes_client.search_podcasts,
                    keyword,
                    genre_ids=genre_ids_str, # Pass the string of genre IDs
                    offset=ln_offset,
                    page_size=LISTENNOTES_PAGE_SIZE,
                    episode_count_min=MIN_EPISODE_COUNT, # Minimum episodes required
                    interviews_only=1, # Only podcasts with guest interviews
                )
                results = response.get('results', []) if isinstance(response, dict) else []
                if not results:
                    logger.info(f"ListenNotes: No results from API for '{keyword}' at offset {ln_offset}.")
                    ln_has_more = False
                    break 

                for item in results:
                    logger.debug(f"ListenNotes: Processing item: {item.get('title_original', 'N/A')}, API ID: {item.get('id')}") 
                    
                    ln_api_id = str(item.get('id', '')).strip()
                    ln_rss = item.get('rss')
                    current_item_source_identifier = ln_rss or ln_api_id
                    if current_item_source_identifier and current_item_source_identifier in processed_ids_session:
                        logger.debug(f"ListenNotes: Item ID {ln_api_id}/RSS {ln_rss} already in processed_ids_session for '{keyword}'. Skipping.")
                        continue

                    existing_media_in_db = await self._get_existing_media_by_identifiers(item, "ListenNotes")
                    logger.debug(f"ListenNotes: For item '{item.get('title_original')}', result of _get_existing_media_by_identifiers is None? {existing_media_in_db is None}")
                    
                    enriched = await self._enrich_podcast_data(item, "ListenNotes", existing_media_from_db=existing_media_in_db)
                    media_id = await self.merge_and_upsert_media(enriched, "ListenNotes", campaign_uuid, keyword)
                    
                    if media_id:
                        upserted_media_ids_this_call.append(media_id)
                        logger.debug(f"ListenNotes: Added media ID: {media_id}")

                        if existing_media_in_db is None: 
                            logger.info(f"New media_id {media_id} (ListenNotes) for '{enriched.get('name')}'. Fetching episodes...")
                            await self.episode_handler_service.fetch_and_store_latest_episodes(media_id=media_id, num_latest=10)
                        else:
                            logger.info(f"Media_id {media_id} (ListenNotes) for '{enriched.get('name')}' already existed. DB Name: {existing_media_in_db.get('name', 'N/A')}, DB ID: {existing_media_in_db.get('media_id', 'N/A')}")
                        
                        if current_item_source_identifier: 
                            processed_ids_session.add(current_item_source_identifier)
                    else:
                        logger.warning(f"ListenNotes: merge_and_upsert_media FAILED for item '{enriched.get('name')}' from keyword '{keyword}'.")
                                
                if not ln_has_more: 
                    logger.debug(f"ListenNotes: Breaking outer pagination loop for '{keyword}' (ln_has_more is False).")
                    break

                ln_has_more = response.get('has_next', False)
                if not ln_has_more:
                    logger.info(f"ListenNotes: No more pages from API for keyword '{keyword}' (has_next is False).")
                ln_offset = response.get('next_offset', ln_offset + LISTENNOTES_PAGE_SIZE) if ln_has_more else ln_offset
                if ln_has_more:
                    await asyncio.sleep(API_CALL_DELAY)
            except RateLimitError as rle:
                logger.warning(f"ListenNotes rate limit for '{keyword}': {rle}")
                await asyncio.sleep(60)
            except APIClientError as apie:
                logger.error(f"ListenNotes API error for '{keyword}': {apie}")
                ln_has_more = False
            except Exception as e:
                logger.error(f"ListenNotes error for '{keyword}': {e}", exc_info=True)
                ln_has_more = False
        logger.info(f"ListenNotes: Finished search for keyword '{keyword}'.")
        return upserted_media_ids_this_call

    async def search_podscan_for_media(self, keyword: str, campaign_uuid: uuid.UUID, 
                                       processed_ids_session: set, podscan_category_ids_override: Optional[str] = None) -> List[int]:
        # MODIFIED: Call the correct ID generation helper
        category_ids_str = podscan_category_ids_override or await self._generate_podscan_category_ids_async(keyword, str(campaign_uuid))
        if not category_ids_str:
            logger.warning(f"PodscanFM: No category IDs generated for keyword '{keyword}', skipping Podscan search.")
            return []
        logger.info(f"PodscanFM: Using category_ids_str '{category_ids_str}' for keyword '{keyword}'.")

        upserted_media_ids_this_call: List[int] = []
        ps_page = 1
        ps_has_more = True 

        while ps_has_more:
            try:
                logger.info(f"PodscanFM: Searching '{keyword}' page {ps_page}")
                response = await self._run_in_executor(
                    self.podscan_client.search_podcasts,
                    keyword,
                    page=ps_page,
                    per_page=PODSCAN_PAGE_SIZE,
                    category_ids=category_ids_str, # MODIFIED: Pass category_ids to Podscan client
                    min_episode_count=MIN_EPISODE_COUNT, # Minimum episodes required
                    has_guests=True, # Only podcasts with guest interviews
                )
                results = response.get('podcasts', []) if isinstance(response, dict) else []
                if not results:
                    logger.info(f"PodscanFM: No results from API for '{keyword}' at page {ps_page}.")
                    ps_has_more = False
                    break 

                for item in results:
                    logger.debug(f"PodscanFM: Processing item: {item.get('podcast_name', 'N/A')}, API ID: {item.get('podcast_id')}") 
                    
                    ps_api_id = str(item.get('podcast_id', '')).strip()
                    ps_rss = item.get('rss_url')
                    current_item_source_identifier = ps_rss or ps_api_id

                    if current_item_source_identifier and current_item_source_identifier in processed_ids_session:
                        logger.debug(f"PodscanFM: Item ID {ps_api_id}/RSS {ps_rss} already in processed_ids_session for '{keyword}'. Skipping.")
                        continue

                    existing_media_in_db = await self._get_existing_media_by_identifiers(item, "PodscanFM")
                    logger.debug(f"PodscanFM: For item '{item.get('podcast_name')}', result of _get_existing_media_by_identifiers is None? {existing_media_in_db is None}")
                    
                    enriched = await self._enrich_podcast_data(item, "PodscanFM", existing_media_from_db=existing_media_in_db)
                    media_id = await self.merge_and_upsert_media(enriched, "PodscanFM", campaign_uuid, keyword)
                    
                    if media_id:
                        upserted_media_ids_this_call.append(media_id)
                        logger.debug(f"PodscanFM: Added media ID: {media_id}")

                        if existing_media_in_db is None: 
                            logger.info(f"New media_id {media_id} (PodscanFM) for '{enriched.get('name')}'. Fetching episodes...")
                            await self.episode_handler_service.fetch_and_store_latest_episodes(media_id=media_id, num_latest=10)
                        else:
                            logger.info(f"Media_id {media_id} (PodscanFM) for '{enriched.get('name')}' already existed. DB Name: {existing_media_in_db.get('name', 'N/A')}, DB ID: {existing_media_in_db.get('media_id', 'N/A')}")
                            
                        if current_item_source_identifier:
                            processed_ids_session.add(current_item_source_identifier)
                    else:
                        logger.warning(f"PodscanFM: merge_and_upsert_media FAILED for item '{enriched.get('name')}' from keyword '{keyword}'.")

                if not ps_has_more: 
                    logger.debug(f"PodscanFM: Breaking outer pagination loop for '{keyword}' (ps_has_more is False).")
                    break
                                
                ps_has_more = len(results) >= PODSCAN_PAGE_SIZE 
                if not ps_has_more:
                    logger.info(f"PodscanFM: No more pages from API for keyword '{keyword}' (processed all results from current page, and page size indicates no more).")
                if ps_has_more:
                    ps_page += 1
                    await asyncio.sleep(API_CALL_DELAY)
            except RateLimitError as rle:
                logger.warning(f"PodscanFM rate limit for '{keyword}': {rle}")
                await asyncio.sleep(60)
            except APIClientError as apie:
                logger.error(f"PodscanFM API error for '{keyword}': {apie}")
                ps_has_more = False
            except Exception as e:
                logger.error(f"PodscanFM error for '{keyword}': {e}", exc_info=True)
                ps_has_more = False
        logger.info(f"PodscanFM: Finished search for keyword '{keyword}'.")
        return upserted_media_ids_this_call

    async def fetch_podcasts_for_campaign(self, campaign_id_str: str, max_matches: Optional[int] = None) -> List[tuple[int, str]]:
        """
        Enhanced version that ensures all discovered podcasts are tracked in campaign_media_discoveries,
        regardless of whether they already exist in the media table.
        """
        max_matches = max_matches or 50  # Default to 50 if not specified
        logger.info(f"Starting enhanced podcast fetch for campaign {campaign_id_str}. Max new discoveries for this run: {max_matches}")
        
        # Track media IDs with their keywords that get NEW discovery records
        media_with_new_discoveries: List[tuple[int, str]] = []
        new_discoveries_count = 0
        
        try:
            campaign_uuid = uuid.UUID(campaign_id_str)
        except ValueError:
            logger.error("Invalid campaign ID: %s", campaign_id_str)
            return []
        
        campaign = await campaign_queries.get_campaign_by_id(campaign_uuid)
        if not campaign:
            logger.error("Campaign %s not found", campaign_uuid)
            return []
        
        keywords: List[str] = campaign.get('campaign_keywords', [])
        if not keywords:
            logger.warning("No keywords for campaign %s. Nothing to discover.", campaign_uuid)
            return []
        
        processed_media_identifiers_this_run: set = set()
        
        logger.info(f"Phase 1: Discovering and upserting media for campaign {campaign_uuid} based on {len(keywords)} keywords.")
        
        # Track all discovered media (new and existing) with their discovery source
        all_discovered_media: List[Tuple[int, str, bool]] = []  # (media_id, keyword, is_new)
        
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            
            logger.info(f"Discovering media for campaign '{campaign_uuid}', keyword: '{kw}'.")
            
            listennotes_genre_ids = await self._generate_genre_ids_async(kw, str(campaign_uuid))
            podscan_category_ids = await self._generate_podscan_category_ids_async(kw, str(campaign_uuid))
            
            # Search ListenNotes with enhanced tracking
            ln_discovered = await self._search_and_track_discoveries(
                'ListenNotes', kw, campaign_uuid, processed_media_identifiers_this_run,
                listennotes_genre_ids=listennotes_genre_ids
            )
            all_discovered_media.extend(ln_discovered)
            
            # Search Podscan with enhanced tracking
            ps_discovered = await self._search_and_track_discoveries(
                'PodscanFM', kw, campaign_uuid, processed_media_identifiers_this_run,
                podscan_category_ids=podscan_category_ids
            )
            all_discovered_media.extend(ps_discovered)
            
            logger.info(f"Finished media discovery for keyword '{kw}' for campaign {campaign_uuid}.")
            await asyncio.sleep(KEYWORD_PROCESSING_DELAY)
        
        logger.info(f"Phase 1 (Media Discovery) completed for campaign {campaign_uuid}. "
                    f"{len(all_discovered_media)} total media items discovered.")
        
        # Phase 2: Create campaign_media_discoveries records for ALL discovered media
        logger.info(f"Phase 2: Creating campaign_media_discoveries records. Limit: {max_matches}")
        
        # Remove duplicates while preserving order
        seen_media_ids = set()
        unique_discovered_media = []
        for media_id, keyword, is_new in all_discovered_media:
            if media_id not in seen_media_ids:
                seen_media_ids.add(media_id)
                unique_discovered_media.append((media_id, keyword, is_new))
        
        # Track discoveries for ALL media (new and existing) up to max_matches
        for media_id, keyword, is_new_media in unique_discovered_media:
            if new_discoveries_count >= max_matches:
                logger.info(f"Reached max_matches limit ({max_matches}) for new discoveries. Stopping.")
                break
            
            # Check if this campaign-media discovery already exists
            exists = await media_queries.check_campaign_media_discovery_exists(campaign_uuid, media_id)
            
            if not exists:
                # Create new discovery record
                discovery_created = await media_queries.track_campaign_media_discovery(campaign_uuid, media_id, keyword)
                if discovery_created:
                    new_discoveries_count += 1
                    media_with_new_discoveries.append((media_id, keyword))
                    logger.info(f"Created discovery #{new_discoveries_count} for {'NEW' if is_new_media else 'EXISTING'} "
                               f"media {media_id} with keyword '{keyword}'")
            else:
                logger.debug(f"Discovery already exists for campaign {campaign_uuid}, media {media_id}")
        
        logger.info(f"Discovery process COMPLETED for campaign {campaign_uuid}. "
                    f"Created {new_discoveries_count} new campaign_media_discoveries records.")
        
        # Publish events for media with new discoveries
        try:
            event_bus = get_event_bus()
            for media_id, keyword in media_with_new_discoveries:
                event = Event(
                    event_type=EventType.MEDIA_CREATED,
                    entity_id=str(media_id),
                    entity_type="media",
                    data={"campaign_id": str(campaign_uuid), "discovery_keyword": keyword},
                    source="media_fetcher"
                )
                await event_bus.publish(event)
            
            if media_with_new_discoveries:
                logger.info(f"Published MEDIA_CREATED events for {len(media_with_new_discoveries)} new discoveries")
        except Exception as e:
            logger.error(f"Error publishing MEDIA_CREATED events: {e}", exc_info=True)
        
        return media_with_new_discoveries
    
    async def _search_and_track_discoveries(
        self,
        source_api: str,
        keyword: str,
        campaign_uuid: uuid.UUID,
        processed_ids_session: Set[str],
        listennotes_genre_ids: Optional[str] = None,
        podscan_category_ids: Optional[str] = None
    ) -> List[Tuple[int, str, bool]]:
        """
        Search for media and track whether each result is new or existing.
        Returns list of (media_id, keyword, is_new) tuples.
        """
        discovered_media = []
        
        if source_api == 'ListenNotes':
            media_results = await self._search_listennotes_with_tracking(
                keyword, listennotes_genre_ids, campaign_uuid, processed_ids_session
            )
        else:  # PodscanFM
            media_results = await self._search_podscan_with_tracking(
                keyword, campaign_uuid, processed_ids_session, podscan_category_ids
            )
        
        for media_id, is_new in media_results:
            discovered_media.append((media_id, keyword, is_new))
        
        return discovered_media
    
    async def _search_listennotes_with_tracking(
        self,
        keyword: str,
        genre_ids_str: Optional[str],
        campaign_uuid: uuid.UUID,
        processed_ids_session: Set[str]
    ) -> List[Tuple[int, bool]]:
        """
        Search ListenNotes and track whether each result is new or existing.
        Returns list of (media_id, is_new) tuples.
        """
        if not genre_ids_str:
            logger.warning(f"ListenNotes: No genre IDs available for keyword '{keyword}', skipping ListenNotes search.")
            return []
        
        logger.info(f"ListenNotes: Using genre_ids_str '{genre_ids_str}' for keyword '{keyword}'.")
        
        media_results = []
        ln_offset = 0
        ln_has_more = True
        
        while ln_has_more:
            try:
                logger.info(f"ListenNotes: Searching '{keyword}' offset {ln_offset}")
                response = await self._run_in_executor(
                    self.listennotes_client.search_podcasts,
                    keyword,
                    genre_ids=genre_ids_str,
                    offset=ln_offset,
                    page_size=LISTENNOTES_PAGE_SIZE,
                    episode_count_min=MIN_EPISODE_COUNT,
                    interviews_only=1
                )
                results = response.get('results', []) if isinstance(response, dict) else []
                if not results:
                    logger.info(f"ListenNotes: No results from API for '{keyword}' at offset {ln_offset}.")
                    ln_has_more = False
                    break
                
                for item in results:
                    current_item_source_identifier = item.get('rss') or str(item.get('id', '')).strip()
                    
                    if current_item_source_identifier and current_item_source_identifier in processed_ids_session:
                        logger.debug(f"ListenNotes: Item {current_item_source_identifier} already processed in this session. Skipping.")
                        continue
                    
                    # Check if media exists
                    existing_media_in_db = await self._get_existing_media_by_identifiers(item, "ListenNotes")
                    is_new = existing_media_in_db is None
                    
                    # Enrich and upsert regardless of whether it's new
                    enriched = await self._enrich_podcast_data(item, "ListenNotes", existing_media_from_db=existing_media_in_db)
                    
                    # Discovery tracking is now handled exclusively in fetch_podcasts_for_campaign
                    media_id = await self.merge_and_upsert_media(
                        enriched, "ListenNotes", campaign_uuid, keyword
                    )
                    
                    if media_id:
                        media_results.append((media_id, is_new))
                        logger.debug(f"ListenNotes: Processed {'NEW' if is_new else 'EXISTING'} media ID: {media_id}")
                        
                        if is_new:
                            logger.info(f"New media_id {media_id} (ListenNotes) for '{enriched.get('name')}'. Fetching episodes...")
                            await self.episode_handler_service.fetch_and_store_latest_episodes(media_id=media_id, num_latest=10)
                        
                        if current_item_source_identifier:
                            processed_ids_session.add(current_item_source_identifier)
                    else:
                        logger.warning(f"ListenNotes: merge_and_upsert_media FAILED for item '{enriched.get('name')}' from keyword '{keyword}'.")
                
                ln_has_more = response.get('has_next', False)
                if ln_has_more:
                    ln_offset = response.get('next_offset', ln_offset + LISTENNOTES_PAGE_SIZE)
                    await asyncio.sleep(API_CALL_DELAY)
                    
            except RateLimitError as rle:
                logger.warning(f"ListenNotes rate limit for '{keyword}': {rle}")
                await asyncio.sleep(60)
                ln_has_more = False
            except APIClientError as apie:
                logger.error(f"ListenNotes API error for '{keyword}': {apie}")
                ln_has_more = False
            except Exception as e:
                logger.error(f"ListenNotes error for '{keyword}': {e}", exc_info=True)
                ln_has_more = False
        
        logger.info(f"ListenNotes: Finished search for keyword '{keyword}'.")
        return media_results
    
    async def _search_podscan_with_tracking(
        self,
        keyword: str,
        campaign_uuid: uuid.UUID,
        processed_ids_session: Set[str],
        podscan_category_ids_override: Optional[str] = None
    ) -> List[Tuple[int, bool]]:
        """
        Search Podscan and track whether each result is new or existing.
        Returns list of (media_id, is_new) tuples.
        """
        category_ids_str = podscan_category_ids_override or await self._generate_podscan_category_ids_async(keyword, str(campaign_uuid))
        if not category_ids_str:
            logger.warning(f"PodscanFM: No category IDs generated for keyword '{keyword}', skipping Podscan search.")
            return []
        
        logger.info(f"PodscanFM: Using category_ids_str '{category_ids_str}' for keyword '{keyword}'.")
        
        media_results = []
        ps_page = 1
        ps_has_more = True
        
        while ps_has_more:
            try:
                logger.info(f"PodscanFM: Searching '{keyword}' page {ps_page}")
                response = await self._run_in_executor(
                    self.podscan_client.search_podcasts,
                    keyword,
                    page=ps_page,
                    per_page=PODSCAN_PAGE_SIZE,
                    category_ids=category_ids_str,
                    min_episode_count=MIN_EPISODE_COUNT,
                    has_guests=True,
                )
                results = response.get('podcasts', []) if isinstance(response, dict) else []
                if not results:
                    logger.info(f"PodscanFM: No results from API for '{keyword}' at page {ps_page}.")
                    ps_has_more = False
                    break
                
                for item in results:
                    ps_api_id = str(item.get('podcast_id', '')).strip()
                    ps_rss = item.get('rss_url')
                    current_item_source_identifier = ps_rss or ps_api_id
                    
                    if current_item_source_identifier and current_item_source_identifier in processed_ids_session:
                        logger.debug(f"PodscanFM: Item {current_item_source_identifier} already processed in this session. Skipping.")
                        continue
                    
                    # Check if media exists
                    existing_media_in_db = await self._get_existing_media_by_identifiers(item, "PodscanFM")
                    is_new = existing_media_in_db is None
                    
                    # Enrich and upsert regardless of whether it's new
                    enriched = await self._enrich_podcast_data(item, "PodscanFM", existing_media_from_db=existing_media_in_db)
                    
                    # Discovery tracking is now handled exclusively in fetch_podcasts_for_campaign
                    media_id = await self.merge_and_upsert_media(
                        enriched, "PodscanFM", campaign_uuid, keyword
                    )
                    
                    if media_id:
                        media_results.append((media_id, is_new))
                        logger.debug(f"PodscanFM: Processed {'NEW' if is_new else 'EXISTING'} media ID: {media_id}")
                        
                        if is_new:
                            logger.info(f"New media_id {media_id} (PodscanFM) for '{enriched.get('name')}'. Fetching episodes...")
                            await self.episode_handler_service.fetch_and_store_latest_episodes(media_id=media_id, num_latest=10)
                        
                        if current_item_source_identifier:
                            processed_ids_session.add(current_item_source_identifier)
                    else:
                        logger.warning(f"PodscanFM: merge_and_upsert_media FAILED for item '{enriched.get('name')}' from keyword '{keyword}'.")
                
                ps_has_more = len(results) >= PODSCAN_PAGE_SIZE
                if ps_has_more:
                    ps_page += 1
                    await asyncio.sleep(API_CALL_DELAY)
                    
            except RateLimitError as rle:
                logger.warning(f"PodscanFM rate limit for '{keyword}': {rle}")
                await asyncio.sleep(60)
                ps_has_more = False
            except APIClientError as apie:
                logger.error(f"PodscanFM API error for '{keyword}': {apie}")
                ps_has_more = False
            except Exception as e:
                logger.error(f"PodscanFM error for '{keyword}': {e}", exc_info=True)
                ps_has_more = False
        
        logger.info(f"PodscanFM: Finished search for keyword '{keyword}'.")
        return media_results

    async def admin_discover_and_process_podcasts(
        self,
        keyword: str,
        campaign_id_for_association: Optional[uuid.UUID] = None,
        max_results_per_source: int = 10 # This already provides a limit for admin function
    ) -> List[Dict[str, Any]]:
        logger.info(f"Admin discovery: '{keyword}', campaign: {campaign_id_for_association}, max: {max_results_per_source}")
        
        genre_generation_context_id = str(campaign_id_for_association) if campaign_id_for_association else f"admin_search_{keyword}"
        genre_ids = await self._generate_genre_ids_async(keyword, genre_generation_context_id)

        # Tracks API items processed in this admin session (across ListenNotes & Podscan for this keyword)
        # to avoid redundant enrichment if same item appears from both sources before DB upsert merges them.
        processed_api_items_this_admin_call: set = set()
        discovered_media_db_ids: List[int] = []

        # --- Search ListenNotes ---
        if genre_ids:
            ln_offset = 0
            ln_has_more = True
            ln_found_count = 0
            while ln_has_more and ln_found_count < max_results_per_source:
                # ... (try/except for API call to self.listennotes_client.search_podcasts) ...
                # response = await self._run_in_executor(...) from previous edit is correct
                logger.info(f"Admin ListenNotes: Searching '{keyword}' offset {ln_offset}")
                try:
                    response = await self._run_in_executor(
                        self.listennotes_client.search_podcasts, keyword, genre_ids=genre_ids,
                        offset=ln_offset, page_size=LISTENNOTES_PAGE_SIZE)
                    results = response.get('results', []) if isinstance(response, dict) else []
                    if results:
                        for item in results:
                            if ln_found_count >= max_results_per_source: break
                            
                            ln_item_id = item.get('rss') or item.get('id')
                            if ln_item_id and ln_item_id in processed_api_items_this_admin_call:
                                logger.debug(f"Admin ListenNotes: item {ln_item_id} already processed in this admin call. Skipping.")
                                continue

                            existing_media = await self._get_existing_media_by_identifiers(item, "ListenNotes")
                            enriched = await self._enrich_podcast_data(item, "ListenNotes", existing_media_from_db=existing_media)
                            
                            # Determine campaign_uuid for upsert/suggestion context
                            # If admin provides one, use it. Otherwise, upsert might occur without suggestion, or with dummy context.
                            # merge_and_upsert_media expects a campaign_uuid.
                            context_campaign_uuid = campaign_id_for_association if campaign_id_for_association else uuid.uuid4() # Dummy if no association

                            media_id = await self.merge_and_upsert_media(enriched, "ListenNotes", context_campaign_uuid, keyword)
                            if media_id:
                                discovered_media_db_ids.append(media_id)
                                ln_found_count += 1
                                if ln_item_id: processed_api_items_this_admin_call.add(ln_item_id)
                                # WORKFLOW OPTIMIZATION: Track discovery for later match creation
                                if campaign_id_for_association: # Only track if admin specified a campaign
                                    await media_queries.track_campaign_media_discovery(campaign_id_for_association, media_id, keyword)
                        
                        ln_has_more = response.get('has_next', False)
                        ln_offset = response.get('next_offset', ln_offset + LISTENNOTES_PAGE_SIZE) if ln_has_more else ln_offset
                        if ln_has_more and ln_found_count < max_results_per_source: await asyncio.sleep(API_CALL_DELAY)
                        else: ln_has_more = False # Stop if limit reached or no more pages
                    else: ln_has_more = False
                except RateLimitError as rle: # Copied error handling from previous edit
                    logger.warning(f"Admin ListenNotes rate limit for '{keyword}': {rle}")
                    await asyncio.sleep(60)
                except APIClientError as apie:
                    logger.error(f"Admin ListenNotes API error for '{keyword}': {apie}")
                    ln_has_more = False 
                except Exception as e:
                    logger.error(f"Admin ListenNotes error for '{keyword}': {e}", exc_info=True)
                    ln_has_more = False
        else:
            logger.warning(f"Admin ListenNotes: No genre IDs for '{keyword}', skipping ListenNotes search.")

        # --- Search Podscan (similar logic) ---
        ps_page = 1
        ps_has_more = True
        ps_found_count = 0
        while ps_has_more and ps_found_count < max_results_per_source:
            # ... (try/except for API call to self.podscan_client.search_podcasts) ...
            logger.info(f"Admin PodscanFM: Searching '{keyword}' page {ps_page}")
            try:
                response = await self._run_in_executor(
                    self.podscan_client.search_podcasts, keyword, page=ps_page, per_page=PODSCAN_PAGE_SIZE)
                results = response.get('podcasts', []) if isinstance(response, dict) else []
                if results:
                    for item in results:
                        if ps_found_count >= max_results_per_source: break

                        ps_item_id = item.get('rss_url') or item.get('podcast_id')
                        if ps_item_id and ps_item_id in processed_api_items_this_admin_call:
                            logger.debug(f"Admin PodscanFM: item {ps_item_id} already processed in this admin call. Skipping.")
                            continue

                        existing_media = await self._get_existing_media_by_identifiers(item, "PodscanFM")
                        enriched = await self._enrich_podcast_data(item, "PodscanFM", existing_media_from_db=existing_media)
                        
                        context_campaign_uuid_ps = campaign_id_for_association if campaign_id_for_association else uuid.uuid4()
                        media_id = await self.merge_and_upsert_media(enriched, "PodscanFM", context_campaign_uuid_ps, keyword)
                        
                        if media_id:
                            discovered_media_db_ids.append(media_id)
                            ps_found_count += 1
                            if ps_item_id: processed_api_items_this_admin_call.add(ps_item_id)
                            # WORKFLOW OPTIMIZATION: Track discovery for later match creation
                            if campaign_id_for_association:
                                await media_queries.track_campaign_media_discovery(campaign_id_for_association, media_id, keyword)
                    
                    ps_has_more = len(results) >= PODSCAN_PAGE_SIZE
                    if ps_has_more and ps_found_count < max_results_per_source: 
                        ps_page += 1
                        await asyncio.sleep(API_CALL_DELAY)
                    else: ps_has_more = False
                else: ps_has_more = False
            except RateLimitError as rle: # Copied error handling
                logger.warning(f"Admin PodscanFM rate limit for '{keyword}': {rle}")
                await asyncio.sleep(60)
            except APIClientError as apie:
                logger.error(f"Admin PodscanFM API error for '{keyword}': {apie}")
                ps_has_more = False
            except Exception as e:
                logger.error(f"Admin PodscanFM error for '{keyword}': {e}", exc_info=True)
                ps_has_more = False
        
        # Fetch the full media records from the DB
        final_media_records: List[Dict[str, Any]] = []
        if discovered_media_db_ids:
            unique_discovered_media_db_ids = list(set(discovered_media_db_ids))
            logger.info(f"Fetching {len(unique_discovered_media_db_ids)} unique media records from DB for admin response.")
            for m_id in unique_discovered_media_db_ids:
                media_record = await media_queries.get_media_by_id_from_db(m_id)
                if media_record:
                    final_media_records.append(media_record)
            
        logger.info(f"Admin discovery for '{keyword}' finished. Returning {len(final_media_records)} media items.")
        return final_media_records

    def cleanup(self) -> None:
        if self.executor:
            self.executor.shutdown(wait=True)
            logger.info("MediaFetcher executor shut down")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch & store podcasts for a campaign")
    parser.add_argument("campaign_id", help="PostgreSQL Campaign UUID")
    args = parser.parse_args()

    async def run():
        await get_db_pool() # Use modular connection
        fetcher = MediaFetcher()
        try:
            await fetcher.fetch_podcasts_for_campaign(args.campaign_id)
        finally:
            fetcher.cleanup()
            await close_db_pool() # Use modular connection
            logger.info("Script finished for Campaign ID: %s", args.campaign_id)

    asyncio.run(run())


if __name__ == "__main__":
    main()