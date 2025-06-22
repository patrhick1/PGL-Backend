# podcast_outreach/api/routers/review_tasks.py

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from podcast_outreach.api.schemas import review_task_schemas
from podcast_outreach.api.schemas.discovery_schemas import EnhancedReviewTaskResponse, ReviewTaskApprovalRequest, ReviewTaskFilters
from podcast_outreach.database.queries import review_tasks as review_task_queries
from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
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
    task_status: Optional[str] = Query(None, description="Filter by task status (e.g., 'pending', 'approved', 'completed')"),
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
            status=task_status,
            assigned_to_id=assigned_to_id,
            campaign_id=campaign_id
        )
        return {"items": tasks, "total": total_count, "page": page, "size": size}
    except Exception as e:
        logger.exception(f"Error listing review tasks: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list review tasks.")

# 🚀 NEW ENHANCED ENDPOINTS FOR FRONTEND INTEGRATION

@router.get("/enhanced", 
           response_model=List[EnhancedReviewTaskResponse],
           summary="Get enhanced review tasks with full context")
async def get_enhanced_review_tasks(
    campaign_id: Optional[str] = Query(None, description="Filter by campaign ID"),
    task_type: Optional[str] = Query(None, description="Filter by task type (match_suggestion, pitch_review)"),
    status: Optional[str] = Query("pending", description="Filter by status (pending, approved, rejected)"),
    min_vetting_score: Optional[float] = Query(None, description="Minimum AI vetting score (0-10)"),
    limit: int = Query(20, description="Number of results", ge=1, le=100),
    offset: int = Query(0, description="Results to skip", ge=0),
    current_user: dict = Depends(get_current_user)
):
    """
    🎯 FRONTEND INTEGRATION: Get enhanced review tasks with full context for the approval interface.
    
    Returns:
    - Full AI vetting analysis and reasoning
    - Podcast details and metadata  
    - Campaign context
    - User-friendly recommendations
    - Discovery information
    """
    try:
        # Get review tasks with enhanced data
        enhanced_tasks = []
        
        # Get basic tasks first
        tasks, total = await review_task_queries.get_all_review_tasks_paginated(
            task_type=task_type,
            status=status,
            size=limit,
            offset=offset
        )
        
        for task in tasks:
            try:
                enhanced_task = await _build_enhanced_review_task(task)
                
                # Apply vetting score filter if specified
                if min_vetting_score and enhanced_task.vetting_score:
                    if enhanced_task.vetting_score < min_vetting_score:
                        continue
                
                # Apply campaign filter if specified  
                if campaign_id and str(enhanced_task.campaign_id) != campaign_id:
                    continue
                    
                enhanced_tasks.append(enhanced_task)
                
            except Exception as task_error:
                logger.warning(f"Error enhancing task {task.get('review_task_id')}: {task_error}")
                continue
        
        return enhanced_tasks
        
    except Exception as e:
        logger.exception(f"Error getting enhanced review tasks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get enhanced review tasks: {str(e)}"
        )

@router.post("/{review_task_id}/approve",
            response_model=EnhancedReviewTaskResponse,
            summary="Approve/reject review task")
