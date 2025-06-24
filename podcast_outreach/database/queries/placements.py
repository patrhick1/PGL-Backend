# podcast_outreach/database/queries/placements.py
import logging
from typing import Any, Dict, Optional, List, Tuple
import uuid
from datetime import datetime

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool

logger = get_logger(__name__)

async def create_placement_in_db(placement_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    query = """
    INSERT INTO placements (
        campaign_id, media_id, current_status, status_ts, meeting_date,
        call_date, outreach_topic, recording_date, go_live_date, episode_link, notes, pitch_id
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
    ) RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                placement_data['campaign_id'],
                placement_data['media_id'],
                placement_data.get('current_status', 'pending'),
                placement_data.get('status_ts', datetime.utcnow()),
                placement_data.get('meeting_date'),
                placement_data.get('call_date'),
                placement_data.get('outreach_topic'),
                placement_data.get('recording_date'),
                placement_data.get('go_live_date'),
                placement_data.get('episode_link'),
                placement_data.get('notes'),
                placement_data.get('pitch_id') # New field
            )
            logger.info(f"Placement created: {row.get('placement_id')}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error creating placement for campaign {placement_data.get('campaign_id')} and media {placement_data.get('media_id')}: {e}")
            raise

async def get_placement_by_id(placement_id: int) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM placements WHERE placement_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, placement_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching placement {placement_id}: {e}")
            raise

async def update_placement_in_db(placement_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not update_data:
        logger.warning(f"No update data provided for placement {placement_id}.")
        return await get_placement_by_id(placement_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_data.items():
        if key == 'placement_id': continue
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses:
        return await get_placement_by_id(placement_id)
    
    # Always update status_ts if current_status is being updated
    if 'current_status' in update_data and 'status_ts' not in update_data:
        set_clauses.append(f"status_ts = ${idx}")
        values.append(datetime.utcnow())
        idx +=1

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE placements SET {set_clause_str} WHERE placement_id = ${idx} RETURNING *;"
    values.append(placement_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Placement {placement_id} updated with fields: {list(update_data.keys())}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error updating placement {placement_id}: {e}")
            raise

async def delete_placement_from_db(placement_id: int) -> bool:
    query = "DELETE FROM placements WHERE placement_id = $1 RETURNING placement_id;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            deleted_row = await conn.fetchval(query, placement_id)
            if deleted_row is not None:
                logger.info(f"Placement deleted: {placement_id}")
                return True
            logger.warning(f"Placement not found for deletion or delete failed: {placement_id}")
            return False
        except Exception as e:
            logger.exception(f"Error deleting placement {placement_id} from DB: {e}")
            raise

async def get_placements_for_campaign(campaign_id: uuid.UUID) -> List[Dict[str, Any]]:
    """Fetches all placement records for a specific campaign_id."""
    query = "SELECT * FROM placements WHERE campaign_id = $1 ORDER BY created_at DESC;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, campaign_id)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching placements for campaign {campaign_id}: {e}")
            return []

async def get_placements_paginated(
    campaign_id: Optional[uuid.UUID] = None,
    page: int = 1,
    size: int = 20
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetches placements with pagination, optionally filtered by campaign_id."""
    offset = (page - 1) * size
    
    base_query = "FROM placements"
    conditions = []
    params = []
    
    if campaign_id:
        conditions.append(f"campaign_id = ${len(params) + 1}")
        params.append(campaign_id)
        
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    query = f"""
        SELECT * {base_query} {where_clause}
        ORDER BY created_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2};
    """
    params.extend([size, offset])
    
    count_query = f"SELECT COUNT(*) AS total {base_query} {where_clause};"
    count_params = params[:-2] # Exclude limit and offset for count

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, *params)
            total_record = await conn.fetchrow(count_query, *count_params)
            total = total_record['total'] if total_record else 0
            return [dict(row) for row in rows], total
        except Exception as e:
            logger.exception(f"Error fetching paginated placements: {e}")
            return [], 0

