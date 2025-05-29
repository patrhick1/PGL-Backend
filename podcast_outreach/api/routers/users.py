# podcast_outreach/api/routers/users.py (or people.py)
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, Optional

from ..schemas.person_schemas import PersonInDB # For response
from ..schemas.settings_schemas import NotificationSettingsUpdate, PrivacySettingsUpdate # Create this schema
from podcast_outreach.database.queries import people as people_queries
from ..dependencies import get_current_user

router = APIRouter(prefix="/users/me", tags=["Current User Settings"]) # Example prefix

@router.patch("/notification-settings", response_model=PersonInDB, summary="Update Notification Settings")
async def update_my_notification_settings(
    settings_data: NotificationSettingsUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated.")

    # The settings_data.model_dump() will be a dict like {"emailNotifications": true, ...}
    # This dict can be directly stored in the JSONB column.
    updated_person = await people_queries.update_person_in_db(
        person_id, 
        {"notification_settings": settings_data.model_dump()}
    )
    if not updated_person:
        raise HTTPException(status_code=500, detail="Failed to update notification settings.")
    return PersonInDB(**updated_person)

@router.patch("/privacy-settings", response_model=PersonInDB, summary="Update Privacy Settings")
async def update_my_privacy_settings(
    settings_data: PrivacySettingsUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated.")
    
    updated_person = await people_queries.update_person_in_db(
        person_id, 
        {"privacy_settings": settings_data.model_dump()}
    )
    if not updated_person:
        raise HTTPException(status_code=500, detail="Failed to update privacy settings.")
    return PersonInDB(**updated_person)