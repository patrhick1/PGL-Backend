# podcast_outreach/services/media/episode_sync.py

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Set

import aiohttp # For asynchronous HTTP requests
from bs4 import BeautifulSoup # For parsing RSS
from email.utils import parsedate_to_datetime # For parsing RSS dates

# Project-specific services and modules (UPDATED IMPORTS)
from podcast_outreach.database.queries import media as media_queries # Use modular query
from podcast_outreach.database.queries import episodes as episode_queries # Use modular query
from podcast_outreach.database.connection import get_db_pool, close_db_pool, get_background_task_pool # Use modular connection
from podcast_outreach.integrations.podscan import PodscanAPIClient # Use new integration path
from podcast_outreach.utils.exceptions import APIClientError # Use new utils path
from podcast_outreach.utils.data_processor import parse_date as fallback_parse_date # Use new utils path
from podcast_outreach.services.media.episode_handler import EpisodeHandlerService

# --- Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Constants ---
# Max number of concurrent podcast processing tasks
MAX_CONCURRENT_PODCAST_SYNC_TASKS: int = int(os.getenv("EPISODE_SYNC_MAX_CONCURRENT_TASKS", "10"))
# Max number of episodes to keep per podcast
EPISODES_TO_KEEP_PER_PODCAST: int = 10
# Number of most recent episodes to flag for transcription
EPISODES_TO_FLAG_FOR_TRANSCRIPTION: int = 4
# How often to check podcasts for new episodes (in hours)
DEFAULT_SYNC_INTERVAL_HOURS: int = 24
# HTTP request timeout
HTTP_REQUEST_TIMEOUT: int = 20 # seconds
# Custom headers for fetching RSS
RSS_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Initialize Podscan Client (synchronous, will be run in executor)
# Ensure PODSCANAPI env var is set for PodscanAPIClient
try:
    podscan_client = PodscanAPIClient()
except APIClientError as e: # Assuming APIClientError can be raised on init if key is missing
    logger.warning(f"PodscanAPIClient could not be initialized: {e}. Podscan features will be unavailable.")
    podscan_client = None


def robust_parse_rss_date(date_string: Optional[str]) -> Optional[datetime]:
    """Parses date strings commonly found in RSS feeds, returning a timezone-aware datetime object (UTC)."""
    if not date_string:
        return None
    try:
        dt = parsedate_to_datetime(date_string)
        # If naive, assume UTC. If aware, convert to UTC.
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        logger.debug(f"parsedate_to_datetime failed for '{date_string}', trying fallback.")
        try:
            # fallback_parse_date should ideally also return timezone-aware datetime or handle UTC conversion
            dt = fallback_parse_date(date_string)
            if dt: # Ensure fallback_parse_date returns a datetime object
                if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
                    return dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            return None
        except Exception as e_fallback:
            logger.warning(f"Fallback date parsing also failed for '{date_string}': {e_fallback}")
            return None


