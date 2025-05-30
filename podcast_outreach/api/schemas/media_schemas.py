# podcast_outreach/api/schemas/media_schemas.py

import uuid
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, date

class MediaBase(BaseModel):
    # Core fields from schema
    name: Optional[str] = None
    title: Optional[str] = None # Often same as name, but can differ
    rss_url: Optional[str] = None 
    rss_feed_url: Optional[str] = None # Explicitly from your schema list
    website: Optional[str] = None
    description: Optional[str] = None
    ai_description: Optional[str] = None
    contact_email: Optional[str] = None
    language: Optional[str] = None
    category: Optional[str] = None # Primary category string
    image_url: Optional[str] = None
    
    # Stats & IDs from schema
    company_id: Optional[int] = None # FK to companies
    avg_downloads: Optional[int] = None # General field, might map to audience_size
    audience_size: Optional[int] = None # Specifically from Podscan reach
    total_episodes: Optional[int] = None
    itunes_id: Optional[str] = None # Stored as TEXT in DB
    podcast_spotify_id: Optional[str] = None # Renamed from spotify_id for clarity
    listen_score: Optional[float] = None # REAL in DB
    listen_score_global_rank: Optional[int] = None # INTEGER in DB (was text before, ensure DB is int)
    itunes_rating_average: Optional[float] = None
    itunes_rating_count: Optional[int] = None
    spotify_rating_average: Optional[float] = None
    spotify_rating_count: Optional[int] = None

    # Status & Source from schema
    fetched_episodes: Optional[bool] = Field(default=False)
    source_api: Optional[str] = None # e.g., "ListenNotes", "PodscanFM", "Mixed"
    api_id: Optional[str] = None # ID from the source_api (e.g. ListenNotes ID, Podscan podcast_id)
    
    # Dates from schema
    last_posted_at: Optional[datetime] = None # TIMESTAMPTZ
    last_enriched_at: Optional[datetime] = None # TIMESTAMPTZ, new field
    
    # Social Links from schema
    podcast_twitter_url: Optional[str] = None
    podcast_linkedin_url: Optional[str] = None
    podcast_instagram_url: Optional[str] = None
    podcast_facebook_url: Optional[str] = None
    podcast_youtube_url: Optional[str] = None
    podcast_tiktok_url: Optional[str] = None
    podcast_other_social_url: Optional[str] = None
    # New fields from DB schema (if not already present)
    host_names: Optional[List[str]] = None # Assuming TEXT[] in DB, maps to List[str]
    rss_owner_name: Optional[str] = None
    rss_owner_email: Optional[str] = None
    rss_explicit: Optional[bool] = None
    rss_categories: Optional[List[str]] = None # Assuming TEXT[]
    twitter_followers: Optional[int] = None
    twitter_following: Optional[int] = None
    is_twitter_verified: Optional[bool] = None
    linkedin_connections: Optional[int] = None # Placeholder, might not be directly available
    instagram_followers: Optional[int] = None
    tiktok_followers: Optional[int] = None
    facebook_likes: Optional[int] = None # Placeholder
    youtube_subscribers: Optional[int] = None
    publishing_frequency_days: Optional[int] = None
    quality_score: Optional[float] = None # REAL in DB
    first_episode_date: Optional[date] = None # DATE in DB
    latest_episode_date: Optional[date] = None # DATE in DB

    # embedding is intentionally omitted from general CRUD models

class MediaCreate(MediaBase):
    name: str # Name is required to create a media entry
    pass

class MediaUpdate(BaseModel):
    name: Optional[str] = None
    title: Optional[str] = None
    rss_url: Optional[str] = None
    rss_feed_url: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    ai_description: Optional[str] = None
    contact_email: Optional[str] = None
    language: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    company_id: Optional[int] = None
    avg_downloads: Optional[int] = None
    audience_size: Optional[int] = None
    total_episodes: Optional[int] = None
    itunes_id: Optional[str] = None
    podcast_spotify_id: Optional[str] = None
    listen_score: Optional[float] = None
    listen_score_global_rank: Optional[int] = None
    itunes_rating_average: Optional[float] = None
    itunes_rating_count: Optional[int] = None
    spotify_rating_average: Optional[float] = None
    spotify_rating_count: Optional[int] = None
    fetched_episodes: Optional[bool] = None
    source_api: Optional[str] = None
    api_id: Optional[str] = None
    last_posted_at: Optional[datetime] = None
    podcast_twitter_url: Optional[str] = None
    podcast_linkedin_url: Optional[str] = None
    podcast_instagram_url: Optional[str] = None
    podcast_facebook_url: Optional[str] = None
    podcast_youtube_url: Optional[str] = None
    podcast_tiktok_url: Optional[str] = None
    podcast_other_social_url: Optional[str] = None
    last_enriched_at: Optional[datetime] = None # New field
    # Optional updates for other new DB fields if they can be set on update
    host_names: Optional[List[str]] = None
    rss_owner_name: Optional[str] = None
    rss_owner_email: Optional[str] = None
    rss_explicit: Optional[bool] = None
    rss_categories: Optional[List[str]] = None
    twitter_followers: Optional[int] = None
    twitter_following: Optional[int] = None
    is_twitter_verified: Optional[bool] = None
    linkedin_connections: Optional[int] = None
    instagram_followers: Optional[int] = None
    tiktok_followers: Optional[int] = None
    facebook_likes: Optional[int] = None
    youtube_subscribers: Optional[int] = None
    publishing_frequency_days: Optional[int] = None
    quality_score: Optional[float] = None
    first_episode_date: Optional[date] = None
    latest_episode_date: Optional[date] = None

class MediaInDB(MediaBase):
    media_id: int # Auto-generated by SERIAL
    created_at: datetime

    class Config:
        from_attributes = True

class AdminDiscoveryRequestSchema(BaseModel):
    query: str
    campaign_id: Optional[uuid.UUID] = None