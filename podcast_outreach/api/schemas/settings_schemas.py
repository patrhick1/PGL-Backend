# podcast_outreach/api/schemas/settings_schemas.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

class NotificationSettingsUpdate(BaseModel):
    emailNotifications: Optional[bool] = None
    podcastMatches: Optional[bool] = None
    applicationUpdates: Optional[bool] = None
    weeklyReports: Optional[bool] = None
    marketingEmails: Optional[bool] = None
    # Add all fields from your frontend notificationSchema

class PrivacySettingsUpdate(BaseModel):
    profileVisibility: Optional[str] = None # e.g., "public", "hosts", "private"
    dataSharing: Optional[bool] = None
    analyticsTracking: Optional[bool] = None

class UserDataExportResponse(BaseModel):
    message: str
    task_id: Optional[str] = None # If using task_manager to track the async export

class AccountDeletionRequest(BaseModel):
    password: str = Field(..., description="Current password for verification")

class AccountDeletionResponse(BaseModel):
    message: str

class AccountDeletionConfirm(BaseModel):
    token: str = Field(..., description="Deletion confirmation token received via email")