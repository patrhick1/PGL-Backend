import os
import uuid
import logging
from pydantic import BaseModel, Field, ConfigDict
from fastapi import APIRouter, Depends, HTTPException

from podcast_outreach.api.dependencies import get_current_user
from podcast_outreach.services.storage_service import storage_service
from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.queries import media_kits as media_kit_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import people as people_queries

logger = get_logger(__name__)
router = APIRouter(prefix="/storage", tags=["File Storage"])

# --- Pydantic Schemas for this Router ---

class PresignedUrlRequest(BaseModel):
    file_name: str = Field(..., alias='fileName')
    upload_context: str = Field(..., alias='uploadContext')

class PresignedUrlResponse(BaseModel):
    upload_url: str = Field(..., alias='uploadUrl')
    object_key: str = Field(..., alias='objectKey')
    final_url: str = Field(..., alias='finalUrl')

    model_config = ConfigDict(
        populate_by_name=True,
        by_alias=True,
    )

class UploadCompletionRequest(BaseModel):
    object_key: str = Field(..., alias='objectKey')
    upload_context: str = Field(..., alias='uploadContext')
    campaign_id: uuid.UUID = Field(..., alias='campaignId')

class UploadCompletionResponse(BaseModel):
    success: bool
    message: str
    file_url: str = Field(..., alias='fileUrl')

# --- API Endpoint ---

@router.post("/generate-upload-url", response_model=PresignedUrlResponse)
async def generate_upload_url(
    request_data: PresignedUrlRequest,
    user: dict = Depends(get_current_user)
):
    """
    Generates a presigned URL for uploading a file directly to S3.
    The frontend receives this URL and performs the upload.
    """
    person_id = user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Sanitize file name and create a unique object key in S3
    file_extension = os.path.splitext(request_data.file_name)[1]
    unique_id = uuid.uuid4()
    
    # Create a structured path in S3 for better organization
    object_key = f"uploads/{request_data.upload_context}/user_{person_id}/{unique_id}{file_extension}"

    # --- MODIFIED SECTION ---
    # The generate_presigned_upload_url can return None on failure. We must handle this.
    upload_url = storage_service.generate_presigned_upload_url(object_key)

    if not upload_url:
        # This is the critical change. Instead of returning a 200 OK with null data,
        # we now raise a 500 Internal Server Error.
        logger.error(f"Failed to generate presigned URL for user {person_id} and object {object_key}. Check S3 configuration and permissions.")
        raise HTTPException(
            status_code=500, 
            detail="Could not generate upload URL. AWS S3 is not configured. Please contact administrator to set up AWS credentials."
        )
    # --- END OF MODIFIED SECTION ---

    return PresignedUrlResponse(
        upload_url=upload_url,
        object_key=object_key,
        final_url=storage_service.get_object_url(object_key)
    )

@router.post("/upload-complete", response_model=UploadCompletionResponse)
async def handle_upload_completion(
    request_data: UploadCompletionRequest,
    user: dict = Depends(get_current_user)
):
    """
    Handles the completion of file uploads and updates the appropriate database records.
    Currently supports media_kit_headshot and media_kit_logo upload contexts.
    """
    person_id = user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=401, detail="User not authenticated")

    # Verify the campaign exists and user has access
    campaign = await campaign_queries.get_campaign_by_id(request_data.campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Authorization: Ensure user can access this campaign
    if user.get("role") == "client" and campaign.get("person_id") != person_id:
        raise HTTPException(status_code=403, detail="Access denied to this campaign")

    file_url = storage_service.get_object_url(request_data.object_key)
    
    try:
        # Handle media kit image uploads
        if request_data.upload_context in ["media_kit_headshot", "media_kit_logo"]:
            # Get or create media kit for this campaign
            existing_kit = await media_kit_queries.get_media_kit_by_campaign_id_from_db(request_data.campaign_id)
            
            if existing_kit:
                # Update existing media kit with new image URL
                update_data = {}
                if request_data.upload_context == "media_kit_headshot":
                    update_data["headshot_image_url"] = file_url
                elif request_data.upload_context == "media_kit_logo":
                    update_data["logo_image_url"] = file_url
                
                updated_kit = await media_kit_queries.update_media_kit_in_db(
                    existing_kit["media_kit_id"], 
                    update_data
                )
                
                if not updated_kit:
                    raise HTTPException(status_code=500, detail="Failed to update media kit with image URL")
                    
                message = f"Media kit {request_data.upload_context.replace('media_kit_', '')} updated successfully"
            else:
                # Create new media kit with the image
                person = await people_queries.get_person_by_id_from_db(person_id)
                if not person:
                    raise HTTPException(status_code=404, detail="User profile not found")
                
                # Generate unique slug for new media kit
                base_slug = f"{person.get('full_name', 'user').lower().replace(' ', '-')}-{campaign.get('campaign_name', 'campaign').lower().replace(' ', '-')}"
                slug = f"{base_slug}-{uuid.uuid4().hex[:8]}"
                
                kit_data = {
                    "campaign_id": request_data.campaign_id,
                    "person_id": person_id,
                    "slug": slug,
                    "title": f"{person.get('full_name', 'User')} Media Kit",
                    "is_public": True
                }
                
                if request_data.upload_context == "media_kit_headshot":
                    kit_data["headshot_image_url"] = file_url
                elif request_data.upload_context == "media_kit_logo":
                    kit_data["logo_image_url"] = file_url
                
                created_kit = await media_kit_queries.create_media_kit_in_db(kit_data)
                
                if not created_kit:
                    raise HTTPException(status_code=500, detail="Failed to create media kit with image")
                    
                message = f"Media kit created with {request_data.upload_context.replace('media_kit_', '')} successfully"
        
        # Handle profile image uploads (existing logic could be added here)
        elif request_data.upload_context == "profile_image":
            # Update user's profile_image_url
            updated_person = await people_queries.update_person_in_db(
                person_id,
                {"profile_image_url": file_url}
            )
            
            if not updated_person:
                raise HTTPException(status_code=500, detail="Failed to update profile image")
                
            message = "Profile image updated successfully"
        
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported upload context: {request_data.upload_context}")

        logger.info(f"Upload completion handled for user {person_id}, context: {request_data.upload_context}, file: {file_url}")
        
        return UploadCompletionResponse(
            success=True,
            message=message,
            file_url=file_url
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling upload completion: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process upload completion: {str(e)}")