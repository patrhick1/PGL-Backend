import logging
from typing import Any, Dict, Optional, List
from datetime import datetime

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import match_suggestions # For process_match_suggestion_approval

logger = logging.getLogger(__name__)

async def create_review_task_in_db(task_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Creates a new review task in the database."""
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
                task_data['task_type'],
                task_data['related_id'],
                task_data.get('campaign_id'), # campaign_id can be None for other task types potentially
                task_data.get('assigned_to'),
                task_data.get('status', 'pending'), # Default status if not provided
                task_data.get('notes')
            )
            if row:
                logger.info(f"ReviewTask created for type '{row['task_type']}' related_id {row['related_id']}")
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error creating ReviewTask in DB: {e}")
            raise

async def update_review_task_status_in_db(review_task_id: int, status: str, notes: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Updates the status and completed_at timestamp of a review task. Optionally updates notes."""
    set_clauses = ["status = $1", "completed_at = NOW()"]
    values = [status]
    idx = 2 # Start parameter index from $2

    if notes is not None:
        set_clauses.append(f"notes = ${idx}")
        values.append(notes)
        idx += 1

    query = f"""
    UPDATE review_tasks
    SET {', '.join(set_clauses)}
    WHERE review_task_id = ${idx}
    RETURNING *;
    """
    values.append(review_task_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            if row:
                logger.info(f"ReviewTask ID {review_task_id} updated to status '{status}'.")
                return dict(row)
            logger.warning(f"ReviewTask ID {review_task_id} not found for update.")
            return None
        except Exception as e:
            logger.exception(f"Error updating ReviewTask ID {review_task_id}: {e}")
            raise

async def get_review_task_by_id_from_db(review_task_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a review task by its ID."""
    query = "SELECT * FROM review_tasks WHERE review_task_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, review_task_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching ReviewTask by ID {review_task_id}: {e}")
            raise

async def process_match_suggestion_approval(review_task_id: int, new_status: str, approver_notes: Optional[str] = None) -> bool:
    """Processes the approval/rejection of a review task, specifically handling match_suggestion approvals."""
    
    # Step 1: Fetch the review task to get its details (like task_type and related_id)
    review_task = await get_review_task_by_id_from_db(review_task_id)
    if not review_task:
        logger.error(f"ReviewTask ID {review_task_id} not found. Cannot process approval.")
        return False

    # Step 2: Update the review task itself
    updated_review_task = await update_review_task_status_in_db(review_task_id, new_status, approver_notes)
    if not updated_review_task:
        logger.error(f"Failed to update ReviewTask ID {review_task_id}. Aborting further processing.")
        return False

    logger.info(f"ReviewTask ID {review_task_id} status updated to '{new_status}'.")

    # Step 3: If the task was a 'match_suggestion' and it was 'approved', update the match_suggestion table
    if review_task.get('task_type') == 'match_suggestion' and new_status == 'approved':
        related_match_id = review_task.get('related_id')
        if related_match_id is None:
            logger.error(f"ReviewTask ID {review_task_id} is a match_suggestion but has no related_id. Cannot approve match.")
            return False # Or raise an error for data inconsistency
        
        # This calls a function in match_suggestions.py, which is correct.
        approved_match = await match_suggestions.approve_match_and_create_pitch_task(related_match_id)
        if not approved_match:
            logger.error(f"Failed to approve MatchSuggestion ID {related_match_id} linked to ReviewTask ID {review_task_id}.")
            # Potentially consider rolling back the review_task update or setting its status to an error state
            return False
        logger.info(f"Successfully approved MatchSuggestion ID {related_match_id} as part of ReviewTask ID {review_task_id} approval.")
    
    elif review_task.get('task_type') == 'match_suggestion' and new_status == 'rejected':
        related_match_id = review_task.get('related_id')
        if related_match_id:
             # Example: update match_suggestions.status to 'rejected'
             # await match_suggestions.update_match_suggestion_in_db(related_match_id, {'status': 'rejected', 'client_approved': False})
             logger.info(f"MatchSuggestion ID {related_match_id} (from ReviewTask {review_task_id}) was marked as '{new_status}'. Additional logic for match_suggestions update can be added here.")
        else:
            logger.warning(f"ReviewTask ID {review_task_id} (match_suggestion) was rejected but has no related_id.")

    return True

async def get_all_review_tasks_paginated(
    page: int = 1,
    size: int = 20,
    task_type: Optional[str] = None,
    status: Optional[str] = None,
    assigned_to_id: Optional[int] = None,
    campaign_id: Optional[str] = None # Assuming campaign_id is UUID, but comes as str from query param
) -> tuple[List[Dict[str, Any]], int]:
    """Fetches review tasks with filtering and pagination."""
    offset = (page - 1) * size
    
    conditions = []
    params = []
    param_idx = 1

    if task_type:
        conditions.append(f"task_type = ${param_idx}")
        params.append(task_type)
        param_idx += 1
    if status:
        conditions.append(f"status = ${param_idx}")
        params.append(status)
        param_idx += 1
    if assigned_to_id is not None:
        conditions.append(f"assigned_to = ${param_idx}")
        params.append(assigned_to_id)
        param_idx += 1
    if campaign_id:
        conditions.append(f"campaign_id = ${param_idx}")
        params.append(campaign_id) # Keep as string, asyncpg handles UUID conversion if column is UUID
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    base_query = "FROM review_tasks WHERE " + where_clause
    
    query = f"SELECT * {base_query} ORDER BY created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1};"
    params.extend([size, offset])
    
    count_query = f"SELECT COUNT(*) AS total {base_query};"
    # Params for count_query are the same as for the main query, excluding limit and offset
    count_params = params[:-2] if len(params) > 1 else [] 

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, *params)
            total_record = await conn.fetchrow(count_query, *count_params)
            total = total_record['total'] if total_record else 0
            return [dict(row) for row in rows], total
        except Exception as e:
            logger.exception(f"Error fetching paginated review tasks: {e}")
            return [], 0
        
async def count_review_tasks_by_status(status: str, person_id: Optional[int] = None) -> int:
    """Counts review tasks by status, optionally filtered by person_id (via campaign)."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            base_query = "SELECT COUNT(rt.*) FROM review_tasks rt"
            params = [status]
            conditions = [f"rt.status = $1"]

            if person_id is not None:
                base_query += " JOIN campaigns c ON rt.campaign_id = c.campaign_id"
                conditions.append(f"c.person_id = ${len(params) + 1}")
                params.append(person_id)
            
            where_clause = "WHERE " + " AND ".join(conditions)
            query = f"{base_query} {where_clause};"
            
            count = await conn.fetchval(query, *params)
            return count if count is not None else 0
        except Exception as e:
            logger.exception(f"Error counting review tasks (person_id: {person_id}, status: {status}): {e}")
            return 0
