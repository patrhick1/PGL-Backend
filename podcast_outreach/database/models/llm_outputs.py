# podcast_outreach/database/models/llm_outputs.py
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List

class GeminiPodcastEnrichment(BaseModel):
    """
    Pydantic model for structured output from Gemini during the initial podcast/host
    information discovery phase (e.g., finding social URLs, host names).
    """
    podcast_name: Optional[str] = Field(None, description="The official name of the podcast.")
    podcast_twitter_url: Optional[str] = Field(None, description="Official Twitter/X URL for the podcast found by Gemini.")
    podcast_linkedin_url: Optional[str] = Field(None, description="Official LinkedIn URL for the podcast (e.g., company page) found by Gemini.")
    podcast_instagram_url: Optional[str] = Field(None, description="Official Instagram URL for the podcast found by Gemini.")
    podcast_facebook_url: Optional[str] = Field(None, description="Official Facebook URL for the podcast found by Gemini.")
    podcast_youtube_url: Optional[str] = Field(None, description="Official YouTube channel URL for the podcast found by Gemini.")
    podcast_tiktok_url: Optional[str] = Field(None, description="Official TikTok profile URL for the podcast found by Gemini.")
    host_names: Optional[List[str]] = Field(None, description="Actual human names of podcast hosts (e.g., 'John Smith', 'Sarah Johnson'). Only include specific person names, never descriptions or instructions.")
    # Host-specific social URLs found by Gemini will be handled by trying to create/update people records
    # and linking them. These fields are for direct discovery if needed.
    host_linkedin_url: Optional[str] = Field(None, description="LinkedIn profile URL of a primary host found by Gemini.")
    host_twitter_url: Optional[str] = Field(None, description="Twitter/X profile URL of a primary host found by Gemini.")

class LLMQualityVettingOutput(BaseModel):
    """
    Pydantic model for structured output from an LLM when assessing qualitative aspects
    of a podcast to contribute to its overall quality_score.
    """
    # Score from 0 to 100, reflecting LLM's assessment of content quality, relevance, etc.
    # based on podcast description, title, and potentially sample transcripts.
    content_quality_score: Optional[float] = Field(None, description="LLM-assessed content quality score (0-100) based on available text data.")
    explanation: Optional[str] = Field(None, description="Brief explanation from the LLM for its content_quality_score.")
    # detected_content_issues: Optional[List[str]] = Field(None, description="Flags for potential content issues like poor audio indicators, off-topic discussions etc.") 

# NEW MODEL FOR EPISODE ANALYSIS
class EpisodeAnalysisOutput(BaseModel):
    """
    Pydantic model for structured output from an LLM when analyzing episode content
    to identify hosts, guests, themes, and keywords.
    """
    host_names_identified: Optional[List[str]] = Field(None, description="Names of the hosts identified in the episode content.")
    guest_names_identified: Optional[List[str]] = Field(None, description="Names of the guests identified in the episode content.")
    episode_themes: Optional[List[str]] = Field(None, description="Key themes or topics discussed in the episode.")
    episode_keywords: Optional[List[str]] = Field(None, description="Important keywords extracted from the episode content.")
    ai_analysis_summary: Optional[str] = Field(None, description="A brief summary of the AI's findings or overall analysis of the episode content.")