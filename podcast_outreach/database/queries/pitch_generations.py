import logging
from typing import Any, Dict, Optional
import uuid
from datetime import datetime

# Assuming db_service_pg.py is the central connection pool manager
import db_service_pg

logger = logging.getLogger(__name__)

async def create_pitch_generation_in_db(pitch_gen_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Inserts a new pitch generation record into the database.

    Args:
        pitch_gen_data: A dictionary containing data for the pitch_generations table.
                        Expected keys: campaign_id (UUID), media_id (int), template_id (str),
                        draft_text (str), ai_model_used (str), pitch_topic (str),
                        temperature (float), generation_status (str), send_ready_bool (bool).

    Returns:
        The created pitch generation record as a dictionary, or None on failure.
    """
    query = """
    INSERT INTO pitch_generations (
        campaign_id, media_id, template_id, draft_text, ai_model_used,
        pitch_topic, temperature, generated_at, reviewer_id, reviewed_at,
        final_text, send_ready_bool, generation_status
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
    ) RETURNING *;
    """
    pool = await db_service_pg.get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                pitch_gen_data['campaign_id'],
                pitch_gen_data['media_id'],
                pitch_gen_data['template_id'],
                pitch_gen_data['draft_text'],
                pitch_gen_data.get('ai_model_used'),
                pitch_gen_data.get('pitch_topic'),
                pitch_gen_data.get('temperature'),
                pitch_gen_data.get('generated_at', datetime.utcnow()), # Default to now if not provided
                pitch_gen_data.get('reviewer_id'),
                pitch_gen_data.get('reviewed_at'),
                pitch_gen_data.get('final_text'),
                pitch_gen_data.get('send_ready_bool', False),
                pitch_gen_data.get('generation_status', 'draft')
            )
            if row:
                logger.info(f"Pitch generation record created: {row['pitch_gen_id']}")
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error creating pitch generation record for campaign {pitch_gen_data.get('campaign_id')} and media {pitch_gen_data.get('media_id')}: {e}")
            raise

async def get_pitch_generation_by_id(pitch_gen_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a pitch generation record by its ID."""
    query = "SELECT * FROM pitch_generations WHERE pitch_gen_id = $1;"
    pool = await db_service_pg.get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, pitch_gen_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching pitch generation {pitch_gen_id}: {e}")
            raise

async def update_pitch_generation_in_db(pitch_gen_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates a pitch generation record."""
    if not update_data:
        logger.warning(f"No update data provided for pitch generation {pitch_gen_id}.")
        return await get_pitch_generation_by_id(pitch_gen_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_data.items():
        if key == 'pitch_gen_id': continue
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses:
        return await get_pitch_generation_by_id(pitch_gen_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE pitch_generations SET {set_clause_str} WHERE pitch_gen_id = ${idx} RETURNING *;"
    values.append(pitch_gen_id)

    pool = await db_service_pg.get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Pitch generation {pitch_gen_id} updated with fields: {list(update_data.keys())}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error updating pitch generation {pitch_gen_id}: {e}")
            raise
