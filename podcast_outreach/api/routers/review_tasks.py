# podcast_outreach/api/routers/review_tasks.py

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from podcast_outreach.api.schemas import review_task_schemas
from podcast_outreach.database.queries import review_tasks as review_task_queries
from podcast_outreach.api.dependencies import get_current_user # Assuming you have this dependency

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/review-tasks",
    tags=["Review Tasks"],
    # dependencies=[Depends(get_current_user)] # Add authentication if needed for all routes
)

@router.post("/", response_model=review_task_schemas.ReviewTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_review_task(
    task_data: review_task_schemas.ReviewTaskCreate,
    current_user: dict = Depends(get_current_user) # Or a more specific admin/staff check
):
    """Create a new review task. 
    Primarily for system internal use when a reviewable event occurs (e.g., match suggestion, pitch generation).
    Humans might not create these directly often but could via admin interfaces."""
    try:
        # The schema uses assigned_to_id, but db query expects assigned_to
        db_task_data = task_data.dict(exclude_unset=True)
        if 'assigned_to_id' in db_task_data:
            db_task_data['assigned_to'] = db_task_data.pop('assigned_to_id')
        
        created_task = await review_task_queries.create_review_task_in_db(db_task_data)
        if not created_task:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create review task in database.")
        return created_task
    except Exception as e:
        logger.exception(f"Error creating review task: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/{review_task_id}", response_model=review_task_schemas.ReviewTaskResponse)
async def get_review_task(
    review_task_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific review task by its ID."""
    task = await review_task_queries.get_review_task_by_id_from_db(review_task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review task not found")
    return task

@router.patch("/{review_task_id}", response_model=review_task_schemas.ReviewTaskResponse)
async def update_review_task(
    review_task_id: int,
    update_data: review_task_schemas.ReviewTaskUpdate,
    current_user: dict = Depends(get_current_user) # User who performs the update
):
    """Update a review task. This is the primary endpoint for users to approve, reject, or reassign tasks."""
    existing_task = await review_task_queries.get_review_task_by_id_from_db(review_task_id)
    if not existing_task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review task not found")

    # For status updates, we might trigger specific processing logic
    if update_data.status:
        if existing_task.get('task_type') == 'match_suggestion' and update_data.status in ['approved', 'rejected']:
            success = await review_task_queries.process_match_suggestion_approval(
                review_task_id=review_task_id,
                new_status=update_data.status,
                approver_notes=update_data.notes
            )
            if not success:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                                    detail=f"Failed to process match suggestion {update_data.status}.")
            # Fetch the updated task to return the final state including completed_at
            updated_task_after_processing = await review_task_queries.get_review_task_by_id_from_db(review_task_id)
            return updated_task_after_processing
        
        elif existing_task.get('task_type') == 'pitch_review' and update_data.status == 'completed': # or 'approved'
            # Assuming pitch approval updates the pitch_generation and then the review task
            # This logic might be in pitch_generations.approve_pitch_generation which calls update_review_task_status_in_db
            # So, if we call that from here, ensure it doesn't create a loop.
            # For now, a simple status update. The specific approval logic for pitches is in the pitch_generations router.
            # If direct pitch approval from here is needed, wire it similarly to match_suggestion_approval.
            updated_task = await review_task_queries.update_review_task_status_in_db(
                review_task_id=review_task_id,
                status=update_data.status,
                notes=update_data.notes
            )
            if not updated_task:
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update review task status to {update_data.status}")
            return updated_task
        else:
            # Generic status update if no special processing is defined for this task_type/status combination
            updated_task = await review_task_queries.update_review_task_status_in_db(
                review_task_id=review_task_id,
                status=update_data.status,
                notes=update_data.notes # Pass notes for generic updates too
            )
            if not updated_task:
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update review task status to {update_data.status}")
            return updated_task
    else:
        # If only notes or assignment is being changed, without a status change that triggers a workflow.
        # Note: update_review_task_status_in_db is designed for status changes. Need a more generic update for other fields.
        # For simplicity, let's assume updates always involve a status or use notes with a status.
        # If only notes/assignment change is needed without status change, a different DB query might be better.
        # This current structure implies status is key for updates via this endpoint.
        # Or, we can call update_review_task_status_in_db by passing the *existing* status if only notes/assignee changes.
        current_status = existing_task['status']
        updated_task = await review_task_queries.update_review_task_status_in_db(
                review_task_id=review_task_id,
                status=current_status, # Keep current status if not provided in update_data
                notes=update_data.notes
            )
        # Add assignment logic if update_data.assigned_to_id is present - this needs a separate DB query or an extended one.
        # For now, focusing on status and notes. Assignment changes would require extending update_review_task_status_in_db or a new function.
        if not updated_task:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update review task.")
        return updated_task


@router.get("/", response_model=review_task_schemas.PaginatedReviewTaskList)
async def list_review_tasks(
    current_user: dict = Depends(get_current_user),
    task_type: Optional[str] = Query(None, description="Filter by task type (e.g., 'match_suggestion', 'pitch_review')"),
    status: Optional[str] = Query(None, description="Filter by task status (e.g., 'pending', 'approved', 'completed')"),
    assigned_to_id: Optional[int] = Query(None, description="Filter by ID of the person assigned"),
    campaign_id: Optional[str] = Query(None, description="Filter by campaign UUID"), # Keep as str for Query
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Number of items per page")
):
    """List review tasks with filtering and pagination."""
    try:
        tasks, total_count = await review_task_queries.get_all_review_tasks_paginated(
            page=page,
            size=size,
            task_type=task_type,
            status=status,
            assigned_to_id=assigned_to_id,
            campaign_id=campaign_id
        )
        return {"items": tasks, "total": total_count, "page": page, "size": size}
    except Exception as e:
        logger.exception(f"Error listing review tasks: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list review tasks.")

# TODO: Add a GET endpoint to list review tasks with filtering and pagination.
# Example:
# @router.get("/", response_model=review_task_schemas.PaginatedReviewTaskList)
# async def list_review_tasks(
#     current_user: dict = Depends(get_current_user),
#     task_type: Optional[str] = Query(None),
#     status: Optional[str] = Query(None),
#     assigned_to_id: Optional[int] = Query(None),
#     page: int = Query(1, ge=1),
#     size: int = Query(20, ge=1, le=100)
# ):
#     # Implement database query to fetch tasks with filters and pagination
#     # tasks, total_count = await review_task_queries.get_all_review_tasks_paginated(...)
#     # return {"items": tasks, "total": total_count, "page": page, "size": size}
#     pass 