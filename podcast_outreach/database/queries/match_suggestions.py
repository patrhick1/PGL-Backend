import logging
from typing import Any, Dict, Optional

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import review_tasks

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


async def approve_match_and_create_pitch_task(match_id: int) -> Optional[Dict[str, Any]]:
    """Mark a match suggestion as approved and create a pitch review task."""
    update_query = """
    UPDATE match_suggestions
    SET client_approved = TRUE,
        status = 'approved',
        approved_at = NOW()
    WHERE match_id = $1
    RETURNING *;
    """

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(update_query, match_id)
            if not row:
                return None
            match = dict(row)
        except Exception as e:
            logger.exception("Error approving match suggestion: %s", e)
            raise

    # Create a follow-up review task for pitching. Failures shouldn't block approval.
    try:
        await review_tasks.create_review_task_in_db(
            {
                "task_type": "pitch_review",
                "related_id": match["match_id"],
                "campaign_id": match["campaign_id"],
                "status": "pending",
            }
        )
    except Exception as e:  # pragma: no cover - optional future-proofing
        logger.exception("Error creating pitch review task for match %s: %s", match_id, e)

    return match
