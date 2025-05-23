"""Campaign related database queries."""
from typing import Dict, Any, Optional, List
import uuid
from datetime import datetime

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool

logger = get_logger(__name__)

async def create_campaign_in_db(campaign_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    query = """
    INSERT INTO campaigns (
        campaign_id, person_id, attio_client_id, campaign_name, campaign_type,
        campaign_bio, campaign_angles, campaign_keywords, compiled_social_posts,
        podcast_transcript_link, compiled_articles_link, mock_interview_trancript,
        start_date, end_date, goal_note, media_kit_url, instantly_campaign_id
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17
    ) RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            keywords = campaign_data.get("campaign_keywords", []) or []
            row = await conn.fetchrow(
                query,
                campaign_data['campaign_id'], campaign_data['person_id'], campaign_data.get('attio_client_id'),
                campaign_data['campaign_name'], campaign_data.get('campaign_type'),
                campaign_data.get('campaign_bio'), campaign_data.get('campaign_angles'), keywords,
                campaign_data.get('compiled_social_posts'), campaign_data.get('podcast_transcript_link'),
                campaign_data.get('compiled_articles_link'), campaign_data.get('mock_interview_trancript'),
                campaign_data.get('start_date'), campaign_data.get('end_date'),
                campaign_data.get('goal_note'), campaign_data.get('media_kit_url'),
                campaign_data.get('instantly_campaign_id') # New field
            )
            logger.info(f"Campaign created: {campaign_data.get('campaign_id')}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error creating campaign (ID: {campaign_data.get('campaign_id')}) in DB: {e}")
            raise

async def get_campaign_by_id(campaign_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM campaigns WHERE campaign_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id)
            if not row:
                logger.warning(f"Campaign not found: {campaign_id}")
                return None
            return dict(row)
        except Exception as e:
            logger.exception(f"Error fetching campaign {campaign_id}: {e}")
            raise

async def get_all_campaigns_from_db(skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    query = "SELECT * FROM campaigns ORDER BY created_at DESC OFFSET $1 LIMIT $2;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, skip, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching all campaigns: {e}")
            raise

async def update_campaign(campaign_id: uuid.UUID, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not update_fields:
        logger.warning(f"No update data for campaign {campaign_id}. Fetching current.")
        return await get_campaign_by_id(campaign_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_fields.items():
        if key == "campaign_keywords" and val is not None and not isinstance(val, list):
            keywords_list = [kw.strip() for kw in str(val).split(',') if kw.strip()]
            if not keywords_list and str(val).strip():
                keywords_list = [kw.strip() for kw in str(val).split() if kw.strip()]
            val = keywords_list

        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses:
        return await get_campaign_by_id(campaign_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE campaigns SET {set_clause_str} WHERE campaign_id = ${idx} RETURNING *;"
    values.append(campaign_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Campaign updated: {campaign_id} with fields: {list(update_fields.keys())}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error updating campaign {campaign_id}: {e}")
            raise

async def delete_campaign_from_db(campaign_id: uuid.UUID) -> bool:
    query = "DELETE FROM campaigns WHERE campaign_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, campaign_id)
            deleted_count = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
            if deleted_count > 0:
                logger.info(f"Campaign deleted: {campaign_id}")
                return True
            logger.warning(f"Campaign not found for deletion or delete failed: {campaign_id}")
            return False
        except Exception as e:
            logger.exception(f"Error deleting campaign {campaign_id} from DB: {e}")
            raise
