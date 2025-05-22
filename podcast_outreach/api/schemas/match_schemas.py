# podcast_outreach/api/schemas/match_schemas.py

import uuid
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class MatchSuggestionBase(BaseModel):
    campaign_id: uuid.UUID # FK to campaigns table
    media_id: int        # FK to media table
    match_score: Optional[float] = None # NUMERIC can be float
    matched_keywords: Optional[List[str]] = None # TEXT[]
    ai_reasoning: Optional[str] = None
    status: Optional[str] = Field(default="pending", description="Status: pending, approved, rejected") 

class MatchSuggestionCreate(MatchSuggestionBase):
    pass

class MatchSuggestionUpdate(BaseModel):
    match_score: Optional[float] = None
    matched_keywords: Optional[List[str]] = None
    ai_reasoning: Optional[str] = None
    client_approved: Optional[bool] = None
    approved_at: Optional[datetime] = None # Can be set when client_approved is set to True
    status: Optional[str] = None

class MatchSuggestionInDB(MatchSuggestionBase):
    match_id: int
    client_approved: bool # Will have a default from DB if not set
    approved_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True