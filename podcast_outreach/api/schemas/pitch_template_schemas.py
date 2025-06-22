from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

class PitchTemplateBase(BaseModel):
    template_id: str = Field(..., description="User-defined unique ID for the template, e.g., 'friendly_v1' or 'podcast_guest_initial_outreach'. Should be URL-safe.", min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    media_type: Optional[str] = Field(None, description="Type of media this template is generally for (e.g., 'podcast', 'blog', 'youtube')", max_length=100)
    target_media_type: Optional[str] = Field(None, description="Specific target within the media type (e.g., 'tech_podcast', 'lifestyle_blog')", max_length=100)
    language_code: Optional[str] = Field(None, description="Language code, e.g., 'en-US', 'es-ES'", max_length=10)
    tone: Optional[str] = Field(None, description="Tone of the pitch (e.g., 'formal', 'friendly', 'humorous')", max_length=100)
    prompt_body: str = Field(..., description="The main template content with placeholders like {client_name}, {podcast_name}, {custom_angle}, etc.")
    created_by: Optional[str] = Field(None, description="Identifier of the user who created/last modified the template", max_length=255)

    model_config = ConfigDict(
        from_attributes=True,  # Replaces orm_mode = True
        str_strip_whitespace=True  # Replaces anystr_strip_whitespace = True
    )

class PitchTemplateCreate(PitchTemplateBase):
    pass # template_id is required and part of PitchTemplateBase

class PitchTemplateUpdate(BaseModel):
    media_type: Optional[str] = Field(None, description="Type of media this template is generally for", max_length=100)
    target_media_type: Optional[str] = Field(None, description="Specific target within the media type", max_length=100)
    language_code: Optional[str] = Field(None, description="Language code, e.g., 'en-US', 'es-ES'", max_length=10)
    tone: Optional[str] = Field(None, description="Tone of the pitch", max_length=100)
    prompt_body: Optional[str] = Field(None, description="The main template content with placeholders.")
    # created_by can also be updated if desired, or left to be set only on creation
    # created_by: Optional[str] = Field(None, description="Identifier of the user who modified the template", max_length=255)

    model_config = ConfigDict(
        str_strip_whitespace=True
    )

class PitchTemplateInDB(PitchTemplateBase):
    created_at: datetime
    # Add updated_at if you add it to the table and queries
    # updated_at: Optional[datetime] = None 

    model_config = ConfigDict(
        from_attributes=True
    ) 