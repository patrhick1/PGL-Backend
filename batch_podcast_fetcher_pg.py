import logging
import os
import time
import asyncio
import argparse
import uuid
from typing import Optional, List, Dict, Any
import concurrent.futures
import html # For unescaping HTML entities in podcast names/descriptions
from datetime import datetime # For date parsing if needed
import functools # Added for functools.partial

# Project-specific services and modules
import db_service_pg # For PostgreSQL interactions
from src.openai_service import OpenAIService # For genre ID generation
from src.external_api_service import ListenNotesAPIClient, PodscanAPIClient, APIClientError, NotFoundError, RateLimitError # External podcast search APIs
from src.mipr_podcast import generate_genre_ids # For generating genre IDs based on keywords
from src.data_processor import parse_date # If needed for date fields from APIs

# --- Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Constants ---
LISTENNOTES_PAGE_SIZE = 10 # Default page_size for ListenNotes search in external_api_service
PODSCAN_PAGE_SIZE = 20 # Default per_page for Podscan search
API_CALL_DELAY = 1.2 # seconds to wait between paginated calls or between different API calls
KEYWORD_PROCESSING_DELAY = 2 # seconds to wait after processing all sources for a keyword

def _sanitize_numeric_string(value: Any, target_type: type = float) -> Optional[Any]:
    """Helper to clean strings like '10%' or 'N/A' into numbers, or return None."""
    if value is None: return None
    if isinstance(value, (int, float)):
        if target_type == int: return int(value) # Ensure int if target is int
        return value # Already numeric
    
    s_value = str(value).strip()
    if not s_value or s_value.lower() == 'n/a': return None
    
    s_value = s_value.replace('%', '')
    s_value = s_value.replace(',', '') 
    
    try:
        if target_type == float:
            return float(s_value)
        elif target_type == int:
            # Try converting to float first to handle cases like "10.0", then to int
            return int(float(s_value))
    except ValueError:
        logger.warning(f"Could not convert sanitized string '{s_value}' to {target_type}.")
        return None
    return None

