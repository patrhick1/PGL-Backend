# podcast_outreach/services/chatbot/enhanced_nlp_processor_v2.py

import json
import re
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ValidationError
from podcast_outreach.logging_config import get_logger
from podcast_outreach.services.ai.gemini_client import GeminiService

logger = get_logger(__name__)

# Pydantic models matching questionnaire structure
class ContactInfo(BaseModel):
    fullName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    socialMedia: Optional[List[str]] = []

class ProfessionalInfo(BaseModel):
    aboutWork: Optional[str] = None
    expertiseTopics: Optional[List[str]] = []
    achievements: Optional[str] = None
    uniquePerspectives: Optional[str] = None
    yearsExperience: Optional[int] = None
    industry: Optional[str] = None

class Achievement(BaseModel):
    description: str
    metric: Optional[str] = None
    outcome: Optional[str] = None
    type: Optional[str] = None

class Story(BaseModel):
    subject: Optional[str] = None
    challenge: Optional[str] = None
    action: Optional[str] = None
    result: Optional[str] = None
    metrics: Optional[List[str]] = []
    keywords: Optional[List[str]] = []

class ExtractedData(BaseModel):
    contact_info: Optional[ContactInfo] = Field(default_factory=ContactInfo)
    professional_info: Optional[ProfessionalInfo] = Field(default_factory=ProfessionalInfo)
    achievements: Optional[List[Achievement]] = []
    stories: Optional[List[Story]] = []
    expertise_keywords: Optional[List[str]] = []
    topics_can_discuss: Optional[List[str]] = []
    target_audience: Optional[str] = None
    unique_value: Optional[str] = None
    media_experience: Optional[Dict[str, Any]] = {}
    sample_questions: Optional[Dict[str, str]] = {}
    social_proof: Optional[Dict[str, Any]] = {}
    promotion_preferences: Optional[Dict[str, str]] = {}

class ConversationMemory:
    def __init__(self):
        self.mentioned_names = set()
        self.mentioned_companies = set()
        self.discussed_topics = set()
        self.captured_data_points = set()
        
    def update(self, message: str, extracted_data: ExtractedData):
        """Track what we've already discussed to avoid repetition"""
        # Extract mentioned names
        name_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
        names = re.findall(name_pattern, message)
        self.mentioned_names.update(names)
        
        # Track captured data points
        if extracted_data.contact_info.fullName:
            self.captured_data_points.add("name")
        if extracted_data.contact_info.email:
            self.captured_data_points.add("email")
        if extracted_data.professional_info.aboutWork:
            self.captured_data_points.add("work_description")
        if extracted_data.expertise_keywords:
            self.captured_data_points.add("expertise")
        if extracted_data.stories:
            self.captured_data_points.add("success_story")
        if extracted_data.achievements:
            self.captured_data_points.add("achievements")
        
    def should_ask_about(self, topic: str) -> bool:
        return topic not in self.discussed_topics and topic not in self.captured_data_points

