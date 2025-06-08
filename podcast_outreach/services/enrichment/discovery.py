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

async def _run_full_enrichment_task(media_id: int):
    """
    A standalone async function to run the full enrichment and scoring pipeline for one media item.
    This is designed to be called as a non-blocking background task.
    """
    logger.info(f"Starting background enrichment task for media_id: {media_id}")
    try:
        # Initialize all the necessary services for the orchestrator
        gemini_service = GeminiService()
        social_discovery_service = SocialDiscoveryService()
        data_merger = DataMergerService()
        enrichment_agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger)
        quality_service = QualityService()
        orchestrator = EnrichmentOrchestrator(enrichment_agent, quality_service)

        # 1. Enrich media profile (social links, emails, etc.)
        media_data = await media_queries.get_media_by_id_from_db(media_id)
        if not media_data:
            logger.error(f"Enrichment task failed: Media with id {media_id} not found.")
            return

        enriched_profile = await orchestrator.enrichment_agent.enrich_podcast_profile(media_data)
        if enriched_profile:
            # Convert the Pydantic model to a dictionary
            update_data = enriched_profile.model_dump(exclude_none=True)
            
            # --- NEW FIX: Convert all HttpUrl objects to strings ---
            for key, value in update_data.items():
                if isinstance(value, HttpUrl):
                    update_data[key] = str(value)
            # --- END OF NEW FIX ---

            fields_to_remove = ['unified_profile_id', 'recent_episodes', 'quality_score']
            for field in fields_to_remove:
                if field in update_data: del update_data[field]
            if 'primary_email' in update_data:
                update_data['contact_email'] = update_data.pop('primary_email')
            if 'rss_feed_url' in update_data:
                update_data['rss_url'] = update_data.pop('rss_feed_url')

            await media_queries.update_media_enrichment_data(media_id, update_data)
            logger.info(f"Successfully ran enrichment agent for media_id: {media_id}")
        else:
            logger.warning(f"Enrichment agent returned no profile for media_id: {media_id}.")

        # 2. Update quality score
        # Refetch data after enrichment to get the most current profile for scoring
        refetched_media_data = await media_queries.get_media_by_id_from_db(media_id)
        if refetched_media_data:
            await orchestrator._update_quality_score_for_media(refetched_media_data)
        
        logger.info(f"Completed background enrichment task for media_id: {media_id}")

    except Exception as e:
        logger.error(f"Error in background enrichment task for media_id {media_id}: {e}", exc_info=True)

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
                task_name = f"enrichment_media_{media_id}"
                logger.info(f"Creating non-blocking asyncio task '{task_name}'...")
                # This now creates a fire-and-forget asyncio task that runs the enrichment
                # in the background without blocking the main discovery API response.
                task = asyncio.create_task(_run_full_enrichment_task(media_id), name=task_name)
                task.add_done_callback(_log_task_exception) # Add the callback here

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