async def fetch_episodes_from_rss_async(
    rss_url: str,
    http_session: aiohttp.ClientSession,
    max_episodes_to_parse: int = 20 # Parse a bit more initially to ensure we find all recent ones
) -> List[Dict[str, Any]]:
    """Asynchronously fetches and parses episode information from an RSS feed."""
    logger.debug(f"Attempting to fetch episodes from RSS: {rss_url}")
    raw_episodes = []
    try:
        async with http_session.get(rss_url, headers=RSS_FETCH_HEADERS, timeout=HTTP_REQUEST_TIMEOUT) as response:
            response.raise_for_status()
            content = await response.text()

        # BeautifulSoup parsing can be blocking; run in executor if feeds are very large/complex
        # For typical feeds, direct call is often acceptable in async if not too frequent.
        # For true non-blocking, would need an async XML parser or careful executor use.
        loop = asyncio.get_running_loop()
        soup = await loop.run_in_executor(None, BeautifulSoup, content, 'xml')

        items = soup.find_all('item')
        logger.debug(f"Found {len(items)} items in RSS feed: {rss_url}")

        for item in items[:max_episodes_to_parse * 2]: # Parse more to allow for date issues or future-dated items
            pub_date = robust_parse_rss_date(item.findtext('pubDate'))
            if not pub_date:
                logger.warning(f"Skipping episode in {rss_url} due to unparsable pubDate: {item.findtext('pubDate')}")
                continue

            audio_url = None
            enclosure = item.find('enclosure')
            if enclosure and enclosure.get('url'):
                audio_url = enclosure['url']
            # Basic check if guid might be an audio url
            elif item.find('guid') and item.findtext('guid', '').startswith(('http://', 'https://')):
                    guid_text = item.findtext('guid')
                    if any(guid_text.lower().endswith(ext) for ext in ['.mp3', '.m4a', '.ogg', '.wav', '.aac']):
                        audio_url = guid_text
            
            api_episode_id_from_rss = item.findtext('guid') # Store GUID as potential API ID

            if not audio_url: # Skip if no audio URL, as it's key for uniqueness & playback
                logger.debug(f"Skipping episode '{item.findtext('title')}' from {rss_url} due to missing audio URL.")
                continue

            description_text = item.findtext('description') or item.findtext('content:encoded') or item.findtext('itunes:summary')
            # Strip HTML from description if necessary (using a simple approach or a library)
            if description_text:
                    desc_soup = BeautifulSoup(description_text, 'html.parser')
                    description_text = desc_soup.get_text(separator='\n', strip=True)


            raw_episodes.append({
                "title": item.findtext('title') or 'No Title',
                "publish_date": pub_date, # datetime object
                "episode_url": audio_url, # This is the audio file URL
                "episode_summary": description_text,
                "transcript": None, # RSS feeds typically don't have transcripts
                "downloaded": False,
                # Podscan specific fields will be None or derived if possible
                "api_episode_id": api_episode_id_from_rss, 
                "duration_sec": None, # Try to parse from itunes:duration if available
                "guest_names": None, # Not typically in basic RSS
            })
        
        # Sort by publish_date descending before returning
        raw_episodes.sort(key=lambda x: x["publish_date"], reverse=True)
        logger.info(f"Successfully parsed {len(raw_episodes)} episodes from RSS: {rss_url}")
        return raw_episodes[:max_episodes_to_parse] # Return a limited set

    except aiohttp.ClientError as e:
        logger.error(f"AIOHTTP error fetching RSS {rss_url}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error processing RSS {rss_url}: {e}", exc_info=True)
    return []


