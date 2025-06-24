# podcast_outreach/services/enrichment/discovery.py

import logging
from typing import List, Dict, Any, Optional
import uuid # For campaign_id type
import asyncio
from pydantic import HttpUrl

from podcast_outreach.services.media.podcast_fetcher import MediaFetcher
# Removed task_manager as we will run the orchestrator directly
# from podcast_outreach.services.tasks.manager import task_manager

# Imports to run enrichment directly
from podcast_outreach.services.enrichment.enrichment_orchestrator import EnrichmentOrchestrator
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService
from podcast_outreach.services.enrichment.data_merger import DataMergerService
from podcast_outreach.services.enrichment.enrichment_agent import EnrichmentAgent
from podcast_outreach.services.enrichment.quality_score import QualityService
from podcast_outreach.database.queries import media as media_queries

logger = logging.getLogger(__name__)

# Moved to business logic layer - see services/business_logic/enrichment_processing.py

def _log_task_exception(task: asyncio.Task) -> None:
    """Callback to log exceptions from background tasks."""
    try:
        task.result()
    except asyncio.CancelledError:
        pass  # Task cancellation is expected, no need to log as an error.
    except Exception as e:
        logger.error(f"Exception in background task {task.get_name()}: {e}", exc_info=True)

class DiscoveryService:
    """High level orchestration for podcast discovery and enrichment."""

    def __init__(self) -> None:
        self.fetcher = MediaFetcher() # MediaFetcher initializes EpisodeHandlerService

    async def discover_for_campaign(self, campaign_id: str, max_matches: Optional[int] = None) -> List[tuple[int, str]]:
        """
        Run discovery flow for a campaign. This is the main entry point.
        1. Fetches/upserts media and creates initial match suggestions.
        2. For each NEW media item, it triggers a full background enrichment pipeline.
        3. Refreshes episodes for all pending matches to ensure data is current.
        """
        logger.info(f"DiscoveryService: Starting discovery for campaign {campaign_id}, max_matches: {max_matches}")
        
        # Phase 1: MediaFetcher finds/upserts media and tracks discoveries up to max_matches.
        # The fetcher now returns a list of (media_id, keyword) tuples for NEW campaign_media_discoveries records.
        media_with_new_discoveries = await self.fetcher.fetch_podcasts_for_campaign(campaign_id, max_matches=max_matches)
        logger.info(f"DiscoveryService: MediaFetcher completed. Created {len(media_with_new_discoveries)} new campaign_media_discoveries records for campaign {campaign_id}.")

        # Phase 2: For each media with new discovery record, trigger the full enrichment pipeline as a background task.
        if media_with_new_discoveries:
            logger.info(f"Triggering background enrichment for {len(media_with_new_discoveries)} media items with new discoveries.")
            for media_id, keyword in media_with_new_discoveries:
                task_name = f"enrichment_media_{media_id}"
                logger.info(f"Creating non-blocking asyncio task '{task_name}'...")
                # Use TaskManager for enrichment instead of direct asyncio task
                from podcast_outreach.services.tasks.manager import task_manager
                import time
                
                task_id = f"enrichment_{media_id}_{int(time.time())}"
                task_manager.start_task(task_id, f"enrichment_media_{media_id}")
                task_manager.run_enrichment_pipeline(task_id, media_id=media_id)

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

        # Return the media IDs with keywords that have new discovery records (to be processed by enhanced workflow)
        return media_with_new_discoveries