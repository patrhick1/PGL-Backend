# podcast_outreach/api/schemas/episode_schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date # Ensure date is imported

class EpisodeBase(BaseModel):
    title: Optional[str] = None
    publish_date: Optional[date] = None
    duration_sec: Optional[int] = None
    episode_summary: Optional[str] = None
    ai_episode_summary: Optional[str] = None
    episode_url: Optional[str] = None
    transcript: Optional[str] = None
    # embedding: Optional[List[float]] = None # Usually not sent in API responses directly
    transcribe: Optional[bool] = None
    downloaded: Optional[bool] = None
    guest_names: Optional[str] = None # Consider making this List[str] if it's often multiple guests
    source_api: Optional[str] = None
    api_episode_id: Optional[str] = None
    episode_themes: Optional[List[str]] = None
    episode_keywords: Optional[List[str]] = None
    ai_analysis_done: Optional[bool] = Field(False)

    class Config:
        from_attributes = True # Pydantic V2 way for orm_mode

class EpisodeCreate(EpisodeBase):
    media_id: int
    title: str # Title is likely required for creation
    episode_url: str # URL is likely required

class EpisodeUpdate(BaseModel):
    title: Optional[str] = None
    publish_date: Optional[date] = None
    duration_sec: Optional[int] = None
    episode_summary: Optional[str] = None
    ai_episode_summary: Optional[str] = None
    episode_url: Optional[str] = None
    transcript: Optional[str] = None
    embedding: Optional[List[float]] = None
    transcribe: Optional[bool] = None
    downloaded: Optional[bool] = None
    guest_names: Optional[str] = None
    source_api: Optional[str] = None
    api_episode_id: Optional[str] = None
    episode_themes: Optional[List[str]] = None
    episode_keywords: Optional[List[str]] = None
    ai_analysis_done: Optional[bool] = None

class EpisodeInDB(EpisodeBase):
    episode_id: int
    media_id: int
    created_at: datetime
    updated_at: datetime
    # embedding is intentionally left out for typical list/get responses unless specifically needed.
    # If needed, it can be added here or in a more specific schema. 