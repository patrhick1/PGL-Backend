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

@router.get("/metrics", summary="Get Placement Metrics")
async def get_placement_metrics(
    campaign_id: Optional[uuid.UUID] = Query(None, description="Filter by specific campaign"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    user: dict = Depends(get_current_user)
):
    """
    Get placement performance metrics for the current user.
    Returns statistics on placement statuses, conversion rates, upcoming placements, etc.
    Can be filtered by campaign and time period.
    """
    from datetime import date, timedelta
    from podcast_outreach.database.connection import get_db_pool
    
    try:
        person_id = user.get("person_id")
        if not person_id:
            raise HTTPException(status_code=400, detail="User not properly authenticated")
        
        pool = await get_db_pool()
        
        # Build the base query with user filtering
        base_conditions = ["c.person_id = $1"]
        params = [person_id]
        
        # Add campaign filter if provided
        if campaign_id:
            base_conditions.append(f"pl.campaign_id = ${len(params) + 1}")
            params.append(campaign_id)
        
        # Add date filter
        if days:
            base_conditions.append(f"pl.created_at >= NOW() - INTERVAL '{days} days'")
        
        where_clause = " AND ".join(base_conditions)
        
        async with pool.acquire() as conn:
            # Get overall placement metrics
            metrics_query = f"""
            SELECT 
                COUNT(*) as total_placements,
                COUNT(CASE WHEN pl.current_status = 'scheduled' THEN 1 END) as scheduled,
                COUNT(CASE WHEN pl.current_status = 'recording_booked' THEN 1 END) as recording_booked,
                COUNT(CASE WHEN pl.current_status = 'recorded' THEN 1 END) as recorded,
                COUNT(CASE WHEN pl.current_status = 'live' THEN 1 END) as live,
                COUNT(CASE WHEN pl.current_status = 'paid' THEN 1 END) as paid,
                COUNT(CASE WHEN pl.current_status IN ('cancelled', 'rejected') THEN 1 END) as cancelled,
                COUNT(CASE WHEN pl.go_live_date IS NOT NULL THEN 1 END) as has_go_live_date,
                COUNT(CASE WHEN pl.recording_date IS NOT NULL THEN 1 END) as has_recording_date,
                COUNT(CASE WHEN pl.go_live_date >= CURRENT_DATE THEN 1 END) as upcoming_go_live,
                COUNT(CASE WHEN pl.recording_date >= CURRENT_DATE THEN 1 END) as upcoming_recordings
            FROM placements pl
            JOIN campaigns c ON pl.campaign_id = c.campaign_id
            WHERE {where_clause}
            """
            
            metrics = await conn.fetchrow(metrics_query, *params)
            
            # Get upcoming placements
            upcoming_query = f"""
            SELECT 
                pl.placement_id,
                pl.current_status,
                pl.recording_date,
                pl.go_live_date,
                pl.outreach_topic,
                c.campaign_name,
                m.name as media_name,
                m.host_names
            FROM placements pl
            JOIN campaigns c ON pl.campaign_id = c.campaign_id
            LEFT JOIN media m ON pl.media_id = m.media_id
            WHERE {where_clause}
            AND (pl.recording_date >= CURRENT_DATE OR pl.go_live_date >= CURRENT_DATE)
            ORDER BY COALESCE(pl.recording_date, pl.go_live_date) ASC
            LIMIT 10
            """
            
            upcoming = await conn.fetch(upcoming_query, *params)
            
            # Get recent placements
            recent_query = f"""
            SELECT 
                pl.placement_id,
                pl.current_status,
                pl.created_at,
                pl.status_ts,
                c.campaign_name,
                m.name as media_name
            FROM placements pl
            JOIN campaigns c ON pl.campaign_id = c.campaign_id
            LEFT JOIN media m ON pl.media_id = m.media_id
            WHERE {where_clause}
            ORDER BY pl.created_at DESC
            LIMIT 10
            """
            
            recent = await conn.fetch(recent_query, *params)
            
            # Get campaign breakdown if not filtering by specific campaign
            campaign_breakdown = []
            if not campaign_id:
                campaign_query = f"""
                SELECT 
                    c.campaign_id,
                    c.campaign_name,
                    COUNT(pl.placement_id) as total_placements,
                    COUNT(CASE WHEN pl.current_status IN ('live', 'paid') THEN 1 END) as completed,
                    COUNT(CASE WHEN pl.current_status IN ('scheduled', 'recording_booked') THEN 1 END) as scheduled,
                    COUNT(CASE WHEN pl.current_status IN ('cancelled', 'rejected') THEN 1 END) as cancelled
                FROM campaigns c
                LEFT JOIN placements pl ON c.campaign_id = pl.campaign_id
                WHERE c.person_id = $1
                GROUP BY c.campaign_id, c.campaign_name
                HAVING COUNT(pl.placement_id) > 0
                ORDER BY COUNT(pl.placement_id) DESC
                LIMIT 10
                """
                
                campaign_rows = await conn.fetch(campaign_query, person_id)
                campaign_breakdown = [dict(row) for row in campaign_rows]
            
            # Calculate pitch to placement conversion rate
            pitch_count_query = f"""
            SELECT COUNT(DISTINCT p.pitch_id) as total_pitches
            FROM pitches p
            JOIN campaigns c ON p.campaign_id = c.campaign_id
            WHERE c.person_id = $1
            AND p.pitch_state IN ('sent', 'opened', 'replied', 'clicked', 'replied_interested', 'live', 'paid')
            """
            pitch_count_params = [person_id]
            if campaign_id:
                pitch_count_query += " AND p.campaign_id = $2"
                pitch_count_params.append(campaign_id)
            if days:
                pitch_count_query += f" AND p.created_at >= NOW() - INTERVAL '{days} days'"
            
            pitch_result = await conn.fetchrow(pitch_count_query, *pitch_count_params)
            total_pitches = pitch_result['total_pitches'] if pitch_result else 0
            
        # Calculate rates and prepare response
        total = metrics['total_placements'] or 0
        completed = (metrics['live'] or 0) + (metrics['paid'] or 0) + (metrics['recorded'] or 0)
        scheduled = (metrics['scheduled'] or 0) + (metrics['recording_booked'] or 0)
        
        return {
            "period_days": days,
            "campaign_id": str(campaign_id) if campaign_id else None,
            "totals": {
                "total_placements": total,
                "scheduled": metrics['scheduled'] or 0,
                "recording_booked": metrics['recording_booked'] or 0,
                "recorded": metrics['recorded'] or 0,
                "live": metrics['live'] or 0,
                "paid": metrics['paid'] or 0,
                "cancelled": metrics['cancelled'] or 0,
                "completed": completed,
                "in_progress": scheduled
            },
            "conversion": {
                "total_pitches_sent": total_pitches,
                "total_placements": total,
                "conversion_rate": round((total / total_pitches * 100) if total_pitches > 0 else 0, 2),
                "completion_rate": round((completed / total * 100) if total > 0 else 0, 2)
            },
            "upcoming": {
                "recordings": metrics['upcoming_recordings'] or 0,
                "go_live": metrics['upcoming_go_live'] or 0,
                "events": [
                    {
                        "placement_id": p['placement_id'],
                        "status": p['current_status'],
                        "recording_date": p['recording_date'].isoformat() if p['recording_date'] else None,
                        "go_live_date": p['go_live_date'].isoformat() if p['go_live_date'] else None,
                        "topic": p['outreach_topic'],
                        "campaign_name": p['campaign_name'],
                        "media_name": p['media_name'],
                        "host_names": p['host_names'] or []
                    }
                    for p in upcoming
                ]
            },
            "recent_activity": [
                {
                    "placement_id": p['placement_id'],
                    "status": p['current_status'],
                    "created_at": p['created_at'].isoformat() if p['created_at'] else None,
                    "updated_at": p['status_ts'].isoformat() if p['status_ts'] else None,
                    "campaign_name": p['campaign_name'],
                    "media_name": p['media_name']
                }
                for p in recent
            ],
            "campaign_breakdown": campaign_breakdown
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching placement metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch placement metrics: {str(e)}"
        )

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