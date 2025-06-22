# podcast_outreach/services/media_kits/generator.py
import logging
import uuid
import re
import json
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from podcast_outreach.database.queries import media_kits as media_kit_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.integrations.google_docs import GoogleDocsService
from podcast_outreach.logging_config import get_logger
from podcast_outreach.utils.data_processor import extract_document_id

# LLM Service
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService

logger = get_logger(__name__)

def generate_slug(text: str) -> str:
    """Generate URL-friendly slug from text."""
    # Convert to lowercase, replace spaces with hyphens, remove non-alphanumeric characters
    slug = re.sub(r'[^a-zA-Z0-9\s-]', '', text.lower())
    slug = re.sub(r'\s+', '-', slug)
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug

class MediaKitService:
    """Enhanced Media Kit generation service using LLM for comprehensive content creation."""
    
    def __init__(self):
        self.gemini_service = GeminiService()  # Using enhanced Gemini 2.0-flash
        self.social_discovery_service = SocialDiscoveryService()
        self.google_docs_service = GoogleDocsService()

    def _is_gdoc_link(self, text: Optional[str]) -> bool:
        """Checks if the provided text is a Google Doc link."""
        return text and isinstance(text, str) and text.startswith("https://docs.google.com/document/d/")

    def _extract_questionnaire_content(self, questionnaire_data: Dict[str, Any]) -> str:
        """Extract and format questionnaire content for LLM processing."""
        content_parts = []
        
        # Helper function to extract text from various data types
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
        
        # Extract contact and basic info
        contact_info = []
        for field in ["full_name", "email", "phone", "company", "title", "website"]:
            if field in questionnaire_data:
                value = extract_text(questionnaire_data[field])
                if value:
                    content_parts.append(f"{field.replace('_', ' ').title()}: {value}")
        
        # Extract professional background
        for field in ["professional_bio", "background", "expertise", "experience", "credentials"]:
            if field in questionnaire_data:
                value = extract_text(questionnaire_data[field])
                if value:
                    content_parts.append(f"{field.replace('_', ' ').title()}: {value}")
        
        # Extract topics and expertise
        for field in ["suggested_topics", "areas_of_expertise", "specialties", "topics"]:
            if field in questionnaire_data:
                value = extract_text(questionnaire_data[field])
                if value:
                    content_parts.append(f"{field.replace('_', ' ').title()}: {value}")
        
        # Extract social proof and achievements
        for field in ["achievements", "awards", "certifications", "testimonials", "media_appearances"]:
            if field in questionnaire_data:
                value = extract_text(questionnaire_data[field])
                if value:
                    content_parts.append(f"{field.replace('_', ' ').title()}: {value}")
        
        # Extract promotion and preferences
        for field in ["promotion_preferences", "booking_preferences", "interview_style", "availability"]:
            if field in questionnaire_data:
                value = extract_text(questionnaire_data[field])
                if value:
                    content_parts.append(f"{field.replace('_', ' ').title()}: {value}")
        
        # Extract any remaining fields
        for key, value in questionnaire_data.items():
            if key not in ["full_name", "email", "phone", "company", "title", "website", 
                          "professional_bio", "background", "expertise", "experience", "credentials",
                          "suggested_topics", "areas_of_expertise", "specialties", "topics",
                          "achievements", "awards", "certifications", "testimonials", "media_appearances",
                          "promotion_preferences", "booking_preferences", "interview_style", "availability"]:
                text_value = extract_text(value)
                if text_value:
                    content_parts.append(f"{key.replace('_', ' ').title()}: {text_value}")
        
        return "\n".join(content_parts)

    async def _generate_keywords(self, questionnaire_content: str, campaign_id: uuid.UUID) -> List[str]:
        """Generate 20 relevant keywords from questionnaire data using LLM."""
        try:
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

Please respond with exactly 20 keywords separated by commas. Provide only the comma-separated keywords, with no numbering, asterisks, or any other introductory/concluding text.
"""
            response = await self.gemini_service.create_message(
                prompt,
                workflow="media_kit_keywords",
                related_campaign_id=campaign_id
            )
            if response:
                # Parse keywords from response
                keywords = [k.strip() for k in response.split(',') if k.strip()]
                # Ensure we have exactly 20 keywords
                if len(keywords) > 20:
                    keywords = keywords[:20]
                elif len(keywords) < 20:
                    # Pad with general terms if needed
                    while len(keywords) < 20:
                        keywords.append(f"expert-{len(keywords)+1}")
                
                logger.info(f"Generated {len(keywords)} keywords for campaign {campaign_id}")
                return keywords
            else:
                logger.warning(f"Empty response from LLM for keywords generation for campaign {campaign_id}")
                return ["expert", "speaker", "thought-leader", "professional", "industry-expert"] * 4  # Fallback

        except Exception as e:
            logger.error(f"Error generating keywords for campaign {campaign_id}: {e}")
            return ["expert", "speaker", "thought-leader", "professional", "industry-expert"] * 4  # Fallback

    async def _generate_tagline(self, questionnaire_content: str, campaign_id: uuid.UUID) -> str:
        """Generate a compelling tagline using LLM."""
        try:
            prompt = f"""
Based on the following client questionnaire data, create a compelling, professional tagline for their media kit. The tagline should be:
- Concise (5-10 words)
- Highlight their unique expertise
- Be memorable and professional
- Suitable for podcast introductions

Questionnaire Data:
{questionnaire_content}

Please respond with just the tagline, no additional text, and no asterisks or markdown.
"""
            response = await self.gemini_service.create_message(
                prompt,
                workflow="media_kit_tagline",
                related_campaign_id=campaign_id
            )
            if response:
                tagline = response.strip().strip('"\'')
                logger.info(f"Generated tagline for campaign {campaign_id}: {tagline}")
                return tagline
            else:
                logger.warning(f"Empty response from LLM for tagline generation for campaign {campaign_id}")
                return "Expert Podcast Guest"

        except Exception as e:
            logger.error(f"Error generating tagline for campaign {campaign_id}: {e}")
            return "Expert Podcast Guest"

    async def _generate_comprehensive_bio(self, questionnaire_content: str, campaign_id: uuid.UUID) -> Dict[str, str]:
        """Generate comprehensive bio sections using LLM."""
        try:
            prompt = f"""
