# podcast_outreach/services/campaigns/questionnaire_processor.py
import logging
import uuid
from typing import Dict, Any, List, Optional
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.services.campaigns.questionnaire_social_processor import QuestionnaireSocialProcessor
from podcast_outreach.services.campaigns.angles_generator import AnglesProcessorPG
import json # For storing as JSONB
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class QuestionnaireProcessor:
    """Enhanced questionnaire processor with LLM-powered keyword generation."""
    
    def __init__(self):
        self.gemini_service = GeminiService()  # Using enhanced Gemini 2.0-flash
        self.social_processor = QuestionnaireSocialProcessor()  # For social media processing

    async def _generate_keywords_from_questionnaire_llm(self, questionnaire_data: Dict[str, Any]) -> List[str]:
        """Generate keywords from questionnaire data using LLM instead of hardcoded topics."""
        try:
            # Extract all questionnaire content
            content_parts = []
            
            def extract_text(value):
                if isinstance(value, str):
                    return value.strip()
                elif isinstance(value, list):
                    return " | ".join([str(v) for v in value if v])
                elif isinstance(value, dict):
                    return " | ".join([f"{k}: {v}" for k, v in value.items() if v])
                elif value is not None:
                    return str(value)
                return ""
            
            # Extract contact information from nested structure
            contact_info = questionnaire_data.get("contactInfo", {})
            if isinstance(contact_info, dict):
                full_name = contact_info.get("fullName", "")
                email = contact_info.get("email", "")
                if full_name:
                    content_parts.append(f"Full Name: {full_name}")
                if email:
                    content_parts.append(f"Email: {email}")
            
            # Extract professional background from nested structure
            professional_bio = questionnaire_data.get("professionalBio", {})
            if isinstance(professional_bio, dict):
                about_work = professional_bio.get("aboutWork", "")
                expertise = professional_bio.get("expertiseTopics", "")
                achievements = professional_bio.get("achievements", "")
                
                if about_work:
                    content_parts.append(f"About Their Work: {about_work}")
                if expertise:
                    expertise_str = expertise if isinstance(expertise, str) else ", ".join(expertise) if isinstance(expertise, list) else str(expertise)
                    content_parts.append(f"Areas of Expertise: {expertise_str}")
                if achievements:
                    content_parts.append(f"Key Achievements: {achievements}")
            
            # Extract suggested topics from nested structure
            suggested_topics = questionnaire_data.get("suggestedTopics", {})
            if isinstance(suggested_topics, dict):
                topics = suggested_topics.get("topics", "")
                key_stories = suggested_topics.get("keyStoriesOrMessages", "")
                
                if topics:
                    topics_str = topics if isinstance(topics, str) else ", ".join(topics) if isinstance(topics, list) else str(topics)
                    content_parts.append(f"Preferred Podcast Topics: {topics_str}")
                if key_stories:
                    content_parts.append(f"Key Stories and Messages: {key_stories}")
            
            # Extract sample questions
            sample_questions = questionnaire_data.get("sampleQuestions", {})
            if isinstance(sample_questions, dict):
                frequently_asked = sample_questions.get("frequentlyAsked", "")
                love_to_be_asked = sample_questions.get("loveToBeAsked", "")
                
                if frequently_asked:
                    content_parts.append(f"Frequently Asked Questions: {frequently_asked}")
                if love_to_be_asked:
                    content_parts.append(f"Questions They Love to Be Asked: {love_to_be_asked}")
            
            # Extract social proof from nested structure
            social_proof = questionnaire_data.get("socialProof", {})
            if isinstance(social_proof, dict):
                testimonials = social_proof.get("testimonials", "")
                stats = social_proof.get("notableStats", "")
                
                if testimonials:
                    content_parts.append(f"Testimonials: {testimonials}")
                if stats:
                    content_parts.append(f"Notable Stats: {stats}")
            
            # Extract media experience
            media_experience = questionnaire_data.get("mediaExperience", {})
            if isinstance(media_experience, dict):
                previous_appearances = media_experience.get("previousAppearances", [])
                if previous_appearances:
                    appearances_text = " | ".join([str(app) for app in previous_appearances if app])
                    content_parts.append(f"Previous Media Appearances: {appearances_text}")
            
            # Extract promotion preferences from nested structure
            promotion_prefs = questionnaire_data.get("promotionPrefs", {})
            if isinstance(promotion_prefs, dict):
                preferred_intro = promotion_prefs.get("preferredIntro", "")
                items_to_promote = promotion_prefs.get("itemsToPromote", "")
                
                if preferred_intro:
                    content_parts.append(f"Preferred Introduction: {preferred_intro}")
                if items_to_promote:
                    content_parts.append(f"Items to Promote: {items_to_promote}")
            
            # Extract any remaining top-level fields not covered above
            excluded_fields = {
                "contactInfo", "professionalBio", "suggestedTopics", "sampleQuestions", 
                "socialProof", "mediaExperience", "promotionPrefs"
            }
            
            for key, value in questionnaire_data.items():
                if key not in excluded_fields:
                    text_value = extract_text(value)
                    if text_value:
                        content_parts.append(f"{key.replace('_', ' ').title()}: {text_value}")
            
            questionnaire_content = "\n".join(content_parts)
            
            if not questionnaire_content.strip():
                logger.warning("No questionnaire content available for keyword generation")
                return ["expert", "speaker", "thought-leader", "professional", "industry-expert"]
            
            # Create LLM prompt for keyword generation
            prompt = f"""
Based on the following client questionnaire data, generate exactly 20 relevant keywords that represent their expertise, topics, and areas of knowledge. 

These keywords should:
- Be specific to their actual expertise (not generic)
- Include industry terms, topics they can speak about on a podcast
- Represent their unique value proposition
- Be useful for podcast hosts to understand their niche
- Include both broad and specific terms

Questionnaire Data:
{questionnaire_content}

Please respond with exactly 20 keywords separated by commas, no numbering or additional text:
"""
            
            # Get LLM response
            response = await self.gemini_service.create_message(prompt)
            
            if response:
                # Parse keywords from response
                keywords = [k.strip() for k in response.split(',') if k.strip()]
                
                # Clean up keywords (remove quotes, normalize)
                keywords = [re.sub(r'^["\']|["\']$', '', k).strip() for k in keywords]
                keywords = [k for k in keywords if k and len(k) > 2]  # Filter out very short keywords
                
                # Ensure we have exactly 20 keywords
                if len(keywords) > 20:
                    keywords = keywords[:20]
                elif len(keywords) < 20:
                    # Pad with fallback keywords if needed
                    fallback_keywords = ["expert", "speaker", "thought-leader", "professional", "industry-expert", 
                                       "consultant", "advisor", "entrepreneur", "specialist", "authority"]
                    while len(keywords) < 20 and fallback_keywords:
                        keywords.append(fallback_keywords.pop(0))
                    # If still not enough, repeat some
                    while len(keywords) < 20:
                        keywords.append(f"expert-{len(keywords)+1}")
                
                logger.info(f"Generated {len(keywords)} keywords from questionnaire using LLM")
                return keywords
            else:
                logger.warning("Empty response from LLM for keyword generation")
                return ["expert", "speaker", "thought-leader", "professional", "industry-expert"] * 4  # Fallback keywords
                
        except Exception as e:
            logger.error(f"Error generating keywords from questionnaire with LLM: {e}")
            return ["expert", "speaker", "thought-leader", "professional", "industry-expert"] * 4  # Fallback keywords

    def construct_mock_interview_from_questionnaire(self, questionnaire_data: Dict[str, Any]) -> str:
        """Note: Mock interviews are no longer used for bio generation. This function is deprecated."""
        logger.warning("construct_mock_interview_from_questionnaire is deprecated. Bio generation now uses questionnaire data directly.")
        return "Bio and angles will be generated directly from questionnaire data."

    async def process_campaign_questionnaire_submission(
        self, campaign_id: uuid.UUID, questionnaire_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process questionnaire submission with LLM-powered keyword generation."""
        logger.info(f"Processing questionnaire submission for campaign {campaign_id}")
        
        try:
            # Generate keywords using LLM instead of hardcoded extraction
            logger.info(f"Generating keywords from questionnaire using LLM for campaign {campaign_id}")
            generated_keywords = await self._generate_keywords_from_questionnaire_llm(questionnaire_data)
            
            # Generate mock interview transcript
            mock_interview_transcript = await self._generate_mock_interview_transcript(questionnaire_data)
            
            # Update campaign with questionnaire data, mock interview, and LLM-generated keywords
            update_data = {
                "questionnaire_responses": questionnaire_data,
                "questionnaire_keywords": generated_keywords,
                "mock_interview_transcript": mock_interview_transcript
            }
            
            # Update the campaign - FIXED: use correct method name
            updated_campaign = await campaign_queries.update_campaign(campaign_id, update_data)
            
            if updated_campaign:
                logger.info(f"Successfully processed questionnaire for campaign {campaign_id}")
                logger.info(f"Generated {len(generated_keywords)} keywords and mock interview transcript")
                
                # Trigger bio and angles generation now that we have a mock interview transcript
                angles_processor = AnglesProcessorPG()
                try:
                    logger.info(f"Triggering bio/angles generation for campaign {campaign_id} after questionnaire submission")
                    bio_result = await angles_processor.process_campaign(str(campaign_id))
                    bio_status = bio_result.get("status", "error")
                    if bio_status == "success":
                        logger.info(f"Successfully generated bio/angles for campaign {campaign_id}")
                    else:
                        logger.warning(f"Bio generation returned status: {bio_status} for campaign {campaign_id}")
                except Exception as bio_error:
                    logger.error(f"Error generating bio/angles for campaign {campaign_id}: {bio_error}")
                    # Don't fail the questionnaire processing if bio generation fails
                finally:
                    angles_processor.cleanup()
                
                # Note: Background task processing can be triggered manually via the API
                # /tasks/run/process_campaign_content?campaign_id={campaign_id}
                
                return {
                    "success": True,
                    "campaign_id": str(campaign_id),
                    "keywords_count": len(generated_keywords),
                    "status": "questionnaire_completed"
                }
            else:
                logger.error(f"Failed to update campaign {campaign_id} with questionnaire data")
                return {
                    "success": False,
                    "error": "Failed to update campaign with questionnaire data"
                }
                
        except Exception as e:
            logger.error(f"Error processing questionnaire submission for campaign {campaign_id}: {e}")
            return {
                "success": False,
                "error": f"Error processing questionnaire: {str(e)}"
            }

    async def _generate_mock_interview_transcript(self, questionnaire_data: Dict[str, Any]) -> str:
        """Generate a mock interview transcript from questionnaire data"""
        try:
            # Extract key information for transcript generation
            contact_info = questionnaire_data.get("contactInfo", {})
            full_name = contact_info.get("fullName", "Guest")
            
            professional_bio = questionnaire_data.get("professionalBio", {})
            about_work = professional_bio.get("aboutWork", "")
            
            stories = questionnaire_data.get("stories", [])
            achievements = questionnaire_data.get("achievements", [])
            
            # Create a structured prompt for transcript generation
            prompt = f"""Generate a natural podcast interview transcript based on this questionnaire data:

Guest Name: {full_name}
Professional Background: {about_work}

Stories Shared: {len(stories)}
Key Achievements: {len(achievements)}

Create a realistic 5-7 minute interview transcript that naturally incorporates the guest's information.
Include both interviewer questions and guest responses.
Make it conversational and engaging."""

            response = await self.gemini_service.create_message(
                prompt=prompt,
                model="gemini-2.0-flash",
                workflow="questionnaire_mock_interview"
            )
            
            if response:
                return response.strip()
            else:
                # Fallback to basic transcript
                return f"Interview transcript with {full_name} discussing their expertise and achievements."
                
        except Exception as e:
            logger.error(f"Error generating mock interview transcript: {e}")
            # Return a minimal transcript so processing can continue
            return "Mock interview transcript could not be generated from questionnaire data."

    async def process_questionnaire_with_social_enrichment(
        self, 
        campaign_id: str, 
        questionnaire_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enhanced questionnaire processing that includes social media enrichment
        
        Args:
            campaign_id: Campaign ID
            questionnaire_data: Complete questionnaire response
            
        Returns:
            Dict with processing results including social media insights
        """
        try:
            logger.info(f"Processing questionnaire with social enrichment for campaign {campaign_id}")
            
            # 1. Process the basic questionnaire (existing functionality)
            basic_result = await self.process_campaign_questionnaire_submission(campaign_id, questionnaire_data)
            
            # 2. Process social media data
            client_social_profile = await self.social_processor.process_questionnaire_social_data(
                questionnaire_data, campaign_id
            )
            
            # 3. Extract ideal podcast description for vetting
            ideal_podcast_description = self.social_processor.extract_ideal_podcast_description(questionnaire_data)
            
            # 4. Update campaign with social data and ideal podcast description
            await self._update_campaign_with_enriched_data(
                campaign_id, 
                client_social_profile, 
                ideal_podcast_description
            )
            
            # 5. Return comprehensive results
            return {
                "success": True,
                "basic_processing": basic_result,
                "social_profile": {
                    "handles": [
                        {
                            "platform": handle.platform,
                            "handle": handle.handle,
                            "url": handle.url
                        } for handle in client_social_profile.handles
                    ],
                    "bio_summary": client_social_profile.bio_summary,
                    "expertise_topics": client_social_profile.expertise_topics,
                    "key_messages": client_social_profile.key_messages,
                    "content_themes": client_social_profile.content_themes,
                    "engagement_style": client_social_profile.engagement_style
                },
                "ideal_podcast_description": ideal_podcast_description,
                "campaign_id": campaign_id
            }
            
        except Exception as e:
            logger.error(f"Error in enhanced questionnaire processing for campaign {campaign_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "campaign_id": campaign_id
            }

    async def _update_campaign_with_enriched_data(
        self, 
        campaign_id: str, 
        social_profile, 
        ideal_podcast_description: str
    ) -> bool:
        """Update campaign with enriched social media data and ideal podcast description"""
        try:
            # Prepare update data
            update_data = {
                "ideal_podcast_description": ideal_podcast_description
            }
            
            # Add social media data to questionnaire_responses
            # This preserves the original questionnaire data while adding enrichment
            existing_campaign = await campaign_queries.get_campaign_by_id(uuid.UUID(campaign_id))
            if existing_campaign:
                existing_responses = existing_campaign.get('questionnaire_responses', {})
                
                # Add social enrichment data
                existing_responses['social_enrichment'] = {
                    'bio_summary': social_profile.bio_summary,
                    'expertise_topics': social_profile.expertise_topics,
                    'key_messages': social_profile.key_messages,
                    'content_themes': social_profile.content_themes,
                    'engagement_style': social_profile.engagement_style,
                    'social_handles': [
                        {
                            'platform': handle.platform,
                            'handle': handle.handle,
                            'url': handle.url
                        } for handle in social_profile.handles
                    ],
                    'processed_at': datetime.now(timezone.utc).isoformat()
                }
                
                update_data['questionnaire_responses'] = existing_responses
            
            # Update the campaign
            updated_campaign = await campaign_queries.update_campaign(uuid.UUID(campaign_id), update_data)
            success = updated_campaign is not None
            
            if success:
                logger.info(f"Successfully updated campaign {campaign_id} with enriched data")
                
                # Trigger bio and angles generation if mock interview transcript exists
                if existing_campaign.get('mock_interview_transcript'):
                    angles_processor = AnglesProcessorPG()
                    try:
                        logger.info(f"Triggering bio/angles generation for campaign {campaign_id} after questionnaire submission")
                        bio_result = await angles_processor.process_campaign(campaign_id)
                        bio_status = bio_result.get("status", "error")
                        if bio_status == "success":
                            logger.info(f"Successfully generated bio/angles for campaign {campaign_id}")
                        else:
                            logger.warning(f"Bio generation returned status: {bio_status} for campaign {campaign_id}")
                    except Exception as bio_error:
                        logger.error(f"Error generating bio/angles for campaign {campaign_id}: {bio_error}")
                        # Don't fail the questionnaire processing if bio generation fails
                    finally:
                        angles_processor.cleanup()
                
                # Trigger auto-discovery if enabled for this campaign
                if ideal_podcast_description and existing_campaign.get('auto_discovery_enabled', True):
                    try:
                        from podcast_outreach.services.tasks.manager import task_manager
                        import time
                        
                        task_id = f"auto_discovery_ready_{campaign_id}_{int(time.time())}"
                        task_manager.start_task(task_id, "campaign_ready_auto_discovery")
                        task_manager.run_single_campaign_auto_discovery(task_id, campaign_id)
                        
                        logger.info(f"Triggered auto-discovery for campaign {campaign_id} after questionnaire completion")
                    except Exception as e:
                        logger.error(f"Failed to trigger auto-discovery for campaign {campaign_id}: {e}")
                        # Don't fail the questionnaire processing if auto-discovery fails
            else:
                logger.error(f"Failed to update campaign {campaign_id} with enriched data")
                
            return success
            
        except Exception as e:
            logger.error(f"Error updating campaign {campaign_id} with enriched data: {e}")
            return False


# Create singleton instance for backwards compatibility
questionnaire_processor = QuestionnaireProcessor()

# Standalone function that matches the expected interface for the API router
async def process_campaign_questionnaire_submission(
    campaign_id: uuid.UUID, 
    questionnaire_data: Dict[str, Any]
) -> bool:
    """
    Standalone function wrapper for processing questionnaire submissions.
    Returns True if successful, False otherwise.
    This matches the interface expected by the campaigns API router.
    """
    try:
        result = await questionnaire_processor.process_campaign_questionnaire_submission(campaign_id, questionnaire_data)
        return result.get("success", False)
    except Exception as e:
        logger.error(f"Error in standalone process_campaign_questionnaire_submission: {e}")
        return False

# Standalone function that matches the expected interface for other modules
def construct_mock_interview_from_questionnaire(questionnaire_data: Dict[str, Any]) -> str:
    """
    DEPRECATED: Mock interviews are no longer used. Bio generation now uses questionnaire data directly.
    This function is kept for backward compatibility but returns a deprecation notice.
    """
    logger.warning("construct_mock_interview_from_questionnaire is deprecated. Bio generation now uses questionnaire data directly.")
    return "Bio and angles will be generated directly from questionnaire data."