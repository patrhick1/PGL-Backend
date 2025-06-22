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
        """
        transcript = raw_episode.get('episode_transcript') if source_api == "PodscanFM" else None
        
        standardized = {
            "media_id": media_id,
            "source_api": source_api,
            "transcribe": False, # Default to False, will be flagged later if needed
            "ai_analysis_done": False,
            "downloaded": bool(transcript), # If we have a transcript, it's considered "downloaded"
            "transcript": transcript,
        }

        if source_api == "ListenNotes":
            standardized["title"] = raw_episode.get('title')
            standardized["publish_date"] = parse_date(raw_episode.get('pub_date_ms'))
            standardized["duration_sec"] = raw_episode.get('audio_length_sec')
            standardized["episode_summary"] = raw_episode.get('description')
            standardized["episode_url"] = raw_episode.get('link') 
            standardized["direct_audio_url"] = raw_episode.get('audio') or raw_episode.get('enclosure_url')
            standardized["api_episode_id"] = raw_episode.get('id') 
        elif source_api == "PodscanFM":
            standardized["title"] = raw_episode.get('episode_title')
            standardized["publish_date"] = parse_date(raw_episode.get('posted_at')) 
            standardized["duration_sec"] = None 
            standardized["episode_summary"] = raw_episode.get('episode_description')
            standardized["episode_url"] = raw_episode.get('episode_url') 
            standardized["direct_audio_url"] = raw_episode.get('episode_audio_url')
            standardized["api_episode_id"] = raw_episode.get('episode_id') 
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
        upserts them into the 'episodes' table, and intelligently flags episodes for transcription.
        """
        logger.info(f"Starting episode fetch & store for media_id: {media_id}, num_latest: {num_latest}.")
        
        media_record = await media_queries.get_media_by_id_from_db(media_id)
        if not media_record:
            logger.warning(f"Media record not found for media_id: {media_id}. Cannot fetch episodes.")
            return False

        raw_episodes_from_api = await self._fetch_episodes_from_source(media_record, num_latest)

        if not raw_episodes_from_api:
            logger.info(f"No new episodes found via API for media_id: {media_id}.")
            return True 

        processed_count = 0
        upserted_count = 0
        failed_count = 0
        
        source_api_for_standardization = media_record.get('source_api')
        if not source_api_for_standardization and raw_episodes_from_api:
             logger.warning(f"Source API on media record {media_id} is missing, but episodes were fetched. Standardization might be incorrect.")
             if 'audio_length_sec' in raw_episodes_from_api[0]:
                 source_api_for_standardization = "ListenNotes"
             elif 'episode_audio_url' in raw_episodes_from_api[0]:
                 source_api_for_standardization = "PodscanFM"

        for raw_ep in raw_episodes_from_api:
            processed_count += 1
            standardized_episode = self._standardize_episode_data(raw_ep, source_api_for_standardization, media_id)
            
            if not standardized_episode:
                logger.warning(f"Failed to standardize episode data for media_id {media_id}. Episode API ID: {raw_ep.get('id') or raw_ep.get('episode_id')}, Title: {raw_ep.get('title') or raw_ep.get('episode_title')}")
                failed_count +=1
                continue
            
            try:
                existing_episode = await episode_queries.get_episode_by_api_id(
                    api_episode_id=standardized_episode['api_episode_id'],
                    media_id=media_id,
                    source_api=standardized_episode['source_api']
                )
                
                if existing_episode:
                    # If transcript was missing and now we have it (from Podscan), update it.
                    if not existing_episode.get('transcript') and standardized_episode.get('transcript'):
                        await episode_queries.update_episode_transcription(
                            episode_id=existing_episode['episode_id'],
                            transcript=standardized_episode['transcript']
                        )
                        logger.info(f"Updated existing episode {existing_episode['episode_id']} with transcript from Podscan.")
                else:
                    created_episode = await episode_queries.insert_episode(standardized_episode)
                    if created_episode:
                        upserted_count += 1
                        logger.info(f"New episode '{created_episode.get('title')}' (API ID: {created_episode.get('api_episode_id')}) stored for media_id {media_id}.")
                    else:
                        logger.warning(f"Failed to store standardized episode for media_id {media_id}. Episode API ID: {standardized_episode.get('api_episode_id')}, Title: {standardized_episode.get('title')}")
                        failed_count +=1
                        
            except Exception as e:
                logger.error(f"DB error storing episode for media_id {media_id}: {e}. Episode API ID: {standardized_episode.get('api_episode_id')}, Title: {standardized_episode.get('title')}", exc_info=True)
                failed_count +=1
        
        # After all new episodes are inserted, run the intelligent flagging logic
        await self.flag_episodes_to_meet_transcription_goal(media_id)

        # Update last_fetched_at for the media item
        await media_queries.update_media_after_sync(media_id)
        
        logger.info(f"Episode fetch & store for media_id {media_id} summary: Processed API results: {processed_count}, New episodes stored: {upserted_count}, Failed: {failed_count}.")
        
        # Publish episodes fetched event if we stored new episodes
        if upserted_count > 0:
            try:
                from podcast_outreach.services.events.event_bus import get_event_bus, Event, EventType
                event_bus = get_event_bus()
                event = Event(
                    event_type=EventType.EPISODES_FETCHED,
                    entity_id=str(media_id),
                    entity_type="media",
                    data={
                        "episode_count": upserted_count,
                        "processed_count": processed_count,
                        "failed_count": failed_count
                    },
                    source="episode_handler"
                )
                await event_bus.publish(event)
                logger.info(f"Published EPISODES_FETCHED event for media {media_id} with {upserted_count} new episodes")
            except Exception as e:
                logger.error(f"Error publishing episodes fetched event: {e}")
        
        return failed_count == 0

    async def flag_episodes_to_meet_transcription_goal(self, media_id: int, goal_count: int = 4):
        """
        Ensures that at least `goal_count` of the most recent episodes have a transcript or are flagged for transcription.
        """
        logger.info(f"Checking transcription status for media_id {media_id} to meet goal of {goal_count}.")
        
        # Get the 10 most recent episodes
        recent_episodes = await episode_queries.get_episodes_for_media_paginated(media_id, offset=0, limit=10)
        
        if not recent_episodes:
            logger.info(f"No episodes found for media_id {media_id} to check transcription status.")
            return

        # Count how many of the recent episodes already have a transcript
        transcribed_count = sum(1 for ep in recent_episodes if ep.get('transcript'))
        
        episodes_to_flag_ids = []
        if transcribed_count < goal_count:
            needed = goal_count - transcribed_count
            logger.info(f"Media {media_id} has {transcribed_count} transcribed episodes. Need to flag {needed} more.")
            
            # Find the most recent episodes that do NOT have a transcript yet
            untranscribed_recent_episodes = [ep for ep in recent_episodes if not ep.get('transcript')]
            
            # Select the top `needed` episodes from this list to flag
            episodes_to_flag = untranscribed_recent_episodes[:needed]
            episodes_to_flag_ids = [ep['episode_id'] for ep in episodes_to_flag]
        else:
            logger.info(f"Media {media_id} already meets or exceeds transcription goal ({transcribed_count}/{goal_count}). No new flagging needed.")

        # This single DB call will set the correct episodes to True and all others to False.
        await episode_queries.flag_specific_episodes_for_transcription(media_id, episodes_to_flag_ids)
        
        if episodes_to_flag_ids:
            logger.info(f"Flagged episode IDs {episodes_to_flag_ids} for transcription for media {media_id}.")
        else:
            logger.info(f"No new episodes were flagged for transcription for media {media_id}.")