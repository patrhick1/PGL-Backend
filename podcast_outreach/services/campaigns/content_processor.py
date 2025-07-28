# podcast_outreach/services/campaigns/content_processor.py
import asyncio
import logging
import uuid
from typing import Dict, Any, Optional, List, Set

from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.integrations.google_docs import GoogleDocsService
from podcast_outreach.services.ai.openai_client import OpenAIService
from podcast_outreach.utils.data_processor import extract_document_id
from podcast_outreach.services.matches.match_creation import MatchCreationService
from podcast_outreach.services.media_kits.generator import MediaKitService
from podcast_outreach.logging_config import get_logger

# Optional import for podcast transcriber
try:
    from podcast_outreach.services.media.podcast_transcriber import PodcastTranscriberService
    PODCAST_TRANSCRIBER_AVAILABLE = True
except ImportError as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"PodcastTranscriberService not available: {e}")
    PodcastTranscriberService = None
    PODCAST_TRANSCRIBER_AVAILABLE = False

logger = get_logger(__name__)

class ClientContentProcessor:
    """Enhanced client content processor that handles questionnaire data, podcast transcription, and triggers media kit generation."""

    def __init__(self):
        self.google_docs_service = GoogleDocsService()
        self.openai_service = OpenAIService()
        self.match_creation_service = MatchCreationService()
        self.podcast_transcriber = PodcastTranscriberService() if PODCAST_TRANSCRIBER_AVAILABLE else None
        self.media_kit_service = MediaKitService()

    def _is_gdoc_link(self, text: Optional[str]) -> bool:
        """Checks if the provided text is a Google Doc link."""
        return text and text.startswith("https://docs.google.com/document/d/")

    async def _get_gdoc_content_async(self, doc_link_or_id: Optional[str], doc_title_for_log: str) -> str:
        """Fetches Google Doc content asynchronously given a link or ID."""
        if not doc_link_or_id:
            logger.debug(f"No document link/ID provided for {doc_title_for_log}, skipping fetch.")
            return ""
        
        doc_id = extract_document_id(doc_link_or_id)
        if not doc_id:
            logger.warning(f"Could not extract Google Doc ID from '{doc_link_or_id}' for {doc_title_for_log}.")
            return ""
        
        try:
            logger.info(f"Fetching content from Google Doc: {doc_title_for_log} (ID: {doc_id})")
            # Assuming google_docs_service has an async method or we run its sync method in executor
            # For simplicity, let's assume get_document_content can be awaited if it's async,
            # or it needs to be wrapped like in AnglesProcessorPG if it's sync.
            # Let's assume it's a synchronous method for now, consistent with AnglesProcessorPG
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, self.google_docs_service.get_document_content, doc_id)
            logger.info(f"Successfully fetched content for {doc_title_for_log} (Length: {len(content if content else '')}).")
            return content if content else ""
        except Exception as e:
            logger.error(f"Error fetching Google Doc {doc_title_for_log} (ID: {doc_id}): {e}")
            return ""

    def _format_questionnaire_for_embedding(self, q_data: Optional[Dict[str, Any]]) -> str:
        """Enhanced questionnaire formatting for embedding, following the detailed structure."""
        if not q_data or not isinstance(q_data, dict):
            return ""
        
        formatted_parts = []
        
        try:
            # Section 2: Contact & Basic Info
            contact_info = q_data.get("contactInfo", {})
            if isinstance(contact_info, dict):
                full_name = contact_info.get("fullName", "")
                website = contact_info.get("website", "")
                if full_name:
                    formatted_parts.append(f"Client Name: {full_name}")
                if website:
                    formatted_parts.append(f"Website: {website}")
            
            # Section 3: Professional Bio & Background
            professional_bio = q_data.get("professionalBio", {})
            if isinstance(professional_bio, dict):
                about_work = professional_bio.get("aboutWork", "")
                expertise = professional_bio.get("expertiseTopics", "")
                achievements = professional_bio.get("achievements", "")
                
                if about_work:
                    formatted_parts.append(f"About Their Work: {about_work}")
                if expertise:
                    expertise_str = expertise if isinstance(expertise, str) else ", ".join(expertise) if isinstance(expertise, list) else str(expertise)
                    formatted_parts.append(f"Areas of Expertise: {expertise_str}")
                if achievements:
                    formatted_parts.append(f"Key Achievements: {achievements}")
            
            # Section 5: Suggested Topics & Talking Points
            suggested_topics = q_data.get("suggestedTopics", {})
            if isinstance(suggested_topics, dict):
                topics = suggested_topics.get("topics", "")
                key_stories = suggested_topics.get("keyStoriesOrMessages", "")
                
                if topics:
                    topics_str = topics if isinstance(topics, str) else ", ".join(topics) if isinstance(topics, list) else str(topics)
                    formatted_parts.append(f"Preferred Podcast Topics: {topics_str}")
                if key_stories:
                    formatted_parts.append(f"Key Stories and Messages: {key_stories}")
            
            # Section 7: Testimonials & Social Proof
            social_proof = q_data.get("socialProof", {})
            if isinstance(social_proof, dict):
                testimonials = social_proof.get("testimonials", "")
                stats = social_proof.get("notableStats", "")
                
                if testimonials:
                    formatted_parts.append(f"Testimonials: {testimonials}")
                if stats:
                    formatted_parts.append(f"Notable Stats: {stats}")
            
            # Section 9: Promotion & Contact Preferences
            promotion_prefs = q_data.get("promotionPrefs", {})
            if isinstance(promotion_prefs, dict):
                preferred_intro = promotion_prefs.get("preferredIntro", "")
                items_to_promote = promotion_prefs.get("itemsToPromote", "")
                
                if preferred_intro:
                    formatted_parts.append(f"Preferred Introduction: {preferred_intro}")
                if items_to_promote:
                    formatted_parts.append(f"Items to Promote: {items_to_promote}")
        
        except Exception as e:
            logger.warning(f"Error formatting questionnaire data for embedding: {e}")
        
        return "\n".join(formatted_parts)

    async def _process_podcast_transcriptions(self, campaign_id: uuid.UUID, questionnaire_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process podcast URLs from questionnaire and add transcription insights to campaign data."""
        try:
            logger.info(f"Processing podcast transcriptions for campaign {campaign_id}")
            
            if not self.podcast_transcriber:
                logger.warning(f"Podcast transcriber not available for campaign {campaign_id} - skipping transcription")
                return []
            
            # Process podcast URLs using the transcriber service
            transcription_results = await self.podcast_transcriber.process_podcast_urls_from_questionnaire(
                questionnaire_data, campaign_id
            )
            
            if transcription_results:
                logger.info(f"Processed {len(transcription_results)} podcast URLs for campaign {campaign_id}")
                
                # Store transcription results back to campaign for future reference
                # You might want to create a dedicated field for this or include it in questionnaire_responses
                transcription_summary = {
                    "podcast_transcriptions": transcription_results,
                    "total_processed": len(transcription_results),
                    "successful_transcriptions": len([r for r in transcription_results if r.get("status") == "completed"]),
                    "processed_at": str(uuid.uuid4())  # Using UUID as timestamp placeholder
                }
                
                # Store transcription results in questionnaire_responses JSONB field
                # First get the current campaign to preserve existing questionnaire_responses
                current_campaign = await campaign_queries.get_campaign_by_id(campaign_id)
                current_responses = current_campaign.get('questionnaire_responses', {}) if current_campaign else {}
                if current_responses is None:
                    current_responses = {}
                
                # Add transcription results to the existing responses
                current_responses['podcast_transcription_results'] = transcription_summary
                
                await campaign_queries.update_campaign(campaign_id, {
                    "questionnaire_responses": current_responses
                })
                
                logger.info(f"Stored transcription results for campaign {campaign_id}")
            
            return transcription_results
            
        except Exception as e:
            logger.error(f"Error processing podcast transcriptions for campaign {campaign_id}: {e}")
            return []

    async def _refine_keywords_with_llm(self, text_snippet: str, raw_keywords: List[str], campaign_id: uuid.UUID) -> List[str]:
        """Refine keywords using LLM with enhanced prompt for podcast guest context."""
        max_snippet_len = 2000  # Limit text snippet to avoid token limits
        raw_keywords_str = ", ".join(raw_keywords) if raw_keywords else "No keywords provided"
        
        if len(text_snippet) > max_snippet_len:
            text_snippet = text_snippet[:max_snippet_len] + "... (truncated)"
            
        prompt = f"""
        Given the following client information text and a list of raw keywords, please refine and consolidate this into a final list of up to 25-30 highly relevant, concise keywords (2-4 words each) that best represent the client's expertise and potential podcast topics. 

        Focus on keywords that:
        1. Represent their core expertise and talking points
        2. Would be searched by podcast hosts looking for guests
        3. Reflect topics they're passionate about discussing
        4. Include both broad topics and specific niches
        5. Are relevant to podcast audiences

        Client Information Snippet:
        {text_snippet if text_snippet.strip() else "No detailed text provided, focus on the raw keywords."}

        Raw Keywords:
        {raw_keywords_str}

        Return ONLY a comma-separated list of the final keywords, focusing on podcast-relevant topics and expertise areas.
        """
        try:
            logger.info(f"Refining keywords for campaign {campaign_id} using LLM.")
            response = await self.openai_service.create_chat_completion(
                system_prompt="You are an expert keyword analyst specializing in podcast guest expertise and topics. Your task is to refine keywords for optimal podcast matching.",
                prompt=prompt,
                workflow="keyword_refinement_podcast",
                related_campaign_id=campaign_id,
                parse_json=False
            )
            if response:
                refined_keywords = [kw.strip() for kw in response.split(',') if kw.strip()]
                logger.info(f"LLM refined keywords for campaign {campaign_id}: {refined_keywords}")
                return refined_keywords
            else:
                logger.warning(f"LLM keyword refinement returned no response for campaign {campaign_id}. Using raw keywords.")
                return sorted(list(set(raw_keywords)))
        except Exception as e:
            logger.error(f"Error during LLM keyword refinement for campaign {campaign_id}: {e}. Using raw keywords.")
            return sorted(list(set(raw_keywords)))

    async def process_and_embed_campaign_data(self, campaign_id: uuid.UUID, use_llm_keyword_refinement: bool = True) -> bool:
        """
        Enhanced processing that fetches campaign data, processes podcast transcriptions,
        aggregates text, consolidates keywords, generates embedding, updates the campaign,
        and triggers media kit generation.
        """
        logger.info(f"Starting enhanced content processing and embedding for campaign_id: {campaign_id}")

        # 1. Fetch Core Data
        campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign_data:
            logger.error(f"Campaign {campaign_id} not found. Cannot process content.")
            return False

        person_data = await people_queries.get_person_by_id_from_db(campaign_data['person_id'])
        if not person_data:
            logger.error(f"Person {campaign_data['person_id']} for campaign {campaign_id} not found.")
            # Decide if this is critical. For embedding, it might be.
            # For now, we'll allow it to proceed if other text sources exist.
            # return False 

        # 2. Process Podcast Transcriptions (if questionnaire data is available)
        questionnaire_responses = campaign_data.get('questionnaire_responses')
        if questionnaire_responses and isinstance(questionnaire_responses, dict):
            transcription_results = await self._process_podcast_transcriptions(campaign_id, questionnaire_responses)
            if transcription_results:
                logger.info(f"Processed {len(transcription_results)} podcast transcriptions for campaign {campaign_id}")

        # 3. Aggregate Text for Embedding
        text_segments = []
        campaign_name_for_logs = campaign_data.get("campaign_name", f"Campaign {campaign_id}")

        if person_data and person_data.get('bio'):
            text_segments.append(f"Client Overall Bio:\n{person_data['bio']}\n")

        # Campaign GDoc Bio
        campaign_bio_source = campaign_data.get('campaign_bio')
        if self._is_gdoc_link(campaign_bio_source):
            content = await self._get_gdoc_content_async(campaign_bio_source, f"{campaign_name_for_logs} - Campaign Bio GDoc")
            if content: text_segments.append(f"Campaign Bio (from GDoc):\n{content}\n")
        elif campaign_bio_source: # Direct text
            text_segments.append(f"Campaign Bio (direct):\n{campaign_bio_source}\n")

        # Campaign GDoc Angles
        campaign_angles_source = campaign_data.get('campaign_angles')
        if self._is_gdoc_link(campaign_angles_source):
            content = await self._get_gdoc_content_async(campaign_angles_source, f"{campaign_name_for_logs} - Campaign Angles GDoc")
            if content: text_segments.append(f"Campaign Angles (from GDoc):\n{content}\n")
        elif campaign_angles_source: # Direct text
            text_segments.append(f"Campaign Angles (direct):\n{campaign_angles_source}\n")
        
        # Mock Interview Transcript
        mock_interview_source = campaign_data.get('mock_interview_transcript') # Note: 'trancript' typo from schema
        if self._is_gdoc_link(mock_interview_source):
            content = await self._get_gdoc_content_async(mock_interview_source, f"{campaign_name_for_logs} - Mock Interview GDoc")
            if content: text_segments.append(f"Mock Interview Transcript (from GDoc):\n{content}\n")
        elif mock_interview_source: # Direct text
            text_segments.append(f"Mock Interview Transcript (direct):\n{mock_interview_source}\n")

        # Enhanced Questionnaire Responses
        if questionnaire_responses and isinstance(questionnaire_responses, dict):
            q_text = self._format_questionnaire_for_embedding(questionnaire_responses)
            if q_text:
                text_segments.append(f"Key Information from Questionnaire:\n{q_text}\n")
        
        # Add podcast transcription insights if available
        transcription_results = campaign_data.get('podcast_transcription_results')
        if transcription_results and isinstance(transcription_results, dict):
            successful_transcriptions = [r for r in transcription_results.get('podcast_transcriptions', []) 
                                       if r.get('status') == 'completed' and r.get('analysis')]
            if successful_transcriptions:
                transcription_insights = []
                for result in successful_transcriptions:
                    analysis = result.get('analysis', {})
                    if isinstance(analysis, dict) and analysis.get('analysis'):
                        transcription_insights.append(f"Podcast Analysis - {result.get('title', 'Unknown')}:\n{analysis['analysis']}")
                
                if transcription_insights:
                    text_segments.append(f"Podcast Speaking Insights:\n" + "\n\n".join(transcription_insights) + "\n")
        
        # Other GDoc Links
        other_docs_map = {
            "compiled_social_posts": "Compiled Social Posts GDoc",
            "podcast_transcript_link": "Podcast Transcript GDoc", # Assuming this is a single transcript for the client
            "compiled_articles_link": "Compiled Articles GDoc"
        }
        for field, title_template in other_docs_map.items():
            source = campaign_data.get(field)
            if self._is_gdoc_link(source):
                content = await self._get_gdoc_content_async(source, f"{campaign_name_for_logs} - {title_template}")
                if content: text_segments.append(f"{title_template.replace(' GDoc', '')}:\n{content}\n")
            elif source: # Direct text
                 text_segments.append(f"{title_template.replace(' GDoc', '')} (direct):\n{source}\n")

        aggregated_text = "\n\n---\n\n".join(filter(None, text_segments)).strip()

        if not aggregated_text:
            logger.warning(f"No text content could be aggregated for campaign {campaign_id}. Embedding cannot be generated.")
            # Optionally update campaign status here
            await campaign_queries.update_campaign_status(campaign_id, "pending_content_for_embedding", "No text found for embedding") # Assumes such a query exists
            return False

        logger.info(f"Aggregated text for campaign {campaign_id} (length: {len(aggregated_text)}). First 200 chars: '{aggregated_text[:200]}...'")

        # 4. Consolidate and Refine Keywords
        q_keywords = campaign_data.get('questionnaire_keywords', []) or []
        g_keywords = campaign_data.get('gdoc_keywords', []) or []
        
        raw_keywords_set: Set[str] = set()
        if isinstance(q_keywords, list): raw_keywords_set.update(kw for kw in q_keywords if isinstance(kw, str) and kw.strip())
        if isinstance(g_keywords, list): raw_keywords_set.update(kw for kw in g_keywords if isinstance(kw, str) and kw.strip())
        
        final_keywords_list: List[str] = []
        if use_llm_keyword_refinement:
            text_snippet_for_kw_refinement = aggregated_text if len(aggregated_text) > 200 else ""
            final_keywords_list = await self._refine_keywords_with_llm(text_snippet_for_kw_refinement, list(raw_keywords_set), campaign_id)
        else:
            final_keywords_list = sorted(list(raw_keywords_set))
        
        if not final_keywords_list and raw_keywords_set: # Fallback if LLM fails and there were raw keywords
            final_keywords_list = sorted(list(raw_keywords_set))
            logger.info(f"Using raw unique keywords for campaign {campaign_id} as final list: {final_keywords_list}")
        elif not final_keywords_list:
             logger.warning(f"No keywords (raw or refined) found for campaign {campaign_id}.")
        else:
            logger.info(f"Final keywords for campaign {campaign_id}: {final_keywords_list}")

        # Update campaign with consolidated keywords
        # We update keywords before embedding in case embedding fails, keywords are still useful
        await campaign_queries.update_campaign(campaign_id, {"campaign_keywords": final_keywords_list})
        logger.info(f"Updated campaign {campaign_id} with final keywords: {final_keywords_list}")

        # 5. Generate Embedding for Aggregated Text
        logger.info(f"Generating embedding for aggregated text of campaign {campaign_id}...")
        campaign_embedding = await self.openai_service.get_embedding(
            aggregated_text, 
            workflow="campaign_embedding", 
            related_campaign_id=campaign_id # Pass campaign_id for tracking
        )

        if campaign_embedding is None:
            logger.error(f"Failed to generate embedding for campaign {campaign_id}.")
            # Optionally update campaign status
            await campaign_queries.update_campaign_status(campaign_id, "embedding_failed", "Embedding generation returned None")
            return False
        
        logger.info(f"Embedding generated successfully for campaign {campaign_id}.")

        # 6. Update Campaign with Embedding
        update_payload_embedding = {"embedding": campaign_embedding}
        # Optionally, set a status indicating successful processing
        # update_payload_embedding["status"] = "processed_for_embedding" 
        
        updated = await campaign_queries.update_campaign(campaign_id, update_payload_embedding)
        
        if updated:
            logger.info(f"Successfully processed, embedded, and updated campaign {campaign_id}.")
            await campaign_queries.update_campaign_status(campaign_id, "active_ Intelligenge Processed", "Content aggregated, keywords consolidated, and embedding generated.")
            
            # 7. Trigger Media Kit Generation
            try:
                logger.info(f"Triggering media kit generation for campaign {campaign_id}")
                media_kit_result = await self.media_kit_service.create_or_update_media_kit(campaign_id)
                
                if media_kit_result:
                    logger.info(f"Successfully generated/updated media kit for campaign {campaign_id}")
                else:
                    logger.warning(f"Media kit generation returned no result for campaign {campaign_id}")
                    
            except Exception as e_media_kit:
                logger.error(f"Error generating media kit for campaign {campaign_id}: {e_media_kit}", exc_info=True)
            
            return True
        else:
            logger.error(f"Failed to update campaign {campaign_id} with embedding.")
            # await campaign_queries.update_campaign_status(campaign_id, "update_failed_post_embedding", "Failed to save embedding to DB")
            return False 