class EnhancedNLPProcessor:
    """
    Enhanced NLP processor that uses LLM for intelligent data extraction
    with Pydantic models for consistent schema validation.
    """
    
    def __init__(self):
        self.gemini_service = GeminiService()
        self.model_name = "gemini-2.0-flash"
        self.memory = ConversationMemory()
        
        # Quick extraction patterns for common data
        self.quick_patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            # Only match explicit website mentions, not email domains
            "website": r'(?:my website is |website:|visit |check out |find me at |website at |www\.|https?://)[\w.-]+\.[\w]{2,}(?:/[\w.-]*)*',
            # Only match full LinkedIn URLs
            "linkedin": r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+',
            # Only match full Twitter URLs or explicit @handles
            "twitter": r'(?:(?:https?://)?(?:www\.)?twitter\.com/[\w]+|(?:twitter:|Twitter:|my twitter is |follow me at |@)[\s]*@[\w]+)',
            "years": r'(\d+)\+?\s*years?',
            "metrics": r'\d+%|\$\d+[KMB]?|\d+\s+(?:clients|users|followers|downloads|podcasts|episodes)',
            "company": r'(?:at|with|for|founded|co-founded)\s+([A-Z][\w\s&]+?)(?:\.|,|$)'
        }
    
    async def process(self, message: str, conversation_history: List[Dict], 
                     extracted_data: Dict, existing_keywords: List[str]) -> Dict:
        """Process message with LLM-powered extraction and Pydantic validation"""
        
        # Convert existing extracted_data dict to Pydantic model
        try:
            current_data = ExtractedData(**extracted_data) if extracted_data else ExtractedData()
        except ValidationError:
            current_data = ExtractedData()
        
        # First, do quick extraction of obvious data
        quick_extracts = self._quick_extract(message)
        
        # Then use LLM for deeper understanding
        llm_extracts = await self._llm_extract(message, conversation_history[-3:])
        
        # Merge and validate extracts
        merged_data = self._merge_extracts(quick_extracts, llm_extracts, current_data)
        
        # Update conversation memory
        self.memory.update(message, merged_data)
        
        # Convert back to dict format for compatibility
        return self._to_legacy_format(merged_data)
    
    def _quick_extract(self, text: str) -> Dict:
        """Quickly extract obvious data using regex patterns"""
        extracted = {
            "contact_info": {},
            "metrics": [],
            "social_media": []
        }
        
        # Extract email
        email_match = re.search(self.quick_patterns["email"], text)
        if email_match:
            extracted["contact_info"]["email"] = email_match.group(0)
        
        # Extract website - only if explicitly mentioned
        website_match = re.search(self.quick_patterns["website"], text)
        if website_match:
            url = website_match.group(0)
            # Clean up the URL by removing the prefix phrases
            url = re.sub(r'^(my website is |website:|visit |check out |find me at |website at )', '', url, flags=re.IGNORECASE)
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            # Validate it's a real URL, not part of an email
            if '@' not in url and '.' in url:
                extracted["contact_info"]["website"] = url
        
        # Extract LinkedIn - only if full URL is provided
        linkedin_match = re.search(self.quick_patterns["linkedin"], text)
        if linkedin_match:
            linkedin_url = linkedin_match.group(0)
            if not linkedin_url.startswith(('http://', 'https://')):
                linkedin_url = 'https://' + linkedin_url
            extracted["social_media"].append(linkedin_url)
        
        # Extract Twitter - only if explicitly mentioned
        twitter_match = re.search(self.quick_patterns["twitter"], text)
        if twitter_match:
            twitter_handle = twitter_match.group(0)
            # Clean up Twitter handle
            if '@' in twitter_handle:
                # Extract just the handle
                handle_match = re.search(r'@([\w]+)', twitter_handle)
                if handle_match:
                    extracted["social_media"].append(f"https://twitter.com/{handle_match.group(1)}")
            elif 'twitter.com/' in twitter_handle:
                # Already a full URL
                if not twitter_handle.startswith(('http://', 'https://')):
                    twitter_handle = 'https://' + twitter_handle
                extracted["social_media"].append(twitter_handle)
        
        # Extract metrics
        metrics_matches = re.findall(self.quick_patterns["metrics"], text)
        extracted["metrics"] = metrics_matches
        
        # Extract years of experience
        years_match = re.search(self.quick_patterns["years"], text, re.IGNORECASE)
        if years_match:
            extracted["years_experience"] = int(years_match.group(1))
        
        return extracted
    
    async def _llm_extract(self, message: str, recent_context: List[Dict]) -> ExtractedData:
        """Use LLM to extract structured data from conversation"""
        
        # Format recent context
        context_str = ""
        for msg in recent_context:
            role = "User" if msg.get("type") == "user" else "Assistant"
            context_str += f"{role}: {msg.get('content', '')}\n"
        
        prompt = f"""
You are an expert at extracting structured information from conversations about someone's professional background.

Recent conversation context:
{context_str}

Current message: {message}

Extract the following information from the current message, considering the context. 

IMPORTANT: Return ONLY valid JSON with double quotes for strings. Do not use single quotes or Python dict format.

Return JSON matching this exact structure:
{{
  "contact_info": {{
    "fullName": null,
    "email": null,
    "phone": null,
    "website": null,
    "company": null,
    "role": null,
    "socialMedia": []
  }},
  "professional_info": {{
    "aboutWork": null,
    "expertiseTopics": [],
    "achievements": null,
    "uniquePerspectives": null,
    "yearsExperience": null,
    "industry": null
  }},
  "achievements": [],
  "stories": [],
  "expertise_keywords": [],
  "topics_can_discuss": [],
  "target_audience": null,
  "unique_value": null,
  "media_experience": {{}},
  "sample_questions": {{}},
  "social_proof": {{}},
  "promotion_preferences": {{}}
}}

Rules:
1. Only extract information that is explicitly stated in the message or clearly implied from context
2. Use null for any fields where information is not available
3. For arrays, use empty array [] if nothing is found
4. Be specific - don't make assumptions
5. Extract exact metrics when mentioned (e.g., "38 podcasts", "7000+ followers")
6. For contact_info.fullName, extract the person's full name if mentioned
7. For professional_info.aboutWork, capture what they do professionally in their own words
8. For stories array, each item must be an object with this structure:
   {{"subject": "who/what", "challenge": "problem faced", "action": "what was done", "result": "outcome", "metrics": []}}
9. For achievements array, each item must be an object with this structure:
   {{"description": "what was achieved", "metric": "specific number", "outcome": "result"}}
10. For expertise_keywords, extract technical terms, skills, or areas of expertise as an array of strings

IMPORTANT - HANDLING CORRECTIONS:
- If the user says "for my key achievement..." or "actually, my achievement is..." or similar correction phrases, this is NEW information that REPLACES previous data
- Look for correction indicators: "actually", "correction", "I meant", "for my", "let me clarify", "to be clear"
- When a correction is detected, extract ONLY the new information, not the old

CRITICAL RULES FOR URLs AND SOCIAL MEDIA:
- NEVER infer or create URLs from email addresses
- ONLY extract website if explicitly mentioned (e.g., "my website is...", "visit me at...")
- ONLY add socialMedia entries if full URLs or handles are explicitly provided
- DO NOT assume someone has social media if not mentioned
- If only an email is provided, leave website and socialMedia empty

IMPORTANT: Return ONLY the JSON object, no explanations or additional text."""
        
        try:
            response = await self.gemini_service.create_message(
                prompt=prompt,
                model=self.model_name,
                workflow="chatbot_nlp_extraction"
            )
            
            # Clean up the response to ensure it's valid JSON
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            # Parse and validate with Pydantic
            try:
                # First try to parse as JSON
                extracted = ExtractedData.model_validate_json(response)
                return extracted
            except (ValidationError, json.JSONDecodeError) as e:
                # If that fails, try to evaluate as Python dict and convert to JSON
                try:
                    import ast
                    # Safely evaluate the string as a Python literal
                    data_dict = ast.literal_eval(response)
                    # Convert to JSON and parse with Pydantic
                    extracted = ExtractedData.model_validate(data_dict)
                    return extracted
                except Exception as eval_error:
                    logger.error(f"Failed to parse LLM response. JSON error: {e}, Eval error: {eval_error}")
                    logger.error(f"Response was: {response[:500]}...")
                    # Return minimal extracted data to avoid complete failure
                    minimal_data = ExtractedData()
                    # Try to at least get the name from the message
                    if message:
                        import re
                        # Try to extract name patterns
                        name_patterns = [
                            r"(?:my name is|I'm|I am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                            r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)[,!.]",
                        ]
                        for pattern in name_patterns:
                            match = re.search(pattern, message)
                            if match:
                                minimal_data.contact_info.fullName = match.group(1).strip()
                                break
                    return minimal_data
                
        except Exception as e:
            logger.error(f"Error in LLM extraction: {e}")
            return ExtractedData()
    
    def _merge_extracts(self, quick: Dict, llm: ExtractedData, existing: ExtractedData) -> ExtractedData:
        """Merge quick extracts, LLM extracts, and existing data intelligently"""
        
        # Start with existing data
        merged = existing.model_copy(deep=True)
        
        # Merge contact info (prefer quick extracts for accuracy)
        if quick.get("contact_info", {}).get("email"):
            merged.contact_info.email = quick["contact_info"]["email"]
        elif llm.contact_info.email:
            merged.contact_info.email = llm.contact_info.email
            
        if quick.get("contact_info", {}).get("website"):
            merged.contact_info.website = quick["contact_info"]["website"]
        elif llm.contact_info.website:
            merged.contact_info.website = llm.contact_info.website
        
        # Merge social media
        if quick.get("social_media"):
            merged.contact_info.socialMedia = list(set(
                (merged.contact_info.socialMedia or []) + quick["social_media"]
            ))
        
        # Merge other contact info from LLM
        if llm.contact_info.fullName and not merged.contact_info.fullName:
            merged.contact_info.fullName = llm.contact_info.fullName
        if llm.contact_info.company and not merged.contact_info.company:
            merged.contact_info.company = llm.contact_info.company
        if llm.contact_info.role and not merged.contact_info.role:
            merged.contact_info.role = llm.contact_info.role
        
        # Merge professional info
        if llm.professional_info.aboutWork:
            merged.professional_info.aboutWork = llm.professional_info.aboutWork
        if llm.professional_info.uniquePerspectives:
            merged.professional_info.uniquePerspectives = llm.professional_info.uniquePerspectives
        if quick.get("years_experience"):
            merged.professional_info.yearsExperience = quick["years_experience"]
        elif llm.professional_info.yearsExperience:
            merged.professional_info.yearsExperience = llm.professional_info.yearsExperience
        
        # Merge expertise keywords
        if llm.expertise_keywords:
            merged.expertise_keywords = list(set(
                (merged.expertise_keywords or []) + llm.expertise_keywords
            ))[:20]  # Limit to 20
        
        # Merge topics
        if llm.topics_can_discuss:
            merged.topics_can_discuss = list(set(
                (merged.topics_can_discuss or []) + llm.topics_can_discuss
            ))
        
        # Add new achievements
        if llm.achievements:
            existing_descriptions = {a.description for a in merged.achievements or []}
            for achievement in llm.achievements:
                if achievement.description not in existing_descriptions:
                    merged.achievements.append(achievement)
        
        # Add new stories
        if llm.stories:
            merged.stories.extend(llm.stories)
        
        # Update target audience and unique value
        if llm.target_audience:
            merged.target_audience = llm.target_audience
        if llm.unique_value:
            merged.unique_value = llm.unique_value
        
        return merged
    
    def _to_legacy_format(self, data: ExtractedData) -> Dict:
        """Convert Pydantic model to legacy dict format for compatibility"""
        return {
            "keywords": {
                "explicit": data.expertise_keywords or [],
                "implicit": [],
                "contextual": []
            },
            "stories": [story.model_dump() for story in (data.stories or [])],
            "achievements": [ach.model_dump() for ach in (data.achievements or [])],
            "contact_info": data.contact_info.model_dump(exclude_none=True),
            "professional_bio": {
                "about_work": data.professional_info.aboutWork,
                "expertise_topics": data.professional_info.expertiseTopics,
                "achievements": data.professional_info.achievements,
                "unique_perspectives": data.professional_info.uniquePerspectives,
                "years_experience": data.professional_info.yearsExperience
            },
            "metrics": [],
            "topics": {
                "suggested": data.topics_can_discuss or [],
                "key_messages": ""
            },
            "media_experience": data.media_experience or {},
            "target_audience": data.target_audience or "",
            "unique_value": data.unique_value or "",
            "sample_questions": data.sample_questions or {},
            "social_proof": data.social_proof or {},
            "promotion_preferences": data.promotion_preferences or {}
        }
    
    async def check_data_completeness(self, extracted_data: Dict) -> Dict[str, bool]:
        """Check which critical data points have been collected"""
        
        # Convert to Pydantic model for easier checking
        try:
            data = ExtractedData(**extracted_data) if extracted_data else ExtractedData()
        except ValidationError:
            data = ExtractedData()
        
        completeness = {
            "has_name": bool(data.contact_info.fullName),
            "has_email": bool(data.contact_info.email),
            "has_website": bool(data.contact_info.website),
            "has_professional_bio": bool(data.professional_info.aboutWork),
            "has_expertise_keywords": len(data.expertise_keywords or []) >= 3,
            "has_achievements": len(data.achievements or []) > 0,
            "has_success_story": len(data.stories or []) > 0,
            "has_podcast_topics": len(data.topics_can_discuss or []) > 0,
            "has_target_audience": bool(data.target_audience),
            "has_unique_value": bool(data.unique_value),
            "ready_for_media_kit": False
        }
        
        # Check if ready for media kit
        essential_data = [
            completeness["has_name"],
            completeness["has_email"],
            completeness["has_professional_bio"],
            completeness["has_expertise_keywords"],
            completeness["has_achievements"] or completeness["has_success_story"],
            completeness["has_podcast_topics"]
        ]
        
        completeness["ready_for_media_kit"] = sum(essential_data) >= 5
        
        return completeness
    
    def suggest_next_data_point(self, completeness: Dict[str, bool]) -> Optional[str]:
        """Suggest what data to collect next based on what's missing"""
        
        priority_order = [
            ("has_name", "their name"),
            ("has_email", "their email address"),
            ("has_professional_bio", "what they do professionally"),
            ("has_success_story", "a specific success story or case study"),
            ("has_expertise_keywords", "their main areas of expertise"),
            ("has_podcast_topics", "topics they'd like to discuss on podcasts"),
            ("has_website", "their website or online presence"),
            ("has_target_audience", "their target audience"),
            ("has_achievements", "their key achievements or metrics"),
            ("has_unique_value", "what makes them unique")
        ]
        
        for check, description in priority_order:
            if not completeness.get(check, False):
                return description
        
        return None

    def calculate_progress(self, extracted_data: Dict) -> int:
        """Calculate progress based on data quality tiers"""
        
        # Convert to Pydantic model for easier checking
        try:
            data = ExtractedData(**extracted_data) if extracted_data else ExtractedData()
        except ValidationError:
            data = ExtractedData()
        
        # Essential data (0-60%)
        essential_progress = {
            "has_name": 10,
            "has_email": 10,
            "has_about_work": 15,
            "has_expertise": 10,
            "has_story_or_achievement": 15
        }
        
        # Quality improvements (60-85%)
        quality_progress = {
            "has_website": 5,
            "has_metrics": 5,
            "has_target_audience": 5,
            "has_unique_perspective": 5,
            "has_multiple_stories": 5
        }
        
        # Polish items (85-95%)
        polish_progress = {
            "has_testimonials": 3,
            "has_media_experience": 3,
            "has_promotion_items": 2,
            "has_social_media": 2
        }
        
        total = 0
        
        # Calculate essential progress
        if data.contact_info.fullName:
            total += essential_progress["has_name"]
        if data.contact_info.email:
            total += essential_progress["has_email"]
        if data.professional_info.aboutWork:
            total += essential_progress["has_about_work"]
        if len(data.expertise_keywords or []) >= 3:
            total += essential_progress["has_expertise"]
        if (data.stories or []) or (data.achievements or []):
            total += essential_progress["has_story_or_achievement"]
        
        # Add quality improvements
        if data.contact_info.website:
            total += quality_progress["has_website"]
        if any(s.metrics for s in (data.stories or [])):
            total += quality_progress["has_metrics"]
        if data.target_audience:
            total += quality_progress["has_target_audience"]
        if data.unique_value or data.professional_info.uniquePerspectives:
            total += quality_progress["has_unique_perspective"]
        if len((data.stories or []) + (data.achievements or [])) >= 2:
            total += quality_progress["has_multiple_stories"]
        
        # Add polish items
        if data.social_proof and data.social_proof.get("testimonials"):
            total += polish_progress["has_testimonials"]
        if data.media_experience and (data.media_experience.get("previousAppearances") or data.media_experience.get("speakingClips")):
            total += polish_progress["has_media_experience"]
        if data.promotion_preferences and data.promotion_preferences.get("itemsToPromote"):
            total += polish_progress["has_promotion_items"]
        if data.contact_info.socialMedia:
            total += polish_progress["has_social_media"]
        
        return min(total, 95)  # Cap at 95 until conversation complete

    def evaluate_completion_readiness(self, extracted_data: Dict, message_count: int) -> Dict:
        """Evaluate if we can complete the conversation"""
        
        # Convert to Pydantic model for easier checking
        try:
            data = ExtractedData(**extracted_data) if extracted_data else ExtractedData()
        except ValidationError:
            data = ExtractedData()
        
        # Essential data check
        essential_checks = {
            "has_name": bool(data.contact_info.fullName),
            "has_email": bool(data.contact_info.email),
            "has_work_description": bool(data.professional_info.aboutWork),
            "has_expertise": len(data.expertise_keywords or []) >= 3,
            "has_proof": len(data.stories or []) > 0 or len(data.achievements or []) > 0,
            "has_topics": len(data.topics_can_discuss or []) > 0
        }
        
        essential_score = sum(essential_checks.values()) / len(essential_checks)
        
        # Quality bonus checks
        quality_checks = {
            "has_metrics": any(s.metrics for s in (data.stories or [])) or 
                          any(a.metric for a in (data.achievements or [])),
            "has_website": bool(data.contact_info.website),
            "has_target_audience": bool(data.target_audience),
            "has_unique_value": bool(data.unique_value),
            "multiple_examples": len((data.stories or []) + (data.achievements or [])) >= 2
        }
        
        quality_score = sum(quality_checks.values()) / len(quality_checks)
        
        # Completion criteria
        can_complete_minimal = essential_score >= 0.8 and message_count >= 10
        can_complete_good = essential_score >= 0.9 and quality_score >= 0.4
        can_complete_excellent = essential_score == 1.0 and quality_score >= 0.6
        
        return {
            "can_complete": can_complete_minimal or can_complete_good,
            "completion_quality": (
                "excellent" if can_complete_excellent else
                "good" if can_complete_good else
                "minimal" if can_complete_minimal else
                "insufficient"
            ),
            "essential_score": essential_score,
            "quality_score": quality_score,
            "missing_essential": [k for k, v in essential_checks.items() if not v],
            "suggested_improvements": [k for k, v in quality_checks.items() if not v]
        }