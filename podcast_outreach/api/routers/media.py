# podcast_outreach/api/routers/media.py

import uuid
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional, Dict, Any
from datetime import datetime

# Import schemas
from ..schemas.media_schemas import MediaCreate, MediaUpdate, MediaInDB, AdminDiscoveryRequestSchema

# Import modular queries
from podcast_outreach.database.queries import media as media_queries

# Import dependencies for authentication
from ..dependencies import get_current_user, get_admin_user

# Import the fetcher
from podcast_outreach.services.media.podcast_fetcher import MediaFetcher

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
            existing_media = await media_queries.get_media_by_rss_url_from_db(media.rss_url)
            if existing_media:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Media with RSS URL {media.rss_url} already exists.")

        created_db_media = await media_queries.create_media_in_db(media_dict)
        if not created_db_media:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create media in database.")
        return MediaInDB(**created_db_media)
    except HTTPException:
        raise # Re-raise FastAPI HTTPExceptions
    except Exception as e:
        logger.exception(f"Error in create_media_api for media name {media.name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/", response_model=List[MediaInDB], summary="List All Media (Podcasts)")
async def list_media_api(skip: int = 0, limit: int = 100, user: dict = Depends(get_current_user)):
    """
    Lists all media (podcast) records with pagination. Staff or Admin access required.
    """
    try:
        media_from_db = await media_queries.get_all_media_from_db(skip=skip, limit=limit)
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
        media_from_db = await media_queries.get_media_by_id_from_db(media_id)
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
        updated_db_media = await media_queries.update_media_in_db(media_id, update_data)
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
        success = await media_queries.delete_media_from_db(media_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Media with ID {media_id} not found or delete failed.")
        return # Returns 204 No Content on success
    except Exception as e:
        logger.exception(f"Error in delete_media_api for ID {media_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/discover-admin", response_model=List[MediaInDB], summary="Admin Discover Podcasts")
async def admin_discover_podcasts_api(
    payload: AdminDiscoveryRequestSchema, 
    current_user: dict = Depends(get_admin_user) # Or a more general staff/admin check
):
    """
    Allows Admin/Staff to discover podcasts by keyword.
    This endpoint directly uses the MediaFetcher to search, enrich, and upsert media,
    bypassing client-specific limitations. Results are full media records.
    """
    media_fetcher = MediaFetcher()
    try:
        # The new method in MediaFetcher is admin_discover_and_process_podcasts
        # It expects: keyword: str, campaign_id_for_association: Optional[uuid.UUID], max_results_per_source: int
        # The payload AdminDiscoveryRequestSchema provides query (keyword) and campaign_id.
        # We can use a default for max_results_per_source or make it part of AdminDiscoveryRequestSchema if needed.
        # For now, using the default from the method (e.g., 10).
        
        results_from_fetcher = await media_fetcher.admin_discover_and_process_podcasts(
            keyword=payload.query,
            campaign_id_for_association=payload.campaign_id, # This is Optional[uuid.UUID]
            max_results_per_source=10 # Staff/admin can get a decent number; can be parameterized if needed
        )
        
        # The fetcher method is designed to return a list of dicts that are compatible with MediaInDB
        return [MediaInDB.model_validate(r) for r in results_from_fetcher]
    
    except HTTPException: # Re-raise HTTPExceptions directly if they occur in the fetcher
        raise
    except Exception as e:
        logger.exception(f"Error in admin_discover_podcasts_api for query '{payload.query}': {e}")
        # Consider if more specific error handling from fetcher is needed
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Admin discovery failed: {str(e)}")
    finally:
        # Ensure ThreadPoolExecutor in MediaFetcher is cleaned up
        media_fetcher.cleanup()
