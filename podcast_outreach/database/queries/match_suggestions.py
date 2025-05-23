# podcast_outreach/database/queries/match_suggestions.py

import logging
from typing import Any, Dict, Optional, List
import uuid # For UUID types

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import review_tasks # For process_match_suggestion_approval

logger = get_logger(__name__)

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
            logger.info(f"Match suggestion created: {row.get('match_id')}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception("Error creating match suggestion: %s", e)
            raise

async def get_match_suggestion_by_id_from_db(match_id: int) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM match_suggestions WHERE match_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, match_id)
            if not row:
                logger.debug(f"Match suggestion not found: {match_id}")
                return None
            return dict(row)
        except Exception as e:
            logger.exception(f"Error fetching match suggestion {match_id}: {e}")
            raise

async def get_match_suggestions_for_campaign_from_db(campaign_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    query = "SELECT * FROM match_suggestions WHERE campaign_id = $1 ORDER BY created_at DESC OFFSET $2 LIMIT $3;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, campaign_id, skip, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching match suggestions for campaign {campaign_id}: {e}")
            raise

async def update_match_suggestion_in_db(match_id: int, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not update_fields:
        logger.warning(f"No update data for match suggestion {match_id}. Fetching current.")
        return await get_match_suggestion_by_id_from_db(match_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_fields.items():
        if key == "match_id": continue # Don't update the ID
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses: # No valid fields to update
        return await get_match_suggestion_by_id_from_db(match_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE match_suggestions SET {set_clause_str} WHERE match_id = ${idx} RETURNING *;"
    values.append(match_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Match suggestion updated: {match_id} with fields: {list(update_fields.keys())}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error updating match suggestion {match_id}: {e}")
            raise

async def delete_match_suggestion_from_db(match_id: int) -> bool:
    query = "DELETE FROM match_suggestions WHERE match_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, match_id)
            deleted_count = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
            if deleted_count > 0:
                logger.info(f"Match suggestion deleted: {match_id}")
                return True
            logger.warning(f"Match suggestion not found for deletion or delete failed: {match_id}")
            return False
        except Exception as e:
            logger.exception(f"Error deleting match suggestion {match_id} from DB: {e}")
            raise

async def get_match_suggestion_by_campaign_and_media_ids(campaign_id: uuid.UUID, media_id: int) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM match_suggestions WHERE campaign_id = $1 AND media_id = $2;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id, media_id)
            if not row:
                logger.debug(f"Match suggestion not found for campaign {campaign_id} and media {media_id}.")
                return None
            return dict(row)
        except Exception as e:
            logger.exception(f"Error fetching match suggestion for campaign {campaign_id} and media {media_id}: {e}")
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
