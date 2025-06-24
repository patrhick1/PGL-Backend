# podcast_outreach/api/schemas/match_schemas.py

import uuid
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class MatchSuggestionBase(BaseModel):
    campaign_id: uuid.UUID # FK to campaigns table
    media_id: int        # FK to media table
    match_score: Optional[int] = Field(None, description="Quantitative match score (0-100)")
    matched_keywords: Optional[List[str]] = None # TEXT[]
    ai_reasoning: Optional[str] = None
    status: Optional[str] = Field(default="pending", description="Status: pending, approved, rejected")
    
    # AI Vetting Fields
    vetting_score: Optional[int] = Field(None, description="AI vetting score (0-100)")
    vetting_reasoning: Optional[str] = Field(None, description="AI detailed vetting analysis")
    vetting_checklist: Optional[Dict[str, Any]] = Field(None, description="Dynamic vetting criteria with weights")
    last_vetted_at: Optional[datetime] = Field(None, description="When vetting was last performed")
    
    # Additional match details
    best_matching_episode_id: Optional[int] = Field(None, description="ID of episode that best matches campaign") 

class MatchSuggestionCreate(MatchSuggestionBase):
    pass

class MatchSuggestionUpdate(BaseModel):
    match_score: Optional[int] = None
    matched_keywords: Optional[List[str]] = None
    ai_reasoning: Optional[str] = None
    client_approved: Optional[bool] = None
    approved_at: Optional[datetime] = None # Can be set when client_approved is set to True
    status: Optional[str] = None
    
    # AI Vetting Fields
    vetting_score: Optional[int] = None
    vetting_reasoning: Optional[str] = None
    vetting_checklist: Optional[Dict[str, Any]] = None
    last_vetted_at: Optional[datetime] = None
    best_matching_episode_id: Optional[int] = None

class MatchSuggestionInDB(MatchSuggestionBase):
    match_id: int
    client_approved: bool # Will have a default from DB if not set
    approved_at: Optional[datetime]
    created_at: datetime
    media_name: Optional[str] = None 
    media_website: Optional[str] = None
    campaign_name: Optional[str] = None
    client_name: Optional[str] = None
    review_task_id: Optional[int] = Field(None, description="Associated review task ID if exists")
    class Config:
        from_attributes = True