Based on the following client questionnaire data, create two versions of their professional bio for podcast media kits:

1. LONG BIO (150-250 words): Comprehensive, detailed bio suitable for detailed show notes
2. SHORT BIO (50-75 words): Concise version for quick introductions

Guidelines:
- Write in third person
- Include key credentials, expertise, and achievements
- Make it podcast-friendly and engaging
- Focus on what makes them valuable to audiences
- Include specific accomplishments when available

Questionnaire Data:
{questionnaire_content}

Please format your response *only* as:
LONG BIO:
[The full long bio content here]

SHORT BIO:
[The full short bio content here]

Ensure no other text, conversation, or markdown (like asterisks) is included beyond this strict format.
"""
            response = await self.gemini_service.create_message(
                prompt,
                workflow="media_kit_bio",
                related_campaign_id=campaign_id
            )
            if response:
                bio_sections = self._parse_bio_response(response)
                logger.info(f"Generated bio sections for campaign {campaign_id}")
                return bio_sections
            else:
                logger.warning(f"Empty response from LLM for bio generation for campaign {campaign_id}")
                return {
                    "long_bio": "Professional bio coming soon.",
                    "short_bio": "Expert guest."
                }

        except Exception as e:
            logger.error(f"Error generating bio for campaign {campaign_id}: {e}")
            return {
                "long_bio": "Professional bio coming soon.",
                "short_bio": "Expert guest."
            }

    def _parse_bio_response(self, response: str) -> Dict[str, str]:
        """Parse LLM response to extract bio sections."""
        try:
            # Look for LONG BIO and SHORT BIO sections
            long_bio_match = re.search(r'LONG BIO:\s*(.*?)(?=SHORT BIO:|$)', response, re.DOTALL | re.IGNORECASE)
            short_bio_match = re.search(r'SHORT BIO:\s*(.*?)$', response, re.DOTALL | re.IGNORECASE)
            
            long_bio = long_bio_match.group(1).strip() if long_bio_match else ""
            short_bio = short_bio_match.group(1).strip() if short_bio_match else ""
            
            # Clean up any formatting artifacts
            long_bio = re.sub(r'\n+', ' ', long_bio).strip()
            short_bio = re.sub(r'\n+', ' ', short_bio).strip()
            
            # Fallback if sections not found
            if not long_bio or not short_bio:
                # Try to split by common separators
                parts = response.split('\n\n')
                if len(parts) >= 2:
                    long_bio = parts[0].strip()
                    short_bio = parts[1].strip()
                else:
                    long_bio = response.strip()
                    short_bio = response[:200] + "..." if len(response) > 200 else response.strip()
            
            return {
                "long_bio": long_bio or "Professional bio coming soon.",
                "short_bio": short_bio or "Expert guest."
            }
        except Exception as e:
            logger.error(f"Error parsing bio response: {e}")
            return {
                "long_bio": "Professional bio coming soon.",
                "short_bio": "Expert guest."
            }

    async def _generate_talking_points(self, questionnaire_content: str, campaign_id: uuid.UUID) -> List[Dict[str, str]]:
        """Generate suggested talking points and topics using LLM."""
        try:
            prompt = f"""
Based on the following client questionnaire data, create 5-7 compelling talking points/topics for podcast appearances. Each topic should be:
- Specific and actionable
- Valuable to podcast audiences
- Based on their actual expertise
- Include a brief description of what they can discuss

Questionnaire Data:
{questionnaire_content}

Please format each topic *only* as:
TOPIC: [Title of the topic]
DESCRIPTION: [2-3 sentence description of what they can discuss]

Repeat this block for each of the 5-7 talking points. Do not include any introductory/concluding remarks, conversational text, or any formatting like asterisks or bullet points not explicitly shown in the TOPIC/DESCRIPTION structure. Provide only the structured talking points.
Example of the raw output expected (without any extra text before or after this structure):
TOPIC: Building Remote Teams That Actually Work
DESCRIPTION: Strategies for creating cohesive remote teams, overcoming common communication challenges, and maintaining company culture across distributed workforces.
TOPIC: Another Example Topic
DESCRIPTION: Further details on this second topic.
"""
            response = await self.gemini_service.create_message(
                prompt,
                workflow="media_kit_talking_points",
                related_campaign_id=campaign_id
            )
            if response:
                talking_points = self._parse_talking_points_response(response)
                logger.info(f"Generated {len(talking_points)} talking points for campaign {campaign_id}")
                return talking_points
            else:
                logger.warning(f"Empty response from LLM for talking points generation for campaign {campaign_id}")
                return []

        except Exception as e:
            logger.error(f"Error generating talking points for campaign {campaign_id}: {e}")
            return []

    def _parse_talking_points_response(self, response: str) -> List[Dict[str, str]]:
        """Parse LLM response to extract talking points."""
        try:
            talking_points = []
            
            # Split by TOPIC: markers
            sections = re.split(r'TOPIC:', response, flags=re.IGNORECASE)
            
            for section in sections[1:]:  # Skip first empty section
                # Extract title and description
                lines = section.strip().split('\n')
                if lines:
                    title = lines[0].strip()
                    
                    # Look for DESCRIPTION: marker
                    description_match = re.search(r'DESCRIPTION:\s*(.*?)(?=TOPIC:|$)', section, re.DOTALL | re.IGNORECASE)
                    description = description_match.group(1).strip() if description_match else ""
                    
                    # Clean up
                    title = re.sub(r'^[-•*]\s*', '', title).strip()
                    description = re.sub(r'\n+', ' ', description).strip()
                    
                    if title:
                        talking_points.append({
                            "title": title,
                            "description": description or "Expert insights and actionable advice."
                        })
            
            # If parsing failed, try alternative approach
            if not talking_points:
                lines = response.split('\n')
                current_topic = {}
                
                for line in lines:
                    line = line.strip()
                    if line.lower().startswith('topic:'):
                        if current_topic.get('title'):
                            talking_points.append(current_topic)
                        current_topic = {"title": line[6:].strip(), "description": ""}
                    elif line.lower().startswith('description:'):
                        if current_topic:
                            current_topic["description"] = line[12:].strip()
                    elif line and current_topic.get('title') and not current_topic.get('description'):
                        current_topic["description"] = line
                
                if current_topic.get('title'):
                    talking_points.append(current_topic)
            
            return talking_points[:7]  # Limit to 7 topics
            
        except Exception as e:
            logger.error(f"Error parsing talking points response: {e}")
            return []

    async def _generate_sample_questions(self, questionnaire_content: str, campaign_id: uuid.UUID) -> List[str]:
        """Generate sample interview questions using LLM."""
        try:
            prompt = f"""
