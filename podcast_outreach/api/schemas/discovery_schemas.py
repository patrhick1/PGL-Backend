# podcast_outreach/api/schemas/discovery_schemas.py

import uuid
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

class DiscoveryResponse(BaseModel):
    """Response for the discovery endpoint - immediate response while processing happens in background"""
    status: str = Field(..., description="Status: success, error")
    message: str = Field(..., description="Human readable message")
    campaign_id: uuid.UUID = Field(..., description="Campaign ID that was processed")
    discoveries_initiated: int = Field(..., description="Number of discoveries started")
    estimated_completion_minutes: int = Field(..., description="Estimated time to complete processing")
    track_endpoint: str = Field(..., description="Endpoint to track progress")

class DiscoveryStatus(BaseModel):
    """Status tracking for discovery processing"""
    discovery_id: int = Field(..., description="Discovery ID")
    campaign_id: uuid.UUID = Field(..., description="Campaign ID")
    media_id: int = Field(..., description="Media/Podcast ID")
    media_name: str = Field(..., description="Podcast name")
    discovery_keyword: str = Field(..., description="Keyword used for discovery")
    
    # Processing status
    enrichment_status: str = Field(..., description="pending, in_progress, completed, failed")
    vetting_status: str = Field(..., description="pending, in_progress, completed, failed")
    overall_status: str = Field(..., description="Overall processing status")
    
    # Results
    vetting_score: Optional[float] = Field(None, description="AI vetting score (0-10)")
    match_created: bool = Field(False, description="Whether match suggestion was created")
    review_task_created: bool = Field(False, description="Whether review task was created")
    
    # Timestamps
    discovered_at: datetime = Field(..., description="When discovery was initiated")
    updated_at: datetime = Field(..., description="Last update timestamp")
    
    # Error handling
    enrichment_error: Optional[str] = Field(None, description="Enrichment error if failed")
    vetting_error: Optional[str] = Field(None, description="Vetting error if failed")

class DiscoveryStatusList(BaseModel):
    """List of discovery statuses with pagination"""
    items: List[DiscoveryStatus]
    total: int
    in_progress: int = Field(..., description="Number still processing")
    completed: int = Field(..., description="Number completed")
    failed: int = Field(..., description="Number failed")

class EnhancedReviewTaskResponse(BaseModel):
    """Enhanced review task response with full discovery context and AI reasoning"""
    review_task_id: int
    task_type: str = Field(..., description="match_suggestion, pitch_review, etc.")
    related_id: int = Field(..., description="ID of related entity (match_id, etc)")
    campaign_id: uuid.UUID
    status: str = Field(..., description="pending, approved, rejected, completed")
    created_at: datetime
    completed_at: Optional[datetime] = None
    
    # Campaign context
    campaign_name: Optional[str] = None
    client_name: Optional[str] = None
    
    # Media/Podcast information
    media_id: Optional[int] = None
    media_name: Optional[str] = None
    media_website: Optional[str] = None
    media_image_url: Optional[str] = None
    media_description: Optional[str] = None
    host_names: Optional[List[str]] = Field(None, description="List of podcast hosts")
    
    # Social media handles
    podcast_twitter_url: Optional[str] = None
    podcast_linkedin_url: Optional[str] = None
    podcast_instagram_url: Optional[str] = None
    podcast_facebook_url: Optional[str] = None
    podcast_youtube_url: Optional[str] = None
    podcast_tiktok_url: Optional[str] = None
    
    # Discovery context
    discovery_keyword: Optional[str] = Field(None, description="Keyword used to discover this podcast")
    discovered_at: Optional[datetime] = Field(None, description="When podcast was discovered")
    
    # AI Vetting Results (for match_suggestion tasks)
    vetting_score: Optional[float] = Field(None, description="AI vetting score (0-10)")
    vetting_reasoning: Optional[str] = Field(None, description="Detailed AI reasoning")
    vetting_criteria_met: Optional[Dict[str, Any]] = Field(None, description="Specific criteria analysis")
    
    # Match information
    match_score: Optional[float] = Field(None, description="Basic similarity match score")
    matched_keywords: Optional[List[str]] = Field(None, description="Keywords that matched")
    best_matching_episode_id: Optional[int] = Field(None, description="Episode that best matches campaign")
    
    # User-friendly summary
    recommendation: Optional[str] = Field(None, description="High-level recommendation: Highly Recommended, Good Match, etc.")
    key_highlights: Optional[List[str]] = Field(None, description="Key points from AI analysis")
    potential_concerns: Optional[List[str]] = Field(None, description="Any concerns identified by AI")
    
    # Pitch-related fields (for pitch_review tasks)
    pitch_gen_id: Optional[int] = Field(None, description="ID of the pitch generation")
    pitch_subject_line: Optional[str] = Field(None, description="Generated email subject line")
    pitch_body_full: Optional[str] = Field(None, description="Full generated pitch email body for editing")
    pitch_template_used: Optional[str] = Field(None, description="Template ID used for pitch generation")
    pitch_generation_status: Optional[str] = Field(None, description="Status of the pitch generation")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )

class ReviewTaskApprovalRequest(BaseModel):
    """Request to approve/reject a review task"""
    status: str = Field(..., description="approved, rejected")
    notes: Optional[str] = Field(None, description="Optional notes from reviewer")
    
class ReviewTaskFilters(BaseModel):
    """Filters for review task listing"""
    campaign_id: Optional[uuid.UUID] = None
    task_type: Optional[str] = Field(None, description="match_suggestion, pitch_review")
    status: Optional[str] = Field(None, description="pending, approved, rejected")
    min_vetting_score: Optional[float] = Field(None, description="Minimum AI vetting score")
    discovery_keyword: Optional[str] = Field(None, description="Filter by discovery keyword")
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None