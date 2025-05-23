import logging
from typing import Any, Dict, List

from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import match_suggestions as match_queries

logger = logging.getLogger(__name__)

class MediaFetcher:
    """Stub service for podcast discovery and storage."""

    async def search_listen_notes(self, campaign_id: str) -> List[Dict[str, Any]]:
        logger.info("Searching ListenNotes for campaign %s", campaign_id)
        return []  # Placeholder for API call

    async def search_podscan(self, campaign_id: str) -> List[Dict[str, Any]]:
        logger.info("Searching Podscan for campaign %s", campaign_id)
        return []  # Placeholder for API call

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
            suggestion = await match_queries.create_match_suggestion_in_db(
                {"campaign_id": campaign_id, "media_id": media["media_id"]}
            )
            if suggestion:
                suggestions.append(suggestion)
        return suggestions
