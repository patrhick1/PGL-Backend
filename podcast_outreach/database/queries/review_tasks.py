import logging
from typing import Any, Dict, Optional, List
from datetime import datetime

from db_service_pg import get_db_pool # Still importing from root db_service_pg for now
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
