# podcast_outreach/api/schemas/dashboard_schemas.py
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime # Ensure datetime is imported for type hints

# Schema for individual stats card (if you plan to use it)
class DashboardStat(BaseModel):
    title: str
    value: str # Keep as string for flexibility (e.g., "10", "75%", "$1.2k")
    change: Optional[str] = None # e.g., "+12% from last month"
    icon_name: Optional[str] = None # For frontend to map to an icon component

# Schema for the main stats overview
class DashboardStatsOverview(BaseModel):
    active_campaigns: int
    approved_placements: int # Renamed from approvedBookings for consistency
    pending_reviews: int # e.g., pending match_suggestions or pitch_reviews
    success_rate_placements: float # e.g., (approved_placements / total_pitches_sent) * 100

# Schema for a recent placement item
class RecentPlacementItem(BaseModel):
    placement_id: int
    status: Optional[str] = None
    created_at: datetime # Use datetime type
    podcast_name: Optional[str] = None
    podcast_category: Optional[str] = None
    podcast_cover_image_url: Optional[str] = None
    campaign_name: Optional[str] = None # Added for context
    client_name: Optional[str] = None # Added for context

# Schema for a recommended podcast item
class RecommendedPodcastItem(BaseModel):
    media_id: int
    name: Optional[str] = None
    host_names: Optional[List[str]] = None # Assuming host_names is a list in your media table
    category: Optional[str] = None
    audience_size: Optional[int] = None # Example metric for recommendation
    description: Optional[str] = None
    image_url: Optional[str] = None
    quality_score: Optional[float] = None # If you use this for recommendations
    website: Optional[str] = None # Added for linking