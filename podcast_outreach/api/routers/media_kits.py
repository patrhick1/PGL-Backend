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
from podcast_outreach.api.schemas.media_kit_schemas import MediaKitImageAddRequest

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
    user: Dict[str, Any] = Depends(get_current_user) # Clients can manage their own, Staff/Admin can manage any
):
    """
    Creates a new media kit for a campaign or updates an existing one.
    The service will pull bio/angles from the campaign's GDocs.
    Editable content like headline, intro, achievements are passed in the request body.
    Clients can create/update media kits for their own campaigns. Staff/Admin can manage any campaign.
    """
    campaign = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
    
    # Authorization: Ensure user can access this campaign
    if user.get("role") == "client" and campaign.get("person_id") != user.get("person_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this campaign's media kit.")
    # Admin/staff can manage any campaign

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
    
    # Map custom_intro to introduction field
    if "custom_intro" in update_payload:
        update_payload["introduction"] = update_payload.pop("custom_intro")
    
    # Validate call_to_action_url if provided
    if "call_to_action_url" in update_payload:
        url = update_payload["call_to_action_url"]
        # Convert Pydantic HttpUrl to string if needed
        if hasattr(url, '__str__') and not isinstance(url, str):
            update_payload["call_to_action_url"] = str(url)
        # Allow empty string to clear the URL
        elif url == "":
            update_payload["call_to_action_url"] = None
    
    if "slug" in update_payload and update_payload["slug"] != existing_kit.get("slug"):
        if await media_kit_queries.check_slug_exists(update_payload["slug"], exclude_media_kit_id=existing_kit["media_kit_id"]):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Slug '{update_payload['slug']}' already exists.")

    updated_kit = await media_kit_queries.update_media_kit_in_db(existing_kit["media_kit_id"], update_payload)
    if not updated_kit:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update media kit settings.")
    return mk_schemas.MediaKitInDB(**updated_kit)

# --- Publicly Accessible Media Kit Endpoint ---
@router.get("/media-kits/{media_kit_id}", 
            response_model=mk_schemas.MediaKitInDB, 
            summary="Get Media Kit by ID",
            tags=["Media Kits - Direct Access"])
