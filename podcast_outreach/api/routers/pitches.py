# podcast_outreach/api/routers/pitches.py

import uuid
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime

# Import schemas
from ..schemas.pitch_schemas import PitchGenerationRequest, PitchGenerationResponse, PitchInDB, PitchGenerationInDB, PitchGenerationContentUpdate

# Import services
from podcast_outreach.services.pitches.generator import PitchGeneratorService
from podcast_outreach.services.pitches.sender import PitchSenderService

# Import modular queries
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import pitch_generations as pitch_gen_queries
from podcast_outreach.database.queries import campaigns as campaign_queries # For validation
from podcast_outreach.database.queries import media as media_queries # For validation
from podcast_outreach.database.queries import people as people_queries # For enrichment

# Import dependencies for authentication
from ..dependencies import get_current_user, get_admin_user

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pitches", tags=["Pitches"])

@router.post("/generate-batch", status_code=status.HTTP_202_ACCEPTED, summary="Generate Pitches for Multiple Matches")
async def generate_pitches_batch_api(
    requests: List[PitchGenerationRequest],
    user: dict = Depends(get_current_user)
):
    """
    Generate pitches for multiple approved matches with different templates.
    Each request can specify a different template for each match.
    
    Example request body:
    [
        {"match_id": 1, "pitch_template_id": "template_1"},
        {"match_id": 2, "pitch_template_id": "template_2"},
        {"match_id": 3, "pitch_template_id": "template_1"}
    ]
    """
    if user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to generate pitches.")
    
    generator_service = PitchGeneratorService()
    results = {"successful": [], "failed": []}
    
    for request in requests:
        try:
            result = await generator_service.generate_pitch_for_match(
                match_id=request.match_id,
                pitch_template_id=request.pitch_template_id
            )
            
            if result.get("status") == "success":
                results["successful"].append({
                    "match_id": request.match_id,
                    "pitch_gen_id": result.get("pitch_gen_id"),
                    "message": result.get("message")
                })
            else:
                results["failed"].append({
                    "match_id": request.match_id,
                    "error": result.get("message")
                })
                
        except Exception as e:
            logger.exception(f"Error generating pitch for match {request.match_id}: {e}")
            results["failed"].append({
                "match_id": request.match_id,
                "error": str(e)
            })
    
    return {
        "status": "completed",
        "message": f"Batch generation completed. Success: {len(results['successful'])}, Failed: {len(results['failed'])}",
        "results": results
    }

@router.post("/generate", response_model=PitchGenerationResponse, status_code=status.HTTP_202_ACCEPTED, summary="Generate Pitch for Approved Match")
async def generate_pitch_for_match_api(
    request_data: PitchGenerationRequest,
    user: dict = Depends(get_current_user)
):
    """
    Triggers the AI-powered generation of a pitch email for an approved match suggestion.
    Staff or Admin access required.
    """
    generator_service = PitchGeneratorService()
    try:
        result = await generator_service.generate_pitch_for_match(
            match_id=request_data.match_id,
            pitch_template_id=request_data.pitch_template_id
        )
        
        if result.get("status") == "failed":
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.get("message"))
        
        return PitchGenerationResponse(**result)
    except HTTPException:
        raise # Re-raise FastAPI HTTPExceptions
    except Exception as e:
        logger.exception(f"Error generating pitch for match {request_data.match_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred during pitch generation: {str(e)}")

