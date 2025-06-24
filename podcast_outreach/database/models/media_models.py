from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List
from datetime import datetime
import uuid

class EpisodeInfo(BaseModel):
    """Standardized structure for a single episode's metadata, often from RSS."""
    episode_id: Optional[str] = Field(None, description="Unique ID for the episode, if available.")
    title: Optional[str] = Field(None, description="Title of the episode.")
    published_date: Optional[datetime] = Field(None, description="Date the episode was published.")
    summary: Optional[str] = Field(None, description="Summary or description of the episode.")
    duration_seconds: Optional[int] = Field(None, description="Duration of the episode in seconds.")
    audio_url: Optional[HttpUrl] = Field(None, description="Direct URL to the episode's audio file.")
    link: Optional[HttpUrl] = Field(None, description="URL to the episode's webpage or permalink.")

class SocialProfileInfo(BaseModel):
    """Standardized structure for social media profile data.
    Used internally by discovery services before mapping to EnrichedPodcastProfile.
    """
    platform: str = Field(..., description="e.g., 'linkedin', 'twitter'")
    profile_url: Optional[HttpUrl] = Field(None, description="Canonical URL of the social media profile.")
    handle: Optional[str] = Field(None, description="Username or handle on the platform.")
    followers: Optional[int] = Field(None, description="Number of followers/connections.")
    # Add other common metrics if needed, e.g., for Twitter:
    following_count: Optional[int] = Field(None, description="Number of accounts followed (Twitter).")
    is_verified: Optional[bool] = Field(None, description="Verification status (Twitter).")
    name: Optional[str] = Field(None, description="Display name on the platform.")
    description: Optional[str] = Field(None, description="Profile description or bio.")
    # Engagement can be more complex, kept simple for now
    average_engagement: Optional[float] = Field(None, description="Example engagement metric.")


