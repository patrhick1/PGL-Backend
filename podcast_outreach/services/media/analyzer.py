# podcast_outreach/services/media/analyzer.py

import logging
import asyncio
import time
from typing import Dict, Any, Optional, List
import uuid # For UUID types in AI tracker
import json # For debugging structured output

# Project imports
from podcast_outreach.logging_config import get_logger
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.services.ai.tracker import tracker as ai_tracker
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.models.llm_outputs import EpisodeAnalysisOutput

logger = get_logger(__name__)

class MediaAnalyzerService:
    """
    Analyzes podcast episode content (transcripts, summaries) using AI
    to extract structured metadata like host/guest names, themes, and keywords.
    """

    def __init__(self):
        self.gemini_service = GeminiService()
        logger.info("MediaAnalyzerService initialized.")

    async def analyze_episode(self, episode_id: int) -> Dict[str, Any]:
        """
        Analyzes a single episode using AI to extract structured metadata.

        Args:
            episode_id: The ID of the episode to analyze.

        Returns:
            A dictionary containing the analysis result status and data.
        """
        logger.info(f"Starting AI analysis for episode ID: {episode_id}")
        result = {
            "episode_id": episode_id,
            "status": "failed",
            "message": "Analysis failed due to an unexpected error.",
            "analysis_data": None
        }

        try:
            episode_data = await episode_queries.get_episode_by_id(episode_id)
            if not episode_data:
                result["message"] = f"Episode {episode_id} not found."
                logger.warning(result["message"])
                return result

            # Prioritize transcript, then AI summary, then original summary
            content_for_analysis = episode_data.get('transcript') or \
                                   episode_data.get('ai_episode_summary') or \
                                   episode_data.get('episode_summary')

            if not content_for_analysis:
                result["message"] = f"No sufficient content (transcript or summary) found for episode {episode_id} for analysis."
                logger.warning(result["message"])
                # Mark as analyzed to avoid re-attempting if no content is available
                await episode_queries.update_episode_analysis_data(episode_id, ai_analysis_done=True)
                result["status"] = "skipped_no_content"
                return result

            # Truncate content if it's excessively long to fit within typical LLM context windows
            # Gemini 1.5 Flash has a 1M token context window, so 100k characters is very safe.
            MAX_CONTENT_LENGTH = 100000 
            if len(content_for_analysis) > MAX_CONTENT_LENGTH:
                logger.warning(f"Episode {episode_id} content length ({len(content_for_analysis)}) exceeds {MAX_CONTENT_LENGTH}. Truncating for analysis.")
                content_for_analysis = content_for_analysis[:MAX_CONTENT_LENGTH]

            episode_title = episode_data.get('title', 'Untitled Episode')
            media_id = episode_data.get('media_id')

            analysis_prompt = f"""
            You are an expert podcast content analyst. Your task is to extract structured information
            from the provided podcast episode content.

            Episode Title: {episode_title}

            Episode Content (Summary or Transcript):
            ---
            {content_for_analysis}
            ---

            Based *only* on the provided content, identify the following:
            1.  **Host Names**: List the full names of any hosts explicitly mentioned or clearly identifiable as hosts.
            2.  **Guest Names**: List the full names of any guests explicitly mentioned or clearly identifiable as guests.
            3.  **Episode Themes**: List 3-5 overarching themes or main topics discussed in the episode.
            4.  **Episode Keywords**: List 5-10 specific keywords or key phrases relevant to the episode's content.
            5.  **AI Analysis Summary**: Provide a very brief (1-2 sentences) summary of your overall findings or the episode's main focus.

            If a piece of information is not explicitly present or clearly inferable from the provided text, output `null` or an empty list for that field.
            Do not invent information.
            """

            logger.info(f"Sending episode {episode_id} content to Gemini for structured analysis.")
            
            # Use GeminiService's structured data extraction
            structured_analysis_output: Optional[EpisodeAnalysisOutput] = await self.gemini_service.get_structured_data(
                prompt=analysis_prompt,
                output_model=EpisodeAnalysisOutput,
                workflow="episode_analysis",
                related_media_id=media_id,
                # No related_pitch_gen_id or related_campaign_id for general episode analysis
            )

            if not structured_analysis_output:
                result["message"] = f"Gemini returned no structured analysis for episode {episode_id}."
                logger.error(result["message"])
                # Mark as analyzed to prevent re-attempting if AI consistently fails for this episode
                await episode_queries.update_episode_analysis_data(episode_id, ai_analysis_done=True)
                return result

            # Prepare data for database update
            update_data = {
                "host_names": structured_analysis_output.host_names_identified,
                "guest_names": structured_analysis_output.guest_names_identified,
                "episode_themes": structured_analysis_output.episode_themes,
                "episode_keywords": structured_analysis_output.episode_keywords,
                "ai_analysis_done": True # Mark as analyzed
            }

            # Update the episode record in the database
            updated_episode = await episode_queries.update_episode_analysis_data(
                episode_id=episode_id,
                host_names=update_data["host_names"],
                guest_names=update_data["guest_names"],
                episode_themes=update_data["episode_themes"],
                episode_keywords=update_data["episode_keywords"],
                ai_analysis_done=update_data["ai_analysis_done"]
            )

            if updated_episode:
                result["status"] = "success"
                result["message"] = f"Successfully analyzed and updated episode {episode_id}."
                result["analysis_data"] = structured_analysis_output.model_dump()
                logger.info(f"Episode {episode_id} analysis complete. Hosts: {structured_analysis_output.host_names_identified}, Guests: {structured_analysis_output.guest_names_identified}")
            else:
                result["message"] = f"Analysis successful for episode {episode_id}, but failed to update DB record."
                logger.error(result["message"])

        except Exception as e:
            result["message"] = f"An error occurred during episode analysis for {episode_id}: {str(e)}"
            result["error_details"] = str(e)
            logger.exception(f"Error analyzing episode {episode_id}: {e}")
            # Ensure the episode is marked as analyzed even on error to prevent infinite loops
            await episode_queries.update_episode_analysis_data(episode_id, ai_analysis_done=True)

        return result