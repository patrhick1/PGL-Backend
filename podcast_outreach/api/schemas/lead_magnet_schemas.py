from pydantic import BaseModel, EmailStr, Field
from typing import Dict, Any, Optional
import uuid

class LeadMagnetSubmission(BaseModel):
    full_name: str = Field(..., min_length=2)
    email: EmailStr
    # Simplified questionnaire data expected from the lead magnet form
    # This structure should match what your lead magnet frontend sends.
    # Example fields:
    # company_name: Optional[str] = None
    # website: Optional[str] = None
    # bio_focus: Optional[str] = Field(None, description="Short description of what they do or their main expertise.")
    # key_topics: Optional[List[str]] = Field(None, description="2-3 key topics they can speak about.") 
    # main_achievement: Optional[str] = Field(None, description="A notable achievement.")
    questionnaire_data: Dict[str, Any] = Field(..., description="Simplified questionnaire data collected from the lead magnet form.")

class LeadMagnetResponse(BaseModel):
    message: str
    person_id: Optional[int] = None
    campaign_id: Optional[uuid.UUID] = None
    media_kit_slug: Optional[str] = None 