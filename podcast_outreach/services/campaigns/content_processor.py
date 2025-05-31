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

logger = logging.getLogger(__name__)

class ClientContentProcessor:
    """
    Service to aggregate client information, consolidate keywords, and generate embeddings for campaigns.
    """
    def __init__(self):
        self.google_docs_service = GoogleDocsService()
        self.openai_service = OpenAIService() # For embeddings and optional keyword refinement
        self.match_creation_service = MatchCreationService() # Initialize MatchCreationService

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
        """
        Selectively extracts and formats key answers from questionnaire_data into a coherent text block.
        This is an example and should be tailored to the actual questionnaire structure.
        """
        if not q_data:
            return ""

        segments = []
        
        # Example: Personal Information Section
        personal_info = q_data.get("personalInfo", {})
        if isinstance(personal_info, dict):
            if personal_info.get("bio"):
                segments.append(f"Client Bio (from Questionnaire):\n{personal_info['bio']}\n")
            if personal_info.get("expertise"): # Assuming 'expertise' might be a list of strings
                expertise_str = ", ".join(personal_info['expertise']) if isinstance(personal_info['expertise'], list) else str(personal_info['expertise'])
                segments.append(f"Client Expertise (from Questionnaire):\n{expertise_str}\n")

        # Example: Experience Section
        experience = q_data.get("experience", {})
        if isinstance(experience, dict):
            if experience.get("achievements"): # Assuming 'achievements' is a list
                achievements_str = "\n- " + "\n- ".join(experience['achievements']) if isinstance(experience['achievements'], list) else str(experience['achievements'])
                segments.append(f"Key Achievements (from Questionnaire):{achievements_str}\n")
        
        # Example: Preferences Section
        preferences = q_data.get("preferences", {})
        if isinstance(preferences, dict):
            if preferences.get("preferredTopics"):
                topics_str = "\n- " + "\n- ".join(preferences['preferredTopics']) if isinstance(preferences['preferredTopics'], list) else str(preferences['preferredTopics'])
                segments.append(f"Preferred Topics (from Questionnaire):{topics_str}\n")
            if preferences.get("targetAudience"):
                segments.append(f"Target Audience (from Questionnaire):\n{preferences['targetAudience']}\n")

        # Add more sections as needed based on your questionnaire_data structure
        # e.g., q_data.get('goals'), q_data.get('messaging')

        return "\n\n".join(segments).strip()

    async def _refine_keywords_with_llm(self, text_snippet: str, raw_keywords: List[str], campaign_id: uuid.UUID) -> List[str]:
        """
        Uses an LLM to refine and consolidate raw keywords.
        Returns a list of refined keywords.
        """
        if not raw_keywords:
            return []
        if not text_snippet.strip() and len(raw_keywords) <= 30: # If no text and raw keywords are few, just use them
             return sorted(list(set(raw_keywords)))


        raw_keywords_str = ", ".join(raw_keywords)
        # Limit text_snippet to avoid excessive token usage for keyword refinement
        max_snippet_len = 8000 # Approx 2k tokens, adjust as needed
        if len(text_snippet) > max_snippet_len:
            text_snippet = text_snippet[:max_snippet_len] + "... (truncated)"
            
        prompt = f"""
        Given the following client information text and a list of raw keywords, please refine and consolidate this into a final list of up to 20-30 highly relevant, concise keywords (2-3 words each) that best represent the client's expertise and potential podcast topics. Prioritize keywords that are likely to be searched by podcast hosts or listeners.

        Client Information Snippet:
        {text_snippet if text_snippet.strip() else "No detailed text provided, focus on the raw keywords."}

        Raw Keywords:
        {raw_keywords_str}

        Return ONLY a comma-separated list of the final keywords.
        """
        try:
            logger.info(f"Refining keywords for campaign {campaign_id} using LLM.")
            # Assuming create_chat_completion is an async method in OpenAIService
            response = await self.openai_service.create_chat_completion(
                system_prompt="You are an expert keyword analyst. Your task is to refine a list of keywords based on provided text.",
                prompt=prompt,
                workflow="keyword_refinement",
                related_campaign_id=campaign_id,
                parse_json=False # Expecting comma-separated string
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
            return sorted(list(set(raw_keywords))) # Fallback to unique raw keywords

    async def process_and_embed_campaign_data(self, campaign_id: uuid.UUID, use_llm_keyword_refinement: bool = True) -> bool:
        """
        Fetches campaign data, aggregates text, consolidates keywords, generates embedding, and updates the campaign.
        """
        logger.info(f"Starting content processing and embedding for campaign_id: {campaign_id}")

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

        # 2. Aggregate Text for Embedding
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
        mock_interview_source = campaign_data.get('mock_interview_trancript') # Note: 'trancript' typo from schema
        if self._is_gdoc_link(mock_interview_source):
            content = await self._get_gdoc_content_async(mock_interview_source, f"{campaign_name_for_logs} - Mock Interview GDoc")
            if content: text_segments.append(f"Mock Interview Transcript (from GDoc):\n{content}\n")
        elif mock_interview_source: # Direct text
            text_segments.append(f"Mock Interview Transcript (direct):\n{mock_interview_source}\n")

        # Questionnaire Responses
        questionnaire_responses = campaign_data.get('questionnaire_responses')
        if questionnaire_responses and isinstance(questionnaire_responses, dict):
            q_text = self._format_questionnaire_for_embedding(questionnaire_responses)
            if q_text:
                text_segments.append(f"Key Information from Questionnaire:\n{q_text}\n")
        
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

        # 3. Consolidate and Refine Keywords
        q_keywords = campaign_data.get('questionnaire_keywords', []) or []
        g_keywords = campaign_data.get('gdoc_keywords', []) or []
        
        raw_keywords_set: Set[str] = set()
        if isinstance(q_keywords, list): raw_keywords_set.update(kw for kw in q_keywords if isinstance(kw, str) and kw.strip())
        if isinstance(g_keywords, list): raw_keywords_set.update(kw for kw in g_keywords if isinstance(kw, str) and kw.strip())
        
        final_keywords_list: List[str] = []
        if use_llm_keyword_refinement:
            # Provide a snippet of aggregated_text for context, or just keywords if text is too short/missing
            text_snippet_for_kw_refinement = aggregated_text if len(aggregated_text) > 200 else "" # Arbitrary threshold
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

        # 4. Generate Embedding for Aggregated Text
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

        # 5. Update Campaign with Embedding
        update_payload_embedding = {"embedding": campaign_embedding}
        # Optionally, set a status indicating successful processing
        # update_payload_embedding["status"] = "processed_for_embedding" 
        
        updated = await campaign_queries.update_campaign(campaign_id, update_payload_embedding)
        
        if updated:
            logger.info(f"Successfully processed, embedded, and updated campaign {campaign_id}.")
            await campaign_queries.update_campaign_status(campaign_id, "active_ Intelligenge Processed", "Content aggregated, keywords consolidated, and embedding generated.")
            
            # After successful processing, trigger match creation against media
            try:
                logger.info(f"Triggering match creation for campaign {campaign_id} against media records.")
                # Fetch a list of media to match against. 
                # This could be all media, or filtered based on some criteria.
                # For now, let's fetch a limited number of recent media as an example.
                # In a real scenario, you might have more sophisticated logic for selecting media.
                all_media_records, total_media = await media_queries.get_all_media_from_db(limit=500, offset=0) # Example: match against up to 500 media
                
                if all_media_records:
                    logger.info(f"Campaign {campaign_id} will be matched against {len(all_media_records)} media records.")
                    await self.match_creation_service.create_and_score_match_suggestions_for_campaign(
                        campaign_id=campaign_id,
                        media_records=all_media_records
                    )
                    logger.info(f"Match creation/update process initiated for campaign {campaign_id}.")
                else:
                    logger.info(f"No media records found to match against campaign {campaign_id}.")
            except Exception as e_match:
                logger.error(f"Error triggering match creation for campaign {campaign_id}: {e_match}", exc_info=True)
            
            return True
        else:
            logger.error(f"Failed to update campaign {campaign_id} with embedding.")
            # await campaign_queries.update_campaign_status(campaign_id, "update_failed_post_embedding", "Failed to save embedding to DB")
            return False 