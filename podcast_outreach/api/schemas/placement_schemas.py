# podcast_outreach/api/schemas/placement_schemas.py
import uuid
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date

class PlacementBase(BaseModel):
    campaign_id: uuid.UUID
    media_id: int
    current_status: Optional[str] = Field(default="pending", description="e.g., pending, responded, interested, form_submitted, meeting_booked, recording_booked, recorded, live, paid, rejected")
    status_ts: Optional[datetime] = Field(default_factory=datetime.utcnow)
    meeting_date: Optional[date] = None
    call_date: Optional[date] = None # Could be same as meeting_date or separate
    outreach_topic: Optional[str] = None
    recording_date: Optional[date] = None
    go_live_date: Optional[date] = None
    episode_link: Optional[str] = None
    notes: Optional[str] = None
    # New fields that might be useful for client/team view
    pitch_id: Optional[int] = None # Link to the pitch that led to this placement

class PlacementCreate(PlacementBase):
    pass

class PlacementUpdate(BaseModel):
    # Allow updating most fields
    current_status: Optional[str] = None
    status_ts: Optional[datetime] = None
    meeting_date: Optional[date] = None
    call_date: Optional[date] = None
    outreach_topic: Optional[str] = None
    recording_date: Optional[date] = None
    go_live_date: Optional[date] = None
    episode_link: Optional[str] = None
    notes: Optional[str] = None
    pitch_id: Optional[int] = None
    # campaign_id and media_id are generally not updated once a placement is created

class PlacementInDB(PlacementBase):
    placement_id: int
    created_at: datetime
    # Add fields from related tables for richer responses if needed for client view
    campaign_name: Optional[str] = None
    client_name: Optional[str] = None # Person's full_name associated with campaign_id
    media_name: Optional[str] = None
    media_website: Optional[str] = None

    class Config:
        from_attributes = True

class PlacementWithDetails(PlacementInDB): # For richer client/team views
    # Inherits all from PlacementInDB
    # You can add more specific joined data here if needed
    pass

class PaginatedPlacementList(BaseModel):
    items: List[PlacementInDB] # Or PlacementWithDetails
    total: int
    page: int
    size: int