class EnrichedPodcastProfile(BaseModel):
    """
    A standardized Pydantic model holding combined data from discovery and enrichment
    for a podcast. This model is used to pass data between enrichment steps and
    to structure data before updating the database.
    """
    # --- Unique Identifier ---
    unified_profile_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Internal unique ID for this enriched profile.")
    source_api: Optional[str] = Field(None, description="Primary API source of the initial data (e.g., 'ListenNotes', 'PodscanFM').")
    api_id: Optional[str] = Field(None, description="ID of the podcast from the source_api, used for linking to media.api_id.")

    # --- Core Podcast Info (Aligns with 'media' table) ---
    title: Optional[str] = Field(None, description="Title of the podcast.")
    description: Optional[str] = Field(None, description="Description or synopsis of the podcast.")
    image_url: Optional[HttpUrl] = Field(None, description="URL to the podcast's cover image.")
    website: Optional[HttpUrl] = Field(None, description="Official website of the podcast.")
    language: Optional[str] = Field(None, description="Primary language of the podcast (e.g., 'en', 'en-US').")
    podcast_spotify_id: Optional[str] = Field(None, description="Spotify ID of the podcast.")
    itunes_id: Optional[str] = Field(None, description="iTunes ID of the podcast (as string).")
    total_episodes: Optional[int] = Field(None, description="Total number of episodes available.")
    last_posted_at: Optional[datetime] = Field(None, description="Timestamp of the last posted episode (from API or RSS).")
    rss_feed_url: Optional[HttpUrl] = Field(None, description="URL to the podcast's RSS feed.")
    category: Optional[str] = Field(None, description="Primary category/genre of the podcast.") # From media.category

    # --- Host Information (Denormalized) ---
    host_names: Optional[List[str]] = Field(None, description="Denormalized list of host names. Detailed host info in 'people' table.")

    # --- RSS Feed Enrichment Data (Aligns with 'media' table) ---
    rss_owner_name: Optional[str] = Field(None, description="Name of the podcast owner/author from RSS feed.")
    rss_owner_email: Optional[str] = Field(None, description="Contact email from RSS feed owner tag.")
    rss_explicit: Optional[bool] = Field(None, description="Indicates if the podcast is explicit (from RSS).")
    rss_categories: Optional[List[str]] = Field(None, description="Categories/genres from RSS feed.")
    
    # --- Calculated/Derived Dates (Aligns with 'media' table) ---
    latest_episode_date: Optional[datetime] = Field(None, description="Date of the latest recorded episode (prioritized over last_posted_at if more precise).")
    first_episode_date: Optional[datetime] = Field(None, description="Date of the first recorded episode.")
    publishing_frequency_days: Optional[float] = Field(None, description="Average publishing frequency in days.")

    # --- Social Media URLs (Aligns with 'media' table) ---
    podcast_twitter_url: Optional[HttpUrl] = Field(None, description="Official Twitter/X URL for the podcast.")
    podcast_linkedin_url: Optional[HttpUrl] = Field(None, description="Official LinkedIn URL for the podcast (e.g., company page).")
    podcast_instagram_url: Optional[HttpUrl] = Field(None, description="Official Instagram URL for the podcast.")
    podcast_facebook_url: Optional[HttpUrl] = Field(None, description="Official Facebook URL for the podcast.")
    podcast_youtube_url: Optional[HttpUrl] = Field(None, description="Official YouTube channel URL for the podcast.")
    podcast_tiktok_url: Optional[HttpUrl] = Field(None, description="Official TikTok profile URL for the podcast.")
    podcast_other_social_url: Optional[HttpUrl] = Field(None, description="Any other significant social media URL for the podcast.")

    # --- Contact Information (Derived, aligns with 'media' table contact_email) ---
    primary_email: Optional[str] = Field(None, description="Best contact email found (e.g., media.contact_email or rss_owner_email).")

    # --- Metrics & Engagement (Aligns with 'media' table) ---
    listen_score: Optional[float] = Field(None, description="Listen Score (e.g., from ListenNotes).")
    listen_score_global_rank: Optional[int] = Field(None, description="Global rank by Listen Score.")
    audience_size: Optional[int] = Field(None, description="Estimated audience size (e.g., from Podscan).")
    itunes_rating_average: Optional[float] = Field(None, description="Average rating on iTunes.")
    itunes_rating_count: Optional[int] = Field(None, description="Number of ratings on iTunes.")
    spotify_rating_average: Optional[float] = Field(None, description="Average rating on Spotify.")
    spotify_rating_count: Optional[int] = Field(None, description="Number of ratings on Spotify.")
    
    # Follower counts (Aligns with 'media' table)
    twitter_followers: Optional[int] = Field(None, description="Followers on podcast's Twitter/X.")
    twitter_following: Optional[int] = Field(None, description="Following count on podcast's Twitter/X.")
    is_twitter_verified: Optional[bool] = Field(None, description="Verification status of podcast's Twitter/X.")
    # Note: Host's LinkedIn connections/followers are in 'people' table.
    instagram_followers: Optional[int] = Field(None, description="Followers on podcast's Instagram.")
    tiktok_followers: Optional[int] = Field(None, description="Followers on podcast's TikTok.")
    facebook_likes: Optional[int] = Field(None, description="Likes/followers on podcast's Facebook page.")
    youtube_subscribers: Optional[int] = Field(None, description="Subscribers on podcast's YouTube channel.")

    # --- Quality Score (Aligns with 'media' table) ---
    quality_score: Optional[float] = Field(None, description="Calculated quality score for the podcast.")

    # --- Recent Episodes (from RSS, for context during enrichment, not directly persisted as list to media table) ---
    recent_episodes: Optional[List[EpisodeInfo]] = Field(None, max_items=10, description="List of recent episodes, typically from RSS.")

    # --- Metadata ---
    last_enriched_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of when this profile was last processed by enrichment.")

    class Config:
        validate_assignment = True  # Ensures fields are validated when assigned
        # extra = 'ignore'  # If you want to ignore extra fields during parsing 