class MediaFetcher: # Renamed from original fetch_episodes_to_pg.py's implicit scope
    def __init__(self):
        self.podscan_client = podscan_client # Use the globally initialized client

    async def sync_episodes_for_media(
        self,
        media_item: Dict[str, Any],
        http_session: aiohttp.ClientSession,
        sync_semaphore: asyncio.Semaphore
    ):
        """Processes a single media item to sync its episodes."""
        async with sync_semaphore: # Control concurrency for processing each podcast
            media_id = media_item['media_id']
            media_name = media_item.get('name', f'Media ID {media_id}')
            rss_url = media_item.get('rss_url')
            # Podscan ID is assumed to be in 'api_id' if 'source_api' indicates Podscan
            podscan_api_id = media_item.get('api_id') if media_item.get('source_api') == 'PodscanFM' else None

            logger.info(f"[{media_name}] Starting episode sync for media_id: {media_id}")

            raw_episodes_from_source: List[Dict[str, Any]] = []
            source_used = "None"
            
            # 1. Fetch episodes from external source (Podscan prioritized)
            if podscan_api_id and self.podscan_client:
                logger.info(f"[{media_name}] Attempting to fetch episodes from Podscan (ID: {podscan_api_id})")
                try:
                    loop = asyncio.get_running_loop()
                    # Podscan client's get_podcast_episodes is synchronous
                    podscan_raw_data = await loop.run_in_executor(
                        None, self.podscan_client.get_podcast_episodes, podscan_api_id, per_page=20 # Fetch a bit more
                    )
                    if podscan_raw_data:
                        source_used = "Podscan"
                        for ep_data in podscan_raw_data:
                            pub_date = robust_parse_rss_date(ep_data.get("posted_at"))
                            if not pub_date: continue # Skip if no valid date

                            raw_episodes_from_source.append({
                                "title": ep_data.get("episode_title"),
                                "publish_date": pub_date,
                                "episode_url": ep_data.get("episode_audio_url"),
                                "episode_summary": ep_data.get("episode_description"),
                                "transcript": ep_data.get("episode_transcript"),
                                "downloaded": bool(ep_data.get("episode_transcript")),
                                "api_episode_id": ep_data.get("episode_id"), # Podscan's episode ID
                                "duration_sec": None, # Podscan schema doesn't explicitly state duration
                                "guest_names": None,
                            })
                        logger.info(f"[{media_name}] Fetched {len(raw_episodes_from_source)} episodes from Podscan.")
                    else:
                        logger.info(f"[{media_name}] Podscan returned no episodes. Will try RSS if available.")
                except APIClientError as e: # Catch API specific errors from Podscan client
                        logger.warning(f"[{media_name}] Podscan API client error for ID {podscan_api_id}: {e}. Trying RSS.")
                except Exception as e:
                    logger.warning(f"[{media_name}] Error fetching from Podscan for ID {podscan_api_id}: {e}. Trying RSS.")
            
            if not raw_episodes_from_source and rss_url: # Fallback to RSS or if Podscan wasn't attempted
                logger.info(f"[{media_name}] Fetching episodes from RSS feed: {rss_url}")
                raw_episodes_from_source = await fetch_episodes_from_rss_async(rss_url, http_session)
                if raw_episodes_from_source:
                    source_used = "RSS"
            
            if not raw_episodes_from_source:
                logger.info(f"[{media_name}] No episodes found from any source. Updating last_fetched_at.")
                await media_queries.update_media_after_sync(media_id)
                return

            # Sort by publish_date descending from source to ensure we process newest first
            raw_episodes_from_source.sort(key=lambda x: x["publish_date"], reverse=True)

            # 2. Compare with episodes table (using title and publish_date as key for existence check)
            logger.debug(f"[{media_name}] Fetching existing episode identifiers from DB.")
            existing_episode_identifiers: Set[tuple[str, datetime.date]] = await episode_queries.get_existing_episode_identifiers(media_id)
            logger.debug(f"[{media_name}] Found {len(existing_episode_identifiers)} existing episode identifiers in DB.")

            # 3. Insert only new episodes
            new_episodes_to_insert_payload: List[Dict[str, Any]] = []
            for ep_data in raw_episodes_from_source:
                ep_url = ep_data.get("episode_url")
                ep_title = ep_data.get("title")
                ep_publish_date = ep_data.get("publish_date")

                if not ep_url: # Should have been filtered by fetchers, but double check
                    logger.warning(f"[{media_name}] Skipping episode '{ep_title}' due to missing audio URL after source fetch.")
                    continue
                
                if not ep_title or not ep_publish_date:
                    logger.warning(f"[{media_name}] Skipping episode due to missing title or publish date after source fetch. Title: '{ep_title}', Date: '{ep_publish_date}'.")
                    continue
                
                # Convert publish_date (datetime) to date for comparison, as DB stores DATE type for publish_date
                current_episode_identifier = (ep_title, ep_publish_date.date())

                if current_episode_identifier not in existing_episode_identifiers:
                    # Prepare payload for DB insertion, matching `episodes` table columns
                    payload = {
                        "media_id": media_id,
                        "title": ep_title,
                        "publish_date": ep_publish_date, # Already a datetime object, DB will take DATE part
                        "duration_sec": ep_data.get("duration_sec"),
                        "episode_summary": ep_data.get("episode_summary"),
                        "episode_url": ep_url,
                        "transcript": ep_data.get("transcript"),
                        "downloaded": ep_data.get("downloaded", False),
                        "guest_names": ep_data.get("guest_names"),
                        "source_api": source_used, # Add source_api
                        "api_episode_id": ep_data.get("api_episode_id"), # Add api_episode_id
                        # `transcribe` will be set in a later step
                        # `ai_episode_summary` and `embedding` are populated by other processes
                    }
                    new_episodes_to_insert_payload.append(payload)
                else:
                    logger.debug(f"[{media_name}] Episode with title '{ep_title}' and publish date '{ep_publish_date.date()}' already exists. Skipping.")

            if new_episodes_to_insert_payload:
                logger.info(f"[{media_name}] Found {len(new_episodes_to_insert_payload)} new episodes to insert.")
                await episode_queries.insert_episodes_batch(new_episodes_to_insert_payload)
            else:
                logger.info(f"[{media_name}] No new episodes to insert from source: {source_used}.")

            # 4. Maintain max EPISODES_TO_KEEP_PER_PODCAST episodes
            logger.info(f"[{media_name}] Trimming old episodes, keeping up to {EPISODES_TO_KEEP_PER_PODCAST}.")
            await episode_queries.delete_oldest_episodes(media_id, EPISODES_TO_KEEP_PER_PODCAST)

            # 5. Flag episodes to meet transcription goal using the robust handler
            # This logic correctly re-uses the robust flagging from EpisodeHandlerService
            handler_for_flagging = EpisodeHandlerService()
            logger.info(f"[{media_name}] Intelligently flagging episodes to meet transcription goal of {EPISODES_TO_FLAG_FOR_TRANSCRIPTION}.")
            await handler_for_flagging.flag_episodes_to_meet_transcription_goal(media_id, EPISODES_TO_FLAG_FOR_TRANSCRIPTION)

            # 6. Update last_fetched_at for the media item and latest_episode_date
            await media_queries.update_media_after_sync(media_id)
            await media_queries.update_media_latest_episode_date(media_id)
            logger.info(f"[{media_name}] Successfully synced episodes. Source: {source_used}. Updated sync status and latest episode date.")


