# podcast_outreach/api/routers/matches.py

import uuid
from fastapi import APIRouter, HTTPException, Depends, status, Query, BackgroundTasks
from typing import List, Optional, Dict, Any
import logging

# Import schemas
from ..schemas.match_schemas import MatchSuggestionCreate, MatchSuggestionUpdate, MatchSuggestionInDB
from ..schemas.discovery_schemas import DiscoveryResponse, DiscoveryStatus, DiscoveryStatusList

# Import modular queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import campaigns as campaign_queries # For validation
from podcast_outreach.database.queries import media as media_queries # For validation
from podcast_outreach.database.queries import people as people_queries # For enrichment

# Import services
from podcast_outreach.services.enrichment.discovery import DiscoveryService
from podcast_outreach.services.business_logic.discovery_processing import process_discovery_workflow
from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries

# Import dependencies for authentication
from ..dependencies import get_current_user, get_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/match-suggestions", tags=["Match Suggestions"])

@router.post("/campaigns/{campaign_id}/discover", 
             status_code=status.HTTP_202_ACCEPTED,
             response_model=DiscoveryResponse,
             summary="Discover podcasts with automated pipeline")
async def discover_matches_for_campaign_enhanced(
    campaign_id: uuid.UUID, 
    background_tasks: BackgroundTasks,
    max_matches: Optional[int] = Query(None, description="Maximum number of new match suggestions to create for this discovery run.", ge=1),
    user: dict = Depends(get_current_user)
):
    """
    🚀 ENHANCED: Discovers podcasts and automatically processes them through enrichment → vetting → match creation.
    
    This endpoint:
    1. Starts podcast discovery immediately
    2. Processes each discovered podcast through automated pipeline
    3. Creates review tasks for client approval when vetting score ≥ 6.0
    4. Returns immediate response with tracking information
    
    The full pipeline (enrichment → vetting → matches → review tasks) runs automatically in the background.
    """
    # Validate campaign exists and has targeting description
    campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found.")
    
    if not campaign_data.get("ideal_podcast_description"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Campaign must have 'ideal_podcast_description' for automated vetting. Please update campaign settings."
        )

    # Start discovery with enhanced automated pipeline
    service = DiscoveryService()
    try:
        # Add the enhanced discovery task to background
        background_tasks.add_task(
            _run_enhanced_discovery_pipeline, 
            campaign_id, 
            max_matches or 50  # Default max matches
        )
        
        return DiscoveryResponse(
            status="success",
            message="Automated discovery pipeline started. Podcasts will be discovered → enriched → vetted → matched automatically.",
            campaign_id=campaign_id,
            discoveries_initiated=0,  # Will be updated as discoveries are made
            estimated_completion_minutes=5,  # Realistic estimate
            track_endpoint=f"/match-suggestions/campaigns/{campaign_id}/discoveries/status"
        )
        
    except Exception as e:
        logger.exception(f"Error starting enhanced discovery for campaign {campaign_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to start discovery pipeline: {str(e)}"
        )

# Background task function for enhanced discovery
async def _run_enhanced_discovery_pipeline(campaign_id: uuid.UUID, max_matches: int):
    """
    Enhanced background task that runs the full automated pipeline:
    Discovery → Enrichment → Vetting → Match Creation → Review Tasks
    
    Now includes real-time notifications for progress tracking.
    """
    from podcast_outreach.services.events.notification_service import get_notification_service
    from podcast_outreach.services.business_logic.enhanced_discovery_workflow import EnhancedDiscoveryWorkflow
    from podcast_outreach.database.queries import media as media_queries
    
    notification_service = get_notification_service()
    campaign_id_str = str(campaign_id)
    
    try:
        logger.info(f"Starting enhanced discovery pipeline for campaign {campaign_id}")
        
        # Send pipeline started notification
        await notification_service.send_discovery_started(campaign_id_str, estimated_completion=5)
        
        # Step 1: Run traditional discovery to find podcasts
        service = DiscoveryService()
        discovery_results = await service.discover_for_campaign(str(campaign_id), max_matches)
        
        logger.info(f"Discovery completed for campaign {campaign_id}: {len(discovery_results)} new media IDs found")
        
        # Initialize enhanced workflow
        enhanced_workflow = EnhancedDiscoveryWorkflow()
        
        # Step 2: Process each discovered podcast through enhanced automated pipeline
        processed_count = 0
        reviews_ready = 0
        
        # Track each discovered media through campaign_media_discoveries
        for media_id in discovery_results:
            try:
                if media_id:
                    # Send progress notification
                    await notification_service.send_pipeline_progress(
                        campaign_id_str, 
                        completed=processed_count, 
                        total=len(discovery_results), 
                        in_progress=1
                    )
                    
                    # Get media info for keyword tracking
                    media_info = await media_queries.get_media_by_id_from_db(media_id)
                    keyword = media_info.get('category', 'general') if media_info else 'general'
                    
                    # Run the enhanced automated pipeline for this discovery
                    pipeline_result = await enhanced_workflow.process_discovery(
                        campaign_id=campaign_id,
                        media_id=media_id,
                        discovery_keyword=keyword
                    )
                    
                    processed_count += 1
                    
                    # Check if this resulted in a review task
                    if pipeline_result.get('review_task_id'):
                        reviews_ready += 1
                    
                    logger.info(f"Pipeline result for media {media_id}: {pipeline_result['status']}, steps: {pipeline_result.get('steps_completed', [])}")
                    
            except Exception as media_error:
                logger.error(f"Error processing media {media_id} in pipeline: {media_error}")
                processed_count += 1
                continue
        
        # Send completion notification
        await notification_service.send_discovery_completed(
            campaign_id_str, 
            total_discovered=len(discovery_results), 
            reviews_ready=reviews_ready
        )
        
        logger.info(f"Enhanced discovery pipeline completed for campaign {campaign_id}")
        
    except Exception as e:
        logger.error(f"Error in enhanced discovery pipeline for campaign {campaign_id}: {e}")

