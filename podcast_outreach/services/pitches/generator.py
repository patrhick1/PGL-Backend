import os
import logging
import re
import time
import asyncio
import numpy as np
from scipy.spatial.distance import cosine
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import uuid

# LangChain imports
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.exceptions import OutputParserException

# Anthropic for tokenizer (for accurate token counting)
import anthropic

# Project imports
from podcast_outreach.config import ANTHROPIC_API_KEY, GEMINI_API_KEY
from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import pitch_generations as pitch_gen_queries
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import review_tasks as review_task_queries
from podcast_outreach.integrations import google_docs as google_docs_integration
from podcast_outreach.services.ai import tracker as ai_tracker
from podcast_outreach.services.ai import templates as ai_templates_loader
from podcast_outreach.api.schemas.pitch_schemas import PitchEmail, SubjectLine

logger = get_logger(__name__)

class PitchGeneratorService:
    """
    Handles the process of creating pitch emails for podcast outreach.
    Fetches data from the database, selects the best episode, generates
    personalized pitches using an LLM, and updates records with the results.
    """

    def __init__(self):
        """Initialize services and configurations needed for pitch writing."""
        self.google_docs_service = google_docs_integration.GoogleDocsService()

        # Initialize LLM client (using Anthropic Claude Sonnet as default, can be configured)
        self.model_name = "claude-3-5-sonnet-20241022" # Default model
        self.llm = self._get_llm_client(self.model_name)

        # Initialize Anthropic tokenizer for accurate token counting if using Claude
        self.anthropic_client = None
        if "claude" in self.model_name.lower() and ANTHROPIC_API_KEY:
            self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        elif "gemini" in self.model_name.lower() and GEMINI_API_KEY:
            # For Gemini, token counting is often handled by the LangChain integration or direct API
            pass # No separate tokenizer client needed here
        
        logger.info(f"PitchGeneratorService initialized with LLM: {self.model_name}")

    def _get_llm_client(self, model_name: str):
        """Helper to get the correct LLM client based on model name."""
        if "claude" in model_name.lower():
            if not ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY not set for Claude model.")
            return ChatAnthropic(
                model=model_name,
                anthropic_api_key=ANTHROPIC_API_KEY,
                temperature=0.4,
                max_tokens=2000 # Max output tokens for the model
            )
        elif "gemini" in model_name.lower():
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY not set for Gemini model.")
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=GEMINI_API_KEY,
                temperature=0.4,
                max_output_tokens=2000 # Max output tokens for the model
            )
        else:
            raise ValueError(f"Unsupported LLM model: {model_name}")

    def _extract_google_doc_id(self, url: str) -> Optional[str]:
        """Extracts Google Document ID from a URL."""
        if not url:
            return None
        match = re.search(r'/document/d/([a-zA-Z0-9-_]+)', url)
        if match:
            return match.group(1)
        return None

    def _count_tokens(self, text: str) -> int:
        """
        Count tokens accurately using the appropriate tokenizer for the LLM.
        """
        if "claude" in self.model_name.lower() and self.anthropic_client:
            try:
                # Use the beta.messages.count_tokens method
                count_result = self.anthropic_client.beta.messages.count_tokens(
                    model=self.model_name,
                    messages=[{"role": "user", "content": text}]
                )
                return count_result.input_tokens
            except Exception as e:
                logger.warning(f"Error counting Claude tokens: {str(e)}. Falling back to estimation.")
                return len(text) // 4 # Rough approximation
        elif "gemini" in self.model_name.lower():
            # LangChain's Gemini integration might not expose direct token counting easily
            # Fallback to estimation for now or integrate direct genai.GenerativeModel.count_tokens
            return len(text) // 4 # Rough approximation
        else:
            return len(text) // 4 # Default rough approximation

    async def select_best_episode(self, campaign_id: uuid.UUID, media_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[float]]:
        """
        Selects the best episode for pitching from a given media (podcast) based on campaign relevance.
        Prioritizes episodes with embeddings for similarity scoring.
        If no embeddings, falls back to keyword matching or recent episodes.

        Args:
            campaign_id: The UUID of the campaign.
            media_id: The ID of the media (podcast).

        Returns:
            A tuple: (best_episode_data, match_score).
            best_episode_data is a dictionary of the selected episode's details.
            match_score is a float representing the similarity/relevance.
        """
        logger.info(f"Selecting best episode for campaign {campaign_id} and media {media_id}")

        campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found for episode selection.")
            return None, None

        campaign_embedding = campaign.get('embedding')
        campaign_keywords = campaign.get('campaign_keywords', [])

        # Fetch episodes for the media that have transcripts or summaries
        episodes = await episode_queries.get_episodes_for_media_with_content(media_id)
        if not episodes:
            logger.warning(f"No episodes with content found for media {media_id}.")
            return None, None

        best_episode = None
        highest_score = -1.0 # Cosine similarity ranges from -1 to 1

        # Strategy 1: Embedding similarity (if available)
        if campaign_embedding is not None and len(campaign_embedding) > 0:
            for episode in episodes:
                episode_embedding = episode.get('embedding')
                if episode_embedding is not None and len(episode_embedding) > 0:
                    try:
                        # Ensure embeddings are numpy arrays for cosine similarity
                        emb1 = np.array(campaign_embedding)
                        emb2 = np.array(episode_embedding)
                        score = 1 - cosine(emb1, emb2) # Cosine distance to similarity
                        if score > highest_score:
                            highest_score = score
                            best_episode = episode
                    except Exception as e:
                        logger.warning(f"Error computing embedding similarity for episode {episode.get('episode_id')}: {e}")
            
            if best_episode:
                logger.info(f"Best episode selected by embedding similarity: {best_episode.get('title')} (Score: {highest_score:.2f})")
                return best_episode, highest_score

        # Strategy 2: Keyword matching (fallback if no embeddings or low scores)
        if campaign_keywords:
            for episode in episodes:
                episode_summary = episode.get('ai_episode_summary') or episode.get('episode_summary') or episode.get('transcript')
                if episode_summary:
                    # Simple keyword overlap score
                    score = sum(1 for keyword in campaign_keywords if keyword.lower() in episode_summary.lower())
                    if score > highest_score: # Use raw count as score
                        highest_score = score
                        best_episode = episode
            
            if best_episode:
                logger.info(f"Best episode selected by keyword matching: {best_episode.get('title')} (Keyword Score: {highest_score})")
                return best_episode, highest_score

        # Strategy 3: Most recent episode (final fallback)
        if episodes:
            # Sort by publish_date descending
            sorted_episodes = sorted(episodes, key=lambda x: x.get('publish_date', datetime.min), reverse=True)
            best_episode = sorted_episodes[0]
            highest_score = 0.0 # Default score for fallback
            logger.info(f"Best episode selected by recency: {best_episode.get('title')} (Score: {highest_score})")
            return best_episode, highest_score

        logger.warning(f"Could not select a best episode for campaign {campaign_id} and media {media_id}.")
        return None, None

    async def generate_pitch_from_template(
        self,
        campaign_data: Dict[str, Any],
        media_data: Dict[str, Any],
        episode_data: Dict[str, Any],
        pitch_template_name: str,
        media_kit_content: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Dict[str, int], float]:
        """
        Generates a pitch email and subject line using an LLM and a specified template.

        Args:
            campaign_data: Dictionary of campaign details.
            media_data: Dictionary of media (podcast) details.
            episode_data: Dictionary of the selected episode details.
            pitch_template_name: The name of the pitch template to use.
            media_kit_content: Optional content from the client's media kit.

        Returns:
            Tuple: (generated_email_body, generated_subject_line, token_usage, execution_time)
        """
        start_time = time.time()
        total_token_usage = {"input_tokens": 0, "output_tokens": 0}
        
        # Load pitch template content
        pitch_template_content = await ai_templates_loader.load_pitch_template(pitch_template_name)
        if not pitch_template_content:
            logger.error(f"Pitch template '{pitch_template_name}' not found.")
            return None, None, total_token_usage, 0.0

        # Prepare inputs for the pitch email generation
        inputs = {
            "podcast_name": media_data.get('name', 'the podcast'),
            "host_name": media_data.get('host_names', [''])[0] if media_data.get('host_names') else 'the host',
            "episode_title": episode_data.get('title', 'a recent episode'),
            "episode_summary": episode_data.get('episode_summary', ''),
            "ai_summary": episode_data.get('ai_episode_summary', ''),
            "client_name": campaign_data.get('campaign_name', 'our client'), # Assuming campaign_name is client name
            "client_bio": campaign_data.get('campaign_bio', ''),
            "client_bio_summary": campaign_data.get('campaign_bio', '')[:500], # Simple summary for now
            "pitch_topics": campaign_data.get('campaign_angles', ''),
            "media_kit_content": media_kit_content if media_kit_content else "No content available"
        }

        # Create the pitch email generation chain
        pitch_prompt_template = PromptTemplate(
            template=pitch_template_content,
            input_variables=[
                "podcast_name", "host_name", "episode_title", "episode_summary", 
                "ai_summary", "client_name", "client_bio", "client_bio_summary", 
                "pitch_topics", "media_kit_content"
            ]
        )
        
        pitch_chain = (
            pitch_prompt_template
            | self.llm.with_structured_output(PitchEmail)
        )

        generated_email_body = None
        generated_subject_line = None

        # Generate pitch email
        try:
            formatted_pitch_prompt = pitch_prompt_template.format(**inputs)
            pitch_result = await pitch_chain.ainvoke(inputs)
            generated_email_body = pitch_result.email_body

            # Update token usage for pitch email
            prompt_tokens = self._count_tokens(formatted_pitch_prompt)
            completion_tokens = self._count_tokens(generated_email_body)
            total_token_usage["input_tokens"] += prompt_tokens
            total_token_usage["output_tokens"] += completion_tokens

            ai_tracker.log_usage(
                workflow="pitch_generation_body",
                model=self.model_name,
                tokens_in=prompt_tokens,
                tokens_out=completion_tokens,
                execution_time=(time.time() - start_time), # Partial time
                endpoint="langchain.llm.ainvoke",
                podcast_id=str(media_data.get('media_id'))
            )
            logger.info(f"Generated pitch email for {media_data.get('name')}. Tokens: {prompt_tokens} in, {completion_tokens} out.")

        except OutputParserException as ope:
            logger.error(f"LLM output parsing failed for pitch email: {ope}. Raw content: {ope.llm_output}")
            generated_email_body = f"ERROR: Failed to generate pitch email due to parsing issue. {ope.llm_output}"
        except Exception as e:
            logger.error(f"Error generating pitch email for {media_data.get('name')}: {e}", exc_info=True)
            generated_email_body = f"ERROR: Failed to generate pitch email. {str(e)}"

        # Generate subject line (simplified logic from old script)
        subject_line_template_content = await ai_templates_loader.load_pitch_template("subject_line_template")
        if subject_line_template_content:
            subject_prompt_template = PromptTemplate(
                template=subject_line_template_content,
                input_variables=["episode_summary", "ai_summary"]
            )
            subject_chain = (
                subject_prompt_template
                | self.llm.with_structured_output(SubjectLine)
            )
            try:
                subject_inputs = {
                    "episode_summary": episode_data.get('episode_summary', ''),
                    "ai_summary": episode_data.get('ai_episode_summary', '')
                }
                formatted_subject_prompt = subject_prompt_template.format(**subject_inputs)
                subject_result = await subject_chain.ainvoke(subject_inputs)
                generated_subject_line = subject_result.subject

                # Update token usage for subject line
                prompt_tokens = self._count_tokens(formatted_subject_prompt)
                completion_tokens = self._count_tokens(generated_subject_line)
                total_token_usage["input_tokens"] += prompt_tokens
                total_token_usage["output_tokens"] += completion_tokens

                ai_tracker.log_usage(
                    workflow="pitch_generation_subject",
                    model=self.model_name,
                    tokens_in=prompt_tokens,
                    tokens_out=completion_tokens,
                    execution_time=(time.time() - start_time), # Partial time
                    endpoint="langchain.llm.ainvoke",
                    podcast_id=str(media_data.get('media_id'))
                )
                logger.info(f"Generated subject line for {media_data.get('name')}. Tokens: {prompt_tokens} in, {completion_tokens} out.")

            except OutputParserException as ope:
                logger.error(f"LLM output parsing failed for subject line: {ope}. Raw content: {ope.llm_output}")
                generated_subject_line = f"ERROR: Subject line parsing failed. {ope.llm_output}"
            except Exception as e:
                logger.error(f"Error generating subject line for {media_data.get('name')}: {e}", exc_info=True)
                generated_subject_line = f"ERROR: Subject line generation failed. {str(e)}"
        else:
            logger.warning("Subject line template not found. Using default subject line.")
            generated_subject_line = f"Great episode about {episode_data.get('title', 'your podcast')}"

        execution_time = time.time() - start_time
        return generated_email_body, generated_subject_line, total_token_usage, execution_time

    async def generate_pitch_for_match(self, match_id: int, pitch_template_name: str = "friendly_intro_template") -> Dict[str, Any]:
        """
        Orchestrates the pitch generation process for an approved match suggestion.
        
        Args:
            match_id: The ID of the approved match suggestion.
            pitch_template_name: The name of the pitch template to use.

        Returns:
            A dictionary with the status and details of the pitch generation.
        """
        logger.info(f"Starting pitch generation for match_id: {match_id} using template: {pitch_template_name}")
        
        result = {
            "status": "failed",
            "message": "An unexpected error occurred.",
            "pitch_gen_id": None,
            "review_task_id": None,
            "campaign_id": None,
            "media_id": None,
            "generated_at": datetime.utcnow().isoformat(),
            "pitch_text_preview": None,
            "subject_line_preview": None,
            "error_details": None
        }

        try:
            # 1. Fetch match suggestion
            match_suggestion = await match_queries.get_match_suggestion_by_id_from_db(match_id)
            if not match_suggestion:
                result["message"] = f"Match suggestion {match_id} not found."
                return result
            
            if match_suggestion.get('status') != 'approved':
                result["message"] = f"Match suggestion {match_id} is not approved (current status: {match_suggestion.get('status')})."
                return result

            campaign_id = match_suggestion['campaign_id']
            media_id = match_suggestion['media_id']
            result["campaign_id"] = campaign_id
            result["media_id"] = media_id

            # 2. Fetch campaign and media data
            campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
            media_data = await media_queries.get_media_by_id_from_db(media_id)

            if not campaign_data or not media_data:
                result["message"] = "Campaign or Media data not found for the match."
                return result

            # 3. Select the best episode for pitching
            best_episode_data, match_score = await self.select_best_episode(campaign_id, media_id)
            if not best_episode_data:
                result["message"] = "Could not select a best episode for pitching."
                return result
            
            logger.info(f"Selected episode {best_episode_data.get('episode_id')} ('{best_episode_data.get('title')}') for pitching.")

            # 4. Fetch media kit content (if URL is provided in campaign)
            media_kit_content = None
            media_kit_url = campaign_data.get('media_kit_url')
            if media_kit_url:
                doc_id = self._extract_google_doc_id(media_kit_url)
                if doc_id:
                    try:
                        media_kit_content = await asyncio.to_thread(self.google_docs_service.get_document_content, doc_id)
                        logger.info(f"Fetched media kit content (length: {len(media_kit_content)} chars).")
                    except Exception as e:
                        logger.warning(f"Failed to fetch media kit content from {media_kit_url}: {e}")
                        media_kit_content = "Error fetching media kit content."
                else:
                    logger.warning(f"Could not extract Google Doc ID from media kit URL: {media_kit_url}")

            # 5. Generate pitch using AI template
            email_body, subject_line, token_usage, exec_time = await self.generate_pitch_from_template(
                campaign_data, media_data, best_episode_data, pitch_template_name, media_kit_content
            )

            if not email_body or not subject_line:
                result["message"] = "AI failed to generate complete pitch email or subject line."
                result["error_details"] = {"email_body_error": email_body, "subject_line_error": subject_line}
                return result

            # 6. Save into pitch_generations
            pitch_gen_data = {
                "campaign_id": campaign_id,
                "media_id": media_id,
                "template_id": pitch_template_name,
                "draft_text": email_body,
                "ai_model_used": self.model_name,
                "pitch_topic": best_episode_data.get('title'), # Use episode title as pitch topic
                "temperature": 0.4, # Hardcoded from LLM init
                "generation_status": "draft",
                "send_ready_bool": False # Not ready until reviewed
            }
            created_pitch_gen = await pitch_gen_queries.create_pitch_generation_in_db(pitch_gen_data)
            if not created_pitch_gen:
                result["message"] = "Failed to save pitch generation to database."
                return result
            result["pitch_gen_id"] = created_pitch_gen['pitch_gen_id']
            result["pitch_text_preview"] = email_body[:500] + "..." if len(email_body) > 500 else email_body
            result["subject_line_preview"] = subject_line

            # 7. Save into pitches (initial record)
            pitch_data = {
                "campaign_id": campaign_id,
                "media_id": media_id,
                "attempt_no": 1, # First attempt
                "match_score": match_score,
                "matched_keywords": match_suggestion.get('matched_keywords'),
                "score_evaluated_at": datetime.utcnow(),
                "outreach_type": "cold_email",
                "subject_line": subject_line,
                "body_snippet": email_body[:250], # Store a snippet
                "pitch_gen_id": created_pitch_gen['pitch_gen_id'],
                "pitch_state": "generated",
                "client_approval_status": "pending_review",
                "created_by": "system_ai" # Or actual user if available
            }
            created_pitch = await pitch_queries.create_pitch_in_db(pitch_data)
            if not created_pitch:
                result["message"] = "Failed to save initial pitch record to database."
                return result
            # No need to return pitch_id, as pitch_gen_id is the primary reference for review

            # 8. Create pitch review task
            review_task_data = {
                "task_type": "pitch_review",
                "related_id": created_pitch_gen['pitch_gen_id'], # Link to pitch_generations record
                "campaign_id": campaign_id,
                "status": "pending",
                "notes": f"Review generated pitch for campaign '{campaign_data.get('campaign_name')}' and podcast '{media_data.get('name')}'."
            }
            created_review_task = await review_task_queries.create_review_task_in_db(review_task_data)
            if created_review_task:
                result["review_task_id"] = created_review_task['review_task_id']
                logger.info(f"Created pitch review task {created_review_task['review_task_id']} for pitch generation {created_pitch_gen['pitch_gen_id']}.")
            else:
                logger.warning(f"Failed to create review task for pitch generation {created_pitch_gen['pitch_gen_id']}.")

            result["status"] = "success"
            result["message"] = "Pitch generated and review task created successfully."
            return result

        except Exception as e:
            logger.error(f"Overall error in pitch generation for match {match_id}: {e}", exc_info=True)
            result["message"] = f"An unhandled error occurred during pitch generation: {str(e)}"
            result["error_details"] = str(e)
            return result
