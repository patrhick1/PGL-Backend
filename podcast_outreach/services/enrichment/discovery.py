# podcast_outreach/services/enrichment/discovery.py

import logging
from typing import List, Dict, Any, Optional
import uuid # For campaign_id type
import asyncio

from podcast_outreach.services.media.podcast_fetcher import MediaFetcher
# Removed: from podcast_outreach.database.queries import review_tasks as review_tasks_queries
# This import doesn't seem to be used in the provided snippet of discover_for_campaign

logger = logging.getLogger(__name__)

class DiscoveryService:
    """High level orchestration for podcast discovery and enrichment."""

    def __init__(self) -> None:
        self.fetcher = MediaFetcher() # MediaFetcher initializes EpisodeHandlerService

    async def discover_for_campaign(self, campaign_id: str, max_matches: Optional[int] = None) -> List[Dict[str, Any]]:
        """Run discovery flow for a campaign. 
        The MediaFetcher handles media upsertion and match suggestion creation,
        including initial episode fetch for new media.
        This service then ensures episodes are up-to-date for all pending suggestions for the campaign.
        """
        logger.info(f"DiscoveryService: Starting discovery for campaign {campaign_id}, max_matches: {max_matches}")
        
        # Phase 1: MediaFetcher finds/upserts media, creates match suggestions, and fetches initial episodes for NEW media.
        await self.fetcher.fetch_podcasts_for_campaign(campaign_id, max_matches=max_matches)
        logger.info(f"DiscoveryService: MediaFetcher completed initial discovery for campaign {campaign_id}.")

        # Phase 2: Retrieve pending match suggestions for this campaign.
        from podcast_outreach.database.queries import match_suggestions as match_queries
        
        limit_for_retrieval = max_matches if max_matches is not None and max_matches > 0 else 100 # Or a higher sensible default for all pending
        pending_suggestions_for_campaign: List[Dict[str, Any]] = []
        try:
            logger.info(f"DiscoveryService: Fetching pending match suggestions for campaign {campaign_id} (limit: {limit_for_retrieval}).")
            # Fetch all pending, not just newly created, to ensure all relevant matches get episode refresh if needed.
            pending_suggestions_for_campaign = await match_queries.get_all_match_suggestions_enriched(
                campaign_id=uuid.UUID(campaign_id), 
                status="pending", # Focus on suggestions that are actively being considered
                limit=limit_for_retrieval, 
                skip=0
            )
            logger.info(f"DiscoveryService: Retrieved {len(pending_suggestions_for_campaign)} pending match suggestions for campaign {campaign_id}.")

        except Exception as e:
            logger.error(f"DiscoveryService: Error fetching pending suggestions for campaign {campaign_id}: {e}", exc_info=True)
            # Proceeding without suggestions if fetch fails, or could re-raise

        # Phase 3: Ensure latest episodes are fetched for all media associated with these pending suggestions.
        if pending_suggestions_for_campaign:
            logger.info(f"DiscoveryService: Ensuring latest episodes are fetched for {len(pending_suggestions_for_campaign)} media items from pending suggestions.")
            media_ids_to_update = list(set([sugg['media_id'] for sugg in pending_suggestions_for_campaign if sugg.get('media_id')]))
            
            update_tasks = []
            for media_id_to_update in media_ids_to_update:
                logger.info(f"DiscoveryService: Scheduling episode update for media_id {media_id_to_update} linked to campaign {campaign_id}.")
                update_tasks.append(
                    self.fetcher.episode_handler_service.fetch_and_store_latest_episodes(media_id=media_id_to_update, num_latest=10)
                )
            
            if update_tasks:
                results = await asyncio.gather(*update_tasks, return_exceptions=True)
                for i, res in enumerate(results):
                    m_id = media_ids_to_update[i]
                    if isinstance(res, Exception):
                        logger.error(f"DiscoveryService: Error updating episodes for media_id {m_id}: {res}", exc_info=False)
                    elif not res: # fetch_and_store_latest_episodes returns False on some failures
                        logger.warning(f"DiscoveryService: Episode update for media_id {m_id} reported failure or no new episodes.")
                    else:
                        logger.info(f"DiscoveryService: Successfully processed episode update for media_id {m_id}.")
        else:
            logger.info(f"DiscoveryService: No pending suggestions found for campaign {campaign_id} to update episodes for.")

        # The method is expected to return the list of suggestions as per its original signature.
        # If the goal was to return newly created ones, the logic to fetch them after MediaFetcher and before episode update would be slightly different.
        # For now, returning the (potentially episode-updated) pending suggestions.
        return pending_suggestions_for_campaign
