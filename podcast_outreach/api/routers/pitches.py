# podcast_outreach/api/routers/pitches.py

import uuid
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional, Dict, Any
from datetime import datetime

# Import schemas
from api.schemas.pitch_schemas import PitchGenerationRequest, PitchGenerationResponse, PitchInDB, PitchGenerationInDB

# Import services
from podcast_outreach.services.pitches.generator import PitchGeneratorService
from podcast_outreach.services.pitches.sender import PitchSenderService

# Import modular queries
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import pitch_generations as pitch_gen_queries
from podcast_outreach.database.queries import campaigns as campaign_queries # For validation
from podcast_outreach.database.queries import media as media_queries # For validation

# Import dependencies for authentication
from api.dependencies import get_current_user, get_admin_user

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pitches", tags=["Pitches"])

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
            pitch_template_name=request_data.pitch_template_name
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
    """
    Retrieves a specific pitch generation record by ID. Staff or Admin access required.
    """
    try:
        generation_from_db = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
        if not generation_from_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch generation with ID {pitch_gen_id} not found.")
        return PitchGenerationInDB(**generation_from_db)
    except Exception as e:
        logger.exception(f"Error in get_pitch_generation_api for ID {pitch_gen_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/", response_model=List[PitchInDB], summary="List All Pitches")
async def list_pitches_api(skip: int = 0, limit: int = 100, user: dict = Depends(get_current_user)):
    """
    Lists all pitch records with pagination. Staff or Admin access required.
    """
    try:
        pitches_from_db = await pitch_queries.get_all_pitches_from_db(skip=skip, limit=limit)
        return [PitchInDB(**p) for p in pitches_from_db]
    except Exception as e:
        logger.exception(f"Error in list_pitches_api: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/{pitch_id}", response_model=PitchInDB, summary="Get Specific Pitch by ID")
async def get_pitch_api(pitch_id: int, user: dict = Depends(get_current_user)):
    """
    Retrieves a specific pitch record by ID. Staff or Admin access required.
    """
    try:
        pitch_from_db = await pitch_queries.get_pitch_by_id(pitch_id)
        if not pitch_from_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch with ID {pitch_id} not found.")
        return PitchInDB(**pitch_from_db)
    except Exception as e:
        logger.exception(f"Error in get_pitch_api for ID {pitch_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
