# podcast_outreach/api/schemas/settings_schemas.py
from pydantic import BaseModel
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