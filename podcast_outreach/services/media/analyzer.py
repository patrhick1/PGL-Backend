# podcast_outreach/services/media/analyzer.py

import logging
import asyncio
import time
from typing import Dict, Any, Optional, List
import uuid # For UUID types in AI tracker
import json # For debugging structured output

# Project imports
from podcast_outreach.logging_config import get_logger
from podcast_outreach.services.ai.gemini_client import GeminiService, GeminiSafetyBlockError
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

            # Create template and user query for structured data extraction
            prompt_template = """
            You are an expert podcast content analyst. Your task is to extract structured information
            from the provided podcast episode content.

            {user_query}

            Based *only* on the provided content, identify the following:
            1.  **Host Names**: List the full names of any hosts explicitly mentioned or clearly identifiable as hosts.
            2.  **Guest Names**: List the full names of any guests explicitly mentioned or clearly identifiable as guests.
            3.  **Episode Themes**: List 3-5 overarching themes or main topics discussed in the episode.
            4.  **Episode Keywords**: List 5-10 specific keywords or key phrases relevant to the episode's content.
            5.  **AI Analysis Summary**: Provide a very brief (1-2 sentences) summary of your overall findings or the episode's main focus.

            If a piece of information is not explicitly present or clearly inferable from the provided text, output `null` or an empty list for that field.
            Do not invent information.

            {format_instructions}
            """

            user_query = f"""
            Episode Title: {episode_title}

            Episode Content (Summary or Transcript):
            ---
            {content_for_analysis}
            ---
            """

            logger.info(f"Sending episode {episode_id} content to Gemini for structured analysis.")
            
            # Use GeminiService's structured data extraction
            structured_analysis_output: Optional[EpisodeAnalysisOutput] = await self.gemini_service.get_structured_data(
                prompt_template_str=prompt_template,
                user_query=user_query,
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

    async def analyze_podcast_from_episodes(self, media_id: int) -> Dict[str, Any]:
        """
        Analyzes a podcast as a whole using its episode transcripts and analysis data.
        
        Args:
            media_id: The ID of the media/podcast to analyze.
            
        Returns:
            A dictionary containing the podcast-level analysis result.
        """
        logger.info(f"Starting podcast-level analysis for media ID: {media_id}")
        result = {
            "media_id": media_id,
            "status": "failed", 
            "message": "Podcast analysis failed due to an unexpected error.",
            "analysis_data": None
        }
        
        try:
            # Get episodes with content for this media
            episodes = await episode_queries.get_episodes_for_media_with_content(media_id)
            if not episodes:
                result["message"] = f"No episodes with content found for media {media_id} for podcast analysis."
                logger.warning(result["message"])
                result["status"] = "skipped_no_content"
                return result
            
            # Limit to most recent episodes to avoid context window issues
            recent_episodes = episodes[:10]  # Use up to 10 most recent episodes
            
            # Combine all episode content for analysis
            combined_content = []
            episode_titles = []
            
            for episode in recent_episodes:
                title = episode.get('title', 'Untitled Episode')
                episode_titles.append(title)
                
                # Prioritize transcript, then AI summary, then original summary
                content = episode.get('transcript') or \
                         episode.get('ai_episode_summary') or \
                         episode.get('episode_summary', '')
                
                if content:
                    combined_content.append(f"Episode: {title}\n{content[:5000]}")  # Limit each episode to 5k chars
            
            if not combined_content:
                result["message"] = f"No episode content available for podcast analysis of media {media_id}."
                logger.warning(result["message"])
                result["status"] = "skipped_no_content"
                return result
            
            # Truncate combined content if too long
            full_content = "\n\n---\n\n".join(combined_content)
            MAX_CONTENT_LENGTH = 150000  # Leave room for podcast-level analysis prompt
            if len(full_content) > MAX_CONTENT_LENGTH:
                logger.warning(f"Media {media_id} combined content length ({len(full_content)}) exceeds {MAX_CONTENT_LENGTH}. Truncating for podcast analysis.")
                full_content = full_content[:MAX_CONTENT_LENGTH]
            
            # Get media information
            from podcast_outreach.database.queries import media as media_queries
            media_data = await media_queries.get_media_by_id_from_db(media_id)
            podcast_name = media_data.get('name', 'Unknown Podcast') if media_data else 'Unknown Podcast'
            
            # Create podcast-level analysis prompt
            prompt_template = """
            You are an expert podcast content analyst. Your task is to analyze this podcast as a whole
            based on multiple episode transcripts and provide strategic insights.

            {user_query}

            Based on the provided episode content, analyze the following:
            1. **Podcast Themes**: What are the 5-7 main themes/topics this podcast consistently covers?
            2. **Host Style**: Describe the host's communication style, personality, and approach (formal/casual, expert/conversational, etc.)
            3. **Target Audience**: Who is the likely target audience for this podcast?
            4. **Content Format**: What's the typical format (interview-style, solo, panel, narrative, etc.)?
            5. **Key Value Propositions**: What unique value does this podcast provide to listeners?
            6. **Guest Patterns**: What types of guests are typically featured (if applicable)?
            7. **Strategic Insights**: What would make someone a good guest for this podcast? What topics would resonate?

            Provide specific, actionable insights that could help with guest booking and content strategy.
            Base your analysis only on the provided content - don't make assumptions beyond what's evident.

            {format_instructions}
            """
            
            user_query = f"""
            Podcast Name: {podcast_name}
            Number of Episodes Analyzed: {len(recent_episodes)}
            Episode Titles: {', '.join(episode_titles[:5])}{'...' if len(episode_titles) > 5 else ''}

            Combined Episode Content:
            ---
            {full_content}
            ---
            """
            
            logger.info(f"Sending podcast-level content for media {media_id} to Gemini for analysis.")
            
            # Use a simple text response for podcast-level analysis since it's more complex
            analysis_response = await self.gemini_service.create_message(
                prompt=prompt_template.format(user_query=user_query, format_instructions="Provide a detailed analysis in structured paragraphs."),
                workflow="podcast_level_analysis",
                related_media_id=media_id
            )
            
            if not analysis_response:
                result["message"] = f"Gemini returned no podcast-level analysis for media {media_id}."
                logger.error(result["message"])
                return result
            
            # Update media record with podcast-level analysis and create embedding
            from podcast_outreach.database.queries import media as media_queries
            
            # Store AI description in database
            await media_queries.update_media_ai_description(media_id, analysis_response)
            
            # Generate podcast-level embedding for better matching
            from podcast_outreach.services.ai.openai_client import OpenAIService
            openai_service = OpenAIService()
            
            podcast_embedding_text = f"Podcast: {podcast_name}\nDescription: {analysis_response}"
            podcast_embedding = await openai_service.get_embedding(
                text=podcast_embedding_text,
                workflow="podcast_embedding",
                related_ids={"media_id": media_id}
            )
            
            if podcast_embedding:
                await media_queries.update_media_embedding(media_id, podcast_embedding)
                logger.info(f"Updated podcast embedding for media {media_id}")
            
            result["status"] = "success"
            result["message"] = f"Successfully analyzed podcast for media {media_id} and updated AI description."
            result["analysis_data"] = {
                "podcast_analysis": analysis_response,
                "episodes_analyzed": len(recent_episodes),
                "total_episodes_available": len(episodes),
                "embedding_generated": bool(podcast_embedding)
            }
            
            logger.info(f"Podcast-level analysis complete for media {media_id}")
            
        except GeminiSafetyBlockError as e:
            # Handle safety blocks specially - create a generic safe description
            result["status"] = "safety_blocked"
            result["message"] = f"Podcast content was blocked by safety filters for media {media_id}. Using fallback description."
            
            # Create a safe, generic AI description
            safe_description = (
                f"This podcast '{podcast_name}' features discussions on various topics. "
                f"Due to content safety considerations, a detailed analysis could not be generated. "
                f"Please listen to the episodes directly to learn more about the podcast's content and style."
            )
            
            # Still update the database with the safe description
            from podcast_outreach.database.queries import media as media_queries
            await media_queries.update_media_ai_description(media_id, safe_description)
            
            # Log the safety block for monitoring
            logger.warning(f"Safety block for media {media_id}: {e}")
            
            # Could track safety blocks in a separate table in the future
            # For now, the safe description in the database indicates it was blocked
            
        except Exception as e:
            result["message"] = f"An error occurred during podcast analysis for media {media_id}: {str(e)}"
            result["error_details"] = str(e)
            logger.exception(f"Error analyzing podcast for media {media_id}: {e}")
        
        return result