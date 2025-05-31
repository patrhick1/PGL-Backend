# podcast_outreach/api/schemas/pitch_schemas.py

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime

class PitchEmail(BaseModel):
    """Pitch email response model"""
    email_body: str = Field(
        ..., 
        description="The complete pitch email body text, ready to be sent to the podcast host"
    )

class SubjectLine(BaseModel):
    """Subject line response model"""
    subject: str = Field(
        ..., 
        description="A clear, concise, and engaging email subject line"
    )

class PitchGenerationRequest(BaseModel):
    match_id: int = Field(..., description="The ID of the approved match suggestion for which to generate a pitch.")
    pitch_template_id: str = Field(..., description="ID of the pitch template to use (e.g., 'friendly_intro_template').")

class PitchGenerationResponse(BaseModel):
    pitch_gen_id: int
    campaign_id: uuid.UUID
    media_id: int
    generated_at: datetime
    status: str
    message: str
    pitch_text_preview: Optional[str] = None
    subject_line_preview: Optional[str] = None
    review_task_id: Optional[int] = None

class PitchInDB(BaseModel):
    pitch_id: int
    campaign_id: uuid.UUID
    media_id: int
    attempt_no: int
    match_score: Optional[float]
    matched_keywords: Optional[List[str]]
    score_evaluated_at: Optional[datetime]
    outreach_type: Optional[str]
    subject_line: Optional[str]
    body_snippet: Optional[str]
    send_ts: Optional[datetime]
    reply_bool: Optional[bool]
    reply_ts: Optional[datetime]
    instantly_lead_id: Optional[str] = None # Added for Instantly Lead ID
    pitch_gen_id: Optional[int]
    placement_id: Optional[int]
    pitch_state: Optional[str]
    client_approval_status: Optional[str]
    created_by: Optional[str]
    created_at: datetime

    # Enriched fields
    campaign_name: Optional[str] = None
    media_name: Optional[str] = None
    client_name: Optional[str] = None
    # Potentially full draft_text from pitch_generations if displaying sent content
    draft_text: Optional[str] = None 

    class Config:
        from_attributes = True

class PitchGenerationInDB(BaseModel):
    pitch_gen_id: int
    campaign_id: uuid.UUID
    media_id: int
    template_id: str
    draft_text: Optional[str] = None
    ai_model_used: Optional[str]
    pitch_topic: Optional[str]
    temperature: Optional[float]
    generated_at: datetime
    reviewer_id: Optional[str]
    reviewed_at: Optional[datetime]
    final_text: Optional[str]
    send_ready_bool: Optional[bool]
    generation_status: Optional[str]

    class Config:
        from_attributes = True

class PitchGenerationContentUpdate(BaseModel):
    draft_text: Optional[str] = Field(None, description="The updated draft text of the pitch email body.")
    new_subject_line: Optional[str] = Field(None, description="The updated subject line for the pitch.")

    class Config:
        from_attributes = True # Or orm_mode for Pydantic v1 compatibility
