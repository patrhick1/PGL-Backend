# podcast_outreach/services/enrichment/discovery.py

import logging
from typing import List, Dict, Any
import uuid # For campaign_id type

from podcast_outreach.services.media.podcast_fetcher import MediaFetcher
from podcast_outreach.database.queries import review_tasks as review_tasks_queries # Use modular query

logger = logging.getLogger(__name__)

class DiscoveryService:
    """High level orchestration for podcast discovery and enrichment."""

    def __init__(self) -> None:
        self.fetcher = MediaFetcher()

    async def discover_for_campaign(self, campaign_id: str) -> List[Dict[str, Any]]:
        """Run discovery flow for a campaign and create review tasks."""
        # The MediaFetcher.fetch_podcasts_for_campaign already handles the full flow
        # of searching, merging/upserting media, and creating match suggestions and review tasks.
        # So, we just need to call that.
        
        # The fetch_podcasts_for_campaign method returns None, so we need to adjust this.
        # It creates match suggestions internally. We need to fetch them back.
        
        # First, run the fetcher to populate media and match_suggestions
        await self.fetcher.fetch_podcasts_for_campaign(campaign_id)

        # Then, retrieve the newly created match suggestions for this campaign
        # This assumes match_suggestions are created with a 'pending' status
        # and we want to return them for immediate review.
        # You might need a specific query for "newly created" or "pending" matches.
        from podcast_outreach.database.queries import match_suggestions as match_queries
        
        # Fetch all pending match suggestions for this campaign
        suggestions = await match_queries.get_match_suggestions_for_campaign_from_db(
            uuid.UUID(campaign_id), status="pending" # Assuming status filter is supported
        )
        
        # If the get_match_suggestions_for_campaign_from_db doesn't support status filter,
        # you'd fetch all and filter in Python:
        # all_suggestions = await match_queries.get_match_suggestions_for_campaign_from_db(uuid.UUID(campaign_id))
        # suggestions = [s for s in all_suggestions if s.get('status') == 'pending']
        from podcast_outreach.database.queries import media as media_queries

        enhanced_suggestions = []
        for suggestion_dict in suggestions: # Assuming suggestions is a list of dicts here
            media_record = await media_queries.get_media_by_id_from_db(suggestion_dict['media_id'])
            suggestion_dict['media_name'] = media_record.get('name') if media_record else 'Unknown Media'
            suggestion_dict['media_website'] = media_record.get('website') if media_record else None
        enhanced_suggestions.append(suggestion_dict)

         # Return the list of dicts

        logger.info(f"Discovery for campaign {campaign_id} completed. Found {len(suggestions)} new match suggestions.")
        return enhanced_suggestions