async def approve_review_task(
    review_task_id: int,
    approval_data: ReviewTaskApprovalRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    🎯 FRONTEND INTEGRATION: Approve or reject a review task.
    
    For match_suggestion tasks:
    - approved: Creates outreach eligibility
    - rejected: Archives the match
    """
    try:
        # Get existing task
        existing_task = await review_task_queries.get_review_task_by_id_from_db(review_task_id)
        if not existing_task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review task not found")
        
        # Process the approval (this handles match suggestion updates, etc.)
        if existing_task.get('task_type') == 'match_suggestion' and approval_data.status in ['approved', 'rejected']:
            success = await review_task_queries.process_match_suggestion_approval(
                review_task_id=review_task_id,
                new_status=approval_data.status,
                approver_notes=approval_data.notes
            )
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to process match suggestion {approval_data.status}"
                )
        
        # Get the updated task with enhanced data
        updated_task = await review_task_queries.get_review_task_by_id_from_db(review_task_id)
        enhanced_task = await _build_enhanced_review_task(updated_task)
        
        return enhanced_task
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error approving review task {review_task_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve review task: {str(e)}"
        )

# Helper function to build enhanced review task responses
async def _build_enhanced_review_task(task: dict) -> EnhancedReviewTaskResponse:
    """Build enhanced review task with full context"""
    
    # Get campaign data
    campaign_data = None
    if task.get("campaign_id"):
        campaign_data = await campaign_queries.get_campaign_by_id(task["campaign_id"])
    
    # Get media data and discovery context
    media_data = None
    discovery_data = None
    
    if task.get("task_type") == "match_suggestion" and task.get("related_id"):
        # Get match suggestion to find media_id
        from podcast_outreach.database.queries import match_suggestions as match_queries
        match_data = await match_queries.get_match_suggestion_by_id(task["related_id"])
        
        if match_data and match_data.get("media_id"):
            media_data = await media_queries.get_media_by_id_from_db(match_data["media_id"])
            
            # Get discovery data for this campaign-media combo
            if task.get("campaign_id"):
                discovery_data = await cmd_queries.get_discovery_by_campaign_and_media(
                    task["campaign_id"], match_data["media_id"]
                )
    
    # Generate user-friendly recommendation
    recommendation = "Review Required"
    key_highlights = []
    potential_concerns = []
    
    if task.get("vetting_score"):
        score = task["vetting_score"]
        if score >= 8.0:
            recommendation = "Highly Recommended"
            key_highlights.append(f"Excellent vetting score ({score}/10)")
        elif score >= 6.5:
            recommendation = "Good Match"
            key_highlights.append(f"Good vetting score ({score}/10)")
        elif score >= 5.0:
            recommendation = "Acceptable Match"
            key_highlights.append(f"Meets minimum criteria ({score}/10)")
        else:
            recommendation = "Below Threshold"
            potential_concerns.append(f"Low vetting score ({score}/10)")
    
    # Add highlights from vetting criteria
    if task.get("vetting_criteria_met"):
        criteria = task["vetting_criteria_met"]
        if isinstance(criteria, dict):
            for criterion, met in criteria.items():
                if met:
                    key_highlights.append(f"✓ {criterion}")
                else:
                    potential_concerns.append(f"✗ {criterion}")
    
    return EnhancedReviewTaskResponse(
        review_task_id=task["review_task_id"],
        task_type=task["task_type"],
        related_id=task["related_id"],
        campaign_id=task["campaign_id"],
        status=task["status"],
        created_at=task["created_at"],
        completed_at=task.get("completed_at"),
        
        # Campaign context
        campaign_name=campaign_data.get("campaign_name") if campaign_data else None,
        client_name=campaign_data.get("client_name") if campaign_data else None,
        
        # Media information
        media_id=media_data.get("media_id") if media_data else None,
        media_name=media_data.get("name") if media_data else None,
        media_website=media_data.get("website") if media_data else None,
        media_image_url=media_data.get("image_url") if media_data else None,
        media_description=media_data.get("ai_description") or media_data.get("description") if media_data else None,
        
        # Discovery context
        discovery_keyword=discovery_data.get("discovery_keyword") if discovery_data else None,
        discovered_at=discovery_data.get("discovered_at") if discovery_data else None,
        
        # AI Vetting Results
        vetting_score=task.get("vetting_score"),
        vetting_reasoning=task.get("vetting_reasoning"),
        vetting_criteria_met=task.get("vetting_criteria_met"),
        
        # Match information
        match_score=task.get("match_score"),
        matched_keywords=task.get("matched_keywords"),
        best_matching_episode_id=task.get("best_matching_episode_id"),
        
        # User-friendly summary
        recommendation=recommendation,
        key_highlights=key_highlights[:5],  # Limit to top 5
        potential_concerns=potential_concerns[:3]  # Limit to top 3 concerns
    )