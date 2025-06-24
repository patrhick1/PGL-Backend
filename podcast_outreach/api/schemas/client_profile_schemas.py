# podcast_outreach/api/schemas/client_profile_schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
import uuid

class ClientProfileBase(BaseModel):
    plan_type: str = Field(default='free', description="Client's subscription plan type")
    daily_discovery_allowance: int = Field(default=10)
    weekly_discovery_allowance: int = Field(default=50)
    subscription_provider_id: Optional[str] = None
    subscription_status: Optional[str] = None
    subscription_ends_at: Optional[datetime] = None

class ClientProfileCreate(ClientProfileBase):
    person_id: int # Required when creating/linking

class ClientProfileUpdate(BaseModel): # For admin updates
    plan_type: Optional[str] = None
    daily_discovery_allowance: Optional[int] = None
    weekly_discovery_allowance: Optional[int] = None
    subscription_provider_id: Optional[str] = None
    subscription_status: Optional[str] = None
    subscription_ends_at: Optional[datetime] = None
    # Admin might also reset counts directly, but usually done by cron/logic
    current_daily_discoveries: Optional[int] = None
    current_weekly_discoveries: Optional[int] = None
    last_daily_reset: Optional[date] = None
    last_weekly_reset: Optional[date] = None


class ClientProfileInDB(ClientProfileBase):
    client_profile_id: int
    person_id: int
    current_daily_discoveries: int
    current_weekly_discoveries: int
    last_daily_reset: date
    last_weekly_reset: date
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# For client discovery preview endpoint
class PodcastPreviewSchema(BaseModel):
    media_id: int
    name: Optional[str] = None
    image_url: Optional[str] = None
    short_description: Optional[str] = None
    website: Optional[str] = None # Good to include for client to check
    # Add other minimal fields you want to show in a preview
    # e.g., primary_category, estimated_audience_size (if available quickly)

# For client discovery status endpoint
class ClientDiscoveryStatusSchema(BaseModel):
    person_id: int
    plan_type: str
    daily_discoveries_used: int
    daily_discovery_allowance: int
    weekly_discoveries_used: int
    weekly_discovery_allowance: int
    can_discover_today: bool
    can_discover_this_week: bool

# For client requesting match review
class ClientRequestMatchReviewSchema(BaseModel):
    campaign_id: uuid.UUID
    media_ids: List[int] = Field(..., min_items=1)