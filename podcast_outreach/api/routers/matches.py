# podcast_outreach/api/routers/matches.py

import uuid
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional, Dict, Any
import logging

# Import schemas
from ..schemas.match_schemas import MatchSuggestionCreate, MatchSuggestionUpdate, MatchSuggestionInDB

# Import modular queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import campaigns as campaign_queries # For validation
from podcast_outreach.database.queries import media as media_queries # For validation

# Import services
from podcast_outreach.services.enrichment.discovery import DiscoveryService

# Import dependencies for authentication
from ..dependencies import get_current_user, get_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/match-suggestions", tags=["Match Suggestions"])

@router.post("/campaigns/{campaign_id}/discover", response_model=List[MatchSuggestionInDB], summary="Discover podcasts for a campaign")
async def discover_matches_for_campaign(campaign_id: uuid.UUID, user: dict = Depends(get_current_user)):
    """
    Search for podcasts and create match suggestions with review tasks.
    Staff or Admin access required.
    """
    # Validate campaign exists
    campaign_exists = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found.")

    service = DiscoveryService()
    try:
        suggestions = await service.discover_for_campaign(str(campaign_id))
        return [MatchSuggestionInDB(**s) for s in suggestions]
    except Exception as e:
        logger.exception(f"Error discovering matches for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to discover matches: {str(e)}")

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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/campaign/{campaign_id}", response_model=List[MatchSuggestionInDB], summary="List Match Suggestions for a Campaign")
async def list_match_suggestions_for_campaign_api(campaign_id: uuid.UUID, skip: int = 0, limit: int = 100, user: dict = Depends(get_current_user)):
    """
    Lists match suggestions for a specific campaign. Staff or Admin access required.
    """
    try:
        suggestions_from_db = await match_queries.get_match_suggestions_for_campaign_from_db(campaign_id, skip=skip, limit=limit)
        return [MatchSuggestionInDB(**s) for s in suggestions_from_db]
    except Exception as e:
        logger.exception(f"Error in list_match_suggestions_for_campaign_api for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/{match_id}", response_model=MatchSuggestionInDB, summary="Get Specific Match Suggestion by ID")
async def get_match_suggestion_api(match_id: int, user: dict = Depends(get_current_user)):
    """
    Retrieves a specific match suggestion by ID. Staff or Admin access required.
    """
    try:
        suggestion_from_db = await match_queries.get_match_suggestion_by_id_from_db(match_id)
        if not suggestion_from_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Match suggestion with ID {match_id} not found.")
        return MatchSuggestionInDB(**suggestion_from_db)
    except Exception as e:
        logger.exception(f"Error in get_match_suggestion_api for ID {match_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