async def main_episode_sync_orchestrator():
    """Main orchestrator for fetching and syncing podcast episodes."""
    logger.info("--- Starting Smart Episode Sync Process ---")
    
    await get_db_pool()
    
    # Use a semaphore to limit overall concurrent podcast processing tasks
    sync_semaphore = asyncio.Semaphore(MAX_CONCURRENT_PODCAST_SYNC_TASKS)

    media_fetcher_instance = MediaFetcher() # Create an instance of MediaFetcher

    async with aiohttp.ClientSession() as http_session: # Create one session for all RSS fetches
        media_to_sync = await media_queries.get_media_to_sync_episodes(interval_hours=DEFAULT_SYNC_INTERVAL_HOURS)
        
        if not media_to_sync:
            logger.info("No media items found requiring an episode sync at this time.")
        else:
            logger.info(f"Found {len(media_to_sync)} media items to process for episode sync.")
            
            tasks = [
                media_fetcher_instance.sync_episodes_for_media(media_item, http_session, sync_semaphore)
                for media_item in media_to_sync
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                media_name = media_to_sync[i].get('name', f"Media ID {media_to_sync[i]['media_id']}")
                if isinstance(result, Exception):
                    logger.error(f"Error processing media '{media_name}': {result}", exc_info=result)
                else:
                    logger.debug(f"Successfully completed episode sync for media '{media_name}'.")

    await close_db_pool()
    logger.info("--- Smart Episode Sync Process Finished ---")