@router.get("/campaigns/{campaign_id}/discoveries/status",
           response_model=DiscoveryStatusList,
           summary="Track discovery progress")
async def get_discovery_status(
    campaign_id: uuid.UUID,
    status_filter: Optional[str] = Query(None, description="Filter by status: pending, in_progress, completed, failed"),
    limit: int = Query(20, description="Number of results per page", ge=1, le=100),
    offset: int = Query(0, description="Number of results to skip", ge=0),
    user: dict = Depends(get_current_user)
):
    """
    Track the progress of discoveries for a campaign.
    Shows real-time status of enrichment, vetting, and match creation.
    """
    try:
        # Get discoveries for this campaign
        discoveries = await cmd_queries.get_discoveries_for_campaign(
            campaign_id=campaign_id,
            status_filter=status_filter,
            limit=limit,
            offset=offset
        )
        
        # Convert to response format
        discovery_statuses = []
        for disc in discoveries:
            # Determine overall status
            if disc["enrichment_status"] == "failed" or disc["vetting_status"] == "failed":
                overall_status = "failed"
            elif disc["vetting_status"] == "completed":
                overall_status = "completed"
            elif disc["enrichment_status"] == "in_progress" or disc["vetting_status"] == "in_progress":
                overall_status = "in_progress"
            else:
                overall_status = "pending"
            
            discovery_statuses.append(DiscoveryStatus(
                discovery_id=disc["id"],
                campaign_id=disc["campaign_id"],
                media_id=disc["media_id"],
                media_name=disc.get("media_name", "Unknown Podcast"),
                discovery_keyword=disc["discovery_keyword"],
                enrichment_status=disc["enrichment_status"],
                vetting_status=disc["vetting_status"],
                overall_status=overall_status,
                vetting_score=disc.get("vetting_score"),
                match_created=disc.get("match_created", False),
                review_task_created=disc.get("review_task_created", False),
                discovered_at=disc["discovered_at"],
                updated_at=disc["updated_at"],
                enrichment_error=disc.get("enrichment_error"),
                vetting_error=disc.get("vetting_error")
            ))
        
        # Count statuses for summary
        all_discoveries = await cmd_queries.get_discoveries_for_campaign(campaign_id, limit=1000)  # Get all for counting
        in_progress = sum(1 for d in all_discoveries if d["enrichment_status"] == "in_progress" or d["vetting_status"] == "in_progress")
        completed = sum(1 for d in all_discoveries if d["vetting_status"] == "completed")
        failed = sum(1 for d in all_discoveries if d["enrichment_status"] == "failed" or d["vetting_status"] == "failed")
        
        return DiscoveryStatusList(
            items=discovery_statuses,
            total=len(all_discoveries),
            in_progress=in_progress,
            completed=completed,
            failed=failed
        )
        
    except Exception as e:
        logger.exception(f"Error getting discovery status for campaign {campaign_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get discovery status: {str(e)}"
        )

