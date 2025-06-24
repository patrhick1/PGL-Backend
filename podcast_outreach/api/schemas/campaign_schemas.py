# podcast_outreach/api/schemas/campaign_schemas.py

import uuid
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date

class CampaignBase(BaseModel):
    person_id: int # Foreign key to PEOPLE table
    attio_client_id: Optional[uuid.UUID] = None
    campaign_name: str
    campaign_type: Optional[str] = None
    campaign_bio: Optional[str] = None # Link to GDoc or text
    campaign_angles: Optional[str] = None # Link to GDoc or text
    campaign_keywords: Optional[List[str]] = None # Stored as TEXT[] in DB
    questionnaire_keywords: Optional[List[str]] = None # LLM generated keywords from questionnaire
    gdoc_keywords: Optional[List[str]] = None # Keywords from Google Docs analysis
    compiled_social_posts: Optional[str] = None # Link to GDoc or text
    podcast_transcript_link: Optional[str] = None # Link to GDoc
    compiled_articles_link: Optional[str] = None # Link to GDoc
    mock_interview_trancript: Optional[str] = None # Link to GDoc or text
    # embedding: Optional[List[float]] = None # VECTOR(1536) - Handled separately if needed
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    goal_note: Optional[str] = None
    media_kit_url: Optional[str] = None
    instantly_campaign_id: Optional[str] = None # Instantly.ai campaign ID for integration
    ideal_podcast_description: Optional[str] = None  # Description of ideal podcast for vetting
    questionnaire_responses: Optional[Dict[str, Any]] = None

class CampaignCreate(CampaignBase):
    campaign_id: uuid.UUID = Field(default_factory=uuid.uuid4) # Client can provide or defaults to new UUID

class CampaignUpdate(BaseModel):
    person_id: Optional[int] = None
    attio_client_id: Optional[uuid.UUID] = None
    campaign_name: Optional[str] = None
    campaign_type: Optional[str] = None
    campaign_bio: Optional[str] = None
    campaign_angles: Optional[str] = None
    campaign_keywords: Optional[List[str]] = None
    questionnaire_keywords: Optional[List[str]] = None # Allow updating this field too
    gdoc_keywords: Optional[List[str]] = None # Keywords from Google Docs analysis
    compiled_social_posts: Optional[str] = None
    podcast_transcript_link: Optional[str] = None
    compiled_articles_link: Optional[str] = None
    mock_interview_trancript: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    goal_note: Optional[str] = None
    media_kit_url: Optional[str] = None
    instantly_campaign_id: Optional[str] = None # Instantly.ai campaign ID for integration
    ideal_podcast_description: Optional[str] = None  # Description of ideal podcast for vetting
    questionnaire_responses: Optional[Dict[str, Any]] = None

class CampaignInDB(CampaignBase):
    campaign_id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True # For SQLAlchemy or other ORMs; helps map to DB objects

class QuestionnaireDraftData(BaseModel):
    questionnaire_data: Dict[str, Any] = Field(..., description="Partial or complete questionnaire data to be saved as a draft.")

class AnglesBioTriggerResponse(BaseModel):
    campaign_id: uuid.UUID
    status: str # e.g., "processing_started", "success", "error", "skipped"
    message: str
    details: Optional[Dict[str, Any]] = None

class QuestionnaireSubmitData(BaseModel):
    questionnaire_data: Dict[str, Any] # This will hold the structured JSON from the frontend