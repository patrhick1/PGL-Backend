import logging
from typing import List, Dict, Any

from podcast_outreach.services.media.fetcher import MediaFetcher
from podcast_outreach.database.queries import review_tasks

logger = logging.getLogger(__name__)

class DiscoveryService:
    """High level orchestration for podcast discovery and enrichment."""

    def __init__(self) -> None:
        self.fetcher = MediaFetcher()

    async def discover_for_campaign(self, campaign_id: str) -> List[Dict[str, Any]]:
        """Run discovery flow for a campaign and create review tasks."""
        ln = await self.fetcher.search_listen_notes(campaign_id)
        ps = await self.fetcher.search_podscan(campaign_id)
        media_records = await self.fetcher.merge_and_upsert_media(ln, ps)
        suggestions = await self.fetcher.create_match_suggestions(campaign_id, media_records)
        for sugg in suggestions:
            await review_tasks.create_review_task_in_db(
                {
                    "task_type": "match_suggestion",
                    "related_id": sugg["match_id"],
                    "campaign_id": campaign_id,
                }
            )
        return suggestions
