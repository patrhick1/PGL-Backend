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
    min_vetting_score: Optional[int] = Query(None, ge=0, le=100, description="Minimum AI vetting score (0-100)"),
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
        
        # OWNERSHIP FILTER: For clients, get their campaigns first
        client_campaign_ids = None
        if current_user.get("role") == "client":
            # Get all campaigns owned by this client
            client_campaigns = await campaign_queries.get_campaigns_by_person_id(current_user.get("person_id"))
            client_campaign_ids = [str(c["campaign_id"]) for c in client_campaigns]
            
            # If they specified a campaign_id, verify they own it
            if campaign_id and campaign_id not in client_campaign_ids:
                # Return empty list if they're trying to access a campaign they don't own
                return []
        
        # Get basic tasks first
        # Convert offset to page number
        page = (offset // limit) + 1 if limit > 0 else 1
        
        # For clients, we need to fetch tasks for ALL their campaigns
        # We can't paginate properly if filtering happens after fetching
        if client_campaign_ids and not campaign_id:
            # Fetch ALL tasks for all client's campaigns (no limit per campaign)
            all_tasks = []
            for camp_id in client_campaign_ids:
                # Fetch ALL tasks for this campaign by using a very high limit
                camp_tasks, camp_total = await review_task_queries.get_all_review_tasks_paginated(
                    task_type=task_type,
                    status=status,
                    page=1,
                    size=10000,  # High limit to get all tasks for the campaign
                    campaign_id=camp_id
                )
                all_tasks.extend(camp_tasks)
            
            # Sort by creation date (newest first) and vetting score
            all_tasks.sort(key=lambda x: (x.get('created_at', ''), x.get('vetting_score', 0)), reverse=True)
            
            # Apply pagination to the combined results
            total = len(all_tasks)
            tasks = all_tasks[offset:offset + limit]
        else:
            # Standard query for non-clients or when campaign_id is specified
            tasks, total = await review_task_queries.get_all_review_tasks_paginated(
                task_type=task_type,
                status=status,
                page=page,
                size=limit,
                campaign_id=campaign_id
            )
        
        for task in tasks:
            try:
                enhanced_task = await _build_enhanced_review_task(task)
                
                # Apply vetting score filter if specified
                if min_vetting_score and enhanced_task.vetting_score:
                    if enhanced_task.vetting_score < min_vetting_score:
                        continue
                
                # Apply campaign filter if specified (shouldn't happen as we filter at query level)
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
    
    # OWNERSHIP CHECK: Ensure clients can only update tasks for their own campaigns
    if current_user.get("role") == "client":
        campaign = await campaign_queries.get_campaign_by_id(existing_task.get("campaign_id"))
        if not campaign or campaign.get("person_id") != current_user.get("person_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update tasks for this campaign"
            )

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
        
        # OWNERSHIP CHECK: Ensure clients can only approve their own campaigns
        if current_user.get("role") == "client":
            # Get the campaign associated with this review task
            campaign = await campaign_queries.get_campaign_by_id(existing_task.get("campaign_id"))
            if not campaign:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, 
                    detail="Campaign not found for this review task"
                )
            
            # Check if the client owns this campaign
            if campaign.get("person_id") != current_user.get("person_id"):
                logger.warning(
                    f"Client {current_user.get('username')} attempted to approve task "
                    f"{review_task_id} for campaign they don't own"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to approve tasks for this campaign"
                )
        # Staff and admin users can approve any task (no additional check needed)
        
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
        
        # Handle pitch review approvals (frontend sends 'approved', we mark as 'completed')
        elif existing_task.get('task_type') == 'pitch_review' and approval_data.status == 'approved':
            # Import pitch_generations queries
            from podcast_outreach.database.queries import pitch_generations as pitch_gen_queries
            
            # Get the pitch generation ID from metadata
            pitch_gen_id = existing_task.get('metadata', {}).get('pitch_generation_id')
            if not pitch_gen_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No pitch generation ID found in review task metadata"
                )
            
            # Approve the pitch generation
            success = await pitch_gen_queries.approve_pitch_generation(
                pitch_gen_id=pitch_gen_id,
                reviewer_id=current_user.get('person_id')
            )
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to approve pitch generation"
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
    match_data = None
    pitch_gen_data = None
    pitch_data = None
    
    if task.get("task_type") == "match_suggestion" and task.get("related_id"):
        # Get match suggestion to find media_id
        from podcast_outreach.database.queries import match_suggestions as match_queries
        match_data = await match_queries.get_match_suggestion_by_id_from_db(task["related_id"])
        
        if match_data and match_data.get("media_id"):
            media_data = await media_queries.get_media_by_id_from_db(match_data["media_id"])
            
            # Get discovery data for this campaign-media combo
            if task.get("campaign_id"):
                discovery_data = await cmd_queries.get_discovery_by_campaign_and_media(
                    task["campaign_id"], match_data["media_id"]
                )
    
    elif task.get("task_type") == "pitch_review" and task.get("related_id"):
        # For pitch review, related_id is the pitch_gen_id
        from podcast_outreach.database.queries import pitch_generations as pitch_gen_queries
        from podcast_outreach.database.queries import pitches as pitch_queries
        
        pitch_gen_data = await pitch_gen_queries.get_pitch_generation_by_id(task["related_id"])
        
        if pitch_gen_data:
            # Get the associated pitch record
            pitch_data = await pitch_queries.get_pitch_by_pitch_gen_id(task["related_id"])
            
            # Get media data
            if pitch_gen_data.get("media_id"):
                media_data = await media_queries.get_media_by_id_from_db(pitch_gen_data["media_id"])
            
            # Get match data to inherit vetting information
            if pitch_data and pitch_data.get("matched_keywords"):
                # Try to find the original match suggestion
                from podcast_outreach.database.queries import match_suggestions as match_queries
                if task.get("campaign_id") and pitch_gen_data.get("media_id"):
                    match_data = await match_queries.get_match_suggestion_by_campaign_and_media_ids(
                        task["campaign_id"], pitch_gen_data["media_id"]
                    )
    
    # Generate user-friendly recommendation
    recommendation = "Review Required"
    key_highlights = []
    potential_concerns = []
    
    if task.get("vetting_score"):
        score = task["vetting_score"]
        if score >= 80:
            recommendation = "Highly Recommended"
            key_highlights.append(f"Excellent vetting score ({score}/100)")
        elif score >= 65:
            recommendation = "Good Match"
            key_highlights.append(f"Good vetting score ({score}/100)")
        elif score >= 50:
            recommendation = "Acceptable Match"
            key_highlights.append(f"Meets minimum criteria ({score}/100)")
        else:
            recommendation = "Below Threshold"
            potential_concerns.append(f"Low vetting score ({score}/100)")
    
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
        host_names=media_data.get("host_names") if media_data else None,
        
        # Social media handles
        podcast_twitter_url=media_data.get("podcast_twitter_url") if media_data else None,
        podcast_linkedin_url=media_data.get("podcast_linkedin_url") if media_data else None,
        podcast_instagram_url=media_data.get("podcast_instagram_url") if media_data else None,
        podcast_facebook_url=media_data.get("podcast_facebook_url") if media_data else None,
        podcast_youtube_url=media_data.get("podcast_youtube_url") if media_data else None,
        podcast_tiktok_url=media_data.get("podcast_tiktok_url") if media_data else None,
        
        # Discovery context
        discovery_keyword=discovery_data.get("discovery_keyword") if discovery_data else None,
        discovered_at=discovery_data.get("discovered_at") if discovery_data else None,
        
        # AI Vetting Results (from task or match_data)
        vetting_score=task.get("vetting_score") or (match_data.get("vetting_score") if match_data else None),
        vetting_reasoning=task.get("vetting_reasoning") or (match_data.get("vetting_reasoning") if match_data else None),
        vetting_criteria_met=task.get("vetting_criteria_met") or (match_data.get("vetting_criteria_met") if match_data else None),
        
        # Match information (from match_data)
        match_score=task.get("match_score") or (match_data.get("match_score") if match_data else None),
        matched_keywords=(match_data.get("matched_keywords") if match_data else None),
        best_matching_episode_id=(match_data.get("best_matching_episode_id") if match_data else None),
        
        # User-friendly summary
        recommendation=recommendation,
        key_highlights=key_highlights[:5],  # Limit to top 5
        potential_concerns=potential_concerns[:3],  # Limit to top 3 concerns
        
        # Pitch-related fields (when task_type is pitch_review)
        pitch_gen_id=pitch_gen_data.get("pitch_gen_id") if pitch_gen_data else None,
        pitch_subject_line=pitch_data.get("subject_line") if pitch_data else None,
        pitch_body_full=pitch_gen_data.get("draft_text") if pitch_gen_data else None,  # Return FULL body for editing
        pitch_template_used=pitch_gen_data.get("template_id") if pitch_gen_data else None,
        pitch_generation_status=pitch_gen_data.get("generation_status") if pitch_gen_data else None
    )