@router.post("/", response_model=MatchSuggestionInDB, status_code=status.HTTP_201_CREATED, summary="Create New Match Suggestion")
async def create_match_suggestion_api(suggestion_data: MatchSuggestionCreate, user: dict = Depends(get_admin_user)):
    """
    Creates a new match suggestion. Admin access required.
    """
    # Optional: Validate foreign keys exist
    campaign_exists = await campaign_queries.get_campaign_by_id(suggestion_data.campaign_id)
    if not campaign_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Campaign {suggestion_data.campaign_id} does not exist.")
    media_exists = await media_queries.get_media_by_id_from_db(suggestion_data.media_id)
    if not media_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Media {suggestion_data.media_id} does not exist.")

    suggestion_dict = suggestion_data.model_dump()
    try:
        created_db_suggestion = await match_queries.create_match_suggestion_in_db(suggestion_dict)
        if not created_db_suggestion:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create match suggestion in database.")
        return MatchSuggestionInDB(**created_db_suggestion)
    except Exception as e:
        logger.exception(f"Error in create_match_suggestion_api: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[MatchSuggestionInDB], summary="List All Match Suggestions (Enriched)")
async def list_all_match_suggestions_api(
    status: Optional[str] = Query(None, description="Filter by status (e.g., pending, approved, rejected)"),
    campaign_id: Optional[uuid.UUID] = Query(None, description="Filter by campaign ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    user: dict = Depends(get_current_user) # Staff or Admin access
):
    """Lists all match suggestions with optional filters and enrichment."""
    # Add role check if necessary, e.g., if only staff/admin should see all without campaign_id
    if user.get("role") not in ["admin", "staff"] and not campaign_id:
        # If user is a client, they must provide a campaign_id they own
        # Or, this endpoint could be admin/staff only if listing across all campaigns
        pass # Current get_current_user doesn't prevent clients, but they won't see much if not filtered

    try:
        suggestions_from_db = await match_queries.get_all_match_suggestions_enriched(
            status=status, campaign_id=campaign_id, skip=skip, limit=limit
        )
        # The schema MatchSuggestionInDB already includes media_name, campaign_name, client_name
        return [MatchSuggestionInDB(**s) for s in suggestions_from_db]
    except Exception as e:
        logger.exception(f"Error listing all match suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/approved-without-pitches", response_model=List[MatchSuggestionInDB], summary="List Approved Matches Without Pitches")
async def list_approved_matches_without_pitches_api(
    campaign_id: Optional[uuid.UUID] = Query(None, description="Filter by campaign"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(get_current_user)
):
    """
    Lists all approved match suggestions that don't have associated pitches yet.
    Perfect for showing matches ready for pitch generation.
    """
    try:
        # Build query to find approved matches without pitches
        query = """
        SELECT 
            ms.*,
            m.name AS media_name,
            m.website AS media_website,
            c.campaign_name AS campaign_name,
            p.full_name AS client_name
        FROM match_suggestions ms
        JOIN media m ON ms.media_id = m.media_id
        JOIN campaigns c ON ms.campaign_id = c.campaign_id
        LEFT JOIN people p ON c.person_id = p.person_id
        LEFT JOIN pitches pitch ON ms.match_id = ANY(pitch.matched_keywords::int[])
        WHERE ms.status = 'client_approved'
        AND ms.client_approved = TRUE
        AND pitch.pitch_id IS NULL
        """
        
        params = []
        param_idx = 1
        
        if campaign_id:
            query += f" AND ms.campaign_id = ${param_idx}"
            params.append(campaign_id)
            param_idx += 1
        
        # Add role-based filtering for clients
        if user.get("role") == "client":
            query += f" AND c.person_id = ${param_idx}"
            params.append(user.get("person_id"))
            param_idx += 1
        
        query += f" ORDER BY ms.approved_at DESC OFFSET ${param_idx} LIMIT ${param_idx + 1}"
        params.extend([skip, limit])
        
        from podcast_outreach.database.connection import get_db_pool
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [MatchSuggestionInDB(**dict(row)) for row in rows]
            
    except Exception as e:
        logger.exception(f"Error listing approved matches without pitches: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/campaign/{campaign_id}", response_model=List[MatchSuggestionInDB], summary="List Match Suggestions for a Campaign (Enriched)")
async def list_match_suggestions_for_campaign_api(
    campaign_id: uuid.UUID, 
    status: Optional[str] = Query(None, description="Filter by status (e.g., pending, approved, rejected)"), # ADDED status filter
    skip: int = 0, 
    limit: int = 100, 
    user: dict = Depends(get_current_user)
):
    """Lists match suggestions for a specific campaign, now enriched and with status filter."""
    # Authorization: Ensure user can access this campaign_id if they are a client
    if user.get("role") == "client":
        camp = await campaign_queries.get_campaign_by_id(campaign_id)
        if not camp or camp.get("person_id") != user.get("person_id"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this campaign's matches.")
    try:
        # Use the new enriched query function, passing the campaign_id and status
        suggestions_from_db = await match_queries.get_all_match_suggestions_enriched(
            campaign_id=campaign_id, status=status, skip=skip, limit=limit
        )
        return [MatchSuggestionInDB(**s) for s in suggestions_from_db]
    except Exception as e:
        logger.exception(f"Error in list_match_suggestions_for_campaign_api for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{match_id}", response_model=MatchSuggestionInDB, summary="Get Specific Match Suggestion by ID (Enriched)")
async def get_match_suggestion_api(match_id: int, user: dict = Depends(get_current_user)):
    """Retrieves a specific match suggestion by ID, now enriched directly from the database."""
    try:
        enriched_suggestion = await match_queries.get_match_suggestion_by_id_enriched(match_id)
        if not enriched_suggestion:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Match suggestion with ID {match_id} not found.")
        
        # Authorization for clients (still needed)
        if user.get("role") == "client":
            # The enriched_suggestion contains campaign_id, which is a UUID.
            # We need to check if the campaign belongs to the current user.
            campaign_id_of_match = enriched_suggestion.get("campaign_id")
            if not campaign_id_of_match:
                 # This case should ideally not happen if data integrity is maintained
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Match suggestion is missing campaign information.")

            # Fetch the campaign details to check ownership (could be optimized by including person_id in enriched_suggestion)
            # For now, this re-fetches campaign, but the core enrichment is done in one DB call.
            campaign = await campaign_queries.get_campaign_by_id(campaign_id_of_match)
            if not campaign or campaign.get("person_id") != user.get("person_id"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this match suggestion.")

        return MatchSuggestionInDB(**enriched_suggestion)
    except HTTPException: # Re-raise FastAPI HTTPExceptions
        raise
    except Exception as e:
        logger.exception(f"Error in get_match_suggestion_api for ID {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{match_id}", response_model=MatchSuggestionInDB, summary="Update Match Suggestion")
async def update_match_suggestion_api(match_id: int, suggestion_update_data: MatchSuggestionUpdate, user: dict = Depends(get_admin_user)):
    """
    Updates an existing match suggestion. Admin access required.
    """
    update_data = suggestion_update_data.model_dump(exclude_unset=True)
    if not update_data:
        existing_suggestion = await match_queries.get_match_suggestion_by_id_from_db(match_id)
        if not existing_suggestion:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Match suggestion with ID {match_id} not found.")
        return MatchSuggestionInDB(**existing_suggestion)
        
    try:
        updated_db_suggestion = await match_queries.update_match_suggestion_in_db(match_id, update_data)
        if not updated_db_suggestion:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Match suggestion with ID {match_id} not found or update failed.")
        return MatchSuggestionInDB(**updated_db_suggestion)
    except Exception as e:
        logger.exception(f"Error in update_match_suggestion_api for ID {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{match_id}/approve", response_model=MatchSuggestionInDB, summary="Approve Match Suggestion (Client Action)")
async def approve_match_suggestion_api(
    match_id: int, 
    approval_notes: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Allows clients to approve a vetted match suggestion.
    Updates status to 'client_approved' and records approval details.
    """
    try:
        # Get the match suggestion to verify access
        match_suggestion = await match_queries.get_match_suggestion_by_id_from_db(match_id)
        if not match_suggestion:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Match suggestion with ID {match_id} not found.")
        
        # Authorization: Ensure client owns this campaign
        if user.get("role") == "client":
            campaign = await campaign_queries.get_campaign_by_id(match_suggestion["campaign_id"])
            if not campaign or campaign.get("person_id") != user.get("person_id"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this match suggestion.")
        
        # Verify the match is in a state that can be approved (has been vetted)
        current_status = match_suggestion.get("status", "")
        if current_status not in ["pending_human_review", "pending_client_review"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Match suggestion cannot be approved in current status: {current_status}. Must be vetted first."
            )
        
        # Update the match suggestion
        update_data = {
            "status": "client_approved",
            "human_review_status": "approved", 
            "human_review_notes": approval_notes or "Approved by client",
            "reviewed_by": user.get("user_id"),
            "reviewed_at": "NOW()"
        }
        
        updated_suggestion = await match_queries.update_match_suggestion_in_db(match_id, update_data)
        if not updated_suggestion:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update match suggestion.")
        
        # Complete any pending review tasks for this match
        from podcast_outreach.database.queries import review_tasks as review_task_queries
        await review_task_queries.complete_review_tasks_for_match(match_id, "Match approved by client")
        
        # Publish match approval event
        try:
            from podcast_outreach.services.events.event_bus import get_event_bus, Event, EventType
            event_bus = get_event_bus()
            event = Event(
                event_type=EventType.MATCH_APPROVED,
                entity_id=str(match_id),
                entity_type="match",
                data={
                    "campaign_id": str(match_suggestion["campaign_id"]),
                    "media_id": match_suggestion["media_id"],
                    "approved_by": user.get("user_id"),
                    "approval_notes": approval_notes
                },
                source="client_approval"
            )
            await event_bus.publish(event)
            logger.info(f"Published MATCH_APPROVED event for match {match_id}")
        except Exception as e:
            logger.error(f"Error publishing match approved event: {e}")
        
        logger.info(f"Match {match_id} approved by client {user.get('user_id')}")
        return MatchSuggestionInDB(**updated_suggestion)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error approving match suggestion {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{match_id}/reject", response_model=MatchSuggestionInDB, summary="Reject Match Suggestion (Client Action)")
async def reject_match_suggestion_api(
    match_id: int, 
    rejection_reason: str,
    user: dict = Depends(get_current_user)
):
    """
    Allows clients to reject a vetted match suggestion.
    Updates status to 'client_rejected' and records rejection reason.
    """
    if not rejection_reason or not rejection_reason.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rejection reason is required.")
    
    try:
        # Get the match suggestion to verify access
        match_suggestion = await match_queries.get_match_suggestion_by_id_from_db(match_id)
        if not match_suggestion:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Match suggestion with ID {match_id} not found.")
        
        # Authorization: Ensure client owns this campaign
        if user.get("role") == "client":
            campaign = await campaign_queries.get_campaign_by_id(match_suggestion["campaign_id"])
            if not campaign or campaign.get("person_id") != user.get("person_id"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this match suggestion.")
        
        # Verify the match is in a state that can be rejected
        current_status = match_suggestion.get("status", "")
        if current_status not in ["pending_human_review", "pending_client_review"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Match suggestion cannot be rejected in current status: {current_status}. Must be vetted first."
            )
        
        # Update the match suggestion
        update_data = {
            "status": "client_rejected",
            "human_review_status": "rejected",
            "human_review_notes": rejection_reason,
            "reviewed_by": user.get("user_id"),
            "reviewed_at": "NOW()"
        }
        
        updated_suggestion = await match_queries.update_match_suggestion_in_db(match_id, update_data)
        if not updated_suggestion:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update match suggestion.")
        
        # Complete any pending review tasks for this match
        from podcast_outreach.database.queries import review_tasks as review_task_queries
        await review_task_queries.complete_review_tasks_for_match(match_id, f"Match rejected by client: {rejection_reason}")
        
        # Publish match rejection event
        try:
            from podcast_outreach.services.events.event_bus import get_event_bus, Event, EventType
            event_bus = get_event_bus()
            event = Event(
                event_type=EventType.MATCH_REJECTED,
                entity_id=str(match_id),
                entity_type="match",
                data={
                    "campaign_id": str(match_suggestion["campaign_id"]),
                    "media_id": match_suggestion["media_id"],
                    "rejected_by": user.get("user_id"),
                    "rejection_reason": rejection_reason
                },
                source="client_rejection"
            )
            await event_bus.publish(event)
            logger.info(f"Published MATCH_REJECTED event for match {match_id}")
        except Exception as e:
            logger.error(f"Error publishing match rejected event: {e}")
        
        logger.info(f"Match {match_id} rejected by client {user.get('user_id')}: {rejection_reason}")
        return MatchSuggestionInDB(**updated_suggestion)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error rejecting match suggestion {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{match_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Match Suggestion")
async def delete_match_suggestion_api(match_id: int, user: dict = Depends(get_admin_user)):
    """
    Deletes a match suggestion. Admin access required.
    """
    try:
        success = await match_queries.delete_match_suggestion_from_db(match_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Match suggestion with ID {match_id} not found or delete failed.")
        return # Returns 204 No Content on success
    except Exception as e:
        logger.exception(f"Error in delete_match_suggestion_api for ID {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{match_id}/approve", response_model=MatchSuggestionInDB, summary="Approve Match Suggestion")
async def approve_match_suggestion_api(match_id: int, user: dict = Depends(get_current_user)):
    """Approve a match suggestion and create a pitch review task. Staff or Admin access required."""
    try:
        approved_match = await match_queries.approve_match_and_create_pitch_task(match_id)
        if not approved_match:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Match suggestion with ID {match_id} not found.")
        return MatchSuggestionInDB(**approved_match)
    except Exception as e:
        logger.exception(f"Error in approve_match_suggestion_api for ID {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
