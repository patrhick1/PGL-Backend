# podcast_outreach/services/media/episode_handler.py

import logging
from typing import List, Dict, Any, Optional
import asyncio

from podcast_outreach.integrations.listen_notes import ListenNotesAPIClient
from podcast_outreach.integrations.podscan import PodscanAPIClient
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.utils.data_processor import parse_date

logger = logging.getLogger(__name__)

class EpisodeHandlerService:
    """
    Handles fetching, processing, and storing podcast episodes.
    """

    def __init__(self):
        self.listennotes_client = ListenNotesAPIClient()
        self.podscan_client = PodscanAPIClient()
        # Potentially add other API clients if more sources are used for episodes
        logger.info("EpisodeHandlerService initialized.")

    async def _fetch_episodes_from_source(self, media_record: Dict[str, Any], num_latest: int) -> List[Dict[str, Any]]:
        """
        Fetches raw episode data from the appropriate API based on the media record.
        """
        episodes_raw = []
        source_api = media_record.get('source_api')
        api_id = media_record.get('api_id') # This is the ListenNotes ID if source_api is ListenNotes, Podscan ID if PodscanFM

        # Todo: Add fallback to RSS if primary API fetch fails or api_id is missing.

        if source_api == "ListenNotes" and api_id:
            logger.info(f"Fetching up to {num_latest} episodes from ListenNotes for media_id {media_record['media_id']} (LN ID: {api_id})")
            # The get_podcast_episodes in ListenNotesAPIClient fetches up to 10 by default, which matches our common case.
            # If num_latest is different and API supports it, we might need to adjust.
            # For now, relying on its default or simple limit.
            fetched_data = await asyncio.to_thread(self.listennotes_client.get_podcast_episodes, podcast_ln_id=api_id)
            if fetched_data:
                episodes_raw = fetched_data[:num_latest] # Ensure we only take num_latest
        elif source_api == "PodscanFM" and api_id:
            logger.info(f"Fetching up to {num_latest} episodes from PodscanFM for media_id {media_record['media_id']} (Podscan ID: {api_id})")
            fetched_data = await asyncio.to_thread(self.podscan_client.get_podcast_episodes, podcast_id=api_id, per_page=num_latest)
            if fetched_data:
                episodes_raw = fetched_data # Already limited by per_page
        else:
            logger.warning(f"Media record for media_id {media_record['media_id']} (Name: {media_record.get('name')}) has no suitable source_api ('{source_api}') or api_id ('{api_id}') for direct episode fetching.")
            # Future: Attempt RSS fetch here if other methods fail
            # For RSS, we'd need to parse the feed, which is a different mechanism.
            # Example: fetched_episodes = await self._fetch_episodes_via_rss(media_record.get('rss_url'), num_latest)


        if not episodes_raw:
            logger.info(f"No episodes fetched from primary source for media_id {media_record['media_id']}.")
        
        return episodes_raw

    def _standardize_episode_data(self, raw_episode: Dict[str, Any], source_api: str, media_id: int) -> Optional[Dict[str, Any]]:
        """
        Maps raw episode data from an API to the schema of the 'episodes' table.
        Returns None if essential data (like title or publish_date) is missing.
        Transcript is intentionally excluded here to avoid large log outputs and will be handled by MediaTranscriber.
        """
        standardized = {
            "media_id": media_id,
            "source_api": source_api,
            "transcribe": True, 
            "ai_analysis_done": False,
            "downloaded": False,
            "transcript": None, # Explicitly set to None initially
        }

        if source_api == "ListenNotes":
            standardized["title"] = raw_episode.get('title')
            standardized["publish_date"] = parse_date(raw_episode.get('pub_date_ms'))
            standardized["duration_sec"] = raw_episode.get('audio_length_sec')
            standardized["episode_summary"] = raw_episode.get('description')
            standardized["episode_url"] = raw_episode.get('link') 
            standardized["api_episode_id"] = raw_episode.get('id') 
        elif source_api == "PodscanFM":
            standardized["title"] = raw_episode.get('episode_title')
            standardized["publish_date"] = parse_date(raw_episode.get('posted_at')) 
            standardized["duration_sec"] = None 
            standardized["episode_summary"] = raw_episode.get('episode_description')
            standardized["episode_url"] = raw_episode.get('episode_url') 
            standardized["api_episode_id"] = raw_episode.get('episode_id') 
            # Do not include raw_episode.get('episode_transcript') here
        else:
            logger.warning(f"Unknown source_api '{source_api}' for episode standardization.")
            return None

        if not standardized.get("title") or not standardized.get("publish_date") or not standardized.get("api_episode_id"):
            logger.warning(f"Essential data missing for episode from {source_api} for media {media_id}. Episode API ID: {raw_episode.get('id') or raw_episode.get('episode_id')}, Title: {raw_episode.get('title') or raw_episode.get('episode_title')}")
            return None
            
        return standardized

    async def fetch_and_store_latest_episodes(self, media_id: int, num_latest: int = 10) -> bool:
        """
        Fetches the latest N episodes for a given media_id, standardizes the data, 
        and upserts them into the 'episodes' table.
        Marks new episodes for transcription.
        """
        logger.info(f"Starting episode fetch & store for media_id: {media_id}, num_latest: {num_latest}.")
        
        media_record = await media_queries.get_media_by_id_from_db(media_id)
        if not media_record:
            logger.warning(f"Media record not found for media_id: {media_id}. Cannot fetch episodes.")
            return False

        raw_episodes_from_api = await self._fetch_episodes_from_source(media_record, num_latest)

        if not raw_episodes_from_api:
            logger.info(f"No new episodes found via API for media_id: {media_id}.")
            # Even if no new episodes are found, it might not be an "error" state.
            # The function's success could mean "processed successfully, found 0 new episodes".
            return True 

        processed_count = 0
        upserted_count = 0
        failed_count = 0
        
        source_api_for_standardization = media_record.get('source_api')
        if not source_api_for_standardization and raw_episodes_from_api:
            # If source_api was missing on media_record, but we got episodes (e.g. via RSS fallback in future)
            # we need to infer it or have the fetch_episodes_from_source return it.
            # For now, this case implies an issue or future enhancement.
             logger.warning(f"Source API on media record {media_id} is missing, but episodes were fetched. Standardization might be incorrect.")
             # Attempt to guess from first episode if it has a clear source marker, otherwise this will be problematic.
             # This is a temporary patch; _fetch_episodes_from_source should ideally return the source used.
             if 'audio_length_sec' in raw_episodes_from_api[0]: # Heuristic for ListenNotes
                 source_api_for_standardization = "ListenNotes"
             elif 'episode_audio_url' in raw_episodes_from_api[0]: # Heuristic for Podscan
                 source_api_for_standardization = "PodscanFM"


        for raw_ep in raw_episodes_from_api:
            processed_count += 1
            standardized_episode = self._standardize_episode_data(raw_ep, source_api_for_standardization, media_id)
            
            if not standardized_episode:
                # Log key identifiers instead of the whole raw_ep
                logger.warning(f"Failed to standardize episode data for media_id {media_id}. Episode API ID: {raw_ep.get('id') or raw_ep.get('episode_id')}, Title: {raw_ep.get('title') or raw_ep.get('episode_title')}")
                failed_count +=1
                continue
            
            try:
                # Upsert logic: Check if episode exists by api_episode_id and source_api for that media_id.
                # If exists, update. If not, insert.
                # episode_queries should have an upsert_episode method.
                
                # For now, let's assume a simple "create if not exists" based on api_episode_id
                existing_episode = await episode_queries.get_episode_by_api_id(
                    api_episode_id=standardized_episode['api_episode_id'],
                    media_id=media_id,
                    source_api=standardized_episode['source_api']
                )
                
                if existing_episode:
                    # Placeholder for update logic if needed. For now, we mainly care about new ones.
                    # Could update summary, title if changed, but usually episodes are immutable.
                    # logger.debug(f"Episode {standardized_episode['api_episode_id']} for media {media_id} already exists. Skipping insert, consider update.")
                    pass
                else:
                    # Corrected to call insert_episode instead of create_episode_in_db
                    created_episode = await episode_queries.insert_episode(standardized_episode)
                    if created_episode:
                        upserted_count += 1
                        logger.info(f"New episode '{created_episode.get('title')}' (API ID: {created_episode.get('api_episode_id')}) stored for media_id {media_id}.")
                    else:
                        # Log key identifiers from standardized_episode
                        logger.warning(f"Failed to store standardized episode for media_id {media_id}. Episode API ID: {standardized_episode.get('api_episode_id')}, Title: {standardized_episode.get('title')}")
                        failed_count +=1
                        
            except Exception as e:
                # Log key identifiers from standardized_episode
                logger.error(f"DB error storing episode for media_id {media_id}: {e}. Episode API ID: {standardized_episode.get('api_episode_id')}, Title: {standardized_episode.get('title')}", exc_info=True)
                failed_count +=1
        
        logger.info(f"Episode fetch & store for media_id {media_id} summary: Processed API results: {processed_count}, New episodes stored: {upserted_count}, Failed: {failed_count}.")
        return failed_count == 0 # Return True if no failures during DB operations 