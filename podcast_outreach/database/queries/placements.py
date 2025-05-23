# podcast_outreach/database/queries/placements.py

import logging
from typing import Any, Dict, Optional, List
import uuid
from datetime import datetime

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool

logger = get_logger(__name__)

async def create_placement_in_db(placement_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    query = """
    INSERT INTO placements (
        campaign_id, media_id, current_status, status_ts, meeting_date,
        call_date, outreach_topic, recording_date, go_live_date, episode_link, notes
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
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
                placement_data.get('notes')
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
