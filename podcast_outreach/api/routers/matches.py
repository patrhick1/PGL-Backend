# podcast_outreach/api/routers/matches.py

import uuid
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
import logging

# Import schemas
from api.schemas.match_schemas import MatchSuggestionCreate, MatchSuggestionUpdate, MatchSuggestionInDB

# Import db_service_pg (assuming it's now at database/queries/db_service_pg.py)
import db_service_pg # Original path, adjust if moved to database/queries/

# Import dependencies (for user auth)
from api.dependencies import get_current_user, get_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/match-suggestions", tags=["Match Suggestions"])

@router.post("/", response_model=MatchSuggestionInDB, status_code=201, summary="Create New Match Suggestion")
async def create_match_suggestion_api(suggestion_data: MatchSuggestionCreate, user: dict = Depends(get_current_user)):
    """
    Creates a new match suggestion. Staff or Admin access required.
    """
    suggestion_dict = suggestion_data.model_dump() # Use model_dump() for Pydantic v2
    try:
        created_db_suggestion = await db_service_pg.create_match_suggestion_in_db(suggestion_dict)
        if not created_db_suggestion:
            raise HTTPException(status_code=500, detail="Failed to create match suggestion in database.")
        return MatchSuggestionInDB(**created_db_suggestion)
    except Exception as e:
        logger.exception(f"Error in create_match_suggestion_api: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/campaign/{campaign_id}", response_model=List[MatchSuggestionInDB], summary="List Match Suggestions for a Campaign")
async def list_match_suggestions_for_campaign_api(campaign_id: uuid.UUID, skip: int = 0, limit: int = 100, user: dict = Depends(get_current_user)):
    """
    Lists match suggestions for a specific campaign. Staff or Admin access required.
    """
    try:
        suggestions_from_db = await db_service_pg.get_match_suggestions_for_campaign_from_db(campaign_id, skip=skip, limit=limit)
        return [MatchSuggestionInDB(**s) for s in suggestions_from_db]
    except Exception as e:
        logger.exception(f"Error in list_match_suggestions_for_campaign_api for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{match_id}", response_model=MatchSuggestionInDB, summary="Get Specific Match Suggestion by ID")
async def get_match_suggestion_api(match_id: int, user: dict = Depends(get_current_user)):
    """
    Retrieves a specific match suggestion by ID. Staff or Admin access required.
    """
    try:
        suggestion_from_db = await db_service_pg.get_match_suggestion_by_id_from_db(match_id)
        if not suggestion_from_db:
            raise HTTPException(status_code=404, detail=f"Match suggestion with ID {match_id} not found.")
        return MatchSuggestionInDB(**suggestion_from_db)
    except Exception as e:
        logger.exception(f"Error in get_match_suggestion_api for ID {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{match_id}", response_model=MatchSuggestionInDB, summary="Update Match Suggestion")
async def update_match_suggestion_api(match_id: int, suggestion_update_data: MatchSuggestionUpdate, user: dict = Depends(get_current_user)):
    """
    Updates an existing match suggestion. Staff or Admin access required.
    """
    update_data = suggestion_update_data.model_dump(exclude_unset=True) # Use model_dump() for Pydantic v2
    if not update_data: # If empty dict is passed, no fields to update
        existing_suggestion = await db_service_pg.get_match_suggestion_by_id_from_db(match_id)
        if not existing_suggestion:
            raise HTTPException(status_code=404, detail=f"Match suggestion with ID {match_id} not found.")
        return MatchSuggestionInDB(**existing_suggestion)
        
    try:
        updated_db_suggestion = await db_service_pg.update_match_suggestion_in_db(match_id, update_data)
        if not updated_db_suggestion:
            raise HTTPException(status_code=404, detail=f"Match suggestion with ID {match_id} not found or update failed.")
        return MatchSuggestionInDB(**updated_db_suggestion)
    except Exception as e:
        logger.exception(f"Error in update_match_suggestion_api for ID {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{match_id}", status_code=204, summary="Delete Match Suggestion")
async def delete_match_suggestion_api(match_id: int, user: dict = Depends(get_admin_user)):
    """
    Deletes a match suggestion. Admin access required.
    """
    try:
        success = await db_service_pg.delete_match_suggestion_from_db(match_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Match suggestion with ID {match_id} not found or delete failed.")
        return # Returns 204 No Content on success
    except Exception as e:
        logger.exception(f"Error in delete_match_suggestion_api for ID {match_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))