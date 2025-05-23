import logging
from typing import Any, Dict, Optional

from db_service_pg import get_db_pool

logger = logging.getLogger(__name__)

async def create_match_suggestion_in_db(suggestion: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Insert a match suggestion and return it."""
    query = """
    INSERT INTO match_suggestions (
        campaign_id, media_id, match_score, matched_keywords, ai_reasoning, status, client_approved, approved_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    RETURNING *;
    """
    keywords = suggestion.get("matched_keywords") or []
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                suggestion["campaign_id"],
                suggestion["media_id"],
                suggestion.get("match_score"),
                keywords,
                suggestion.get("ai_reasoning"),
                suggestion.get("status", "pending"),
                suggestion.get("client_approved", False),
                suggestion.get("approved_at"),
            )
            return dict(row) if row else None
        except Exception as e:
            logger.exception("Error creating match suggestion: %s", e)
            raise