class BatchPodcastFetcherPG:
    def __init__(self):
        self.openai_service = OpenAIService()
        self.listennotes_client = ListenNotesAPIClient()
        self.podscan_client = PodscanAPIClient()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
        logger.info("BatchPodcastFetcherPG services initialized.")

    async def _run_in_executor(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        func_with_args = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(self.executor, func_with_args)

    async def _generate_genre_ids_async(self, keyword: str, campaign_id_str: str) -> Optional[str]:
        try:
            logger.info(f"Generating ListenNotes genre IDs for keyword: '{keyword}' (Campaign: {campaign_id_str})")
            genre_ids_output = await self._run_in_executor(generate_genre_ids, self.openai_service, keyword, campaign_id_str)
            if isinstance(genre_ids_output, list):
                return ",".join(map(str, genre_ids_output))
            elif isinstance(genre_ids_output, str):
                return genre_ids_output
            logger.warning(f"Unexpected type from generate_genre_ids for '{keyword}': {type(genre_ids_output)}")
            return None
        except Exception as e:
            logger.error(f"Error generating genre IDs for '{keyword}': {e}", exc_info=True)
            return None

    def _extract_social_links(self, podscan_reach_socials: List[Dict[str, str]]) -> Dict[str, Optional[str]]:
        social_map = {}
        if not isinstance(podscan_reach_socials, list):
            return social_map
        for item in podscan_reach_socials:
            platform = item.get('platform')
            url = item.get('url')
            if platform and url:
                if platform == 'twitter': social_map['podcast_twitter_url'] = url
                elif platform == 'linkedin': social_map['podcast_linkedin_url'] = url
                elif platform == 'instagram': social_map['podcast_instagram_url'] = url
                elif platform == 'facebook': social_map['podcast_facebook_url'] = url
                elif platform == 'youtube': social_map['podcast_youtube_url'] = url
                elif platform == 'tiktok': social_map['podcast_tiktok_url'] = url
                else: 
                    if 'podcast_other_social_url' not in social_map: 
                        social_map['podcast_other_social_url'] = url
        return social_map

    async def _enrich_podcast_data(self, initial_data: Dict[str, Any], source_api: str) -> Dict[str, Any]:
        enriched_data = initial_data.copy() # Start with a copy of the original data
        enriched_data['source_api'] = source_api 
        # Standardize api_id from the source
        if source_api == "ListenNotes":
            enriched_data['api_id'] = str(initial_data.get('id', '')).strip()
            enriched_data['name'] = html.unescape(str(initial_data.get('title_original', ''))).strip()
            enriched_data['description'] = html.unescape(str(initial_data.get('description_original', ''))).strip() if initial_data.get('description_original') else None
            enriched_data['rss_url'] = initial_data.get('rss')
            enriched_data['itunes_id'] = str(initial_data.get('itunes_id', '')).strip() or None
            enriched_data['website'] = initial_data.get('website')
            enriched_data['image_url'] = initial_data.get('image')
            enriched_data['contact_email'] = initial_data.get('email')
            enriched_data['language'] = initial_data.get('language')
            enriched_data['total_episodes'] = initial_data.get('total_episodes')
            enriched_data['listen_score'] = _sanitize_numeric_string(initial_data.get('listen_score'), int)
            enriched_data['listen_score_global_rank'] = _sanitize_numeric_string(initial_data.get('listen_score_global_rank'), int)
            enriched_data['last_posted_at'] = parse_date(initial_data.get('latest_pub_date_ms'))
            if initial_data.get('genres') and isinstance(initial_data.get('genres'), list):
                enriched_data['category'] = initial_data.get('genres')[0]

        elif source_api == "PodscanFM":
            enriched_data['api_id'] = str(initial_data.get('podcast_id', '')).strip()
            enriched_data['name'] = html.unescape(str(initial_data.get('podcast_name', ''))).strip()
            enriched_data['description'] = html.unescape(str(initial_data.get('podcast_description', ''))).strip() if initial_data.get('podcast_description') else None
            enriched_data['rss_url'] = initial_data.get('rss_url')
            enriched_data['itunes_id'] = str(initial_data.get('podcast_itunes_id', '')).strip() or None
            enriched_data['website'] = initial_data.get('podcast_url')
            enriched_data['image_url'] = initial_data.get('podcast_image_url')
            ps_reach = initial_data.get('reach', {}) or {}
            enriched_data['contact_email'] = ps_reach.get('email')
            enriched_data['language'] = initial_data.get('language', 'English') # Podscan API results have 'language'
            enriched_data['total_episodes'] = _sanitize_numeric_string(initial_data.get('episode_count'), int)
            enriched_data['last_posted_at'] = parse_date(initial_data.get('last_posted_at'))
            enriched_data['podcast_spotify_id'] = initial_data.get('podcast_spotify_id')
            enriched_data['audience_size'] = _sanitize_numeric_string(ps_reach.get('audience_size'), int)
            if ps_reach.get('itunes'):
                enriched_data['itunes_rating_average'] = _sanitize_numeric_string(ps_reach.get('itunes',{}).get('itunes_rating_average'), float)
                enriched_data['itunes_rating_count'] = _sanitize_numeric_string(ps_reach.get('itunes',{}).get('itunes_rating_count'), int)
            if ps_reach.get('spotify'):
                enriched_data['spotify_rating_average'] = _sanitize_numeric_string(ps_reach.get('spotify',{}).get('spotify_rating_average'), float)
                enriched_data['spotify_rating_count'] = _sanitize_numeric_string(ps_reach.get('spotify',{}).get('spotify_rating_count'), int)
            social_links = self._extract_social_links(ps_reach.get('social_links', []))
            for k, v in social_links.items(): enriched_data[k] = v # Direct assignment for social links
            if initial_data.get('podcast_categories') and isinstance(initial_data.get('podcast_categories'), list):
                enriched_data['category'] = initial_data.get('podcast_categories')[0].get('category_name') # Podscan category structure

        # Now, attempt cross-enrichment
        current_rss_url = enriched_data.get('rss_url')
        current_itunes_id_for_lookup = _sanitize_numeric_string(enriched_data.get('itunes_id'), int)
        
        try:
            if source_api == "ListenNotes": # Try to enrich with Podscan
                podscan_match = None
                if current_itunes_id_for_lookup:
                    logger.debug(f"Enriching LN '{enriched_data.get('name')}' with Podscan via iTunes: {current_itunes_id_for_lookup}")
                    await asyncio.sleep(API_CALL_DELAY / 2.0)
                    podscan_match = await self._run_in_executor(self.podscan_client.search_podcast_by_itunes_id, current_itunes_id_for_lookup)
                if not podscan_match and current_rss_url:
                    logger.debug(f"Enriching LN '{enriched_data.get('name')}' with Podscan via RSS: {current_rss_url}")
                    await asyncio.sleep(API_CALL_DELAY / 2.0)
                    podscan_match = await self._run_in_executor(self.podscan_client.search_podcast_by_rss, current_rss_url)
                
                if podscan_match:
                    logger.info(f"Podscan data found for LN item '{enriched_data.get('name')}'. Merging.")
                    enriched_data.setdefault('website', podscan_match.get('podcast_url'))
                    enriched_data.setdefault('podcast_spotify_id', podscan_match.get('podcast_spotify_id'))
                    ps_reach = podscan_match.get('reach', {}) or {}
                    enriched_data.setdefault('audience_size', _sanitize_numeric_string(ps_reach.get('audience_size'), int))
                    if ps_reach.get('email'): enriched_data['contact_email'] = ps_reach.get('email') # Podscan email can be more direct
                    if ps_reach.get('itunes'):
                        enriched_data.setdefault('itunes_rating_average', _sanitize_numeric_string(ps_reach.get('itunes',{}).get('itunes_rating_average'), float))
                        enriched_data.setdefault('itunes_rating_count', _sanitize_numeric_string(ps_reach.get('itunes',{}).get('itunes_rating_count'), int))
                    if ps_reach.get('spotify'):
                        enriched_data.setdefault('spotify_rating_average', _sanitize_numeric_string(ps_reach.get('spotify',{}).get('spotify_rating_average'), float))
                        enriched_data.setdefault('spotify_rating_count', _sanitize_numeric_string(ps_reach.get('spotify',{}).get('spotify_rating_count'), int))
                    social_links = self._extract_social_links(ps_reach.get('social_links', []))
                    for k, v_ps in social_links.items(): enriched_data.setdefault(k, v_ps)
                    ps_last_posted = parse_date(podscan_match.get('last_posted_at'))
                    if ps_last_posted: enriched_data['last_posted_at'] = ps_last_posted
                    enriched_data.setdefault('image_url', podscan_match.get('podcast_image_url') or enriched_data.get('image_url'))
                    ps_itunes_id_str = str(podscan_match.get('podcast_itunes_id','')).strip()
                    if ps_itunes_id_str: enriched_data['itunes_id'] = ps_itunes_id_str
                    ps_desc = podscan_match.get('podcast_description')
                    if ps_desc and isinstance(ps_desc, str) and ps_desc.strip(): # Prefer Podscan description if available
                        enriched_data['description'] = html.unescape(ps_desc)
            
            elif source_api == "PodscanFM": # Try to enrich with ListenNotes
                listennotes_match = None
                if current_itunes_id_for_lookup:
                    logger.debug(f"Enriching Podscan '{enriched_data.get('name')}' with ListenNotes via iTunes: {current_itunes_id_for_lookup}")
                    await asyncio.sleep(API_CALL_DELAY / 2.0)
                    listennotes_match = await self._run_in_executor(self.listennotes_client.lookup_podcast_by_itunes_id, current_itunes_id_for_lookup)
                if not listennotes_match and current_rss_url:
                    logger.debug(f"Enriching Podscan '{enriched_data.get('name')}' with ListenNotes via RSS: {current_rss_url}")
                    await asyncio.sleep(API_CALL_DELAY / 2.0)
                    listennotes_match = await self._run_in_executor(self.listennotes_client.lookup_podcast_by_rss, current_rss_url)

                if listennotes_match:
                    logger.info(f"ListenNotes data found for Podscan item '{enriched_data.get('name')}'. Merging.")
                    enriched_data.setdefault('listen_score', _sanitize_numeric_string(listennotes_match.get('listen_score'), int))
                    enriched_data.setdefault('listen_score_global_rank', _sanitize_numeric_string(listennotes_match.get('listen_score_global_rank'), int))
                    ln_desc = listennotes_match.get('description_original')
                    if ln_desc and isinstance(ln_desc, str) and ln_desc.strip(): # Prefer ListenNotes description
                        enriched_data['description'] = html.unescape(ln_desc)
                    enriched_data.setdefault('language', listennotes_match.get('language') or enriched_data.get('language'))
                    enriched_data.setdefault('total_episodes', listennotes_match.get('total_episodes'))
                    enriched_data.setdefault('image_url', listennotes_match.get('image') or enriched_data.get('image_url'))
                    if enriched_data.get('category') is None and listennotes_match.get('genres') and isinstance(listennotes_match.get('genres'), list) and listennotes_match.get('genres'):
                        enriched_data['category'] = listennotes_match.get('genres')[0]
                    if listennotes_match.get('email'): enriched_data['contact_email'] = listennotes_match.get('email') # Prefer LN email
                    ln_last_posted_ms = listennotes_match.get('latest_pub_date_ms')
                    if ln_last_posted_ms: enriched_data['last_posted_at'] = parse_date(ln_last_posted_ms)
                    ln_itunes_id_str = str(listennotes_match.get('itunes_id','')).strip()
                    if ln_itunes_id_str: enriched_data['itunes_id'] = ln_itunes_id_str 
                    enriched_data.setdefault('website', listennotes_match.get('website') or enriched_data.get('website'))
        except Exception as e:
            logger.warning(f"Error during cross-API enrichment for '{enriched_data.get('name')}': {e}", exc_info=True)
        return enriched_data

    async def _map_and_upsert_media(self, enriched_podcast_data: Dict[str, Any], primary_source_api: str, campaign_uuid: uuid.UUID, keyword: str):
        contact_email = enriched_podcast_data.get('contact_email')
        if not contact_email:
            logger.debug(f"Final check: '{enriched_podcast_data.get('name')}' skipped, no contact_email after enrichment.")
            return

        name_val = str(enriched_podcast_data.get('name', '')).strip()
        if not name_val: # Name is critical
            logger.warning(f"Skipping upsert, media name is empty after enrichment for source {primary_source_api}.")
            return
        
        description_text = enriched_podcast_data.get('description')
        final_description = html.unescape(str(description_text)) if description_text and isinstance(description_text, str) else ''

        media_payload = {
            "name": name_val,
            "title": html.unescape(str(enriched_podcast_data.get('title', name_val) or '')).strip(),
            "rss_url": enriched_podcast_data.get('rss_url'),
            "rss_feed_url": enriched_podcast_data.get('rss_feed_url') or enriched_podcast_data.get('rss_url'), 
            "website": enriched_podcast_data.get('website'),
            "description": final_description,
            "contact_email": contact_email,
            "language": enriched_podcast_data.get('language'),
            "category": enriched_podcast_data.get('category'), 
            "avg_downloads": None, 
            "image_url": enriched_podcast_data.get('image_url'),
            "source_api": enriched_podcast_data.get('source_api'), # Set during enrichment
            "api_id": enriched_podcast_data.get('api_id'), # Set during enrichment
            "itunes_id": enriched_podcast_data.get('itunes_id'), # Should be string or None from enrichment
            "podcast_spotify_id": enriched_podcast_data.get('podcast_spotify_id'),
            "total_episodes": _sanitize_numeric_string(enriched_podcast_data.get('total_episodes'), int),
            "last_posted_at": enriched_podcast_data.get('last_posted_at'), 
            "listen_score": _sanitize_numeric_string(enriched_podcast_data.get('listen_score'), int),
            "listen_score_global_rank": _sanitize_numeric_string(enriched_podcast_data.get('listen_score_global_rank'), int),
            "audience_size": _sanitize_numeric_string(enriched_podcast_data.get('audience_size'), int),
            "itunes_rating_average": _sanitize_numeric_string(enriched_podcast_data.get('itunes_rating_average'), float),
            "itunes_rating_count": _sanitize_numeric_string(enriched_podcast_data.get('itunes_rating_count'), int),
            "spotify_rating_average": _sanitize_numeric_string(enriched_podcast_data.get('spotify_rating_average'), float),
            "spotify_rating_count": _sanitize_numeric_string(enriched_podcast_data.get('spotify_rating_count'), int),
            "podcast_twitter_url": enriched_podcast_data.get('podcast_twitter_url'),
            "podcast_linkedin_url": enriched_podcast_data.get('podcast_linkedin_url'),
            "podcast_instagram_url": enriched_podcast_data.get('podcast_instagram_url'),
            "podcast_facebook_url": enriched_podcast_data.get('podcast_facebook_url'),
            "podcast_youtube_url": enriched_podcast_data.get('podcast_youtube_url'),
            "podcast_tiktok_url": enriched_podcast_data.get('podcast_tiktok_url'),
            "podcast_other_social_url": enriched_podcast_data.get('podcast_other_social_url'),
            "fetched_episodes": enriched_podcast_data.get('fetched_episodes', False)
        }
        media_payload_cleaned = {}
        for k, v in media_payload.items():
            if isinstance(v, str):
                stripped_v = v.strip()
                if stripped_v: media_payload_cleaned[k] = stripped_v
            elif v is not None:
                media_payload_cleaned[k] = v
        
        if not media_payload_cleaned.get("name"): 
            logger.warning(f"Skipping upsert, media name became empty after cleaning for source {primary_source_api}.")
            return
        if not media_payload_cleaned.get("rss_url") and not media_payload_cleaned.get("website"):
             logger.warning(f"Skipping upsert for {media_payload_cleaned.get('name')}, both RSS and Website are missing.")
             return

        try:
            retrieved_media = await db_service_pg.upsert_media_in_db(media_payload_cleaned)
            if retrieved_media and retrieved_media.get('media_id'):
                match_suggestion_data = {
                    'campaign_id': campaign_uuid,
                    'media_id': retrieved_media['media_id'],
                    'matched_keywords': [keyword],
                    'match_score': 1.0, 'status': 'pending',
                    'ai_reasoning': f'Found via {primary_source_api} keyword: {keyword}.'
                }
                await db_service_pg.create_match_suggestion_in_db(match_suggestion_data)
                logger.info(f"DB: Processed match for media ID {retrieved_media['media_id']} ({primary_source_api}, kw '{keyword}').")
            else:
                logger.warning(f"DB: Upsert failed for {primary_source_api} result: {media_payload_cleaned.get('name')}")
        except Exception as e:
            logger.error(f"DB: Error during upsert/match for {primary_source_api} ({media_payload_cleaned.get('name')}): {e}", exc_info=True)
    
    async def fetch_podcasts_for_campaign(self, campaign_id_str: str):
        logger.info(f"Starting podcast fetch for PG Campaign ID: {campaign_id_str}")
        try: campaign_uuid = uuid.UUID(campaign_id_str)
        except ValueError: logger.error(f"Invalid Campaign ID: {campaign_id_str}"); return

        campaign_pg = await db_service_pg.get_campaign_by_id(campaign_uuid)
        if not campaign_pg: logger.error(f"Campaign {campaign_uuid} not found."); return

        campaign_name = campaign_pg.get("campaign_name", f"Campaign_{campaign_id_str}")
        campaign_keywords: List[str] = campaign_pg.get("campaign_keywords", [])

        if not campaign_keywords: logger.warning(f"No keywords for '{campaign_name}'. Skipping."); return
        logger.info(f"Processing '{campaign_name}' with keywords: {campaign_keywords}")

        processed_podcast_identifiers = set() 

        for keyword in campaign_keywords:
            keyword = keyword.strip()
            if not keyword: continue
            logger.info(f"--- Keyword: '{keyword}' for '{campaign_name}' ---")

            # --- ListenNotes Search ---
            listennotes_genre_ids_str = await self._generate_genre_ids_async(keyword, campaign_id_str)
            if listennotes_genre_ids_str:
                logger.info(f"ListenNotes: Using genres '{listennotes_genre_ids_str}' for '{keyword}'")
                ln_offset = 0
                ln_has_more = True
                while ln_has_more:
                    unique_id_key_ln = None
                    try:
                        logger.info(f"ListenNotes: Searching '{keyword}', offset {ln_offset}")
                        ln_response = await self._run_in_executor(
                            self.listennotes_client.search_podcasts, 
                            keyword, genre_ids=listennotes_genre_ids_str, offset=ln_offset, page_size=LISTENNOTES_PAGE_SIZE
                        )
                        ln_results = ln_response.get('results', []) if isinstance(ln_response, dict) else []
                        if ln_results:
                            for ln_result in ln_results:
                                unique_id_key_ln = ln_result.get('rss') or ln_result.get('id') 
                                if unique_id_key_ln and unique_id_key_ln in processed_podcast_identifiers:
                                    logger.debug(f"Skipping already processed ListenNotes item: {unique_id_key_ln}")
                                    continue
                                
                                enriched_data = await self._enrich_podcast_data(ln_result, "ListenNotes")
                                await self._map_and_upsert_media(enriched_data, "ListenNotes", campaign_uuid, keyword)
                                if unique_id_key_ln: processed_podcast_identifiers.add(unique_id_key_ln)
                            
                            ln_has_more = ln_response.get('has_next', False) if isinstance(ln_response, dict) else False
                            ln_offset = ln_response.get('next_offset', ln_offset + LISTENNOTES_PAGE_SIZE) if ln_has_more and isinstance(ln_response, dict) else ln_offset
                            if ln_has_more: await asyncio.sleep(API_CALL_DELAY)
                        else: 
                            ln_has_more = False
                            logger.info(f"ListenNotes: No more results for '{keyword}' at offset {ln_offset}.")
                    except RateLimitError as rle: logger.warning(f"ListenNotes RL for '{keyword}': {rle}. Sleeping 60s."); await asyncio.sleep(60)
                    except APIClientError as apie: logger.error(f"ListenNotes API Client Error for '{keyword}': {apie}"); ln_has_more = False 
                    except Exception as e: logger.error(f"ListenNotes General Error for '{keyword}': {e}", exc_info=True); ln_has_more = False 
            else: logger.warning(f"ListenNotes: No genres for '{keyword}', skipping LN search.")

            # --- PodscanFM Search ---
            ps_page = 1
            ps_has_more = True 
            while ps_has_more:
                unique_id_key_ps = None
                try:
                    logger.info(f"PodscanFM: Searching '{keyword}', page {ps_page}")
                    ps_response = await self._run_in_executor(self.podscan_client.search_podcasts, keyword, page=ps_page, per_page=PODSCAN_PAGE_SIZE)
                    actual_ps_results = ps_response.get('podcasts', []) if isinstance(ps_response, dict) else []

                    if actual_ps_results:
                        for ps_result in actual_ps_results:
                            unique_id_key_ps = ps_result.get('rss_url') or ps_result.get('podcast_id')
                            if unique_id_key_ps and unique_id_key_ps in processed_podcast_identifiers:
                                logger.debug(f"Skipping already processed Podscan item: {unique_id_key_ps}")
                                continue

                            enriched_data = await self._enrich_podcast_data(ps_result, "PodscanFM")
                            await self._map_and_upsert_media(enriched_data, "PodscanFM", campaign_uuid, keyword)
                            if unique_id_key_ps: processed_podcast_identifiers.add(unique_id_key_ps)
                        
                        if len(actual_ps_results) < PODSCAN_PAGE_SIZE: ps_has_more = False 
                        else: ps_page += 1; await asyncio.sleep(API_CALL_DELAY)
                    else: 
                        ps_has_more = False
                        logger.info(f"PodscanFM: No results for '{keyword}' on page {ps_page}.")
                except RateLimitError as rle: logger.warning(f"PodscanFM RL for '{keyword}': {rle}. Sleeping 60s."); await asyncio.sleep(60)
                except APIClientError as apie: logger.error(f"PodscanFM API Client Error for '{keyword}': {apie}"); ps_has_more = False
                except Exception as e: logger.error(f"PodscanFM General Error for '{keyword}': {e}", exc_info=True); ps_has_more = False
            
            logger.info(f"Finished '{keyword}'. Delaying...")
            await asyncio.sleep(KEYWORD_PROCESSING_DELAY)

        logger.info(f"--- Batch podcast fetching COMPLETED for '{campaign_name}' (ID: {campaign_id_str}) ---")

    def cleanup(self):
        if self.executor: self.executor.shutdown(wait=True); logger.info("BatchPodcastFetcherPG executor shut down.")

async def main():
    parser = argparse.ArgumentParser(description="Fetch & store podcasts for a campaign.")
    parser.add_argument("campaign_id", help="PostgreSQL Campaign UUID.")
    args = parser.parse_args()
    await db_service_pg.init_db_pool()
    fetcher = BatchPodcastFetcherPG()
    try: await fetcher.fetch_podcasts_for_campaign(args.campaign_id)
    finally:
        fetcher.cleanup()
        await db_service_pg.close_db_pool()
        logger.info(f"Script finished for Campaign ID: {args.campaign_id}")

if __name__ == "__main__":
    asyncio.run(main()) 