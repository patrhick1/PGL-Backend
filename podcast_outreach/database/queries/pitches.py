import logging
from typing import Any, Dict, Optional, List
import uuid
from datetime import datetime

# Assuming db_service_pg.py is the central connection pool manager
from podcast_outreach.database.connection import get_db_pool

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
    pool = await get_db_pool()
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
    pool = await get_db_pool()
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

    pool = await get_db_pool()
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
    pool = await get_db_pool()
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
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, pitch_gen_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching pitch by pitch_gen_id {pitch_gen_id}: {e}")
            raise

async def count_pitches_by_state(pitch_states: List[str], person_id: Optional[int] = None) -> int:
    """Counts pitches matching given states, optionally filtered by person_id (via campaign)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            if not pitch_states:
                return 0
            
            state_placeholders = ', '.join([f'${i+1}' for i in range(len(pitch_states))])
            params = list(pitch_states)
            
            query_parts = ["SELECT COUNT(p.*) FROM pitches p"]
            
            if person_id is not None:
                query_parts.append("JOIN campaigns c ON p.campaign_id = c.campaign_id")
                query_parts.append(f"WHERE c.person_id = ${len(params) + 1} AND p.pitch_state IN ({state_placeholders})")
                params.append(person_id)
            else:
                query_parts.append(f"WHERE p.pitch_state IN ({state_placeholders})")

            query = " ".join(query_parts)
            count = await conn.fetchval(query, *params)
            return count if count is not None else 0
        except Exception as e:
            logger.exception(f"Error counting pitches by state (person_id: {person_id}, states: {pitch_states}): {e}")
            return 0

async def get_all_pitches_enriched(
    skip: int = 0, 
    limit: int = 100,
    campaign_id: Optional[uuid.UUID] = None,
    media_id: Optional[int] = None,
    pitch_states: Optional[List[str]] = None, # For IN clause
    client_approval_status: Optional[str] = None,
    person_id: Optional[int] = None # For filtering by client
) -> List[Dict[str, Any]]:
    """Fetches all pitches with optional filters and enrichment."""
    conditions = []
    params = []
    param_idx = 1

    select_clauses = [
        "p.*",
        "c.campaign_name",
        "m.name AS media_name",
        "cl.full_name AS client_name",
        "pg.draft_text" # Get draft_text from pitch_generations
    ]

    joins = [
        "LEFT JOIN campaigns c ON p.campaign_id = c.campaign_id",
        "LEFT JOIN media m ON p.media_id = m.media_id",
        "LEFT JOIN people cl ON c.person_id = cl.person_id",
        "LEFT JOIN pitch_generations pg ON p.pitch_gen_id = pg.pitch_gen_id"
    ]

    if campaign_id:
        conditions.append(f"p.campaign_id = ${param_idx}")
        params.append(campaign_id)
        param_idx += 1
    if media_id:
        conditions.append(f"p.media_id = ${param_idx}")
        params.append(media_id)
        param_idx += 1
    if pitch_states:
        # Create placeholders like ($2, $3, $4) for the IN clause
        state_placeholders = ", ".join([f"${param_idx + i}" for i in range(len(pitch_states))])
        conditions.append(f"p.pitch_state IN ({state_placeholders})")
        params.extend(pitch_states)
        param_idx += len(pitch_states)
    if client_approval_status:
        conditions.append(f"p.client_approval_status = ${param_idx}")
        params.append(client_approval_status)
        param_idx += 1
    if person_id: # Filter by client (person_id associated with the campaign)
        conditions.append(f"c.person_id = ${param_idx}")
        params.append(person_id)
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query_str = f"""
    SELECT {', '.join(select_clauses)}
    FROM pitches p
    {' '.join(joins)}
    WHERE {where_clause}
    ORDER BY p.created_at DESC
    OFFSET ${param_idx} LIMIT ${param_idx + 1};
    """
    params.extend([skip, limit])

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query_str, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching all enriched pitches: {e}")
            return []

# Ensure this function is removed or updated if get_all_pitches_enriched replaces its use cases
async def get_all_pitches_from_db(
    skip: int = 0, limit: int = 100,
    campaign_id: Optional[uuid.UUID] = None,
    media_id: Optional[int] = None,
    pitch_state: Optional[str] = None,
    client_approval_status: Optional[str] = None
) -> List[Dict[str, Any]]:
    logger.warning("get_all_pitches_from_db is being called. Consider using get_all_pitches_enriched for richer data.")
    # ... (keep existing implementation of get_all_pitches_from_db for now or deprecate)
    # For this exercise, I'll assume it's kept for any part of the code still using it without enrichment.
    conditions = []
    params = []
    param_idx = 1
    if campaign_id:
        conditions.append(f"campaign_id = ${param_idx}"); params.append(campaign_id); param_idx +=1
    if media_id:
        conditions.append(f"media_id = ${param_idx}"); params.append(media_id); param_idx +=1
    if pitch_state:
        conditions.append(f"pitch_state = ${param_idx}"); params.append(pitch_state); param_idx +=1
    if client_approval_status:
        conditions.append(f"client_approval_status = ${param_idx}"); params.append(client_approval_status); param_idx +=1

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"SELECT * FROM pitches WHERE {where_clause} ORDER BY created_at DESC OFFSET ${param_idx} LIMIT ${param_idx+1};"
    params.extend([skip, limit])
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching all pitches (un-enriched): {e}")
            return []

async def get_pitch_by_id_enriched(pitch_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a single pitch by its ID and enriches it with related data."""
    query = """
    SELECT 
        p.*,
        c.campaign_name,
        m.name AS media_name,
        cl.full_name AS client_name,
        pg.draft_text
    FROM pitches p
    LEFT JOIN campaigns c ON p.campaign_id = c.campaign_id
    LEFT JOIN media m ON p.media_id = m.media_id
    LEFT JOIN people cl ON c.person_id = cl.person_id
    LEFT JOIN pitch_generations pg ON p.pitch_gen_id = pg.pitch_gen_id
    WHERE p.pitch_id = $1;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, pitch_id)
            if not row:
                logger.debug(f"Enriched pitch not found: {pitch_id}")
                return None
            return dict(row)
        except Exception as e:
            logger.exception(f"Error fetching enriched pitch {pitch_id}: {e}")
            return None # Or raise