Based on the following client questionnaire data, create 10-15 engaging interview questions that podcast hosts can use. The questions should:
- Be open-ended and conversation-friendly
- Draw out their expertise and stories
- Be engaging for audiences
- Cover different aspects of their knowledge
- Include both professional and personal angle questions

Questionnaire Data:
{questionnaire_content}

Please provide only the questions, one per line. Do not include numbering, bullet points, asterisks, or any introductory/concluding text.
"""
            response = await self.gemini_service.create_message(
                prompt,
                workflow="media_kit_sample_questions",
                related_campaign_id=campaign_id
            )
            if response:
                questions = [q.strip() for q in response.split('\n') if q.strip()]
                # Clean up numbering if present
                questions = [re.sub(r'^\d+\.\s*', '', q) for q in questions]
                questions = [q for q in questions if q and len(q) > 10]  # Filter out short/empty questions
                
                logger.info(f"Generated {len(questions)} sample questions for campaign {campaign_id}")
                return questions[:15]  # Limit to 15 questions
            else:
                logger.warning(f"Empty response from LLM for sample questions generation for campaign {campaign_id}")
                return []

        except Exception as e:
            logger.error(f"Error generating sample questions for campaign {campaign_id}: {e}")
            return []

    async def _process_media_appearances(self, questionnaire_content: str, questionnaire_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Process and format media appearances from questionnaire data, prioritizing nested structures."""
        appearances = []
        processed_urls = set() # To avoid duplicate entries based on URL

        # Priority 1: Check for specific nested structure "mediaExperience.previousAppearances"
        media_experience = questionnaire_data.get("mediaExperience")
        if isinstance(media_experience, dict):
            previous_appearances_list = media_experience.get("previousAppearances")
            if isinstance(previous_appearances_list, list):
                for item in previous_appearances_list:
                    if isinstance(item, dict):
                        url = item.get("link") or item.get("url", "")
                        if url and url in processed_urls:
                            continue # Skip duplicate by URL
                        
                        appearances.append({
                            "title": item.get("podcastName") or item.get("showName") or item.get("title", "Media Appearance"), # Added showName
                            "outlet": item.get("outlet") or item.get("podcastName") or item.get("showName", "Unknown Outlet"), # Use podcastName/showName as outlet
                            "url": url,
                            "date": item.get("date", ""),
                            "description": item.get("topicDiscussed") or item.get("description", ""),
                            "type": "previous_appearance" # Add type
                        })
                        if url: 
                            processed_urls.add(url)
            
            # Process "speakingClips" from mediaExperience similarly
            speaking_clips_list = media_experience.get("speakingClips")
            if isinstance(speaking_clips_list, list):
                for item in speaking_clips_list:
                    if isinstance(item, dict):
                        url = item.get("link") or item.get("url", "")
                        # Decide if speaking clips and appearances share URL space for uniqueness check:
                        # if url and url in processed_urls: continue
                        
                        appearances.append({
                            "title": item.get("title", "Speaking Clip"),
                            "url": url,
                            "description": item.get("description", ""), # Clips might have simpler structure
                            "type": "speaking_clip" # Add type
                        })
                        # if url: processed_urls.add(url) # Add to processed_urls if they are unique by URL

        # Fallback or additional source: Check for root-level general media fields
        # Only if no appearances were found via the specific mediaExperience structure, to avoid duplicates from less specific fields.
        if not appearances:
            media_fields_fallback = ["media_appearances", "previous_interviews", "podcast_appearances"]
            for field in media_fields_fallback:
                if field in questionnaire_data:
                    value = questionnaire_data[field]
                    if isinstance(value, list):
                        for item in value:
                            url = ""
                            if isinstance(item, dict):
                                url = item.get("url", "")
                                if url and url in processed_urls: continue
                                appearances.append({
                                    "title": item.get("title", "Media Appearance"),
                                    "outlet": item.get("outlet", "Unknown Outlet"),
                                    "url": url,
                                    "date": item.get("date", ""),
                                    "description": item.get("description", "")
                                })
                            elif isinstance(item, str) and item.strip():
                                # For simple strings, URL is unknown, so duplication check is harder here unless item itself is a URL
                                appearances.append({
                                    "title": "Media Appearance", "outlet": item.strip(),
                                    "url": "", "date": "", "description": ""
                                })
                            if url: processed_urls.add(url)
                            
                    elif isinstance(value, str) and value.strip():
                        lines = value.split('\n')
                        for line in lines:
                            if line.strip():
                                appearances.append({
                                    "title": "Media Appearance", "outlet": line.strip(),
                                    "url": "", "date": "", "description": ""
                                })
        
        logger.info(f"Processed {len(appearances)} media appearances")
        return appearances[:10]  # Limit to 10 appearances

    async def _generate_testimonials_section(self, questionnaire_content: str, questionnaire_data: Dict[str, Any], campaign_id: uuid.UUID) -> str:
        """Generate testimonials and social proof section using LLM."""
        try:
            # Extract any existing testimonials from questionnaire
            existing_testimonials = []
            testimonial_fields = ["testimonials", "reviews", "recommendations", "social_proof"]
            
            for field in testimonial_fields:
                if field in questionnaire_data:
                    value = questionnaire_data[field]
                    if isinstance(value, list):
                        existing_testimonials.extend([str(t) for t in value if t])
                    elif isinstance(value, str) and value.strip():
                        existing_testimonials.append(value.strip())
            
            if existing_testimonials:
                testimonials_text = "\n".join(existing_testimonials)
                prompt = f"""
Based on the following client questionnaire data and existing testimonials, create a compelling testimonials/social proof section for their media kit.

If there are existing testimonials, format them professionally. If there are no testimonials, create a social proof section highlighting their credentials, achievements, and authority in their field.

Questionnaire Data:
{questionnaire_content}

Existing Testimonials:
{testimonials_text}

Provide *only* the final, well-formatted testimonials/social proof section content below, with no introductory phrases, concluding remarks, or conversational text. Do not use asterisks for emphasis unless it's part of a direct quote from a testimonial.
"""
            else:
                prompt = f"""
Based on the following client questionnaire data, create a compelling social proof section for their media kit. Since there are no existing testimonials, focus on:
- Their credentials and qualifications
- Notable achievements or recognition
- Professional authority indicators
- Industry standing or reputation markers

Questionnaire Data:
{questionnaire_content}

Provide *only* the final, professional social proof section content below, with no introductory phrases, concluding remarks, or conversational text. Do not use asterisks for emphasis.
"""
            
            response = await self.gemini_service.create_message(
                prompt,
                workflow="media_kit_testimonials",
                related_campaign_id=campaign_id
            )
            if response:
                testimonials_section = response.strip()
                logger.info(f"Generated testimonials section for campaign {campaign_id}")
                return testimonials_section
            else:
                logger.warning(f"Empty response from LLM for testimonials generation for campaign {campaign_id}")
                return "Experienced professional with proven expertise in their field."

        except Exception as e:
            logger.error(f"Error generating testimonials section for campaign {campaign_id}: {e}")
            return "Experienced professional with proven expertise in their field."

    async def _format_contact_information(self, questionnaire_data: Dict[str, Any]) -> Dict[str, str]:
        """Format contact information for booking, looking into nested structures."""
        contact_info_out = {}
        if not isinstance(questionnaire_data, dict):
            return contact_info_out

        # From contactInfo section
        ci = questionnaire_data.get("contactInfo", {})
        if isinstance(ci, dict):
            if ci.get("email"): contact_info_out["booking_email"] = ci["email"]
            if ci.get("phone"): contact_info_out["phone"] = ci["phone"]
            if ci.get("website"): contact_info_out["website"] = ci["website"]
            if ci.get("socialMedia") and isinstance(ci["socialMedia"], list):
                contact_info_out["social_media_links"] = ci["socialMedia"]

        # From promotionPrefs section
        pp = questionnaire_data.get("promotionPrefs", {})
        if isinstance(pp, dict):
            if pp.get("bestContactForHosts"): # If no booking_email yet, use this as a fallback or primary
                if "booking_email" not in contact_info_out or not contact_info_out["booking_email"]:
                    contact_info_out["booking_email_alt"] = pp["bestContactForHosts"]
                elif pp["bestContactForHosts"] != contact_info_out.get("booking_email"): # Avoid duplication if same as main email
                    contact_info_out["preferred_contact_for_hosts"] = pp["bestContactForHosts"]
        
        # Fallback for general email if specific booking email not found
        if "booking_email" not in contact_info_out and questionnaire_data.get("email"): # Top-level email
             contact_info_out["booking_email"] = questionnaire_data["email"]

        # Separate social links from other contact info
        person_social_links_list = contact_info_out.pop("social_media_links", [])
        booking_contacts_dict = {k: v for k, v in contact_info_out.items()} # Remaining items are booking contacts

        logger.info(f"Formatted contact information. Booking contacts: {booking_contacts_dict}, Social links: {person_social_links_list}")
        return {"booking_contacts": booking_contacts_dict, "person_social_links": person_social_links_list}

    async def _generate_introduction(self, bio_content: str, campaign_id: uuid.UUID) -> str:
        """Generate a compelling introduction (1-2 sentences) based on bio content."""
        if not bio_content.strip():
            return ""
        try:
            prompt = f"""
            Based on the following professional bio content, write a concise and engaging introduction (1-2 sentences, maximum 50 words) suitable for a media kit. This introduction should quickly highlight the person's core identity and expertise.

            Bio Content:
            {bio_content[:1500]} # Use a portion of bio to avoid overly long prompts

            Please respond with just the introduction text, no other conversational text or markdown.
            """
            response = await self.gemini_service.create_message(
                prompt,
                workflow="media_kit_introduction",
                related_campaign_id=campaign_id
            )
            return response.strip() if response else ""
        except Exception as e:
            logger.error(f"Error generating introduction for campaign {campaign_id}: {e}")
            return ""

    async def _generate_key_achievements(self, questionnaire_responses: Dict[str, Any], bio_content: str, campaign_id: uuid.UUID) -> List[str]:
        """Extract or generate a list of key achievements."""
        achievements = []
        # Try to get from questionnaire first
        if isinstance(questionnaire_responses.get("professionalBio"), dict):
            pb = questionnaire_responses["professionalBio"]
            raw_achievements = pb.get("achievements")
            if isinstance(raw_achievements, str) and raw_achievements.strip():
                # Split by common delimiters if it's a string list
                achievements = [a.strip() for a in re.split(r'\n|;|,|•', raw_achievements) if a.strip()]
            elif isinstance(raw_achievements, list):
                achievements = [str(a).strip() for a in raw_achievements if str(a).strip()]

        if achievements:
            logger.info(f"Extracted {len(achievements)} key achievements from questionnaire for campaign {campaign_id}.")
            return achievements[:5] # Limit to 5

        # If not in questionnaire or not parsable, try LLM from bio_content
        logger.info(f"Key achievements not found or not parsable from questionnaire, attempting LLM extraction from bio for campaign {campaign_id}.")
        if not bio_content.strip():
            return []
        try:
            prompt = f"""
            Based on the following professional bio content, identify and list up to 5 key achievements or accomplishments. Each achievement should be a concise phrase or sentence.

            Bio Content:
            {bio_content[:2000]} # Use a portion of bio to avoid overly long prompts

            Please respond *only* with a comma-separated list of these achievements (e.g., Achievement one,Achievement two). If no specific achievements are found, respond with an empty string. Do not include any introductory text, numbering, or asterisks.
            """
            response = await self.gemini_service.create_message(
                prompt,
                workflow="media_kit_key_achievements",
                related_campaign_id=campaign_id
            )
            if response and response.strip(): # Check if response is not None and not empty after stripping
                achievements = [a.strip() for a in response.split(',') if a.strip()]
                logger.info(f"LLM extracted {len(achievements)} key achievements for campaign {campaign_id}.")
                return achievements[:5] # Limit to 5
            logger.info(f"LLM did not return any key achievements or returned an empty string for campaign {campaign_id}.")
            return []
        except Exception as e:
            logger.error(f"Error generating key_achievements with LLM for campaign {campaign_id}: {e}")
            return []

    async def _generate_short_bio_from_long(self, long_bio: str, campaign_id: uuid.UUID, target_words: int = 60) -> str:
        """Generate a short bio summary from a long bio using LLM."""
        if not long_bio.strip():
            return "A professional in their field."
        try:
            prompt = f"""
            Based on the following long professional bio, create a concise SHORT BIO (around {target_words} words) suitable for quick introductions or social media.

            LONG BIO:
            {long_bio}

            Please respond with just the SHORT BIO, no additional text, and no asterisks or markdown.
            """
            response = await self.gemini_service.create_message(
                prompt,
                workflow="media_kit_short_bio_from_long",
                related_campaign_id=campaign_id
            )
            if response:
                short_bio = response.strip().strip('"\'')
                logger.info(f"Generated short bio from long bio for campaign {campaign_id}")
                return short_bio
            else:
                logger.warning(f"Empty response from LLM for short bio generation for campaign {campaign_id}")
                return long_bio[:250] + "..." # Fallback to truncated long bio
        except Exception as e:
            logger.error(f"Error generating short bio from long for campaign {campaign_id}: {e}")
            return long_bio[:250] + "..." # Fallback

    async def create_or_update_media_kit(
        self,
        campaign_id: uuid.UUID,
        editable_content: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Generate or update a comprehensive media kit using LLM."""
        if editable_content is None:
            editable_content = {}

        logger.info(f"Creating/updating LLM-powered media kit for campaign {campaign_id}")

        # Get campaign and person data
        campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found for media kit generation.")
            return None
        
        person_id = campaign.get("person_id")
        if not person_id:
            logger.error(f"Person ID not found for campaign {campaign_id}.")
            return None
        
        person = await people_queries.get_person_by_id_from_db(person_id)
        if not person:
            logger.error(f"Person {person_id} not found for media kit generation.")
            return None

        # Extract questionnaire data
        questionnaire_responses = campaign.get("questionnaire_responses", {})
        if isinstance(questionnaire_responses, str):
            try:
                questionnaire_responses = json.loads(questionnaire_responses)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse questionnaire responses for campaign {campaign_id}")
                questionnaire_responses = {}
        
        # <<< TEMP LOGGING START >>>
        logger.info(f"MEDIA_KIT_SVC: Questionnaire responses for campaign {campaign_id} (type: {type(questionnaire_responses)}): {json.dumps(questionnaire_responses, indent=2)}")
        # <<< TEMP LOGGING END >>>

        if not questionnaire_responses:
            logger.warning(f"No questionnaire responses found for campaign {campaign_id}")
            questionnaire_responses = {}

        # Extract all content for LLM processing
        questionnaire_content = self._extract_questionnaire_content(questionnaire_responses)
        
        # Initialize custom sections list from editable_content or as an empty list
        custom_sections_list = editable_content.get("custom_sections", [])
        if not isinstance(custom_sections_list, list):
            custom_sections_list = []

        # Helper to add unique custom sections
        def add_custom_section(title, content):
            if not any(cs.get("title") == title for cs in custom_sections_list if isinstance(cs, dict)):
                custom_sections_list.append({"title": title, "content": content})

        # Process atAGlanceStats
        at_a_glance_stats = questionnaire_responses.get("atAGlanceStats")
        if isinstance(at_a_glance_stats, dict) and at_a_glance_stats:
            add_custom_section("At a Glance Stats", at_a_glance_stats)

        # Process assets (otherAssets)
        assets_data = questionnaire_responses.get("assets")
        if isinstance(assets_data, dict):
            other_assets = assets_data.get("otherAssets")
            if isinstance(other_assets, list) and other_assets:
                add_custom_section("Other Assets", other_assets)

        # Process finalNotes
        final_notes_data = questionnaire_responses.get("finalNotes")
        if isinstance(final_notes_data, dict) and final_notes_data:
            add_custom_section("Final Notes", final_notes_data)
        
        # <<< TEMP LOGGING START >>>
        logger.info(f"MEDIA_KIT_SVC: Extracted questionnaire_content for LLM (length: {len(questionnaire_content)}):\n{questionnaire_content[:1000]}...")
        # <<< TEMP LOGGING END >>>
        
        if not questionnaire_content:
            logger.warning(f"No questionnaire content available for LLM processing for campaign {campaign_id}")
            # Still proceed with minimal content
            questionnaire_content = f"Client: {person.get('full_name', 'Unknown')}"

        logger.info(f"Processing comprehensive media kit with LLM for campaign {campaign_id}")

        # Initialize gdoc content variables
        gdoc_bio_content_str = None
        gdoc_angles_content_str = None

        # Attempt to fetch GDoc Bio content
        campaign_bio_gdoc_link = campaign.get("campaign_bio")
        if self.google_docs_service and self._is_gdoc_link(campaign_bio_gdoc_link):
            logger.info(f"Fetching GDoc bio from: {campaign_bio_gdoc_link}")
            doc_id = extract_document_id(campaign_bio_gdoc_link)
            if doc_id:
                try:
                    # Assuming get_document_content is synchronous and needs to be run in executor
                    loop = asyncio.get_running_loop()
                    gdoc_bio_content_str = await loop.run_in_executor(None, self.google_docs_service.get_document_content, doc_id)
                    if gdoc_bio_content_str:
                        logger.info(f"Successfully fetched GDoc bio content (length: {len(gdoc_bio_content_str)}).")
                    else:
                        logger.warning(f"GDoc bio content was empty for {campaign_bio_gdoc_link}.")
                except Exception as e_gdoc_bio:
                    logger.error(f"Error fetching GDoc bio content from {campaign_bio_gdoc_link}: {e_gdoc_bio}")
        
        # Generate all sections using LLM or GDoc content
        try:
            # Generate keywords (20 from questionnaire)
            keywords = await self._generate_keywords(questionnaire_content, campaign_id)
            
            # Generate cover page elements
            tagline = await self._generate_tagline(questionnaire_content, campaign_id)
            
            # Bio sections: Prioritize GDoc bio, then LLM, then fallback
            if gdoc_bio_content_str:
                # Simple split for now, assuming GDoc has sections clearly marked or is just the full bio.
                # TODO: Implement more robust parsing of GDoc bio for Full, Summary, Short sections if needed.
                bio_sections = {
                    "long_bio": gdoc_bio_content_str, 
                    "short_bio": await self._generate_short_bio_from_long(gdoc_bio_content_str, campaign_id) # Helper to create short from long
                }
                logger.info(f"Using GDoc bio for campaign {campaign_id}")
            else:
                logger.info(f"GDoc bio not available or failed to fetch, generating bio with LLM for campaign {campaign_id}")
                bio_sections = await self._generate_comprehensive_bio(questionnaire_content, campaign_id)
            
            # Generate Introduction
            # Prioritize GDoc bio content if available for the introduction source
            introduction_source_content = gdoc_bio_content_str if gdoc_bio_content_str else questionnaire_content
            introduction = await self._generate_introduction(introduction_source_content, campaign_id)

            # Generate Key Achievements
            key_achievements_list = await self._generate_key_achievements(questionnaire_responses, introduction_source_content, campaign_id)

            # Prepare focused content for talking points generation
            talking_points_input_parts = []
            if isinstance(questionnaire_responses.get("professionalBio"), dict):
                pb = questionnaire_responses["professionalBio"]
                if pb.get("aboutWork"): talking_points_input_parts.append(f"About their work: {pb["aboutWork"]}")
                if pb.get("expertiseTopics"): talking_points_input_parts.append(f"Areas of expertise: {pb["expertiseTopics"]}")
                if pb.get("achievements"): talking_points_input_parts.append(f"Key achievements: {pb["achievements"]}")
            if isinstance(questionnaire_responses.get("suggestedTopics"), dict):
                st = questionnaire_responses["suggestedTopics"]
                if st.get("topics"): talking_points_input_parts.append(f"Suggested topics by client: {st["topics"]}")
                if st.get("keyStoriesOrMessages"): talking_points_input_parts.append(f"Key stories/messages from client: {st["keyStoriesOrMessages"]}")
            
            focused_content_for_talking_points = "\n".join(talking_points_input_parts) if talking_points_input_parts else questionnaire_content

            # Generate talking points
            talking_points = await self._generate_talking_points(focused_content_for_talking_points, campaign_id)
            
            # Generate sample questions
            sample_questions = await self._generate_sample_questions(questionnaire_content, campaign_id)
            
            # Process media appearances
            media_appearances = await self._process_media_appearances(questionnaire_content, questionnaire_responses)
            
            # Generate testimonials section
            testimonials_section = await self._generate_testimonials_section(questionnaire_content, questionnaire_responses, campaign_id)
            
            # Format contact information
            contact_details_processed = await self._format_contact_information(questionnaire_responses)
            person_social_links_data = contact_details_processed.get("person_social_links", [])
            booking_contact_data = contact_details_processed.get("booking_contacts", {})
            
            # Include social_media_links from contact_information_dict into the main contact_information if not already handled
            # contact_information_for_booking is expected to be a JSON string.
            # social_media_links from questionnaire_responses.contactInfo.socialMedia is now in contact_information_dict["social_media_links"]
            # We'll ensure it's part of the JSON string saved to the DB.
            
        except Exception as e:
            logger.error(f"Error during LLM processing for campaign {campaign_id}: {e}")
            # Fallback to basic content
            keywords = ["expert", "speaker", "professional"] * 7
            tagline = "Expert Podcast Guest"
            bio_sections = {"long_bio": "Professional bio coming soon.", "short_bio": "Expert guest."}
            introduction = "An accomplished professional available for interviews." # Fallback for introduction
            key_achievements_list = [] # Fallback for key_achievements
            talking_points = []
            sample_questions = []
            media_appearances = []
            testimonials_section = "Experienced podcast guest."
            person_social_links_data = [] # Fallback
            booking_contact_data = {} # Fallback

        # Build the complete media kit data
        kit_data = {
            "campaign_id": campaign_id,
            "person_id": person_id,
            "title": editable_content.get("title") or f"Media Kit - {person.get('full_name', 'Client')}",
            
            "headline": tagline,
            "tagline": tagline,
            
            "introduction": introduction, 
            
            "full_bio_content": bio_sections["long_bio"],
            "summary_bio_content": bio_sections.get("short_bio"),
            "short_bio_content": bio_sections.get("short_bio"),
            "bio_source": "gdoc" if gdoc_bio_content_str else "llm_questionnaire",
            
            "keywords": keywords,
            
            "talking_points": talking_points,
            "angles_source": "llm_questionnaire",
            
            "sample_questions": sample_questions,
            
            "previous_appearances": media_appearances,
            
            "testimonials_section": testimonials_section,

            "person_social_links": person_social_links_data, # Populate new field
            "contact_information_for_booking": json.dumps(booking_contact_data) if booking_contact_data else None, 
            
            "key_achievements": key_achievements_list,
            "social_media_stats": editable_content.get("social_media_stats", {}),
            "headshot_image_url": editable_content.get("headshot_image_url"), # Initialize from editable_content
            "logo_image_url": editable_content.get("logo_image_url"), # Initialize from editable_content
            "call_to_action_text": editable_content.get("call_to_action_text"),
            "custom_sections": custom_sections_list, # Use the populated list
            "is_public": editable_content.get("is_public", True),
            "theme_preference": editable_content.get("theme_preference", "modern")
        }

        # Populate headshot and logo from assets if available in questionnaire_responses
        if isinstance(assets_data, dict): # assets_data defined earlier
            if assets_data.get("headshotUrl"):
                # Set single headshot image URL
                kit_data["headshot_image_url"] = assets_data["headshotUrl"]
            
            if assets_data.get("logoUrl"):
                kit_data["logo_image_url"] = assets_data["logoUrl"] # Override or set

        # Generate slug
        base_slug_text = kit_data["title"]
        generated_slug = generate_slug(base_slug_text)
        
        existing_kit = await media_kit_queries.get_media_kit_by_campaign_id_from_db(campaign_id)
        final_slug = generated_slug
        counter = 1
        
        if existing_kit:
            final_slug = existing_kit.get("slug", generated_slug)
        else:
            # Ensure slug is unique
            while await media_kit_queries.check_slug_exists(final_slug):
                final_slug = f"{generated_slug}-{counter}"
                counter += 1
        
        kit_data["slug"] = final_slug

        # <<< TEMP LOGGING START >>>
        logger.info(f"MEDIA_KIT_SVC: Final kit_data before DB save for campaign {campaign_id}: {json.dumps(kit_data, indent=2, default=str)}") # Added default=str for datetime
        # <<< TEMP LOGGING END >>>

        # Save to database
        try:
            if existing_kit:
                logger.info(f"Updating existing media kit for campaign {campaign_id}")
                result_kit_dict = await media_kit_queries.update_media_kit_in_db(existing_kit['media_kit_id'], kit_data)
                media_kit_id_for_social_update = existing_kit['media_kit_id']
            else:
                logger.info(f"Creating new LLM-powered media kit for campaign {campaign_id}")
                result_kit_dict = await media_kit_queries.create_media_kit_in_db(kit_data)
                media_kit_id_for_social_update = result_kit_dict.get('media_kit_id') if result_kit_dict else None

            if result_kit_dict and media_kit_id_for_social_update:
                # Update social stats if not a lead magnet campaign
                if campaign.get("campaign_type") != "lead_magnet_prospect":
                    try:
                        logger.info(f"Updating social stats for media kit {media_kit_id_for_social_update}")
                        updated_kit_with_stats = await self.update_social_stats_for_media_kit(media_kit_id_for_social_update)
                        return updated_kit_with_stats if updated_kit_with_stats else result_kit_dict
                    except Exception as e_social:
                        logger.error(f"Error updating social stats for media kit {media_kit_id_for_social_update}: {e_social}")
                        return result_kit_dict
                else:
                    logger.info(f"Skipping social stats update for lead magnet campaign {campaign_id}")
                    return result_kit_dict
            else:
                logger.error(f"Failed to create/update media kit for campaign {campaign_id}")
                return None

        except Exception as e:
            logger.error(f"Database error creating/updating media kit for campaign {campaign_id}: {e}")
            return None

    async def get_media_kit_by_campaign_id(self, campaign_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        return await media_kit_queries.get_media_kit_by_campaign_id_from_db(campaign_id)

    async def get_media_kit_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        return await media_kit_queries.get_media_kit_by_slug_enriched(slug)

    async def update_social_stats_for_media_kit(self, media_kit_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Update social media stats for the media kit."""
        logger.info(f"Updating social stats for media_kit_id: {media_kit_id}")
        
        kit = await media_kit_queries.get_media_kit_by_id_from_db(media_kit_id)
        if not kit:
            logger.warning(f"Media kit {media_kit_id} not found for social stats update.")
            return None
        
        # person_id = kit.get("person_id") # No longer needed for fetching person details for social links
        # if not person_id:
        #     logger.warning(f"Person_id not found in media kit {media_kit_id}.")
        #     return kit

        # person = await people_queries.get_person_by_id_from_db(person_id) # Removed
        # if not person: # Removed
        #     logger.warning(f"Person {person_id} not found.") # Removed
        #     return kit # Removed

        # Fetch social stats from kit's person_social_links
        social_urls = {}
        person_social_links = kit.get("person_social_links", [])
        if isinstance(person_social_links, list):
            for link_info in person_social_links:
                if isinstance(link_info, dict):
                    platform = str(link_info.get("platform", "")).lower()
                    handle = link_info.get("handle") or link_info.get("url") # Prefer handle, fallback to url
                    if platform and handle:
                        # Map to expected keys if necessary, e.g., "linkedin" -> "linkedin"
                        # Add more platform mappings if the stored platform names differ from expected keys
                        if "linkedin" in platform:
                            social_urls["linkedin"] = handle
                        elif "twitter" in platform:
                            social_urls["twitter"] = handle
                        elif "instagram" in platform:
                            social_urls["instagram"] = handle
                        elif "tiktok" in platform:
                            social_urls["tiktok"] = handle
                        # Add other platforms as needed
                        # else:
                        #     social_urls[platform] = handle # Store with original platform name if no specific mapping
        
        if not social_urls:
            logger.info(f"No social URLs found in person_social_links for media kit {media_kit_id}. Using fallback from person table if desired or skipping.")
            # As per user request, we are not querying people table anymore.
            # So, if no URLs here, then no URLs.
            # We might still want to fetch from questionnaire_data as a further fallback if this is empty.
            # For now, proceeding with what's extracted.
            # If user intends to still use questionnaire_data as a fallback, that logic would be added here.

        # Fallback to questionnaire_data if person_social_links is empty or does not contain URLs.
        # This part needs to be decided: if person_social_links is the SOLE source, then we don't need this.
        # If questionnaire_data is a valid fallback, we'd need to fetch and parse it.
        # For now, assuming person_social_links is the primary source from media_kit.
        # If it's empty or doesn't yield URLs, then social_urls will be empty.
        
        # <<< REMOVE TEMPORARY HARDCODED URLS FOR TESTING >>>
        # social_urls = {
        #    "linkedin": "https://www.linkedin.com/in/maryanne-onwunuma/", # Example: replace with a popular, public profile
        #    "twitter": "https://twitter.com/elonmusk", # Example
        #    "instagram": "https://www.instagram.com/instagram/", # Example
        #    "tiktok": "https://www.tiktok.com/@tiktok" # Example
        # }
        # logger.info(f"TEMPORARY: Using hardcoded social_urls for testing: {social_urls}")
        # <<< END REMOVE TEMPORARY HARDCODED URLS FOR TESTING >>>

        # The old way of getting social_urls from person table:
        # social_urls = {
        #     "twitter": person.get("twitter_profile_url"),
        #     "linkedin": person.get("linkedin_profile_url"),
        #     "instagram": person.get("instagram_profile_url"),
        #     "tiktok": person.get("tiktok_profile_url"),
        # }

        newly_fetched_follower_stats = {}
        any_stat_fetched_this_run = False

        # LinkedIn
        linkedin_url = social_urls.get("linkedin")
        if linkedin_url:
            logger.info(f"Attempting to fetch LinkedIn stats for URL: {linkedin_url}")
            try:
                data_map = await self.social_discovery_service.get_linkedin_data_for_urls([linkedin_url])
                data = data_map.get(linkedin_url)
                if data:
                    logger.debug(f"LinkedIn data received: {data}")
                    count = data.get('followers_count')
                    # If followers_count is None or 0, consider connections_count
                    if count is None or count == 0:
                         connections = data.get('connections_count')
                         if connections is not None:
                             count = connections
                    
                    if count is not None:
                        newly_fetched_follower_stats["linkedin_followers_count"] = count
                        any_stat_fetched_this_run = True
                else:
                    logger.warning(f"No data returned from LinkedIn scraper for {linkedin_url}")
            except Exception as e:
                logger.warning(f"Error fetching LinkedIn stats for {linkedin_url}: {e}", exc_info=True)

        # Twitter
        twitter_url = social_urls.get("twitter")
        if twitter_url:
            logger.info(f"Attempting to fetch Twitter stats for URL: {twitter_url}")
            try:
                data_map = await self.social_discovery_service.get_twitter_data_for_urls([twitter_url])
                data = data_map.get(twitter_url)
                if data:
                    logger.debug(f"Twitter data received: {data}")
                    if data.get('followers_count') is not None:
                        newly_fetched_follower_stats["twitter_followers_count"] = data['followers_count']
                        any_stat_fetched_this_run = True
                else:
                    logger.warning(f"No data returned from Twitter scraper for {twitter_url}")
            except Exception as e:
                logger.warning(f"Error fetching Twitter stats for {twitter_url}: {e}", exc_info=True)

        # Instagram
        instagram_url = social_urls.get("instagram")
        if instagram_url:
            logger.info(f"Attempting to fetch Instagram stats for URL: {instagram_url}")
            try:
                data_map = await self.social_discovery_service.get_instagram_data_for_urls([instagram_url])
                data = data_map.get(instagram_url)
                if data:
                    logger.debug(f"Instagram data received: {data}")
                    if data.get('followers_count') is not None:
                        newly_fetched_follower_stats["instagram_followers_count"] = data['followers_count']
                        any_stat_fetched_this_run = True
                else:
                    logger.warning(f"No data returned from Instagram scraper for {instagram_url}")
            except Exception as e:
                logger.warning(f"Error fetching Instagram stats for {instagram_url}: {e}", exc_info=True)
        
        # TikTok
        tiktok_url = social_urls.get("tiktok")
        if tiktok_url:
            logger.info(f"Attempting to fetch TikTok stats for URL: {tiktok_url}")
            try:
                data_map = await self.social_discovery_service.get_tiktok_data_for_urls([tiktok_url])
                data = data_map.get(tiktok_url)
                if data:
                    logger.debug(f"TikTok data received: {data}")
                    if data.get('followers_count') is not None:
                        newly_fetched_follower_stats["tiktok_followers_count"] = data['followers_count']
                        any_stat_fetched_this_run = True
                else:
                    logger.warning(f"No data returned from TikTok scraper for {tiktok_url}")
            except Exception as e:
                logger.warning(f"Error fetching TikTok stats for {tiktok_url}: {e}", exc_info=True)


        if any_stat_fetched_this_run:
            current_time = datetime.now(timezone.utc).isoformat()
            newly_fetched_follower_stats["last_fetched_at"] = current_time
            logger.info(f"Consolidated social stats to update: {newly_fetched_follower_stats}")
            
            existing_stats = kit.get("social_media_stats", {})
            if isinstance(existing_stats, str):
                try:
                    existing_stats = json.loads(existing_stats)
                except json.JSONDecodeError:
                    logger.warning(f"Malformed JSON string in existing_stats for media kit {media_kit_id}, reinitializing.")
                    existing_stats = {}
            elif not isinstance(existing_stats, dict):
                 logger.warning(f"existing_stats is not a dict for media kit {media_kit_id}, reinitializing. Type: {type(existing_stats)}")
                 existing_stats = {}
            
            final_stats_to_save = {**existing_stats, **newly_fetched_follower_stats}
            
            logger.info(f"Final social_media_stats for media kit {media_kit_id}: {final_stats_to_save}")
            return await media_kit_queries.update_media_kit_in_db(media_kit_id, {"social_media_stats": final_stats_to_save})
        else:
            logger.info(f"No new social stats were successfully fetched for media kit {media_kit_id}. No update to social_media_stats.")
            return kit # Return the original kit if no new stats were fetched 