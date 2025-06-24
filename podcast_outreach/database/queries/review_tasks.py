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
    campaign_id: Optional[str] = None 
) -> tuple[List[Dict[str, Any]], int]:
    """Fetches review tasks with filtering, pagination, and enrichment for pitch_review tasks."""
    offset = (page - 1) * size
    
    select_clauses = [
        "rt.*",
        "c.campaign_name",
        "p.full_name AS client_name",
        # Media name - from either pitch or match suggestion
        "COALESCE(m_pitch.name, m_match.name) AS media_name",
        # Pitch review fields
        "pg.draft_text",
        "pch.subject_line", 
        "pg.media_id AS pitch_media_id",
        # Match suggestion AI fields
        "ms.ai_reasoning",
        "ms.vetting_score",
        "ms.vetting_reasoning",
        "ms.vetting_checklist",
        "ms.match_score",
        "ms.media_id AS match_media_id"
    ]
    
    joins = [
        "LEFT JOIN campaigns c ON rt.campaign_id = c.campaign_id",
        "LEFT JOIN people p ON c.person_id = p.person_id",
        # Conditional joins for pitch_review related data
        "LEFT JOIN pitch_generations pg ON rt.task_type = 'pitch_review' AND rt.related_id = pg.pitch_gen_id",
        "LEFT JOIN pitches pch ON pg.pitch_gen_id = pch.pitch_gen_id",
        "LEFT JOIN media m_pitch ON pg.media_id = m_pitch.media_id",
        # Conditional joins for match_suggestion related data
        "LEFT JOIN match_suggestions ms ON rt.task_type = 'match_suggestion' AND rt.related_id = ms.match_id",
        "LEFT JOIN media m_match ON ms.media_id = m_match.media_id"
    ]
    
    # Note: If task_type is 'match_suggestion', media_name would come from a different join:
    # LEFT JOIN match_suggestions ms ON rt.task_type = 'match_suggestion' AND rt.related_id = ms.match_id
    # LEFT JOIN media m_match ON ms.media_id = m_match.media_id (and select m_match.name)
    # For simplicity, this query prioritizes enrichment for 'pitch_review'. 
    # A more complex query or separate functions might be needed for fully polymorphic enrichment.

    conditions = []
    params = []
    param_idx = 1

    if task_type:
        conditions.append(f"rt.task_type = ${param_idx}")
        params.append(task_type)
        param_idx += 1
    if status:
        conditions.append(f"rt.status = ${param_idx}")
        params.append(status)
        param_idx += 1
    if assigned_to_id is not None:
        conditions.append(f"rt.assigned_to = ${param_idx}")
        params.append(assigned_to_id)
        param_idx += 1
    if campaign_id:
        conditions.append(f"rt.campaign_id = ${param_idx}") # campaign_id on review_tasks table
        params.append(campaign_id)
        param_idx += 1

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query_string = f"""
    SELECT {', '.join(select_clauses)}
    FROM review_tasks rt
    {' '.join(joins)}
    WHERE {where_clause}
    ORDER BY COALESCE(ms.vetting_score, ms.match_score, 0) DESC, rt.created_at DESC
    LIMIT ${param_idx} OFFSET ${param_idx + 1};
    """
    params_for_query = params + [size, offset]
    
    count_query_string = f"""
    SELECT COUNT(rt.*) AS total
    FROM review_tasks rt
    {' '.join(joins)}  -- Apply same joins for accurate count if filters span joined tables, though less critical for base count
    WHERE {where_clause};
    """
    params_for_count = params # Count query doesn't need limit/offset params

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query_string, *params_for_query)
            total_record = await conn.fetchrow(count_query_string, *params_for_count)
            total = total_record['total'] if total_record else 0
            
            # Adapt the returned dictionary to include appropriate IDs and media_id for different task types
            results = []
            for row in rows:
                r = dict(row)
                if r.get('task_type') == 'pitch_review':
                    r['pitch_gen_id'] = r.get('related_id')
                    r['media_id'] = r.get('pitch_media_id')
                elif r.get('task_type') == 'match_suggestion':
                    r['media_id'] = r.get('match_media_id')
                    # The AI fields are already included from the SELECT clause
                results.append(r)
            return results, total
        except Exception as e:
            logger.exception(f"Error fetching paginated and enriched review tasks: {e}")
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

async def get_pending_review_task_by_related_id_and_type(
    related_id: int,
    task_type: str
) -> Optional[Dict[str, Any]]:
    """Fetches a PENDING review task by its related_id and task_type."""
    query = """
    SELECT *
    FROM review_tasks
    WHERE related_id = $1 AND task_type = $2 AND status = 'pending'
    LIMIT 1;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, related_id, task_type)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching pending review task by related_id {related_id} and type {task_type}: {e}")
            return None

async def complete_review_tasks_for_match(match_id: int, completion_notes: str = None) -> bool:
    """Complete all pending review tasks for a specific match."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            query_string = """
            UPDATE review_tasks 
            SET status = 'completed', 
                notes = COALESCE($2, notes),
                completed_at = NOW()
            WHERE related_id = $1 
            AND task_type IN ('match_suggestion', 'match_suggestion_vetting')
            AND status = 'pending'
            RETURNING review_task_id;
            """
            results = await conn.fetch(query_string, match_id, completion_notes)
            completed_count = len(results)
            
            if completed_count > 0:
                logger.info(f"Completed {completed_count} review tasks for match {match_id}")
                return True
            else:
                logger.debug(f"No pending review tasks found for match {match_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error completing review tasks for match {match_id}: {e}")
            return False
