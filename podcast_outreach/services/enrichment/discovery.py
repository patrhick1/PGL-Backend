# podcast_outreach/services/enrichment/discovery.py

import logging
from typing import List, Dict, Any, Optional
import uuid # For campaign_id type
import asyncio

from podcast_outreach.services.media.podcast_fetcher import MediaFetcher
from podcast_outreach.services.tasks.manager import task_manager # For triggering background tasks

logger = logging.getLogger(__name__)

class DiscoveryService:
    """High level orchestration for podcast discovery and enrichment."""

    def __init__(self) -> None:
        self.fetcher = MediaFetcher() # MediaFetcher initializes EpisodeHandlerService

    async def discover_for_campaign(self, campaign_id: str, max_matches: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Run discovery flow for a campaign. This is the main entry point.
        1. Fetches/upserts media and creates initial match suggestions.
        2. For each NEW media item, it triggers a full background enrichment pipeline.
        3. Refreshes episodes for all pending matches to ensure data is current.
        """
        logger.info(f"DiscoveryService: Starting discovery for campaign {campaign_id}, max_matches: {max_matches}")
        
        # Phase 1: MediaFetcher finds/upserts media, creates match suggestions, and fetches initial episodes for NEW media.
        # The fetcher now returns a list of media_ids that were newly created.
        newly_created_media_ids = await self.fetcher.fetch_podcasts_for_campaign(campaign_id, max_matches=max_matches)
        logger.info(f"DiscoveryService: MediaFetcher completed. Found/created {len(newly_created_media_ids)} new media items for campaign {campaign_id}.")

        # Phase 2: For each newly created media item, trigger the full enrichment pipeline as a background task.
        if newly_created_media_ids:
            logger.info(f"Triggering background enrichment for {len(newly_created_media_ids)} new media items.")
            for media_id in newly_created_media_ids:
                # This uses the TaskManager to run the enrichment without blocking the main discovery flow.
                # The 'full_enrichment_and_scoring' task needs to be defined in your task runner.
                task_id = str(uuid.uuid4())
                # We are not using the FastAPI router here, but directly interacting with the task manager logic.
                # This assumes a function is registered in the task manager to handle this action.
                task_manager.start_task(task_id, f"full_enrichment_for_media_{media_id}")
                # In a real scenario, you'd have a worker system that picks up these tasks.
                # For now, we can simulate this by running it in an asyncio task.
                # This is a conceptual trigger; the actual implementation is in tasks.py and its runner.
                logger.info(f"Conceptually triggered background task '{task_id}' for 'full_enrichment_and_scoring' on media_id: {media_id}")
                # To actually run it now (for non-production testing):
                # from podcast_outreach.services.tasks.manager import _run_full_enrichment_task # Example
                # asyncio.create_task(_run_full_enrichment_task(media_id))


        # Phase 3: Retrieve all pending match suggestions for this campaign to refresh their episodes.
        from podcast_outreach.database.queries import match_suggestions as match_queries
        
        limit_for_retrieval = max_matches if max_matches is not None and max_matches > 0 else 100
        pending_suggestions_for_campaign: List[Dict[str, Any]] = []
        try:
            logger.info(f"DiscoveryService: Fetching all pending match suggestions for campaign {campaign_id} to refresh episodes.")
            pending_suggestions_for_campaign = await match_queries.get_all_match_suggestions_enriched(
                campaign_id=uuid.UUID(campaign_id), 
                status="pending",
                limit=limit_for_retrieval, 
                skip=0
            )
            logger.info(f"DiscoveryService: Retrieved {len(pending_suggestions_for_campaign)} pending match suggestions for campaign {campaign_id}.")

        except Exception as e:
            logger.error(f"DiscoveryService: Error fetching pending suggestions for campaign {campaign_id}: {e}", exc_info=True)

        # Phase 4: Ensure latest episodes are fetched for all media associated with these pending suggestions.
        if pending_suggestions_for_campaign:
            logger.info(f"DiscoveryService: Refreshing episodes for {len(pending_suggestions_for_campaign)} media items from pending suggestions.")
            media_ids_to_update = list(set([sugg['media_id'] for sugg in pending_suggestions_for_campaign if sugg.get('media_id')]))
            
            update_tasks = [
                self.fetcher.episode_handler_service.fetch_and_store_latest_episodes(media_id=media_id, num_latest=10)
                for media_id in media_ids_to_update
            ]
            
            if update_tasks:
                results = await asyncio.gather(*update_tasks, return_exceptions=True)
                for i, res in enumerate(results):
                    m_id = media_ids_to_update[i]
                    if isinstance(res, Exception):
                        logger.error(f"DiscoveryService: Error refreshing episodes for media_id {m_id}: {res}", exc_info=False)
                    else:
                        logger.info(f"DiscoveryService: Successfully refreshed episodes for media_id {m_id}.")
        else:
            logger.info(f"DiscoveryService: No pending suggestions found for campaign {campaign_id} to refresh episodes for.")

        return pending_suggestions_for_campaign