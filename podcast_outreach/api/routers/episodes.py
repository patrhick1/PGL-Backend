import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query, status
import uuid

from podcast_outreach.api.schemas import episode_schemas # Assuming schemas exist or will be created
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.api.dependencies import get_current_user # Assuming this dependency for auth

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/episodes",
    tags=["Episodes"],
    dependencies=[Depends(get_current_user)] # Basic auth for accessing episode data
)

@router.get("/", response_model=List[episode_schemas.EpisodeInDB])
async def list_episodes_for_media(
    media_id: int = Query(..., description="The ID of the media to fetch episodes for."),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination."),
    limit: int = Query(100, ge=1, le=200, description="Maximum number of records to return.")
):
    """Retrieve episodes for a specific media ID with pagination."""
    try:
        # Using the recently added paginated query function
        episodes_db = await episode_queries.get_episodes_for_media_paginated(
            media_id=media_id, 
            offset=skip, 
            limit=limit
        )
        
        if not episodes_db:
            # It's not an error if a media has no episodes, return empty list.
            return []
            
        return [episode_schemas.EpisodeInDB(**ep) for ep in episodes_db]
    except Exception as e:
        logger.error(f"Error fetching episodes for media_id {media_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch episodes for media ID {media_id}"
        ) 