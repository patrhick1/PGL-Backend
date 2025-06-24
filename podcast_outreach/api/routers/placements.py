# podcast_outreach/api/routers/placements.py
import uuid
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
import logging

# Import schemas
from ..schemas.placement_schemas import PlacementCreate, PlacementUpdate, PlacementInDB, PaginatedPlacementList, PlacementWithDetails
from ..schemas.campaign_schemas import CampaignInDB # For campaign details if needed

# Import modular queries
from podcast_outreach.database.queries import placements as placement_queries
from podcast_outreach.database.queries import campaigns as campaign_queries # For validation/auth
from podcast_outreach.database.queries import media as media_queries # For validation
from podcast_outreach.database.queries import people as people_queries # For client name

# Import dependencies for authentication
from ..dependencies import get_current_user, get_admin_user, get_staff_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/placements", tags=["Placements"])

async def _enrich_placement_details(placement_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to fetch and add related campaign, client, and media names."""
    if placement_dict.get("campaign_id"):
        campaign = await campaign_queries.get_campaign_by_id(placement_dict["campaign_id"])
        if campaign:
            placement_dict["campaign_name"] = campaign.get("campaign_name")
            if campaign.get("person_id"):
                person = await people_queries.get_person_by_id_from_db(campaign["person_id"])
                if person:
                    placement_dict["client_name"] = person.get("full_name")
    if placement_dict.get("media_id"):
        media = await media_queries.get_media_by_id_from_db(placement_dict["media_id"])
        if media:
            placement_dict["media_name"] = media.get("name")
            placement_dict["media_website"] = media.get("website")
    return placement_dict


@router.post("/", response_model=PlacementInDB, status_code=status.HTTP_201_CREATED, summary="Create New Placement")
async def create_placement_api(placement_data: PlacementCreate, user: dict = Depends(get_staff_user)): # Staff/Admin can create
    """
    Creates a new placement record.
    """
    # Validate foreign keys exist
    campaign_exists = await campaign_queries.get_campaign_by_id(placement_data.campaign_id)
    if not campaign_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Campaign {placement_data.campaign_id} does not exist.")
    media_exists = await media_queries.get_media_by_id_from_db(placement_data.media_id)
    if not media_exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Media {placement_data.media_id} does not exist.")

    placement_dict = placement_data.model_dump()
    try:
        created_db_placement = await placement_queries.create_placement_in_db(placement_dict)
        if not created_db_placement:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create placement in database.")
        
        enriched_placement = await _enrich_placement_details(dict(created_db_placement))
        return PlacementInDB(**enriched_placement)
    except Exception as e:
        logger.exception(f"Error in create_placement_api: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/", response_model=PaginatedPlacementList, summary="List Placements")
async def list_placements_api(
    campaign_id: Optional[uuid.UUID] = Query(None, description="Filter by campaign ID"),
    person_id: Optional[int] = Query(None, description="Filter by client's person ID (for client view)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user)
):
    """
    Lists placement records with pagination and optional filtering.
    - If `person_id` is provided, it filters placements for campaigns belonging to that person (client view).
    - If `campaign_id` is provided, it filters for that specific campaign.
    - Admins/Staff can see all if no filters are applied or can use campaign_id.
    """
    placements_from_db: List[Dict[str, Any]] = []
    total_count = 0

    if user.get("role") == "client":
        # Clients can only see their own placements.
        # Override person_id with the authenticated client's person_id.
        client_person_id = user.get("person_id")
        if not client_person_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client ID not found in session.")
        
        # If a campaign_id is also provided by client, ensure it belongs to them
        if campaign_id:
            campaign = await campaign_queries.get_campaign_by_id(campaign_id)
            if not campaign or campaign.get("person_id") != client_person_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this campaign's placements.")
            # Fetch for specific campaign of the client
            placements_from_db, total_count = await placement_queries.get_placements_paginated(
                campaign_id=campaign_id, page=page, size=size
            )
        else:
            # Fetch all placements for all campaigns of this client
            placements_from_db, total_count = await placement_queries.get_placements_for_person_paginated(
                person_id=client_person_id, page=page, size=size
            )
    elif user.get("role") in ["admin", "staff"]:
        # Admin/Staff can filter by campaign_id or person_id, or get all
        if person_id: # Admin wants to see placements for a specific client
             placements_from_db, total_count = await placement_queries.get_placements_for_person_paginated(
                person_id=person_id, campaign_id_filter=campaign_id, page=page, size=size
            )
        else: # Admin wants to see for a specific campaign or all campaigns
            placements_from_db, total_count = await placement_queries.get_placements_paginated(
                campaign_id=campaign_id, page=page, size=size # if campaign_id is None, gets all
            )
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    enriched_items = []
    for placement_dict in placements_from_db:
        enriched_items.append(PlacementInDB(**await _enrich_placement_details(dict(placement_dict))))
        
    return PaginatedPlacementList(items=enriched_items, total=total_count, page=page, size=size)


@router.get("/{placement_id}", response_model=PlacementInDB, summary="Get Specific Placement")
async def get_placement_api(placement_id: int, user: dict = Depends(get_current_user)):
    """
    Retrieves a specific placement record by ID.
    Clients can only access placements belonging to their campaigns.
    """
    try:
        placement_from_db = await placement_queries.get_placement_by_id(placement_id)
        if not placement_from_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Placement with ID {placement_id} not found.")

        if user.get("role") == "client":
            campaign = await campaign_queries.get_campaign_by_id(placement_from_db['campaign_id'])
            if not campaign or campaign.get("person_id") != user.get("person_id"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this placement.")
        
        enriched_placement = await _enrich_placement_details(dict(placement_from_db))
        return PlacementInDB(**enriched_placement)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in get_placement_api for ID {placement_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put("/{placement_id}", response_model=PlacementInDB, summary="Update Placement")
async def update_placement_api(placement_id: int, placement_update_data: PlacementUpdate, user: dict = Depends(get_staff_user)): # Staff/Admin can update
    """
    Updates an existing placement record.
    """
    update_data = placement_update_data.model_dump(exclude_unset=True)
    if not update_data:
        # Fetch and return current if no update data provided
        current_placement = await placement_queries.get_placement_by_id(placement_id)
        if not current_placement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Placement with ID {placement_id} not found.")
        enriched_current = await _enrich_placement_details(dict(current_placement))
        return PlacementInDB(**enriched_current)
        
    try:
        updated_db_placement = await placement_queries.update_placement_in_db(placement_id, update_data)
        if not updated_db_placement:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Placement with ID {placement_id} not found or update failed.")
        
        enriched_placement = await _enrich_placement_details(dict(updated_db_placement))
        return PlacementInDB(**enriched_placement)
    except Exception as e:
        logger.exception(f"Error in update_placement_api for ID {placement_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete("/{placement_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Placement")
async def delete_placement_api(placement_id: int, user: dict = Depends(get_admin_user)): # Only Admin can delete
    """
    Deletes a placement record.
    """
    try:
        success = await placement_queries.delete_placement_from_db(placement_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Placement with ID {placement_id} not found or delete failed.")
        return 
    except Exception as e:
        logger.exception(f"Error in delete_placement_api for ID {placement_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))