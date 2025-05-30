# podcast_outreach/api/routers/matches.py

import uuid
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
import logging

# Import schemas
from ..schemas.match_schemas import MatchSuggestionCreate, MatchSuggestionUpdate, MatchSuggestionInDB

# Import modular queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import campaigns as campaign_queries # For validation
from podcast_outreach.database.queries import media as media_queries # For validation
from podcast_outreach.database.queries import people as people_queries # For enrichment

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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

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
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

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