@router.patch("/generations/{pitch_gen_id}/approve", response_model=PitchGenerationInDB, summary="Approve a Generated Pitch")
async def approve_pitch_generation_api(
    pitch_gen_id: int,
    user: dict = Depends(get_current_user)
):
    """
    Approves a generated pitch, marking it as ready to send.
    Staff or Admin access required.
    """
    try:
        approved_pitch_gen = await pitch_gen_queries.approve_pitch_generation(
            pitch_gen_id=pitch_gen_id,
            reviewer_id=user["username"]
        )
        if not approved_pitch_gen:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch generation with ID {pitch_gen_id} not found or could not be approved.")
        
        return PitchGenerationInDB(**approved_pitch_gen)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error approving pitch generation {pitch_gen_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred during pitch approval: {str(e)}")

@router.post("/{pitch_id}/send", status_code=status.HTTP_202_ACCEPTED, summary="Send Pitch via Instantly.ai")
async def send_pitch_api(
    pitch_id: int,
    user: dict = Depends(get_current_user)
):
    """
    Sends an approved pitch via Instantly.ai.
    Staff or Admin access required.
    """
    sender_service = PitchSenderService()
    try:
        pitch_record = await pitch_queries.get_pitch_by_id(pitch_id)
        if not pitch_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch record with ID {pitch_id} not found.")
        
        pitch_gen_id = pitch_record.get('pitch_gen_id')
        if not pitch_gen_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Pitch record {pitch_id} is not linked to a pitch generation.")

        pitch_gen_record = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
        if not pitch_gen_record or not pitch_gen_record.get('send_ready_bool'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Pitch generation {pitch_gen_id} is not marked as send-ready.")

        result = await sender_service.send_pitch_to_instantly(pitch_gen_id=pitch_gen_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.get("message"))
        
        return {"message": result.get("message"), "status": "accepted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error sending pitch {pitch_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred during pitch sending: {str(e)}")

@router.get("/generations", response_model=List[PitchGenerationInDB], summary="List All Pitch Generations")
async def list_pitch_generations_api(skip: int = 0, limit: int = 100, user: dict = Depends(get_current_user)):
    """
    Lists all pitch generation records with pagination. Staff or Admin access required.
    """
    try:
        generations_from_db = await pitch_gen_queries.get_all_pitch_generations_from_db(skip=skip, limit=limit)
        return [PitchGenerationInDB(**pg) for pg in generations_from_db]
    except Exception as e:
        logger.exception(f"Error in list_pitch_generations_api: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/generations/{pitch_gen_id}", response_model=PitchGenerationInDB, summary="Get Specific Pitch Generation by ID")
async def get_pitch_generation_api(pitch_gen_id: int, user: dict = Depends(get_current_user)):
    logger.info(f"API: Attempting to fetch pitch generation with ID: {pitch_gen_id}")
    try:
        generation_from_db = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)

        if not generation_from_db:
            logger.warning(f"API: Pitch generation with ID {pitch_gen_id} not found in DB.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch generation with ID {pitch_gen_id} not found.")

        logger.debug(f"API: Raw data from DB for pitch_gen_id {pitch_gen_id}: {generation_from_db}") # Log raw data

        # Attempt Pydantic validation and catch potential errors
        try:
            validated_data = PitchGenerationInDB(**generation_from_db)
            logger.info(f"API: Successfully validated data for pitch_gen_id {pitch_gen_id}.")
            return validated_data
        except Exception as pydantic_exc: # Catch Pydantic validation errors specifically
            logger.error(f"API: Pydantic validation error for pitch_gen_id {pitch_gen_id}. Data: {generation_from_db}. Error: {pydantic_exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Data validation error for pitch generation: {pydantic_exc}")

    except HTTPException: # Re-raise known HTTPExceptions
        raise
    except Exception as e: # Catch other unexpected errors
        logger.exception(f"API: Unexpected error in get_pitch_generation_api for ID {pitch_gen_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

@router.get("/", response_model=List[PitchInDB], summary="List All Pitches (Enriched)")
async def list_pitches_api(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    campaign_id: Optional[uuid.UUID] = Query(None),
    media_id: Optional[int] = Query(None),
    pitch_state__in: Optional[List[str]] = Query(None, alias="pitch_state__in", description="List of pitch states to filter by (e.g., ready_to_send,sent)"),
    client_approval_status: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    """
    Lists all pitch records with pagination and optional filters, now enriched.
    Supports filtering by multiple pitch_states using `pitch_state__in=state1&pitch_state__in=state2`.
    """
    # Basic role check for non-admins trying to list all pitches without campaign filter
    if user.get("role") not in ["admin", "staff"] and not campaign_id:
         # Clients should generally view pitches via their specific campaign or context
         # This endpoint without a campaign_id filter might expose too much.
         # Consider adding a person_id filter for clients, similar to other endpoints.
         pass # For now, allow but enrichment will be limited if no campaign context

    try:
        pitches_from_db = await pitch_queries.get_all_pitches_enriched(
            skip=skip, limit=limit,
            campaign_id=campaign_id,
            media_id=media_id,
            pitch_states=pitch_state__in, # Pass the list of states
            client_approval_status=client_approval_status,
            person_id=user.get("person_id") if user.get("role") == "client" else None # Auto-filter for client role
        )
        return [PitchInDB(**p) for p in pitches_from_db]
    except Exception as e:
        logger.exception(f"Error in list_pitches_api: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/{pitch_id}", response_model=PitchInDB, summary="Get Specific Pitch by ID (Enriched)")
async def get_pitch_api(pitch_id: int, user: dict = Depends(get_current_user)):
    """Retrieves a specific pitch record by ID, now enriched directly from the database."""
    try:
        enriched_pitch = await pitch_queries.get_pitch_by_id_enriched(pitch_id)

        if not enriched_pitch:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch with ID {pitch_id} not found.")
        
        # Authorization for clients (still needed)
        if user.get("role") == "client":
            # The enriched_pitch should contain campaign_id and its associated person_id (client_id)
            # We need to verify that this person_id matches the current_user's person_id
            campaign_id_of_pitch = enriched_pitch.get("campaign_id")
            if not campaign_id_of_pitch:
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Pitch is missing campaign information.")

            # The enrichment should have fetched c.person_id, so we can check that.
            # If client_name was populated, person_id for the campaign owner was found.
            # We need to make sure the DB query for enrichment correctly aliases or includes c.person_id if it's not part of p.* from pitches
            # Let's assume the JOINs in get_pitch_by_id_enriched give us c.person_id implicitly or explicitly
            # and we compare it to user.get("person_id")
            
            # To be robust, fetch campaign and check its person_id if not directly in enriched_pitch
            # This is a fallback, ideally enriched_pitch contains campaign's person_id
            campaign_owner_person_id = None
            campaign_details = await campaign_queries.get_campaign_by_id(campaign_id_of_pitch)
            if campaign_details:
                campaign_owner_person_id = campaign_details.get("person_id")

            if campaign_owner_person_id != user.get("person_id"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this pitch.")

        return PitchInDB(**enriched_pitch)
    except HTTPException: # Re-raise FastAPI HTTPExceptions
        raise
    except Exception as e:
        logger.exception(f"Error in get_pitch_api for ID {pitch_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/bulk-send", status_code=status.HTTP_202_ACCEPTED, summary="Send Multiple Pitches via Instantly.ai")
async def send_pitches_bulk_api(
    pitch_ids: List[int],
    user: dict = Depends(get_current_user)
):
    """
    Sends multiple approved pitches via Instantly.ai.
    Staff or Admin access required.
    Returns a summary of successes and failures.
    """
    if user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to send pitches.")
    
    sender_service = PitchSenderService()
    results = {"successful": [], "failed": []}
    
    for pitch_id in pitch_ids:
        try:
            pitch_record = await pitch_queries.get_pitch_by_id(pitch_id)
            if not pitch_record:
                results["failed"].append({"pitch_id": pitch_id, "error": "Pitch not found"})
                continue
            
            pitch_gen_id = pitch_record.get('pitch_gen_id')
            if not pitch_gen_id:
                results["failed"].append({"pitch_id": pitch_id, "error": "No pitch generation linked"})
                continue
            
            pitch_gen_record = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
            if not pitch_gen_record or not pitch_gen_record.get('send_ready_bool'):
                results["failed"].append({"pitch_id": pitch_id, "error": "Pitch not ready to send"})
                continue
            
            result = await sender_service.send_pitch_to_instantly(pitch_gen_id=pitch_gen_id)
            
            if result.get("success"):
                results["successful"].append({"pitch_id": pitch_id, "message": result.get("message")})
            else:
                results["failed"].append({"pitch_id": pitch_id, "error": result.get("message")})
                
        except Exception as e:
            logger.exception(f"Error sending pitch {pitch_id} in bulk operation: {e}")
            results["failed"].append({"pitch_id": pitch_id, "error": str(e)})
    
    return {
        "message": f"Bulk send completed. Success: {len(results['successful'])}, Failed: {len(results['failed'])}",
        "results": results
    }

@router.patch("/generations/{pitch_gen_id}/content", response_model=PitchGenerationInDB, summary="Update Pitch Draft Content and Subject")
async def update_pitch_generation_content_api(
    pitch_gen_id: int,
    update_data: PitchGenerationContentUpdate, # New schema
    user: dict = Depends(get_current_user) # Staff or Admin access
):
    """
    Updates the draft_text of a pitch generation and/or the subject_line 
    of the associated pitch record.
    """
    if user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to edit pitch content.")

    updated_pitch_gen = None
    updated_pitch = None

    if update_data.draft_text is not None:
        updated_pitch_gen = await pitch_gen_queries.update_pitch_generation(
            pitch_gen_id,
            {"draft_text": update_data.draft_text}
        )
        if not updated_pitch_gen:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch generation {pitch_gen_id} not found or update failed.")

    if update_data.new_subject_line is not None:
        # Find the associated pitch record to update its subject line
        pitch_record = await pitch_queries.get_pitch_by_pitch_gen_id(pitch_gen_id)
        if not pitch_record or not pitch_record.get("pitch_id"):
            logger.warning(f"No associated pitch record found for pitch_gen_id {pitch_gen_id} to update subject line.")
            # Decide if this is an error or if pitch_gen can exist without a pitch record yet.
            # If pitch_gen always has a pitch, this is an error.
            # For now, we'll proceed if pitch_gen was updated, but log a warning.
        else:
            updated_pitch = await pitch_queries.update_pitch_in_db(
                pitch_record["pitch_id"],
                {"subject_line": update_data.new_subject_line}
            )
            if not updated_pitch:
                 logger.warning(f"Failed to update subject line for pitch_id {pitch_record['pitch_id']}.")
    
    # Return the updated pitch generation record as the primary object of this endpoint
    # If only subject was updated, fetch the pitch_gen again to return its current state
    if updated_pitch_gen:
        return PitchGenerationInDB(**updated_pitch_gen)
    elif update_data.new_subject_line and not update_data.draft_text:
        # Only subject was updated, fetch current pitch_gen to return
        current_pitch_gen = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
        if not current_pitch_gen:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch generation {pitch_gen_id} not found after attempting subject update.")
        return PitchGenerationInDB(**current_pitch_gen)
    else:
        # This case should ideally not be reached if at least one update was attempted and failed to find pitch_gen
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update performed or pitch generation not found.")
