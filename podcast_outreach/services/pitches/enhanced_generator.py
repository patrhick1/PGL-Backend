# podcast_outreach/services/pitches/enhanced_generator.py

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
import json

# LangChain imports
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import SystemMessage
from langchain_core.exceptions import OutputParserException

# Anthropic for tokenizer
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
from podcast_outreach.database.queries import pitch_templates as pitch_template_queries
from podcast_outreach.integrations import google_docs as google_docs_integration
from podcast_outreach.services.ai.tracker import tracker as ai_tracker

logger = get_logger(__name__)


class EnhancedPitchGeneratorService:
    """
    Enhanced pitch generator that properly handles templates and matches campaign angles to podcasts.
    """

    def __init__(self):
        """Initialize services and configurations needed for pitch writing."""
        self.google_docs_service = google_docs_integration.GoogleDocsService()
        
        self.model_name = "claude-3-5-sonnet-20241022"
        self.llm = self._get_llm_client(self.model_name)
        
        self.anthropic_client = None
        if "claude" in self.model_name.lower() and ANTHROPIC_API_KEY:
            self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        
        logger.info(f"EnhancedPitchGeneratorService initialized with LLM: {self.model_name}")

    def _get_llm_client(self, model_name: str):
        """Helper to get the correct LLM client based on model name."""
        if "claude" in model_name.lower():
            if not ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY not set for Claude model.")
            return ChatAnthropic(
                model=model_name,
                anthropic_api_key=ANTHROPIC_API_KEY,
                temperature=0.4,
                max_tokens=4000  # Increased for longer pitches
            )
        elif "gemini" in model_name.lower():
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY not set for Gemini model.")
            return ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=GEMINI_API_KEY,
                temperature=0.4,
                max_output_tokens=4000  # Increased for longer outputs
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
        """Count tokens accurately using the appropriate tokenizer for the LLM."""
        if "claude" in self.model_name.lower() and self.anthropic_client:
            try:
                count_result = self.anthropic_client.beta.messages.count_tokens(
                    model=self.model_name,
                    messages=[{"role": "user", "content": text}]
                )
                return count_result.input_tokens
            except Exception as e:
                logger.warning(f"Error counting Claude tokens: {str(e)}. Falling back to estimation.")
                return len(text) // 4
        else:
            return len(text) // 4

    def _extract_talking_points_from_angles(self, angles_text: str) -> List[str]:
        """Extract key talking points from campaign angles text."""
        if not angles_text:
            return ["", "", ""]
        
        # Try to parse structured angles
        angle_lines = angles_text.strip().split('\n')
        talking_points = []
        
        for line in angle_lines[:10]:  # Look at first 10 lines/angles
            # Extract topic/outcome from various formats
            if ';' in line:
                parts = line.split(';')
                if len(parts) >= 2:
                    topic = parts[0].replace('Topic:', '').strip()
                    outcome = parts[1].replace('Outcome:', '').strip()
                    talking_points.append(f"{topic} - {outcome}")
            elif ':' in line and 'Topic' in line:
                topic_part = line.split(':', 1)[1].strip()
                talking_points.append(topic_part)
            elif line.strip() and not line.startswith(('*', '-', '•')):
                # Use the line as-is if it's not a bullet point
                talking_points.append(line.strip())
        
        # Ensure we have at least 3 talking points
        while len(talking_points) < 3:
            talking_points.append("")
        
        return talking_points[:3]

    def _match_angles_to_podcast(self, campaign_angles: str, campaign_keywords: List[str], 
                                episode_data: Dict[str, Any], media_data: Dict[str, Any]) -> str:
        """Match campaign angles to podcast content and return the most relevant angle."""
        if not campaign_angles:
            return "sharing valuable insights with your audience"
        
        # Combine episode and media data for matching - ensure all values are strings
        content_parts = []
        
        # Safely get episode data
        if episode_data:
            content_parts.append(str(episode_data.get('ai_episode_summary') or ''))
            content_parts.append(str(episode_data.get('episode_summary') or ''))
            content_parts.append(str(episode_data.get('title') or ''))
        
        # Safely get media data
        if media_data:
            content_parts.append(str(media_data.get('description') or ''))
            content_parts.append(str(media_data.get('ai_description') or ''))
        
        podcast_content = " ".join(content_parts).lower()
        
        # Score each angle based on keyword matches
        angle_lines = campaign_angles.strip().split('\n')
        best_angle = ""
        best_score = 0
        
        for line in angle_lines[:10]:
            if not line.strip():
                continue
                
            score = 0
            # Check campaign keywords
            for keyword in campaign_keywords:
                if keyword.lower() in podcast_content:
                    score += 2
                if keyword.lower() in line.lower():
                    score += 1
            
            # Check angle content against podcast
            angle_words = line.lower().split()
            for word in angle_words:
                if len(word) > 4 and word in podcast_content:
                    score += 0.5
            
            if score > best_score:
                best_score = score
                best_angle = line
        
        # Format the best angle for the pitch
        if best_angle:
            # Clean up formatting
            best_angle = best_angle.replace('Topic:', '').replace('Outcome:', '')
            if ';' in best_angle:
                parts = best_angle.split(';')
                return f"discussing {parts[0].strip()}"
            return best_angle.strip()
        
        return "sharing valuable insights with your audience"

    def _convert_template_format(self, template_content: str) -> str:
        """Convert double brace {{var}} to single brace {var} for LangChain compatibility."""
        return re.sub(r'\{\{(\w+)\}\}', r'{\1}', template_content)

    async def select_best_episode(self, campaign_id: uuid.UUID, media_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[float]]:
        """
        Selects the best episode for pitching from a given media (podcast) based on campaign relevance.
        """
        logger.info(f"Selecting best episode for campaign {campaign_id} and media {media_id}")

        campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found for episode selection.")
            return None, None

        campaign_embedding = campaign.get('embedding')
        campaign_keywords = campaign.get('campaign_keywords', [])

        episodes = await episode_queries.get_episodes_for_media_with_content(media_id)
        if not episodes:
            logger.warning(f"No episodes with content found for media {media_id}.")
            return None, None

        best_episode = None
        highest_score = -1.0

        # Try embedding similarity first
        if campaign_embedding is not None and len(campaign_embedding) > 0:
            for episode in episodes:
                episode_embedding = episode.get('embedding')
                if episode_embedding is not None and len(episode_embedding) > 0:
                    try:
                        emb1 = np.array(campaign_embedding)
                        emb2 = np.array(episode_embedding)
                        score = 1 - cosine(emb1, emb2)
                        if score > highest_score:
                            highest_score = score
                            best_episode = episode
                    except Exception as e:
                        logger.warning(f"Error computing embedding similarity for episode {episode.get('episode_id')}: {e}")
            
            if best_episode and highest_score > 0.6:  # Only use if similarity is reasonable
                logger.info(f"Best episode selected by embedding similarity: {best_episode.get('title')} (Score: {highest_score:.2f})")
                return best_episode, highest_score

        # Fall back to keyword matching
        if campaign_keywords:
            for episode in episodes:
                episode_content = " ".join([
                    episode.get('ai_episode_summary', ''),
                    episode.get('episode_summary', ''),
                    episode.get('transcript', ''),
                    episode.get('title', '')
                ]).lower()
                
                if episode_content:
                    score = 0
                    for keyword in campaign_keywords:
                        if keyword.lower() in episode_content:
                            score += 1
                    
                    # Normalize score
                    if len(campaign_keywords) > 0:
                        score = score / len(campaign_keywords)
                    
                    if score > highest_score:
                        highest_score = score
                        best_episode = episode
            
            if best_episode:
                logger.info(f"Best episode selected by keyword matching: {best_episode.get('title')} (Score: {highest_score:.2f})")
                return best_episode, highest_score

        # Final fallback to most recent episode
        if episodes:
            sorted_episodes = sorted(episodes, key=lambda x: x.get('publish_date', datetime.min), reverse=True)
            best_episode = sorted_episodes[0]
            highest_score = 0.0
            logger.info(f"Best episode selected by recency: {best_episode.get('title')} (Score: {highest_score})")
            return best_episode, highest_score

        logger.warning(f"Could not select a best episode for campaign {campaign_id} and media {media_id}.")
        return None, None

    async def generate_pitch_from_template(
        self,
        campaign_data: Dict[str, Any],
        media_data: Dict[str, Any],
        episode_data: Dict[str, Any],
        pitch_template_id_str: str,
        media_kit_content: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Dict[str, int], float]:
        """
        Generates a pitch email and subject line using an LLM and a specified template.
        """
        start_time = time.time()
        total_token_usage = {"input_tokens": 0, "output_tokens": 0}
        
        # Fetch template from DB
        db_template = await pitch_template_queries.get_template_by_id(pitch_template_id_str)
        if not db_template or not db_template.get('prompt_body'):
            logger.error(f"Pitch template with ID '{pitch_template_id_str}' not found in DB or has no prompt_body.")
            return None, None, total_token_usage, 0.0
        
        # Convert template format
        pitch_template_content = self._convert_template_format(db_template['prompt_body'])
        
        # Extract host names from media data
        host_names_list = media_data.get('host_names', [])
        host_name = host_names_list[0] if host_names_list else 'there'
        
        # Extract talking points from campaign angles
        campaign_angles = ""
        if campaign_data.get('campaign_angles'):
            angles_data = campaign_data.get('campaign_angles')
            if angles_data and isinstance(angles_data, str):
                if angles_data.startswith('https://docs.google.com'):
                    # It's a Google Doc URL - fetch content
                    doc_id = self._extract_google_doc_id(angles_data)
                    if doc_id:
                        try:
                            logger.info(f"Fetching angles content from Google Doc: {doc_id}")
                            campaign_angles = await asyncio.to_thread(self.google_docs_service.get_document_content, doc_id)
                            logger.info(f"Successfully fetched angles content (length: {len(campaign_angles)})")
                        except Exception as e:
                            logger.warning(f"Failed to fetch angles from Google Doc {doc_id}: {e}")
                            campaign_angles = ""
                    else:
                        logger.warning(f"Could not extract doc ID from angles URL: {angles_data}")
                else:
                    # It's already text content (not a URL)
                    campaign_angles = angles_data
                    logger.info(f"Using angles content directly (length: {len(campaign_angles)})")
        
        talking_points = self._extract_talking_points_from_angles(campaign_angles)
        
        # Extract campaign bio content
        campaign_bio_content = ""
        if campaign_data.get('campaign_bio'):
            bio_data = campaign_data.get('campaign_bio')
            if bio_data and isinstance(bio_data, str):
                if bio_data.startswith('https://docs.google.com'):
                    # It's a Google Doc URL - fetch content
                    doc_id = self._extract_google_doc_id(bio_data)
                    if doc_id:
                        try:
                            logger.info(f"Fetching bio content from Google Doc: {doc_id}")
                            campaign_bio_content = await asyncio.to_thread(self.google_docs_service.get_document_content, doc_id)
                            logger.info(f"Successfully fetched bio content (length: {len(campaign_bio_content)})")
                        except Exception as e:
                            logger.warning(f"Failed to fetch bio from Google Doc {doc_id}: {e}")
                            campaign_bio_content = ""
                    else:
                        logger.warning(f"Could not extract doc ID from bio URL: {bio_data}")
                else:
                    # It's already text content (not a URL)
                    campaign_bio_content = bio_data
                    logger.info(f"Using bio content directly (length: {len(campaign_bio_content)})")
        
        # Match angles to podcast content
        matched_angle = self._match_angles_to_podcast(
            campaign_angles,
            campaign_data.get('campaign_keywords', []),
            episode_data,
            media_data
        )
        
        # Prepare comprehensive inputs
        inputs = {
            # Podcast Information
            "podcast_name": media_data.get('name', 'your podcast'),
            "host_name": host_name,
            "episode_title": episode_data.get('title', 'your recent episode'),
            "episode_summary": episode_data.get('episode_summary') or '',
            "ai_summary_of_best_episode": episode_data.get('ai_episode_summary') or '',
            "latest_news_from_podcast": '',  # Could be populated from recent episodes
            
            # Client Information
            "client_name": campaign_data.get('campaign_name', 'our client'),
            "client_bio_summary": campaign_bio_content or '',
            "campaign_goal": campaign_data.get('goal_note', ''),
            "client_key_talking_point_1": talking_points[0],
            "client_key_talking_point_2": talking_points[1],
            "client_key_talking_point_3": talking_points[2],
            
            # Pitch Details
            "specific_pitch_angle": matched_angle,
            "link_to_client_media_kit": campaign_data.get('media_kit_url', ''),
            "media_kit_highlights": media_kit_content or "Available upon request",
            
            # Context Awareness
            "previous_context": "No previous contact with this podcast host.",
            "context_guidelines": "This is the first contact with this podcast host. Use a warm, professional introduction.",
            
            # Legacy compatibility
            "pitch_topics": campaign_angles,
            "media_kit_content": media_kit_content or "Available upon request",
            "client_bio": campaign_bio_content or '',
            "ai_summary": episode_data.get('ai_episode_summary') or '',
            "guest_name": episode_data.get('guest_names', '')
        }

        # Create the prompt for pitch generation
        system_message = """You are an expert podcast pitch writer. Generate a compelling, personalized pitch email based on the template and information provided. 
        
        IMPORTANT: Return ONLY the email body text, without any JSON formatting, field names, or metadata. The email should be ready to send as-is."""
        
        human_message_template = pitch_template_content + "\n\nGenerate the pitch email based on the above template and the provided information."
        
        # Use ChatPromptTemplate for better structure
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_message),
            HumanMessagePromptTemplate.from_template(human_message_template)
        ])
        
        generated_email_body = None
        generated_subject_line = None

        try:
            # Generate the pitch
            messages = prompt.format_messages(**inputs)
            response = await self.llm.ainvoke(messages)
            generated_email_body = response.content.strip()
            
            # Count tokens
            prompt_text = " ".join([m.content for m in messages])
            prompt_tokens = self._count_tokens(prompt_text)
            completion_tokens = self._count_tokens(generated_email_body)
            total_token_usage["input_tokens"] += prompt_tokens
            total_token_usage["output_tokens"] += completion_tokens

            await ai_tracker.log_usage(
                workflow="pitch_generation_body",
                model=self.model_name,
                tokens_in=prompt_tokens,
                tokens_out=completion_tokens,
                execution_time=(time.time() - start_time),
                endpoint="langchain.llm.ainvoke",
                related_media_id=media_data.get('media_id'),
                related_campaign_id=campaign_data.get('campaign_id')
            )
            logger.info(f"Generated pitch email for {media_data.get('name')}. Tokens: {prompt_tokens} in, {completion_tokens} out.")

        except Exception as e:
            logger.error(f"Error generating pitch email for {media_data.get('name')}: {e}", exc_info=True)
            generated_email_body = f"ERROR: Failed to generate pitch email. {str(e)}"

        # Subject line generation
        subject_template_id = "subject_line_v1"
        db_subject_template = await pitch_template_queries.get_template_by_id(subject_template_id)

        if db_subject_template and db_subject_template.get('prompt_body'):
            subject_template_content = self._convert_template_format(db_subject_template['prompt_body'])
            
            subject_inputs = {
                "podcast_name": media_data.get('name', 'your podcast'),
                "host_name": host_name,
                "episode_title": episode_data.get('title', ''),
                "episode_summary": episode_data.get('episode_summary') or '',
                "ai_summary_of_best_episode": episode_data.get('ai_episode_summary') or '',
                "guest_name": episode_data.get('guest_names', ''),
                "client_name": campaign_data.get('campaign_name', 'a relevant guest'),
                "ai_summary": episode_data.get('ai_episode_summary') or ''
            }
            
            subject_system_message = "Generate a clear, engaging email subject line based on the template. Return ONLY the subject line text, nothing else."
            subject_prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=subject_system_message),
                HumanMessagePromptTemplate.from_template(subject_template_content)
            ])
            
            try:
                subject_messages = subject_prompt.format_messages(**subject_inputs)
                subject_response = await self.llm.ainvoke(subject_messages)
                generated_subject_line = subject_response.content.strip()
                
                # Remove any quotes that might have been added
                generated_subject_line = generated_subject_line.strip('"\'')
                
                prompt_text = " ".join([m.content for m in subject_messages])
                prompt_tokens = self._count_tokens(prompt_text)
                completion_tokens = self._count_tokens(generated_subject_line)
                total_token_usage["input_tokens"] += prompt_tokens
                total_token_usage["output_tokens"] += completion_tokens

                await ai_tracker.log_usage(
                    workflow="pitch_generation_subject",
                    model=self.model_name,
                    tokens_in=prompt_tokens,
                    tokens_out=completion_tokens,
                    execution_time=(time.time() - start_time),
                    endpoint="langchain.llm.ainvoke",
                    related_media_id=media_data.get('media_id'),
                    related_campaign_id=campaign_data.get('campaign_id')
                )
                logger.info(f"Generated subject line for {media_data.get('name')}. Tokens: {prompt_tokens} in, {completion_tokens} out.")

            except Exception as e:
                logger.error(f"Error generating subject line for {media_data.get('name')}: {e}", exc_info=True)
                generated_subject_line = f"Guest opportunity for {media_data.get('name', 'your podcast')} - {campaign_data.get('campaign_name', 'Expert Guest')}"
        else:
            logger.warning("Subject line template not found. Using default subject line.")
            generated_subject_line = f"Guest opportunity for {media_data.get('name', 'your podcast')} - {campaign_data.get('campaign_name', 'Expert Guest')}"

        execution_time = time.time() - start_time
        return generated_email_body, generated_subject_line, total_token_usage, execution_time

    async def generate_pitch_for_match(self, match_id: int, pitch_template_id: str = "generic_pitch_v1") -> Dict[str, Any]:
        """
        Orchestrates the pitch generation process for an approved match suggestion.
        """
        logger.info(f"Starting pitch generation for match_id: {match_id} using template_id: {pitch_template_id}")
        
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
            # Fetch match suggestion
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

            # Fetch campaign and media data
            campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
            media_data = await media_queries.get_media_by_id_from_db(media_id)

            if not campaign_data or not media_data:
                result["message"] = "Campaign or Media data not found for the match."
                return result

            # Select best episode
            best_episode_data, match_score = await self.select_best_episode(campaign_id, media_id)
            if not best_episode_data:
                result["message"] = "Could not select a best episode for pitching."
                return result
            
            logger.info(f"Selected episode {best_episode_data.get('episode_id')} ('{best_episode_data.get('title')}') for pitching.")

            # Fetch media kit content if available
            media_kit_content = None
            media_kit_url = campaign_data.get('media_kit_url')
            if media_kit_url:
                doc_id = self._extract_google_doc_id(media_kit_url)
                if doc_id:
                    try:
                        media_kit_content = await asyncio.to_thread(self.google_docs_service.get_document_content, doc_id)
                        logger.info(f"Fetched media kit content (length: {len(media_kit_content) if media_kit_content else 0} chars).")
                    except Exception as e:
                        logger.warning(f"Failed to fetch media kit content from {media_kit_url}: {e}")

            # Generate pitch
            email_body, subject_line, token_usage, exec_time = await self.generate_pitch_from_template(
                campaign_data, media_data, best_episode_data, pitch_template_id, media_kit_content
            )

            if not email_body or not subject_line:
                result["message"] = "AI failed to generate complete pitch email or subject line."
                result["error_details"] = {"email_body_error": email_body, "subject_line_error": subject_line}
                return result

            # Save pitch generation
            pitch_gen_data = {
                "campaign_id": campaign_id,
                "media_id": media_id,
                "template_id": pitch_template_id,
                "draft_text": email_body,
                "ai_model_used": self.model_name,
                "pitch_topic": best_episode_data.get('title'),
                "temperature": 0.4,
                "generation_status": "draft",
                "send_ready_bool": False
            }
            created_pitch_gen = await pitch_gen_queries.create_pitch_generation_in_db(pitch_gen_data)
            if not created_pitch_gen:
                result["message"] = "Failed to save pitch generation to database."
                return result
            result["pitch_gen_id"] = created_pitch_gen['pitch_gen_id']
            result["pitch_text_preview"] = email_body[:500] + "..." if len(email_body) > 500 else email_body
            result["subject_line_preview"] = subject_line

            # Save pitch record
            pitch_data = {
                "campaign_id": campaign_id,
                "media_id": media_id,
                "attempt_no": 1,
                "match_score": match_score,
                "matched_keywords": match_suggestion.get('matched_keywords'),
                "score_evaluated_at": datetime.utcnow(),
                "outreach_type": "cold_email",
                "subject_line": subject_line,
                "body_snippet": email_body[:250],
                "pitch_gen_id": created_pitch_gen['pitch_gen_id'],
                "pitch_state": "generated",
                "client_approval_status": "pending_review",
                "created_by": "system_ai"
            }
            created_pitch = await pitch_queries.create_pitch_in_db(pitch_data)
            if not created_pitch:
                result["message"] = "Failed to save initial pitch record to database."
                return result

            # Create review task
            review_task_data = {
                "task_type": "pitch_review",
                "related_id": created_pitch_gen['pitch_gen_id'],
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