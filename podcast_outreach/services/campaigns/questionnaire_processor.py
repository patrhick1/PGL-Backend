# podcast_outreach/services/campaigns/questionnaire_processor.py
import logging
import uuid
from typing import Dict, Any, List, Optional
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.services.ai.gemini_client import GeminiService
import json # For storing as JSONB
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class QuestionnaireProcessor:
    """Enhanced questionnaire processor with LLM-powered keyword generation."""
    
    def __init__(self):
        self.gemini_service = GeminiService()  # Using enhanced Gemini 2.0-flash

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
        """Construct a basic mock interview structure from questionnaire data."""
        try:
            # Extract basic information from nested structure
            contact_info = questionnaire_data.get("contactInfo", {})
            full_name = contact_info.get("fullName", "Guest") if isinstance(contact_info, dict) else "Guest"
            
            # Get expertise from professional bio section
            professional_bio = questionnaire_data.get("professionalBio", {})
            expertise = "their field"
            if isinstance(professional_bio, dict):
                expertise_topics = professional_bio.get("expertiseTopics", "")
                if expertise_topics:
                    if isinstance(expertise_topics, list):
                        expertise = ", ".join(expertise_topics)
                    elif isinstance(expertise_topics, str):
                        expertise = expertise_topics
            
            # Create a simple mock interview structure
            mock_interview = f"""
Host: Welcome to the show! I'm here with {full_name}. Can you tell us a bit about yourself?

{full_name}: [Introduction based on professional background]

Host: That's fascinating! What drew you to {expertise}?

{full_name}: [Story about getting into their field]

Host: What are some of the biggest challenges you see in {expertise} today?

{full_name}: [Insights about industry challenges]

Host: What advice would you give to someone just starting out?

{full_name}: [Actionable advice for beginners]

Host: Where can our listeners learn more about you and your work?

{full_name}: [Contact information and call to action]
"""
            
            logger.info(f"Created simple mock interview structure for questionnaire")
            return mock_interview.strip()
            
        except Exception as e:
            logger.error(f"Error creating mock interview: {e}")
            return "Mock interview content will be generated during media kit creation."

    async def process_campaign_questionnaire_submission(
        self, campaign_id: uuid.UUID, questionnaire_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process questionnaire submission with LLM-powered keyword generation."""
        logger.info(f"Processing questionnaire submission for campaign {campaign_id}")
        
        try:
            # Generate keywords using LLM instead of hardcoded extraction
            logger.info(f"Generating keywords from questionnaire using LLM for campaign {campaign_id}")
            generated_keywords = await self._generate_keywords_from_questionnaire_llm(questionnaire_data)
            
            # Create mock interview structure
            logger.info(f"Creating mock interview structure for campaign {campaign_id}")
            mock_interview_transcript = self.construct_mock_interview_from_questionnaire(questionnaire_data)
            
            # Update campaign with questionnaire data, LLM-generated keywords, and mock interview
            update_data = {
                "questionnaire_responses": questionnaire_data,
                "questionnaire_keywords": generated_keywords,
                "mock_interview_trancript": mock_interview_transcript
            }
            
            # Update the campaign - FIXED: use correct method name
            updated_campaign = await campaign_queries.update_campaign(campaign_id, update_data)
            
            if updated_campaign:
                logger.info(f"Successfully processed questionnaire for campaign {campaign_id}")
                logger.info(f"Generated {len(generated_keywords)} keywords and mock interview transcript")
                
                # Note: Background task processing can be triggered manually via the API
                # /tasks/run/process_campaign_content?campaign_id={campaign_id}
                
                return {
                    "success": True,
                    "campaign_id": str(campaign_id),
                    "keywords_count": len(generated_keywords),
                    "has_mock_interview": bool(mock_interview_transcript),
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
    Standalone function wrapper for constructing mock interviews from questionnaire data.
    This function can be imported by other modules that need this functionality.
    """
    try:
        processor = QuestionnaireProcessor()
        return processor.construct_mock_interview_from_questionnaire(questionnaire_data)
    except Exception as e:
        logger.error(f"Error in standalone construct_mock_interview_from_questionnaire: {e}")
        return "Mock interview content will be generated during media kit creation."