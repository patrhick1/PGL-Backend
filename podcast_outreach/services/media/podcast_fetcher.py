# podcast_outreach/services/media/podcast_fetcher.py

import asyncio
import argparse
import uuid
from typing import Optional, List, Dict, Any
import concurrent.futures
import html
import functools
import logging
 
# Import modular queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import review_tasks as review_tasks_queries
from podcast_outreach.database.connection import get_db_pool, close_db_pool # For main function

from src.openai_service import OpenAIService # Still from src, needs to be moved
from podcast_outreach.integrations.listen_notes import ListenNotesAPIClient
from podcast_outreach.integrations.podscan import PodscanAPIClient
from podcast_outreach.utils.exceptions import APIClientError, RateLimitError
from src.mipr_podcast import generate_genre_ids # Still from src, needs to be moved
from src.data_processor import parse_date # Still from src, needs to be moved
 
# --- Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger(__name__)
 
# --- Constants ---
LISTENNOTES_PAGE_SIZE = 10
PODSCAN_PAGE_SIZE = 20
API_CALL_DELAY = 1.2
KEYWORD_PROCESSING_DELAY = 2
 
 
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
 
    async def _enrich_podcast_data(self, initial_data: Dict[str, Any], source_api: str) -> Dict[str, Any]:
        enriched = initial_data.copy()
        enriched['source_api'] = source_api
        if source_api == "ListenNotes":
            enriched['api_id'] = str(initial_data.get('id', '')).strip()
            enriched['name'] = html.unescape(str(initial_data.get('title_original', ''))).strip()
            enriched['description'] = html.unescape(str(initial_data.get('description_original', ''))).strip() or None
            enriched['rss_url'] = initial_data.get('rss')
            enriched['itunes_id'] = str(initial_data.get('itunes_id', '')).strip() or None
            enriched['website'] = initial_data.get('website')
            enriched['image_url'] = initial_data.get('image')
            enriched['contact_email'] = initial_data.get('email')
            enriched['language'] = initial_data.get('language')
            enriched['total_episodes'] = initial_data.get('total_episodes')
            enriched['listen_score'] = _sanitize_numeric_string(initial_data.get('listen_score'), int)
            enriched['listen_score_global_rank'] = _sanitize_numeric_string(initial_data.get('listen_score_global_rank'), int)
            enriched['last_posted_at'] = parse_date(initial_data.get('latest_pub_date_ms'))
            if isinstance(initial_data.get('genres'), list) and initial_data['genres']:
                enriched['category'] = initial_data['genres'][0]
        else:  # PodscanFM
            enriched['api_id'] = str(initial_data.get('podcast_id', '')).strip()
            enriched['name'] = html.unescape(str(initial_data.get('podcast_name', ''))).strip()
            enriched['description'] = html.unescape(str(initial_data.get('podcast_description', ''))).strip() or None
            enriched['rss_url'] = initial_data.get('rss_url')
            enriched['itunes_id'] = str(initial_data.get('podcast_itunes_id', '')).strip() or None
            enriched['website'] = initial_data.get('podcast_url')
            enriched['image_url'] = initial_data.get('podcast_image_url')
            reach = initial_data.get('reach') or {}
            enriched['contact_email'] = reach.get('email')
            enriched['language'] = initial_data.get('language', 'English')
            enriched['total_episodes'] = _sanitize_numeric_string(initial_data.get('episode_count'), int)
            enriched['last_posted_at'] = parse_date(initial_data.get('last_posted_at'))
            enriched['podcast_spotify_id'] = initial_data.get('podcast_spotify_id')
            enriched['audience_size'] = _sanitize_numeric_string(reach.get('audience_size'), int)
            if reach.get('itunes'):
                enriched['itunes_rating_average'] = _sanitize_numeric_string(reach['itunes'].get('itunes_rating_average'), float)
                enriched['itunes_rating_count'] = _sanitize_numeric_string(reach['itunes'].get('itunes_rating_count'), int)
            if reach.get('spotify'):
                enriched['spotify_rating_average'] = _sanitize_numeric_string(reach['spotify'].get('spotify_rating_average'), float)
                enriched['spotify_rating_count'] = _sanitize_numeric_string(reach['spotify'].get('spotify_rating_count'), int)
            for k, v in self._extract_social_links(reach.get('social_links', [])).items():
                enriched[k] = v
            if initial_data.get('podcast_categories'):
                enriched['category'] = initial_data['podcast_categories'][0].get('category_name')
 
        # cross enrich using opposite API
        rss = enriched.get('rss_url')
        itunes_id = _sanitize_numeric_string(enriched.get('itunes_id'), int)
        try:
            if source_api == "ListenNotes":
                match = None
                if itunes_id:
                    await asyncio.sleep(API_CALL_DELAY/2)
                    match = await self._run_in_executor(self.podscan_client.search_podcast_by_itunes_id, itunes_id)
                if not match and rss:
                    await asyncio.sleep(API_CALL_DELAY/2)
                    match = await self._run_in_executor(self.podscan_client.search_podcast_by_rss, rss)
                if match:
                    enriched.setdefault('website', match.get('podcast_url'))
                    enriched.setdefault('podcast_spotify_id', match.get('podcast_spotify_id'))
                    reach = match.get('reach') or {}
                    enriched.setdefault('audience_size', _sanitize_numeric_string(reach.get('audience_size'), int))
                    if reach.get('email'):
                        enriched['contact_email'] = reach.get('email')
                    for k, v in self._extract_social_links(reach.get('social_links', [])).items():
                        enriched.setdefault(k, v)
                    if parse_date(match.get('last_posted_at')):
                        enriched['last_posted_at'] = parse_date(match.get('last_posted_at'))
                    enriched.setdefault('image_url', match.get('podcast_image_url') or enriched.get('image_url'))
                    if match.get('podcast_itunes_id'):
                        enriched['itunes_id'] = str(match.get('podcast_itunes_id')).strip()
                    if match.get('podcast_description'):
                        enriched['description'] = html.unescape(match['podcast_description'])
            else:  # PodscanFM -> enrich with ListenNotes
                match = None
                if itunes_id:
                    await asyncio.sleep(API_CALL_DELAY/2)
                    match = await self._run_in_executor(self.listennotes_client.lookup_podcast_by_itunes_id, itunes_id)
                if not match and rss:
                    await asyncio.sleep(API_CALL_DELAY/2)
                    match = await self._run_in_executor(self.listennotes_client.lookup_podcast_by_rss, rss)
                if match:
                    enriched.setdefault('listen_score', _sanitize_numeric_string(match.get('listen_score'), int))
                    enriched.setdefault('listen_score_global_rank', _sanitize_numeric_string(match.get('listen_score_global_rank'), int))
                    if match.get('description_original'):
                        enriched['description'] = html.unescape(match['description_original'])
                    enriched.setdefault('language', match.get('language') or enriched.get('language'))
                    enriched.setdefault('total_episodes', match.get('total_episodes'))
                    enriched.setdefault('image_url', match.get('image') or enriched.get('image_url'))
                    if match.get('genres'):
                        enriched.setdefault('category', match['genres'][0])
                    if match.get('email'):
                        enriched['contact_email'] = match.get('email')
                    if match.get('latest_pub_date_ms'):
                        enriched['last_posted_at'] = parse_date(match.get('latest_pub_date_ms'))
                    if match.get('itunes_id'):
                        enriched['itunes_id'] = str(match.get('itunes_id')).strip()
                    enriched.setdefault('website', match.get('website') or enriched.get('website'))
        except APIClientError as e:  # pragma: no cover - network errors
            logger.warning("API client error during enrichment for %s: %s", enriched.get('name'), e)
        except Exception as e:  # pragma: no cover - network errors
            logger.warning("Unexpected error during enrichment for %s: %s", enriched.get('name'), e, exc_info=True)
        return enriched
 
    async def merge_and_upsert_media(self, podcast_data: Dict[str, Any], source_api: str,
                                     campaign_uuid: uuid.UUID, keyword: str) -> Optional[int]:
        contact_email = podcast_data.get('contact_email')
        if not contact_email:
            logger.debug("Skipping %s, no contact email", podcast_data.get('name'))
            return None
        name_val = str(podcast_data.get('name', '')).strip()
        if not name_val:
            logger.warning("Skipping upsert, media name is empty from %s", source_api)
            return None
        description_text = podcast_data.get('description')
        final_description = html.unescape(str(description_text)) if isinstance(description_text, str) else ''
        payload = {
            'name': name_val,
            'title': html.unescape(str(podcast_data.get('title', name_val) or '')).strip(),
            'rss_url': podcast_data.get('rss_url'),
            'rss_feed_url': podcast_data.get('rss_feed_url') or podcast_data.get('rss_url'),
            'website': podcast_data.get('website'),
            'description': final_description,
            'contact_email': contact_email,
            'language': podcast_data.get('language'),
            'category': podcast_data.get('category'),
            'avg_downloads': None,
            'image_url': podcast_data.get('image_url'),
            'source_api': source_api,
            'api_id': podcast_data.get('api_id'),
            'itunes_id': podcast_data.get('itunes_id'),
            'podcast_spotify_id': podcast_data.get('podcast_spotify_id'),
            'total_episodes': _sanitize_numeric_string(podcast_data.get('total_episodes'), int),
            'last_posted_at': podcast_data.get('last_posted_at'),
            'listen_score': _sanitize_numeric_string(podcast_data.get('listen_score'), int),
            'listen_score_global_rank': _sanitize_numeric_string(podcast_data.get('listen_score_global_rank'), int),
            'audience_size': _sanitize_numeric_string(podcast_data.get('audience_size'), int),
            'itunes_rating_average': _sanitize_numeric_string(podcast_data.get('itunes_rating_average'), float),
            'itunes_rating_count': _sanitize_numeric_string(podcast_data.get('itunes_rating_count'), int),
            'spotify_rating_average': _sanitize_numeric_string(podcast_data.get('spotify_rating_average'), float),
            'spotify_rating_count': _sanitize_numeric_string(podcast_data.get('spotify_rating_count'), int),
            'podcast_twitter_url': podcast_data.get('podcast_twitter_url'),
            'podcast_linkedin_url': podcast_data.get('podcast_linkedin_url'),
            'podcast_instagram_url': podcast_data.get('podcast_instagram_url'),
            'podcast_facebook_url': podcast_data.get('podcast_facebook_url'),
            'podcast_youtube_url': podcast_data.get('podcast_youtube_url'),
            'podcast_tiktok_url': podcast_data.get('podcast_tiktok_url'),
            'podcast_other_social_url': podcast_data.get('podcast_other_social_url'),
            'fetched_episodes': podcast_data.get('fetched_episodes', False),
        }
        cleaned = {k: v.strip() if isinstance(v, str) else v for k, v in payload.items() if v is not None and (not isinstance(v, str) or v.strip())}
        if not cleaned.get('rss_url') and not cleaned.get('website'):
            logger.warning("Skipping upsert for %s, both RSS and website missing", cleaned.get('name'))
            return None
        try:
            media = await media_queries.upsert_media_in_db(cleaned) # Use modular query
            if media and media.get('media_id'):
                return media['media_id']
        except Exception as e:  # pragma: no cover - DB errors
            logger.error("DB error during upsert for %s: %s", cleaned.get('name'), e, exc_info=True)
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
 
    async def search_listen_notes(self, keyword: str, genre_ids: Optional[str], campaign_uuid: uuid.UUID, processed_ids: set) -> None:
        if not genre_ids:
            logger.warning("ListenNotes: No genres for '%s', skipping", keyword)
            return
        ln_offset = 0
        ln_has_more = True
        while ln_has_more:
            try:
                logger.info("ListenNotes: Searching '%s' offset %s", keyword, ln_offset)
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
                        unique_id = item.get('rss') or item.get('id')
                        if unique_id and unique_id in processed_ids:
                            continue
                        enriched = await self._enrich_podcast_data(item, "ListenNotes")
                        media_id = await self.merge_and_upsert_media(enriched, "ListenNotes", campaign_uuid, keyword)
                        if media_id:
                            await self.create_match_suggestions(media_id, campaign_uuid, keyword)
                            if unique_id:
                                processed_ids.add(unique_id)
                    ln_has_more = response.get('has_next', False)
                    ln_offset = response.get('next_offset', ln_offset + LISTENNOTES_PAGE_SIZE) if ln_has_more else ln_offset
                    if ln_has_more:
                        await asyncio.sleep(API_CALL_DELAY)
                else:
                    ln_has_more = False
            except RateLimitError as rle:
                logger.warning("ListenNotes rate limit for '%s': %s", keyword, rle)
                await asyncio.sleep(60)
            except APIClientError as apie:
                logger.error("ListenNotes API error for '%s': %s", keyword, apie)
                ln_has_more = False
            except Exception as e:
                logger.error("ListenNotes error for '%s': %s", keyword, e, exc_info=True)
                ln_has_more = False
 
    async def search_podscan(self, keyword: str, campaign_uuid: uuid.UUID, processed_ids: set) -> None:
        ps_page = 1
        ps_has_more = True
        while ps_has_more:
            try:
                logger.info("PodscanFM: Searching '%s' page %s", keyword, ps_page)
                response = await self._run_in_executor(
                    self.podscan_client.search_podcasts,
                    keyword,
                    page=ps_page,
                    per_page=PODSCAN_PAGE_SIZE,
                )
                results = response.get('podcasts', []) if isinstance(response, dict) else []
                if results:
                    for item in results:
                        unique_id = item.get('rss_url') or item.get('podcast_id')
                        if unique_id and unique_id in processed_ids:
                            continue
                        enriched = await self._enrich_podcast_data(item, "PodscanFM")
                        media_id = await self.merge_and_upsert_media(enriched, "PodscanFM", campaign_uuid, keyword)
                        if media_id:
                            await self.create_match_suggestions(media_id, campaign_uuid, keyword)
                            if unique_id:
                                processed_ids.add(unique_id)
                    ps_has_more = len(results) >= PODSCAN_PAGE_SIZE
                    if ps_has_more:
                        ps_page += 1
                        await asyncio.sleep(API_CALL_DELAY)
                else:
                    ps_has_more = False
            except RateLimitError as rle:
                logger.warning("PodscanFM rate limit for '%s': %s", keyword, rle)
                await asyncio.sleep(60)
            except APIClientError as apie:
                logger.error("PodscanFM API error for '%s': %s", keyword, apie)
                ps_has_more = False
            except Exception as e:
                logger.error("PodscanFM error for '%s': %s", keyword, e, exc_info=True)
                ps_has_more = False
 
    async def fetch_podcasts_for_campaign(self, campaign_id_str: str) -> None:
        logger.info("Starting podcast fetch for campaign %s", campaign_id_str)
        try:
            campaign_uuid = uuid.UUID(campaign_id_str)
        except ValueError:
            logger.error("Invalid campaign ID: %s", campaign_id_str)
            return
        campaign = await campaign_queries.get_campaign_by_id(campaign_uuid) # Use modular query
        if not campaign:
            logger.error("Campaign %s not found", campaign_uuid)
            return
        keywords: List[str] = campaign.get('campaign_keywords', [])
        if not keywords:
            logger.warning("No keywords for campaign %s", campaign_uuid)
            return
        processed: set = set()
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            genre_ids = await self._generate_genre_ids_async(kw, campaign_id_str)
            await self.search_listen_notes(kw, genre_ids, campaign_uuid, processed)
            await self.search_podscan(kw, campaign_uuid, processed)
            logger.info("Finished keyword '%s'", kw)
            await asyncio.sleep(KEYWORD_PROCESSING_DELAY)
        logger.info("Batch podcast fetching COMPLETED for %s", campaign_uuid)
 
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