async def get_media_kit_by_id(
    media_kit_id: uuid.UUID,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get a media kit by its ID.
    
    Authorization:
    - Clients can only access their own media kits
    - Staff/Admin can access any media kit
    """
    media_kit = await media_kit_queries.get_media_kit_by_id_from_db(media_kit_id)
    if not media_kit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media kit not found.")
    
    # Authorization check
    if user.get("role") == "client" and media_kit.get("person_id") != user.get("person_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this media kit.")
    
    return mk_schemas.MediaKitInDB(**media_kit)

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

@router.post("/campaigns/{campaign_id}/media-kit/images", response_model=mk_schemas.MediaKitInDB, tags=["Media Kits - Campaign Specific"])
async def add_media_kit_image(
    campaign_id: uuid.UUID,
    request_data: MediaKitImageAddRequest,
    user: dict = Depends(get_current_user)
):
    """
    Adds a new image URL (headshot or logo) to a campaign's media kit.
    This is called *after* the image has been uploaded to S3.
    """
    # Authorization check
    campaign = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    if user.get("role") == "client" and campaign.get("person_id") != user.get("person_id"):
        raise HTTPException(status_code=403, detail="Access denied to this media kit.")

    # Get existing media kit
    kit = await media_kit_queries.get_media_kit_by_campaign_id_from_db(campaign_id)
    if not kit:
        raise HTTPException(status_code=404, detail="Media kit not found for this campaign.")

    update_payload = {}
    image_url_str = str(request_data.image_url)

    if request_data.image_type == 'headshot':
        # Update single headshot image URL
        update_payload["headshot_image_url"] = image_url_str

    elif request_data.image_type == 'logo':
        update_payload["logo_image_url"] = image_url_str
    
    else:
        raise HTTPException(status_code=400, detail="Invalid image_type. Must be 'headshot' or 'logo'.")

    # Update the database
    updated_kit = await media_kit_queries.update_media_kit_in_db(kit['media_kit_id'], update_payload)
    if not updated_kit:
        raise HTTPException(status_code=500, detail="Failed to add image to media kit.")

    return updated_kit

@router.put("/media-kits/{media_kit_id}", 
            response_model=mk_schemas.MediaKitInDB, 
            summary="Update All Media Kit Fields",
            tags=["Media Kits - Direct Update"])
async def update_media_kit_all_fields(
    media_kit_id: uuid.UUID,
    update_data: mk_schemas.MediaKitBase,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Update any/all fields of a media kit directly by media_kit_id.
    This endpoint allows updating all fields including:
    - Content fields (headline, tagline, introduction, bios, etc.)
    - Settings (is_public, theme_preference)
    - Images (headshot_image_url, logo_image_url)
    - Social links and stats
    - Custom sections, talking points, achievements, etc.
    
    Authorization:
    - Clients can only update their own media kits
    - Staff/Admin can update any media kit
    """
    # Get the existing media kit first
    existing_kit = await media_kit_queries.get_media_kit_by_id_from_db(media_kit_id)
    if not existing_kit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media kit not found.")
    
    # Authorization check
    if user.get("role") == "client" and existing_kit.get("person_id") != user.get("person_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to update this media kit.")
    
    # Convert the update data to dict, excluding unset values
    update_payload = update_data.model_dump(exclude_unset=True)
    
    # Remove fields that shouldn't be updated directly
    fields_to_exclude = ["media_kit_id", "campaign_id", "person_id", "created_at", "updated_at"]
    for field in fields_to_exclude:
        update_payload.pop(field, None)
    
    # If slug is being updated, check for uniqueness
    if "slug" in update_payload and update_payload["slug"] != existing_kit.get("slug"):
        if await media_kit_queries.check_slug_exists(update_payload["slug"], exclude_media_kit_id=media_kit_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Slug '{update_payload['slug']}' already exists.")
    
    try:
        # Update the media kit
        updated_kit = await media_kit_queries.update_media_kit_in_db(media_kit_id, update_payload)
        if not updated_kit:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update media kit.")
        
        logger.info(f"Media kit {media_kit_id} updated with {len(update_payload)} fields by user {user.get('person_id')}")
        return mk_schemas.MediaKitInDB(**updated_kit)
    except Exception as e:
        logger.exception(f"Error updating media kit {media_kit_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.patch("/media-kits/{media_kit_id}", 
              response_model=mk_schemas.MediaKitInDB, 
              summary="Partially Update Media Kit Fields",
              tags=["Media Kits - Direct Update"])
async def patch_media_kit_fields(
    media_kit_id: uuid.UUID,
    update_data: Dict[str, Any],
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Partially update specific fields of a media kit.
    This is a more flexible PATCH endpoint that accepts any valid media kit fields.
    
    Authorization:
    - Clients can only update their own media kits
    - Staff/Admin can update any media kit
    """
    # Get the existing media kit first
    existing_kit = await media_kit_queries.get_media_kit_by_id_from_db(media_kit_id)
    if not existing_kit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media kit not found.")
    
    # Authorization check
    if user.get("role") == "client" and existing_kit.get("person_id") != user.get("person_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to update this media kit.")
    
    # Remove fields that shouldn't be updated directly
    fields_to_exclude = ["media_kit_id", "campaign_id", "person_id", "created_at", "updated_at"]
    for field in fields_to_exclude:
        update_data.pop(field, None)
    
    # Validate fields exist in the schema
    valid_fields = {
        "title", "slug", "is_public", "theme_preference", "headline", "tagline", 
        "introduction", "full_bio_content", "summary_bio_content", "short_bio_content",
        "bio_source", "keywords", "talking_points", "angles_source", "sample_questions",
        "key_achievements", "previous_appearances", "person_social_links", "social_media_stats",
        "testimonials_section", "headshot_image_url", "logo_image_url", "call_to_action_text",
        "call_to_action_url", "show_contact_form", "contact_information_for_booking", "custom_sections"
    }
    
    # Filter out invalid fields
    filtered_update_data = {k: v for k, v in update_data.items() if k in valid_fields}
    
    if not filtered_update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid fields to update.")
    
    # If slug is being updated, check for uniqueness
    if "slug" in filtered_update_data and filtered_update_data["slug"] != existing_kit.get("slug"):
        if await media_kit_queries.check_slug_exists(filtered_update_data["slug"], exclude_media_kit_id=media_kit_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Slug '{filtered_update_data['slug']}' already exists.")
    
    try:
        # Update the media kit
        updated_kit = await media_kit_queries.update_media_kit_in_db(media_kit_id, filtered_update_data)
        if not updated_kit:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update media kit.")
        
        logger.info(f"Media kit {media_kit_id} patched with fields {list(filtered_update_data.keys())} by user {user.get('person_id')}")
        return mk_schemas.MediaKitInDB(**updated_kit)
    except Exception as e:
        logger.exception(f"Error patching media kit {media_kit_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))