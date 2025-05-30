# podcast_outreach/api/routers/media_kits.py
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional, Dict, Any

from podcast_outreach.api.schemas import media_kit_schemas as mk_schemas
from podcast_outreach.services.media_kits.generator import MediaKitService
from podcast_outreach.api.dependencies import get_current_user, get_admin_user, get_staff_user
from podcast_outreach.database.queries import campaigns as campaign_queries # For auth check
from podcast_outreach.database.queries import media_kits as media_kit_queries # ADDED THIS IMPORT
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()
media_kit_service = MediaKitService() # Instantiate the service

@router.post("/campaigns/{campaign_id}/media-kit", 
             response_model=mk_schemas.MediaKitInDB, 
             status_code=status.HTTP_201_CREATED,
             summary="Create or Update Media Kit for a Campaign",
             tags=["Media Kits - Campaign Specific"])
async def create_or_update_campaign_media_kit(
    campaign_id: uuid.UUID,
    editable_content: mk_schemas.MediaKitEditableContentSchema,
    user: Dict[str, Any] = Depends(get_staff_user) # Staff/Admin can manage
):
    """
    Creates a new media kit for a campaign or updates an existing one.
    The service will pull bio/angles from the campaign's GDocs.
    Editable content like headline, intro, achievements are passed in the request body.
    """
    # Authorization: Ensure user has access to this campaign if not admin (e.g. staff assigned to it)
    # For now, get_staff_user is a broad check. More granular checks can be added.
    campaign = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
    
    # If user is client, ensure they own this campaign
    # This endpoint is currently staff/admin. If clients were to use it directly:
    # if user.get("role") == "client" and campaign.get("person_id") != user.get("person_id"):
    #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this campaign's media kit.")

    try:
        media_kit = await media_kit_service.create_or_update_media_kit(
            campaign_id=campaign_id,
            editable_content=editable_content.model_dump(exclude_unset=True)
        )
        if not media_kit:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create or update media kit.")
        return mk_schemas.MediaKitInDB(**media_kit)
    except Exception as e:
        logger.exception(f"Error in create_or_update_campaign_media_kit for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/campaigns/{campaign_id}/media-kit", 
            response_model=mk_schemas.MediaKitInDB, 
            summary="Get Media Kit for a Campaign",
            tags=["Media Kits - Campaign Specific"])
async def get_campaign_media_kit(
    campaign_id: uuid.UUID,
    user: Dict[str, Any] = Depends(get_current_user) # Client, Staff, or Admin
):
    """Retrieves the media kit associated with a specific campaign."""
    campaign = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")

    if user.get("role") == "client" and campaign.get("person_id") != user.get("person_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this campaign's media kit.")

    media_kit = await media_kit_service.get_media_kit_by_campaign_id(campaign_id)
    if not media_kit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media kit not found for this campaign.")
    return mk_schemas.MediaKitInDB(**media_kit)

@router.patch("/campaigns/{campaign_id}/media-kit/settings", 
              response_model=mk_schemas.MediaKitInDB, 
              summary="Update Media Kit Settings for a Campaign",
              tags=["Media Kits - Campaign Specific"])
async def update_campaign_media_kit_settings(
    campaign_id: uuid.UUID,
    settings_data: mk_schemas.MediaKitSettingsUpdateSchema,
    user: Dict[str, Any] = Depends(get_current_user) # Client, Staff, or Admin
):
    """Updates settings for a campaign's media kit (e.g., slug, is_public, theme)."""
    campaign = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")

    if user.get("role") == "client" and campaign.get("person_id") != user.get("person_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to update settings for this media kit.")

    existing_kit = await media_kit_service.get_media_kit_by_campaign_id(campaign_id)
    if not existing_kit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media kit not found for this campaign to update settings.")

    update_payload = settings_data.model_dump(exclude_unset=True)
    
    if "slug" in update_payload and update_payload["slug"] != existing_kit.get("slug"):
        if await media_kit_queries.check_slug_exists(update_payload["slug"], exclude_media_kit_id=existing_kit["media_kit_id"]):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Slug '{update_payload['slug']}' already exists.")

    updated_kit = await media_kit_queries.update_media_kit_in_db(existing_kit["media_kit_id"], update_payload)
    if not updated_kit:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update media kit settings.")
    return mk_schemas.MediaKitInDB(**updated_kit)

# --- Publicly Accessible Media Kit Endpoint ---
@router.get("/public/media-kit/{slug}", 
            response_model=mk_schemas.MediaKitInDB, # Or a specific PublicMediaKitViewSchema
            summary="Get Public Media Kit by Slug",
            tags=["Media Kits - Public"],
            # No auth Depends here, this is public
            )
async def get_public_media_kit_by_slug(slug: str):
    """Retrieves a publicly available media kit by its slug."""
    media_kit = await media_kit_service.get_media_kit_by_slug(slug)
    if not media_kit or not media_kit.get("is_public"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media kit not found or is not public.")
    return mk_schemas.MediaKitInDB(**media_kit) 