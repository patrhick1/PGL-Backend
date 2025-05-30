# podcast_outreach/services/media/podcast_fetcher.py

import asyncio
import argparse
import uuid
from typing import Optional, List, Dict, Any
import concurrent.futures
import html
import functools
import logging
from datetime import datetime
 
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
from podcast_outreach.services.ai.utils import generate_genre_ids
from podcast_outreach.utils.data_processor import parse_date
 
# --- Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger(__name__)
 
# --- Constants ---
LISTENNOTES_PAGE_SIZE = 10
PODSCAN_PAGE_SIZE = 20
API_CALL_DELAY = 1.2
KEYWORD_PROCESSING_DELAY = 2
ENRICHMENT_FRESHNESS_THRESHOLD_DAYS = 7
 
 
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
        logger.info("MediaFetcher services initialized")
 
    async def _run_in_executor(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        func_with_args = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(self.executor, func_with_args)
 
    async def _generate_genre_ids_async(self, keyword: str, campaign_id_str: str) -> Optional[str]:
        try:
            logger.info("Generating ListenNotes genre IDs for '%s'", keyword)
            genre_ids_output = await self._run_in_executor(generate_genre_ids, self.openai_service, keyword, campaign_id_str)
            if isinstance(genre_ids_output, list):
                return ",".join(map(str, genre_ids_output))
            if isinstance(genre_ids_output, str):
                return genre_ids_output
            logger.warning("Unexpected type from generate_genre_ids: %s", type(genre_ids_output))
        except Exception as e:  # pragma: no cover - network errors
            logger.error("Error generating genre IDs for '%s': %s", keyword, e, exc_info=True)
        return None
 
    def _extract_social_links(self, socials: List[Dict[str, str]]) -> Dict[str, Optional[str]]:
        social_map: Dict[str, Optional[str]] = {}
        for item in socials or []:
            platform = item.get('platform')
            url = item.get('url')
            if not platform or not url:
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
                social_map[key] = url
            else:
                social_map.setdefault('podcast_other_social_url', url)
        return social_map
 
    async def _get_existing_media_by_identifiers(self, initial_data: Dict[str, Any], source_api: str) -> Optional[Dict[str, Any]]:
        """
        Tries to find an existing media record in the DB based on identifiers
        extracted from the initial API data.
        Order of preference: RSS URL, then API ID + Source API.
        """
        rss_url = None
        api_id_val = None
        
        # Determine potential identifiers from initial_data based on source_api
        if source_api == "ListenNotes":
            rss_url = initial_data.get('rss')
            api_id_val = str(initial_data.get('id', '')).strip()
        elif source_api == "PodscanFM":
            rss_url = initial_data.get('rss_url')
            api_id_val = str(initial_data.get('podcast_id', '')).strip()
        # Add other sources if any

        existing_media = None
        # Try fetching by RSS URL first, as it's generally more unique across platforms
        if rss_url:
            # Assuming media_queries.get_media_by_rss_url_from_db exists and is async
            existing_media = await media_queries.get_media_by_rss_url_from_db(rss_url)
        
        # If not found by RSS, try by api_id and source_api
        if not existing_media and api_id_val and source_api:
            # This assumes a query function like get_media_by_api_id_and_source_from_db exists
            # or we build a direct query. For now, let's replicate the logic from upsert:
            pool = await get_db_pool() 
            async with pool.acquire() as conn:
                # Make sure the column names 'api_id' and 'source_api' match your DB schema
                query_existing_api = "SELECT * FROM media WHERE api_id = $1 AND source_api = $2;"
                try:
                    row = await conn.fetchrow(query_existing_api, api_id_val, source_api)
                    if row:
                        existing_media = dict(row)
                except Exception as e:
                    logger.error(f"Error fetching media by api_id {api_id_val} and source {source_api}: {e}")
                    # Decide if to raise or return None. For this context, None is probably fine.

        return existing_media

    async def _enrich_podcast_data(self, initial_data: Dict[str, Any], source_api: str, existing_media_from_db: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Start with a copy of the most complete data available:
        # If existing_media_from_db is present, that's our baseline.
        # Otherwise, initial_data (from current API source) is the baseline.
        if existing_media_from_db:
            enriched = existing_media_from_db.copy()
            # Overlay/update with fresh direct fields from initial_data (the current API source)
            # These are fields that are not typically from "cross-enrichment" but direct from the source.
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
                enriched['last_posted_at'] = parse_date(initial_data.get('latest_pub_date_ms')) or enriched.get('last_posted_at')
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
                enriched['last_posted_at'] = parse_date(initial_data.get('last_posted_at')) or enriched.get('last_posted_at')
                enriched['podcast_spotify_id'] = initial_data.get('podcast_spotify_id') or enriched.get('podcast_spotify_id')
                enriched['audience_size'] = _sanitize_numeric_string(reach.get('audience_size'), int) if reach.get('audience_size') is not None else enriched.get('audience_size')
                if reach.get('itunes'):
                    enriched['itunes_rating_average'] = _sanitize_numeric_string(reach['itunes'].get('itunes_rating_average'), float) if reach['itunes'].get('itunes_rating_average') is not None else enriched.get('itunes_rating_average')
                    enriched['itunes_rating_count'] = _sanitize_numeric_string(reach['itunes'].get('itunes_rating_count'), int) if reach['itunes'].get('itunes_rating_count') is not None else enriched.get('itunes_rating_count')
                # (Apply similar logic for spotify ratings and social links from Podscan initial_data)
                enriched['api_id'] = str(initial_data.get('podcast_id', enriched.get('api_id', ''))).strip() # Ensure current source's API ID

        else: # No existing DB record, start with initial_data from the current API source
            enriched = initial_data.copy()
            # Normalize initial fields from the source like done above for existing records
            if source_api == "ListenNotes":
                enriched['name'] = html.unescape(str(initial_data.get('title_original', ''))).strip()
                enriched['description'] = html.unescape(str(initial_data.get('description_original', ''))).strip() or None
                enriched['rss_url'] = initial_data.get('rss')
                enriched['itunes_id'] = str(initial_data.get('itunes_id', '')).strip() or None
                # (continue for all fields as in the original _enrich_podcast_data for ListenNotes)
                enriched['api_id'] = str(initial_data.get('id', '')).strip()

            elif source_api == "PodscanFM":
                enriched['name'] = html.unescape(str(initial_data.get('podcast_name', ''))).strip()
                enriched['description'] = html.unescape(str(initial_data.get('podcast_description', ''))).strip() or None
                enriched['rss_url'] = initial_data.get('rss_url')
                enriched['itunes_id'] = str(initial_data.get('podcast_itunes_id', '')).strip() or None
                # (continue for all fields as in the original _enrich_podcast_data for PodscanFM)
                enriched['api_id'] = str(initial_data.get('podcast_id', '')).strip()
        
        enriched['source_api'] = source_api # Ensure current source_api is set

        perform_cross_api_enrichment = False
        if not existing_media_from_db: # Always enrich fully if it's a new record
            perform_cross_api_enrichment = True
            logger.info(f"New item '{enriched.get('name')}'. Performing full cross-API enrichment.")
        else: # Existing record, check freshness
            last_enriched_ts_val = existing_media_from_db.get('last_enriched_timestamp')
            is_stale = True
            if last_enriched_ts_val:
                # Ensure last_enriched_ts_val is datetime for comparison
                if isinstance(last_enriched_ts_val, str):
                    try: last_enriched_ts_val = datetime.fromisoformat(last_enriched_ts_val.replace('Z', '+00:00'))
                    except ValueError: last_enriched_ts_val = None
                
                if isinstance(last_enriched_ts_val, datetime):
                    # Make current time timezone-aware if last_enriched_ts_val is
                    now_aware = datetime.now(last_enriched_ts_val.tzinfo if last_enriched_ts_val.tzinfo else None)
                    if (now_aware - last_enriched_ts_val).days < ENRICHMENT_FRESHNESS_THRESHOLD_DAYS:
                        is_stale = False
                        logger.info(f"Enrichment for '{enriched.get('name')}' is fresh (last_enriched_at: {last_enriched_ts_val}). Skipping full cross-API enrichment.")
            
            if is_stale:
                perform_cross_api_enrichment = True
                logger.info(f"Enrichment for '{enriched.get('name')}' is stale or missing. Proceeding with full cross-API enrichment.")

        if perform_cross_api_enrichment:
            logger.info(f"Performing full cross-API enrichment for {enriched.get('name')}")
            # --- Start of inserted original cross-API enrichment logic ---
            rss_for_cross_enrich = enriched.get('rss_url') # Use current state of enriched dict
            itunes_id_for_cross_enrich = _sanitize_numeric_string(enriched.get('itunes_id'), int)
            
            # current_api_source_for_enrich should be 'source_api' (the source of initial_data)
            # The 'enriched' dictionary at this point contains the base data from initial_data,
            # potentially overlaid with existing DB data if it was fresher for non-cross-enriched fields.
            # The 'source_api' variable (parameter to _enrich_podcast_data) indicates the origin of 'initial_data'.

            try:
                if source_api == "ListenNotes": # If initial_data was from ListenNotes, try to enrich with Podscan
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
                        logger.debug(f"Podscan match found for ListenNotes item {enriched.get('name')}: {match.get('podcast_name')}")
                        enriched.setdefault('website', match.get('podcast_url'))
                        enriched.setdefault('podcast_spotify_id', match.get('podcast_spotify_id'))
                        reach = match.get('reach') or {}
                        enriched.setdefault('audience_size', _sanitize_numeric_string(reach.get('audience_size'), int))
                        if reach.get('email') and not enriched.get('contact_email'): # Only set if original email was empty
                            enriched['contact_email'] = reach.get('email')
                        for k, v in self._extract_social_links(reach.get('social_links', [])).items():
                            enriched.setdefault(k, v) # setdefault preserves existing values if any
                        if parse_date(match.get('last_posted_at')): # Update if Podscan has a more recent last_posted_at
                            enriched['last_posted_at'] = parse_date(match.get('last_posted_at'))
                        enriched.setdefault('image_url', match.get('podcast_image_url')) # Prefer Podscan image if LN was missing/bad?
                        if match.get('podcast_itunes_id') and not enriched.get('itunes_id'): # If LN was missing itunes_id
                             enriched['itunes_id'] = str(match.get('podcast_itunes_id')).strip()
                        if match.get('podcast_description') and not enriched.get('description'): # If LN desc was empty
                            enriched['description'] = html.unescape(match['podcast_description'])
                        # Add other Podscan fields to ListenNotes record if missing or preferred
                        if match.get('podcast_categories') and not enriched.get('category'):
                             enriched['category'] = match['podcast_categories'][0].get('category_name')


                elif source_api == "PodscanFM": # If initial_data was from PodscanFM, try to enrich with ListenNotes
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
                        if match.get('latest_pub_date_ms'): # Update if ListenNotes has a more recent last_posted_at
                            enriched['last_posted_at'] = parse_date(match.get('latest_pub_date_ms'))
                        if match.get('itunes_id') and not enriched.get('itunes_id'):
                             enriched['itunes_id'] = str(match.get('itunes_id')).strip()
                        enriched.setdefault('website', match.get('website'))
                        # Add other ListenNotes fields to Podscan record if missing or preferred

            except APIClientError as e:
                logger.warning(f"API client error during conditional cross-enrichment for {enriched.get('name')}: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error during conditional cross-enrichment for {enriched.get('name')}: {e}", exc_info=True)
            # --- End of inserted original cross-API enrichment logic ---
            
            enriched['last_enriched_timestamp'] = datetime.utcnow() # Mark as freshly enriched
        
        return enriched
 
    async def merge_and_upsert_media(self, podcast_data: Dict[str, Any], source_api: str,
                                     campaign_uuid: uuid.UUID, keyword: str) -> Optional[int]:
        contact_email = podcast_data.get('contact_email')
        # if not contact_email: # Business rule: if contact email is critical, keep this check
        #     logger.debug("Skipping %s, no contact email", podcast_data.get('name'))
        #     return None
        name_val = str(podcast_data.get('name', '')).strip()
        if not name_val:
            logger.warning("Skipping upsert, media name is empty for data from source %s", podcast_data.get('source_api'))
            return None
        
        # 'podcast_data' is the 'enriched' dictionary from the modified _enrich_podcast_data
        # It will contain 'last_enriched_timestamp' if full enrichment was done.
        # It also contains the definitive 'source_api' that provided the base record.

        # The upsert_media_in_db function expects a flat dictionary of all possible media columns.
        # The 'podcast_data' (which is 'enriched') should already be in this format.
        # We just need to ensure it gets passed through cleanly.
        
        # Remove keys that are not part of the 'media' table schema if any, or ensure all keys are valid.
        # The `upsert_media_in_db` in media_queries.py is now more robust in handling specific columns.
        # So, directly pass `podcast_data` (which is the `enriched` dict).
        
        if not podcast_data.get('rss_url') and not podcast_data.get('website'):
            logger.warning("Skipping upsert for %s, both RSS and website missing", podcast_data.get('name'))
            return None

        try:
            media = await media_queries.upsert_media_in_db(podcast_data) # Pass the enriched data directly
            if media and media.get('media_id'):
                logger.info(f"Media upserted/updated: {media.get('name')} (ID: {media['media_id']}) from source {podcast_data.get('source_api')}")
                return media['media_id']
            else:
                logger.warning(f"Upsert operation for {podcast_data.get('name')} did not return a valid media record.")
                return None
        except Exception as e:  
            logger.error(f"DB error during upsert for {podcast_data.get('name')}: {e}", exc_info=True)
        return None

    async def create_match_suggestions(self, media_id: int, campaign_uuid: uuid.UUID, keyword: str) -> None:
        try:
            existing = await match_queries.get_match_suggestion_by_campaign_and_media_ids(campaign_uuid, media_id) # Use modular query
            if existing:
                logger.info("MatchSuggestion already exists for media %s and campaign %s", media_id, campaign_uuid)
                return
            suggestion = {
                'campaign_id': campaign_uuid,
                'media_id': media_id,
                'matched_keywords': [keyword],
                'status': 'pending',
            }
            created = await match_queries.create_match_suggestion_in_db(suggestion) # Use modular query
            if created and created.get('match_id'):
                review_task = {
                    'task_type': 'match_suggestion',
                    'related_id': created['match_id'],
                    'campaign_id': campaign_uuid,
                    'status': 'pending',
                }
                await review_tasks_queries.create_review_task_in_db(review_task) # Use modular query
                logger.info("Created ReviewTask for MatchSuggestion %s", created['match_id'])
            else:
                logger.warning("Could not create ReviewTask for media %s", media_id)
        except Exception as e:  # pragma: no cover - DB errors
            logger.error("Error creating match suggestion for media %s: %s", media_id, e, exc_info=True)
 
    async def search_listen_notes(self, keyword: str, genre_ids: Optional[str], campaign_uuid: uuid.UUID, processed_ids_session: set) -> List[int]:
        if not genre_ids:
            logger.warning(f"ListenNotes: No genres for '{keyword}', skipping")
            return []
        
        upserted_media_ids_from_ln: List[int] = []
        ln_offset = 0
        ln_has_more = True
        # Note: max_results_per_source is not directly handled here; this method gets all pages from ListenNotes.
        # The caller (e.g., admin_discover_and_process_podcasts) is responsible for limiting if needed.

        while ln_has_more:
            try:
                logger.info(f"ListenNotes: Searching '{keyword}' offset {ln_offset}")
                response = await self._run_in_executor(
                    self.listennotes_client.search_podcasts,
                    keyword,
                    genre_ids=genre_ids,
                    offset=ln_offset,
                    page_size=LISTENNOTES_PAGE_SIZE,
                )
                results = response.get('results', []) if isinstance(response, dict) else []
                if results:
                    for item in results:
                        # Primary identifier from ListenNotes API item for session de-duplication
                        ln_api_id = str(item.get('id', '')).strip()
                        # Also consider RSS for session de-duplication if available directly
                        ln_rss = item.get('rss')
                        
                        # Use a composite or preferred ID for session tracking for this source
                        # This prevents re-processing the same API item from different pages of *this source's results*.
                        current_item_source_identifier = ln_rss or ln_api_id
                        if current_item_source_identifier and current_item_source_identifier in processed_ids_session:
                            logger.debug(f"ListenNotes: API item {current_item_source_identifier} already processed in this session for keyword '{keyword}'. Skipping.")
                            continue

                        existing_media_in_db = await self._get_existing_media_by_identifiers(item, "ListenNotes")
                        enriched = await self._enrich_podcast_data(item, "ListenNotes", existing_media_from_db=existing_media_in_db)
                        
                        media_id = await self.merge_and_upsert_media(enriched, "ListenNotes", campaign_uuid, keyword)
                        if media_id:
                            upserted_media_ids_from_ln.append(media_id)
                            await self.create_match_suggestions(media_id, campaign_uuid, keyword)
                            if current_item_source_identifier: # Add to session tracker after successful processing
                                processed_ids_session.add(current_item_source_identifier)
                                
                    ln_has_more = response.get('has_next', False)
                    ln_offset = response.get('next_offset', ln_offset + LISTENNOTES_PAGE_SIZE) if ln_has_more else ln_offset
                    if ln_has_more:
                        await asyncio.sleep(API_CALL_DELAY)
                else:
                    ln_has_more = False
            except RateLimitError as rle:
                logger.warning(f"ListenNotes rate limit for '{keyword}': {rle}")
                await asyncio.sleep(60)
            except APIClientError as apie:
                logger.error(f"ListenNotes API error for '{keyword}': {apie}")
                ln_has_more = False
            except Exception as e:
                logger.error(f"ListenNotes error for '{keyword}': {e}", exc_info=True)
                ln_has_more = False
        return upserted_media_ids_from_ln

    async def search_podscan(self, keyword: str, campaign_uuid: uuid.UUID, processed_ids_session: set) -> List[int]:
        upserted_media_ids_from_ps: List[int] = []
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
                )
                results = response.get('podcasts', []) if isinstance(response, dict) else []
                if results:
                    for item in results:
                        ps_api_id = str(item.get('podcast_id', '')).strip()
                        ps_rss = item.get('rss_url')
                        current_item_source_identifier = ps_rss or ps_api_id

                        if current_item_source_identifier and current_item_source_identifier in processed_ids_session:
                            logger.debug(f"PodscanFM: API item {current_item_source_identifier} already processed in this session for keyword '{keyword}'. Skipping.")
                            continue

                        existing_media_in_db = await self._get_existing_media_by_identifiers(item, "PodscanFM")
                        enriched = await self._enrich_podcast_data(item, "PodscanFM", existing_media_from_db=existing_media_in_db)
                        
                        media_id = await self.merge_and_upsert_media(enriched, "PodscanFM", campaign_uuid, keyword)
                        if media_id:
                            upserted_media_ids_from_ps.append(media_id)
                            await self.create_match_suggestions(media_id, campaign_uuid, keyword)
                            if current_item_source_identifier:
                                processed_ids_session.add(current_item_source_identifier)
                                
                    ps_has_more = len(results) >= PODSCAN_PAGE_SIZE
                    if ps_has_more:
                        ps_page += 1
                        await asyncio.sleep(API_CALL_DELAY)
                else:
                    ps_has_more = False
            except RateLimitError as rle:
                logger.warning(f"PodscanFM rate limit for '{keyword}': {rle}")
                await asyncio.sleep(60)
            except APIClientError as apie:
                logger.error(f"PodscanFM API error for '{keyword}': {apie}")
                ps_has_more = False
            except Exception as e:
                logger.error(f"PodscanFM error for '{keyword}': {e}", exc_info=True)
                ps_has_more = False
        return upserted_media_ids_from_ps

    async def fetch_podcasts_for_campaign(self, campaign_id_str: str) -> None: # This is called by DiscoveryService
        logger.info("Starting podcast fetch for campaign %s", campaign_id_str)
        try:
            campaign_uuid = uuid.UUID(campaign_id_str)
        except ValueError:
            logger.error("Invalid campaign ID: %s", campaign_id_str)
            return
        campaign = await campaign_queries.get_campaign_by_id(campaign_uuid)
        if not campaign:
            logger.error("Campaign %s not found", campaign_uuid)
            return
        keywords: List[str] = campaign.get('campaign_keywords', [])
        if not keywords:
            logger.warning("No keywords for campaign %s", campaign_uuid)
            return
        
        # This set tracks items processed across all keywords *for this specific campaign fetch run*.
        # This helps avoid reprocessing if the same podcast (by RSS/API ID) is found via different keywords
        # or from different sources during this single campaign discovery event.
        processed_ids_for_this_campaign_run: set = set()
        
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            logger.info(f"Fetching for campaign '{campaign_uuid}', keyword: '{kw}'")
            genre_ids = await self._generate_genre_ids_async(kw, campaign_id_str) # campaign_id_str is context for AI
            
            # search_listen_notes and search_podscan now return list of upserted media_ids
            # and use the passed set to avoid re-processing items *within their own pagination for that keyword and source*.
            # They also now use the smarter enrichment.
            await self.search_listen_notes(kw, genre_ids, campaign_uuid, processed_ids_for_this_campaign_run)
            await self.search_podscan(kw, campaign_uuid, processed_ids_for_this_campaign_run)
            
            logger.info("Finished keyword '%s' for campaign %s", kw, campaign_uuid)
            await asyncio.sleep(KEYWORD_PROCESSING_DELAY) # Delay between keywords
        logger.info("Batch podcast fetching COMPLETED for %s", campaign_uuid)

    async def admin_discover_and_process_podcasts(
        self,
        keyword: str,
        campaign_id_for_association: Optional[uuid.UUID] = None,
        max_results_per_source: int = 10 
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
                                if campaign_id_for_association: # Only create suggestion if admin specified a campaign
                                    await self.create_match_suggestions(media_id, campaign_id_for_association, keyword)
                        
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
                            if campaign_id_for_association:
                                await self.create_match_suggestions(media_id, campaign_id_for_association, keyword)
                    
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
