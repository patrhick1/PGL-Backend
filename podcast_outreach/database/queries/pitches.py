import logging
from typing import Any, Dict, Optional, List
import uuid
from datetime import datetime

# Assuming db_service_pg.py is the central connection pool manager
import db_service_pg

logger = logging.getLogger(__name__)

async def create_pitch_in_db(pitch_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Inserts a new pitch record into the database.

    Args:
        pitch_data: A dictionary containing data for the pitches table.
                    Expected keys: campaign_id (UUID), media_id (int), attempt_no (int),
                    match_score (float), matched_keywords (List[str]), outreach_type (str),
                    subject_line (str), body_snippet (str), pitch_gen_id (int),
                    pitch_state (str), client_approval_status (str), created_by (str),
                    instantly_lead_id (Optional[str]).

    Returns:
        The created pitch record as a dictionary, or None on failure.
    """
    query = """
    INSERT INTO pitches (
        campaign_id, media_id, attempt_no, match_score, matched_keywords,
        score_evaluated_at, outreach_type, subject_line, body_snippet,
        send_ts, reply_bool, reply_ts, pitch_gen_id, placement_id,
        pitch_state, client_approval_status, created_by, created_at,
        instantly_lead_id -- New column
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19
    ) RETURNING *;
    """
    pool = await db_service_pg.get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                pitch_data['campaign_id'],
                pitch_data['media_id'],
                pitch_data.get('attempt_no', 1),
                pitch_data.get('match_score'),
                pitch_data.get('matched_keywords'),
                pitch_data.get('score_evaluated_at', datetime.utcnow()),
                pitch_data.get('outreach_type'),
                pitch_data.get('subject_line'),
                pitch_data.get('body_snippet'),
                pitch_data.get('send_ts'),
                pitch_data.get('reply_bool', False),
                pitch_data.get('reply_ts'),
                pitch_data.get('pitch_gen_id'),
                pitch_data.get('placement_id'),
                pitch_data.get('pitch_state', 'generated'),
                pitch_data.get('client_approval_status', 'pending_review'),
                pitch_data.get('created_by', 'system'),
                pitch_data.get('created_at', datetime.utcnow()),
                pitch_data.get('instantly_lead_id') # New value
            )
            if row:
                logger.info(f"Pitch record created: {row['pitch_id']}")
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error creating pitch record for campaign {pitch_data.get('campaign_id')} and media {pitch_data.get('media_id')}: {e}")
            raise

async def get_pitch_by_id(pitch_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a pitch record by its ID."""
    query = "SELECT * FROM pitches WHERE pitch_id = $1;"
    pool = await db_service_pg.get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, pitch_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching pitch {pitch_id}: {e}")
            raise

async def update_pitch_in_db(pitch_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates a pitch record."""
    if not update_data:
        logger.warning(f"No update data provided for pitch {pitch_id}.")
        return await get_pitch_by_id(pitch_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_data.items():
        if key == 'pitch_id': continue
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses:
        return await get_pitch_by_id(pitch_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE pitches SET {set_clause_str} WHERE pitch_id = ${idx} RETURNING *;"
    values.append(pitch_id)

    pool = await db_service_pg.get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Pitch {pitch_id} updated with fields: {list(update_data.keys())}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error updating pitch {pitch_id}: {e}")
            raise

async def get_pitch_by_instantly_lead_id(instantly_lead_id: str) -> Optional[Dict[str, Any]]:
    """Fetches a pitch record by its Instantly Lead ID."""
    query = "SELECT * FROM pitches WHERE instantly_lead_id = $1;"
    pool = await db_service_pg.get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, instantly_lead_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching pitch by Instantly Lead ID {instantly_lead_id}: {e}")
            raise

async def get_pitch_by_pitch_gen_id(pitch_gen_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a pitch record by its associated pitch_gen_id."""
    query = "SELECT * FROM pitches WHERE pitch_gen_id = $1;"
    pool = await db_service_pg.get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, pitch_gen_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching pitch by pitch_gen_id {pitch_gen_id}: {e}")
            raise
