import os
import uuid
import logging
from pydantic import BaseModel, Field, ConfigDict
from fastapi import APIRouter, Depends, HTTPException

from podcast_outreach.api.dependencies import get_current_user
from podcast_outreach.services.storage_service import storage_service
from podcast_outreach.logging_config import get_logger

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
            detail="Could not generate upload URL. Check server logs for specific AWS S3 errors."
        )
    # --- END OF MODIFIED SECTION ---

    return PresignedUrlResponse(
        upload_url=upload_url,
        object_key=object_key,
        final_url=storage_service.get_object_url(object_key)
    )