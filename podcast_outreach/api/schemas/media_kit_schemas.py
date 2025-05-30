# podcast_outreach/api/schemas/media_kit_schemas.py
import uuid
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from pydantic import EmailStr

# --- Core Media Kit Schemas ---
class MediaKitBase(BaseModel):
    title: Optional[str] = None
    # slug: str # Slug is part of MediaKitInDB and handled by service, not directly in base for user input here
    is_public: bool = Field(default=False)
    theme_preference: Optional[str] = Field(default='modern')
    headline: Optional[str] = None
    introduction: Optional[str] = None
    full_bio_content: Optional[str] = None # Populated by service from GDocs
    summary_bio_content: Optional[str] = None # Populated by service
    short_bio_content: Optional[str] = None # Populated by service
    talking_points: Optional[List[Dict[str, str]]] = Field(default_factory=list) # Populated by service
    key_achievements: Optional[List[str]] = Field(default_factory=list)
    previous_appearances: Optional[List[Dict[str, str]]] = Field(default_factory=list)
    social_media_stats: Optional[Dict[str, Any]] = Field(default_factory=dict) # Can be user-provided or service-fetched
    headshot_image_urls: Optional[List[str]] = Field(default_factory=list)
    logo_image_url: Optional[str] = None
    call_to_action_text: Optional[str] = None
    contact_information_for_booking: Optional[str] = None
    custom_sections: Optional[List[Dict[str, str]]] = Field(default_factory=list)

# Schema for what user can directly edit/provide when creating/updating via API
class MediaKitEditableContentSchema(BaseModel):
    title: Optional[str] = Field(None, description="Custom title for the media kit. If None, will be auto-generated.")
    headline: Optional[str] = Field(None, description="Main headline for the media kit page.")
    introduction: Optional[str] = Field(None, description="Brief introduction for the media kit page.")
    key_achievements: Optional[List[str]] = Field(None, description="List of key achievements.")
    previous_appearances: Optional[List[Dict[str, str]]] = Field(None, description="List of previous appearances (podcast_name, episode_title, link).")
    # social_media_stats: Optional[Dict[str, Any]] = Field(None, description="User-provided social media links/stats. Service might also fetch/update these.")
    headshot_image_urls: Optional[List[str]] = Field(None, description="List of URLs for client headshots.")
    logo_image_url: Optional[str] = Field(None, description="URL for the client/company logo.")
    call_to_action_text: Optional[str] = Field(None, description="Custom call to action text.")
    contact_information_for_booking: Optional[str] = Field(None, description="Contact info for bookings.")
    custom_sections: Optional[List[Dict[str, str]]] = Field(None, description="Custom sections with title and content.")
    theme_preference: Optional[str] = Field(None, description="Preferred theme for the public media kit page.")
    # Bio and Angles are pulled from campaign GDocs by the service, not directly set here.

class MediaKitSettingsUpdateSchema(BaseModel):
    is_public: Optional[bool] = None
    slug: Optional[str] = Field(None, min_length=3, max_length=100, pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$', description="URL-friendly slug. If changed, uniqueness will be checked.")
    theme_preference: Optional[str] = None

# Internal schemas used by the service, not directly by API input usually
class MediaKitCreateInternal(MediaKitBase): # MediaKitBase now more aligned with DB fields
    campaign_id: uuid.UUID
    person_id: int
    slug: str # Service will ensure this is set and unique before DB interaction
    # Other fields from MediaKitBase will be populated by service or use defaults

class MediaKitUpdateInternal(MediaKitBase): # All fields are optional as it's a PATCH-like update
    title: Optional[str] = None 
    slug: Optional[str] = None
    is_public: Optional[bool] = None
    # ... all other fields from MediaKitBase should be Optional ...
    # This schema can be simplified if we use model_dump(exclude_unset=True) on a more complete model

class MediaKitInDB(MediaKitBase):
    media_kit_id: uuid.UUID 
    campaign_id: uuid.UUID
    person_id: int
    slug: str # Slug is essential and unique
    created_at: datetime
    updated_at: datetime

    # Enriched fields that will be populated by the _enriched queries
    campaign_name: Optional[str] = None
    client_full_name: Optional[str] = None 
    client_email: Optional[EmailStr] = None # Assuming EmailStr is imported from pydantic
    client_website: Optional[str] = None
    client_linkedin_profile_url: Optional[str] = None
    client_twitter_profile_url: Optional[str] = None
    client_instagram_profile_url: Optional[str] = None
    client_tiktok_profile_url: Optional[str] = None
    # Note: social_media_stats is already in MediaKitBase for client-specific stats

    class Config:
        from_attributes = True 

# --- LLM Output Schemas for GDoc Parsing ---
class ParsedBioSections(BaseModel):
    full_bio: str = Field(description="The complete, original biography text.")
    summary_bio: Optional[str] = Field(None, description="A concise summary of the bio, around 2-3 paragraphs.")
    short_bio: Optional[str] = Field(None, description="A very brief bio, 1-2 sentences, suitable for social media.")

class TalkingPoint(BaseModel):
    topic: str = Field(description="The main topic or title of the talking point.")
    outcome: Optional[str] = Field(None, description="The key takeaway or outcome for the audience.")
    description: str = Field(description="A more detailed description or elaboration of the talking point.")

class ParsedTalkingPoints(BaseModel):
    talking_points: List[TalkingPoint] = Field(default_factory=list) 