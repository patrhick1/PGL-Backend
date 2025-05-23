import logging
import asyncio
from typing import Any, Dict, List, Optional, Set
from datetime import datetime
 
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.connection import get_db_pool, close_db_pool # Import for main_episode_sync_orchestrator

import aiohttp
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime
from datetime import timezone
 
from src.external_api_service import PodscanAPIClient, APIClientError
from src.data_processor import parse_date as fallback_parse_date
 
logger = logging.getLogger(__name__)
 
RSS_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0",
}
HTTP_REQUEST_TIMEOUT = 20
 
class MediaFetcher:
    """Service for podcast discovery and episode syncing."""
 
    def __init__(self) -> None:
        self.podscan_client = None
        try:
            self.podscan_client = PodscanAPIClient()
        except Exception as e:  # pragma: no cover - env issues
            logger.warning("Podscan client could not be initialized: %s", e)
 
    async def search_listen_notes(self, campaign_id: str) -> List[Dict[str, Any]]:
        logger.info("Searching ListenNotes for campaign %s", campaign_id)
        return []  # Placeholder
 
    async def search_podscan(self, campaign_id: str) -> List[Dict[str, Any]]:
        logger.info("Searching Podscan for campaign %s", campaign_id)
        return []  # Placeholder
 
    async def merge_and_upsert_media(
        self, listen_results: List[Dict[str, Any]], podscan_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        merged = listen_results + podscan_results
        stored = []
        for item in merged:
            media = await media_queries.upsert_media_in_db(item)
            if media:
                stored.append(media)
        return stored
 
    async def create_match_suggestions(
        self, campaign_id: str, media_records: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        suggestions = []
        for media in media_records:
            suggestion = await match_queries.create_match_suggestion_in_db({"campaign_id": campaign_id, "media_id": media["media_id"]})
            if suggestion:
                suggestions.append(suggestion)
        return suggestions
 
    def _parse_rss_date(self, date_string: Optional[str]) -> Optional[datetime]:
        if not date_string:
            return None
        try:
            dt = parsedate_to_datetime(date_string)
            if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            try:
                dt = fallback_parse_date(date_string)
                if dt:
                    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                        return dt.replace(tzinfo=timezone.utc)
                    return dt.astimezone(timezone.utc)
            except Exception as e:  # pragma: no cover - parsing errors
                logger.debug("Fallback date parsing failed for %s: %s", date_string, e)
        return None
 
    async def _fetch_episodes_from_rss(self, rss_url: str, session: aiohttp.ClientSession, limit: int = 20) -> List[Dict[str, Any]]:
        raw: List[Dict[str, Any]] = []
        try:
            async with session.get(rss_url, headers=RSS_FETCH_HEADERS, timeout=HTTP_REQUEST_TIMEOUT) as response:
                response.raise_for_status()
                text = await response.text()
            loop = asyncio.get_running_loop()
            soup = await loop.run_in_executor(None, BeautifulSoup, text, 'xml')
            items = soup.find_all('item')
            for item in items[: limit * 2]:
                pub = self._parse_rss_date(item.findtext('pubDate'))
                if not pub:
                    continue
                audio_url = None
                enclosure = item.find('enclosure')
                if enclosure and enclosure.get('url'):
                    audio_url = enclosure['url']
                elif item.find('guid') and item.findtext('guid', '').startswith(('http://', 'https://')):
                    guid_text = item.findtext('guid')
                    if any(guid_text.lower().endswith(ext) for ext in ['.mp3', '.m4a', '.ogg', '.wav', '.aac']):
                        audio_url = guid_text
                if not audio_url:
                    continue
                desc = item.findtext('description') or item.findtext('content:encoded') or item.findtext('itunes:summary')
                if desc:
                    d_soup = BeautifulSoup(desc, 'html.parser')
                    desc = d_soup.get_text(separator='\n', strip=True)
                raw.append({
                    "title": item.findtext('title') or 'No Title',
                    "publish_date": pub,
                    "episode_url": audio_url,
                    "episode_summary": desc,
                    "transcript": None,
                    "downloaded": False,
                    "api_episode_id": item.findtext('guid'),
                    "duration_sec": None,
                    "guest_names": None,
                })
            raw.sort(key=lambda x: x["publish_date"], reverse=True)
            return raw[:limit]
        except Exception as e:
            logger.warning("Error fetching RSS %s: %s", rss_url, e)
        return []
 
    async def sync_episodes_for_media(self, media_id: int) -> None:
        media = await media_queries.get_media_by_id_from_db(media_id) # Use modular query
        if not media:
            logger.warning("Media %s not found", media_id)
            return
 
        rss_url = media.get("rss_url")
        podscan_id = media.get("api_id") if media.get("source_api") == "PodscanFM" else None
        media_name = media.get("name", f'Media ID {media_id}')
 
        async with aiohttp.ClientSession() as session:
            episodes: List[Dict[str, Any]] = []
            source = "None"
            if podscan_id and self.podscan_client:
                try:
                    loop = asyncio.get_running_loop()
                    data = await loop.run_in_executor(None, self.podscan_client.get_podcast_episodes, podscan_id, per_page=20)
                    for ep in data:
                        pub = self._parse_rss_date(ep.get("posted_at"))
                        if not pub:
                            continue
                        episodes.append({
                            "title": ep.get("episode_title"),
                            "publish_date": pub,
                            "episode_url": ep.get("episode_audio_url"),
                            "episode_summary": ep.get("episode_description"),
                            "transcript": ep.get("episode_transcript"),
                            "downloaded": bool(ep.get("episode_transcript")),
                            "api_episode_id": ep.get("episode_id"),
                            "duration_sec": None,
                            "guest_names": None,
                        })
                    source = "Podscan"
                except APIClientError as e:
                    logger.warning("Podscan error for %s: %s", media_name, e)
                except Exception as e:
                    logger.warning("Podscan fetch failed for %s: %s", media_name, e)
            if not episodes and rss_url:
                rss_eps = await self._fetch_episodes_from_rss(rss_url, session)
                if rss_eps:
                    episodes = rss_eps
                    source = "RSS"
 
            if not episodes:
                await media_queries.update_media_after_sync(media_id) # Use modular query
                logger.info("%s: no episodes found", media_name)
                return
 
            episodes.sort(key=lambda x: x["publish_date"], reverse=True)
            existing: Set[tuple[str, datetime.date]] = await episode_queries.get_existing_episode_identifiers(media_id) # Use modular query
            inserted = []
            for ep in episodes:
                ident = (ep["title"], ep["publish_date"].date())
                if ident not in existing:
                    payload = {
                        "media_id": media_id,
                        "title": ep["title"],
                        "publish_date": ep["publish_date"],
                        "duration_sec": ep.get("duration_sec"),
                        "episode_summary": ep.get("episode_summary"),
                        "episode_url": ep.get("episode_url"),
                        "transcript": ep.get("transcript"),
                        "downloaded": ep.get("downloaded", False),
                        "guest_names": ep.get("guest_names"),
                        "source_api": source,
                        "api_episode_id": ep.get("api_episode_id"),
                    }
                    rec = await episode_queries.insert_episode(payload) # Use modular query
                    if rec:
                        inserted.append(rec)
            logger.info("%s: inserted %s new episodes", media_name, len(inserted))
            await episode_queries.delete_oldest_episodes(media_id, 10) # Use modular query
            await episode_queries.flag_recent_episodes_for_transcription(media_id, 4) # Use modular query
            await media_queries.update_media_after_sync(media_id) # Use modular query
            await media_queries.update_media_latest_episode_date(media_id) # Use modular query
            logger.info("%s: sync complete via %s", media_name, source)
 
async def main_episode_sync_orchestrator():
    """Main orchestrator for fetching and syncing podcast episodes."""
    logger.info("--- Starting Smart Episode Sync Process ---")
    
    await get_db_pool() # Ensure DB pool is initialized for this script's run
    
    # Max number of concurrent podcast processing tasks
    MAX_CONCURRENT_PODCAST_SYNC_TASKS: int = 10 # From config or hardcoded
    sync_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PODCAST_SYNC_TASKS)
    
    # How often to check podcasts for new episodes (in hours)
    DEFAULT_SYNC_INTERVAL_HOURS: int = 24 # From config or hardcoded

    async with aiohttp.ClientSession() as http_session: # Create one session for all RSS fetches
        media_to_sync = await media_queries.get_media_to_sync_episodes(interval_hours=DEFAULT_SYNC_INTERVAL_HOURS) # Use modular query
        
        if not media_to_sync:
            logger.info("No media items found requiring an episode sync at this time.")
        else:
            logger.info(f"Found {len(media_to_sync)} media items to process for episode sync.")
            
            tasks = [
                MediaFetcher().sync_episodes_for_media(media_item['media_id']) # Call instance method
                for media_item in media_to_sync
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                media_name = media_to_sync[i].get('name', f"Media ID {media_to_sync[i]['media_id']}")
                if isinstance(result, Exception):
                    logger.error(f"Error processing media '{media_name}': {result}", exc_info=result)
                else:
                    logger.debug(f"Successfully completed episode sync for media '{media_name}'.")
 
    await close_db_pool() # Close DB pool after script finishes
    logger.info("--- Smart Episode Sync Process Finished ---")
