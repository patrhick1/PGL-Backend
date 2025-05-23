# podcast_outreach/api/routers/media.py

import uuid
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional, Dict, Any
from datetime import datetime

# Import schemas
from api.schemas.media_schemas import MediaCreate, MediaUpdate, MediaInDB

# Import db_service_pg (assuming it's still at project root for now)
import db_service_pg 

# Import dependencies for authentication
from api.dependencies import get_current_user, get_admin_user

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/media", tags=["Media"])

@router.post("/", response_model=MediaInDB, status_code=status.HTTP_201_CREATED, summary="Create New Media (Podcast)")
async def create_media_api(media: MediaCreate, user: dict = Depends(get_admin_user)):
    """
    Creates a new media (podcast) record. Admin access required.
    """
    media_dict = media.model_dump()
    try:
        # Check for existing media by RSS URL if provided
        if media.rss_url:
            existing_media = await db_service_pg.get_media_by_rss_url_from_db(media.rss_url)
            if existing_media:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Media with RSS URL {media.rss_url} already exists.")

        created_db_media = await db_service_pg.create_media_in_db(media_dict)
        if not created_db_media:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create media in database.")
        return MediaInDB(**created_db_media)
    except Exception as e:
        logger.exception(f"Error in create_media_api for media name {media.name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/", response_model=List[MediaInDB], summary="List All Media (Podcasts)")
async def list_media_api(skip: int = 0, limit: int = 100, user: dict = Depends(get_current_user)):
    """
    Lists all media (podcast) records with pagination. Staff or Admin access required.
    """
    try:
        media_from_db = await db_service_pg.get_all_media_from_db(skip=skip, limit=limit)
        return [MediaInDB(**m) for m in media_from_db]
    except Exception as e:
        logger.exception(f"Error in list_media_api: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/{media_id}", response_model=MediaInDB, summary="Get Specific Media (Podcast) by ID")
async def get_media_api(media_id: int, user: dict = Depends(get_current_user)):
    """
    Retrieves a specific media (podcast) record by ID. Staff or Admin access required.
    """
    try:
        media_from_db = await db_service_pg.get_media_by_id_from_db(media_id)
        if not media_from_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Media with ID {media_id} not found.")
        return MediaInDB(**media_from_db)
    except Exception as e:
        logger.exception(f"Error in get_media_api for ID {media_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put("/{media_id}", response_model=MediaInDB, summary="Update Media (Podcast)")
async def update_media_api(media_id: int, media_update_data: MediaUpdate, user: dict = Depends(get_admin_user)):
    """
    Updates an existing media (podcast) record. Admin access required.
    """
    update_data = media_update_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided.")
    try:
        updated_db_media = await db_service_pg.update_media_in_db(media_id, update_data)
        if not updated_db_media:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Media with ID {media_id} not found or update failed.")
        return MediaInDB(**updated_db_media)
    except Exception as e:
        logger.exception(f"Error in update_media_api for ID {media_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete("/{media_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Media (Podcast)")
async def delete_media_api(media_id: int, user: dict = Depends(get_admin_user)):
    """
    Deletes a media (podcast) record. Admin access required.
    """
    try:
        success = await db_service_pg.delete_media_from_db(media_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Media with ID {media_id} not found or delete failed.")
        return # Returns 204 No Content on success
    except Exception as e:
        logger.exception(f"Error in delete_media_api for ID {media_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
