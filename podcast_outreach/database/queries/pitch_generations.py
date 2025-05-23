import logging
from typing import Any, Dict, Optional
import uuid
from datetime import datetime

# Assuming db_service_pg.py is the central connection pool manager
import db_service_pg
from podcast_outreach.database.queries import review_tasks

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

async def approve_pitch_generation(pitch_gen_id: int, reviewer_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Approves a pitch generation, setting it as send-ready and updating its status.
    Also marks the associated review task as completed.
    """
    pool = await db_service_pg.get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                # 1. Update pitch_generations record
                update_query = """
                UPDATE pitch_generations
                SET send_ready_bool = TRUE,
                    generation_status = 'approved',
                    reviewed_at = NOW(),
                    reviewer_id = COALESCE($1, reviewer_id)
                WHERE pitch_gen_id = $2
                RETURNING *;
                """
                updated_pitch_gen = await conn.fetchrow(update_query, reviewer_id, pitch_gen_id)
                if not updated_pitch_gen:
                    logger.warning(f"Pitch generation {pitch_gen_id} not found for approval.")
                    return None
                
                updated_pitch_gen_dict = dict(updated_pitch_gen)
                logger.info(f"Pitch generation {pitch_gen_id} approved and marked send-ready.")

                # 2. Find and update the associated review task
                # Assuming there's a review task with task_type 'pitch_review' and related_id matching pitch_gen_id
                review_task_query = """
                SELECT review_task_id FROM review_tasks
                WHERE task_type = 'pitch_review' AND related_id = $1 AND status = 'pending'
                LIMIT 1;
                """
                pending_review_task = await conn.fetchrow(review_task_query, pitch_gen_id)

                if pending_review_task:
                    review_task_id = pending_review_task['review_task_id']
                    await review_tasks.update_review_task_status_in_db(review_task_id, 'completed', f"Pitch approved by {reviewer_id or 'system'}")
                    logger.info(f"Associated review task {review_task_id} marked as completed.")
                else:
                    logger.warning(f"No pending pitch_review task found for pitch_gen_id {pitch_gen_id}.")

                # 3. Update the corresponding pitch record's approval status
                pitch_record_query = """
                UPDATE pitches
                SET client_approval_status = 'approved',
                    pitch_state = 'ready_to_send'
                WHERE pitch_gen_id = $1
                RETURNING pitch_id;
                """
                updated_pitch_record = await conn.fetchrow(pitch_record_query, pitch_gen_id)
                if updated_pitch_record:
                    logger.info(f"Associated pitch record {updated_pitch_record['pitch_id']} updated to 'approved' and 'ready_to_send'.")
                else:
                    logger.warning(f"No associated pitch record found for pitch_gen_id {pitch_gen_id} to update approval status.")

                return updated_pitch_gen_dict

            except Exception as e:
                logger.exception(f"Error approving pitch generation {pitch_gen_id}: {e}")
                raise