async def get_placements_for_person_paginated(
    person_id: int,
    campaign_id_filter: Optional[uuid.UUID] = None, # Optional: further filter by specific campaign of this person
    page: int = 1,
    size: int = 20
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetches placements for all campaigns belonging to a specific person, with pagination."""
    offset = (page - 1) * size
    
    base_query = """
        FROM placements p
        JOIN campaigns c ON p.campaign_id = c.campaign_id
        WHERE c.person_id = $1
    """
    params = [person_id]
    
    conditions = []
    if campaign_id_filter:
        conditions.append(f"p.campaign_id = ${len(params) + 1}")
        params.append(campaign_id_filter)
        
    where_clause_additional = " AND " + " AND ".join(conditions) if conditions else ""

    query = f"""
        SELECT p.* {base_query} {where_clause_additional}
        ORDER BY p.created_at DESC
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2};
    """
    params.extend([size, offset])
    
    count_query = f"SELECT COUNT(p.*) AS total {base_query} {where_clause_additional};"
    count_params = params[:-2]

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, *params)
            total_record = await conn.fetchrow(count_query, *count_params)
            total = total_record['total'] if total_record else 0
            return [dict(row) for row in rows], total
        except Exception as e:
            logger.exception(f"Error fetching paginated placements for person {person_id}: {e}")
            return [], 0
        
async def count_placements_by_status(statuses: List[str], person_id: Optional[int] = None) -> int:
    """Counts placements matching given statuses, optionally filtered by person_id (via campaign)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            if not statuses:
                return 0
            
            status_placeholders = ', '.join([f'${i+1}' for i in range(len(statuses))])
            params = list(statuses)
            
            query_parts = [f"SELECT COUNT(p.*) FROM placements p"]
            
            if person_id is not None:
                query_parts.append("JOIN campaigns c ON p.campaign_id = c.campaign_id")
                query_parts.append(f"WHERE c.person_id = ${len(params) + 1} AND p.current_status IN ({status_placeholders})")
                params.append(person_id)
            else:
                query_parts.append(f"WHERE p.current_status IN ({status_placeholders})")

            query = " ".join(query_parts)
            count = await conn.fetchval(query, *params)
            return count if count is not None else 0
        except Exception as e:
            logger.exception(f"Error counting placements by status (person_id: {person_id}, statuses: {statuses}): {e}")
            return 0

async def get_placements_paginated( # Modified to accept person_id_for_campaign_filter
    campaign_id: Optional[uuid.UUID] = None,
    person_id_for_campaign_filter: Optional[int] = None, # New parameter
    page: int = 1,
    size: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "DESC"
) -> Tuple[List[Dict[str, Any]], int]:
    offset = (page - 1) * size
    
    valid_sort_columns = ["created_at", "status_ts", "meeting_date", "recording_date", "go_live_date"]
    if sort_by not in valid_sort_columns:
        sort_by = "created_at"
    sort_order_sql = "DESC" if sort_order.upper() == "DESC" else "ASC"

    base_query_select = "SELECT p.*"
    base_query_from = "FROM placements p"
    conditions = []
    params = []
    
    if person_id_for_campaign_filter is not None:
        base_query_from += " JOIN campaigns c ON p.campaign_id = c.campaign_id"
        conditions.append(f"c.person_id = ${len(params) + 1}")
        params.append(person_id_for_campaign_filter)

    if campaign_id: # Can be used in conjunction with person_id_for_campaign_filter
        conditions.append(f"p.campaign_id = ${len(params) + 1}")
        params.append(campaign_id)
        
    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
    
    query = f"""
        {base_query_select} {base_query_from} {where_clause}
        ORDER BY p.{sort_by} {sort_order_sql} NULLS LAST
        LIMIT ${len(params) + 1} OFFSET ${len(params) + 2};
    """
    params.extend([size, offset])
    
    count_query = f"SELECT COUNT(p.*) AS total {base_query_from} {where_clause};"
    count_params = params[:-2] 

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, *params)
            total_record = await conn.fetchrow(count_query, *count_params)
            total = total_record['total'] if total_record else 0
            return [dict(row) for row in rows], total
        except Exception as e:
            logger.exception(f"Error fetching paginated placements: {e}")
            return [], 0