import logging
from typing import Any, Dict, Optional

from db_service_pg import get_db_pool

logger = logging.getLogger(__name__)

async def create_review_task_in_db(task_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Insert a new review task and return the created row."""
    query = """
    INSERT INTO review_tasks (
        task_type, related_id, campaign_id, assigned_to, status, notes
    ) VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                task_data["task_type"],
                task_data["related_id"],
                task_data.get("campaign_id"),
                task_data.get("assigned_to"),
                task_data.get("status", "pending"),
                task_data.get("notes"),
            )
            return dict(row) if row else None
        except Exception as e:
            logger.exception("Error creating review task: %s", e)
            raise
