# podcast_outreach/services/chatbot/data_merger.py

from typing import Dict, List, Optional, Union
from pydantic import BaseModel
import re

class DataMerger:
    """
    Merges and converts chatbot extracted data to questionnaire format
    for compatibility with existing bio and angles generation.
    """
    
    def merge_conversation_to_questionnaire(self, extracted_data: Dict) -> Dict:
        """Convert chatbot extracted data to questionnaire format"""
        
        # Extract contact info - handle both nested and flat structures
        contact_info = extracted_data.get("contact_info", {})
        
        # Check for flat structure fields (from agentic chatbot)
        full_name = (contact_info.get("fullName") or 
                    contact_info.get("name") or 
                    extracted_data.get("full_name") or 
                    extracted_data.get("name", ""))
        
        email = (contact_info.get("email") or 
                extracted_data.get("email", ""))
        
        phone = (contact_info.get("phone") or 
                extracted_data.get("phone", ""))
        
        website = (contact_info.get("website") or 
                  extracted_data.get("website", ""))
        
        # Get social media data and convert to questionnaire format
        social_media_raw = (contact_info.get("socialMedia") or 
                           extracted_data.get("social_media", []))
        
        # Convert social media to questionnaire format [{platform, url}]
        social_media = self._format_social_media_for_questionnaire(social_media_raw)
        
        # Map chatbot fields to questionnaire structure
        questionnaire_data = {
            "contactInfo": {
                "fullName": full_name,
                "email": email,
                "phone": phone,
                "website": website,
                "socialMedia": social_media if isinstance(social_media, list) else []
            },
            "professionalBio": {
                "aboutWork": self._get_professional_bio(extracted_data),
                "expertiseTopics": self._get_expertise_topics(extracted_data),
                "achievements": self._format_achievements(extracted_data.get("achievements", [])),
                "uniquePerspectives": self._get_unique_perspectives(extracted_data)
            },
            "suggestedTopics": {
                "topics": self._get_suggested_topics(extracted_data),
                "keyStoriesOrMessages": self._get_key_stories_or_messages(extracted_data)
            },
            "sampleQuestions": extracted_data.get("sample_questions", {
                "frequentlyAsked": "",
                "loveToBeAsked": ""
            }),
            "socialProof": extracted_data.get("social_proof", {
                "testimonials": "",
                "notableStats": self._extract_metrics(extracted_data)
            }),
            "mediaExperience": extracted_data.get("media_experience", {
                "previousAppearances": [],
                "speakingClips": []
            }),
            "promotionPrefs": extracted_data.get("promotion_preferences", {
                "preferredIntro": "",
                "itemsToPromote": ""
            }),
            "finalNotes": {
                "idealPodcastDescription": extracted_data.get("ideal_podcast", ""),
                "anythingElse": extracted_data.get("additional_notes", "")
            }
        }
        
        # Only include non-empty fields
        return self._clean_empty_fields(questionnaire_data)
    
    def _get_professional_bio(self, extracted_data: Dict) -> str:
        """Get professional bio handling both string and dict formats"""
        # First try direct professional_bio field (flat structure)
        bio = extracted_data.get("professional_bio", "")
        if isinstance(bio, str) and bio:
            return bio
        elif isinstance(bio, dict):
            return bio.get("about_work", "")
        
        # Also check for current_role and company to build a bio if missing
        if not bio:
            role = extracted_data.get("current_role", "")
            company = extracted_data.get("company", "")
            if role and company:
                return f"{role} at {company}"
            elif role:
                return role
        
        return ""
    
    def _get_expertise_topics(self, extracted_data: Dict) -> str:
        """Get expertise topics from various possible locations"""
        # First try expertise_keywords (used by agentic chatbot)
        expertise_keywords = extracted_data.get("expertise_keywords", [])
        if expertise_keywords:
            return ", ".join(expertise_keywords)
        
        # Fall back to keywords.explicit (used by old chatbot)
        keywords = extracted_data.get("keywords", {})
        if isinstance(keywords, dict):
            return ", ".join(keywords.get("explicit", []))
        
        return ""
    
    def _get_unique_perspectives(self, extracted_data: Dict) -> str:
        """Get unique perspectives from various possible locations"""
        # First try unique_perspective (used by agentic chatbot)
        unique = extracted_data.get("unique_perspective", "")
        if unique:
            return unique
            
        # Try unique_value
        unique = extracted_data.get("unique_value", "")
        if unique:
            return unique
            
        # Finally try professional_bio dict format
        bio = extracted_data.get("professional_bio", {})
        if isinstance(bio, dict):
            return bio.get("unique_perspectives", "")
        
        return ""
    
    def _format_achievements(self, achievements) -> str:
        """Format achievements for questionnaire - handles both list and string formats"""
        if not achievements:
            return ""
        
        # Handle string format (from agentic chatbot)
        if isinstance(achievements, str):
            return achievements
        
        # Handle list format (from old chatbot)
        if isinstance(achievements, list):
            formatted = []
            for a in achievements:
                if isinstance(a, dict):
                    text = a.get("description", "")
                    if a.get("metric"):
                        text += f" ({a['metric']})"
                    if text:
                        formatted.append(text)
                elif isinstance(a, str):
                    # Handle list of strings
                    formatted.append(a)
            return " | ".join(formatted)
        
        return ""
    
    def _get_suggested_topics(self, extracted_data: Dict) -> str:
        """Get suggested topics from various possible locations"""
        # First try podcast_topics (used by agentic chatbot)
        podcast_topics = extracted_data.get("podcast_topics", [])
        if podcast_topics:
            if isinstance(podcast_topics, list):
                return ", ".join(str(topic) for topic in podcast_topics)
            else:
                return str(podcast_topics)
        
        # Fall back to topics.suggested (used by old chatbot)
        topics = extracted_data.get("topics", {})
        if isinstance(topics, dict):
            suggested = topics.get("suggested", [])
            if suggested:
                return ", ".join(str(topic) for topic in suggested)
        
        return ""
    
    def _get_key_stories_or_messages(self, extracted_data: Dict) -> str:
        """Get key stories or messages from various sources"""
        # First try key_message (used by agentic chatbot)
        key_message = extracted_data.get("key_message", "")
        if key_message:
            return key_message
        
        # Check topics.key_message structure (from state converter)
        topics = extracted_data.get("topics", {})
        if isinstance(topics, dict) and topics.get("key_message"):
            return topics["key_message"]
        
        # Try success_stories (used by agentic chatbot)
        success_stories = extracted_data.get("success_stories", "")
        if isinstance(success_stories, list):
            # Join if it's a list
            return " | ".join(str(story) for story in success_stories if story)
        elif success_stories:
            return str(success_stories)
        
        # Fall back to stories format (used by old chatbot)
        stories = extracted_data.get("stories", [])
        if stories:
            return self._format_stories(stories)
        
        return ""
    
    def _format_stories(self, stories: List[Dict]) -> str:
        """Format stories for questionnaire"""
        if not stories:
            return ""
        
        formatted = []
        for s in stories:
            if isinstance(s, dict):
                parts = []
                if s.get("challenge"):
                    parts.append(f"Challenge: {s['challenge']}")
                if s.get("result"):
                    parts.append(f"Result: {s['result']}")
                if parts:
                    formatted.append(" - ".join(parts))
        
        return " | ".join(formatted)
    
    def _extract_metrics(self, extracted_data: Dict) -> str:
        """Extract notable metrics from all data"""
        metrics = []
        
        # From stories
        for story in extracted_data.get("stories", []):
            if isinstance(story, dict) and story.get("metrics"):
                metrics.extend(story["metrics"])
        
        # From achievements
        for achievement in extracted_data.get("achievements", []):
            if isinstance(achievement, dict) and achievement.get("metric"):
                metrics.append(achievement["metric"])
        
        # From metrics field
        if extracted_data.get("metrics"):
            metrics.extend(extracted_data["metrics"])
        
        # Remove duplicates and return
        unique_metrics = list(dict.fromkeys(metrics))
        return ", ".join(unique_metrics[:5])  # Limit to 5 key metrics
    
    def _clean_empty_fields(self, data: Dict) -> Dict:
        """Remove empty fields from the data structure"""
        cleaned = {}
        
        for key, value in data.items():
            if isinstance(value, dict):
                nested_cleaned = self._clean_empty_fields(value)
                if nested_cleaned:
                    cleaned[key] = nested_cleaned
            elif isinstance(value, list) and value:
                cleaned[key] = value
            elif isinstance(value, str) and value.strip():
                cleaned[key] = value
            elif value is not None and not isinstance(value, (dict, list, str)):
                cleaned[key] = value
        
        return cleaned
    
    def _format_social_media_for_questionnaire(self, social_media_raw: Union[List, str]) -> List[Dict[str, str]]:
        """Convert various social media formats to questionnaire format [{platform, url}]"""
        formatted_social_media = []
        
        if not social_media_raw:
            return []
        
        # If it's already in the correct format, return it
        if isinstance(social_media_raw, list):
            for item in social_media_raw:
                if isinstance(item, dict):
                    # If it already has platform and url, use it
                    if 'platform' in item and 'url' in item:
                        formatted_social_media.append({
                            'platform': item['platform'],
                            'url': item['url']
                        })
                    # If it has value field (from bucket entry), extract from it
                    elif 'value' in item:
                        # Recursively process the value
                        inner_formatted = self._format_social_media_for_questionnaire(item['value'])
                        formatted_social_media.extend(inner_formatted)
                    else:
                        # Try to extract platform and url from dict
                        platform = item.get('platform', 'other')
                        url = item.get('url', '') or item.get('handle', '')
                        if url:
                            formatted_social_media.append({
                                'platform': platform,
                                'url': url
                            })
                elif isinstance(item, str):
                    # Parse string to extract platform and URL
                    parsed = self._parse_social_media_string(item)
                    if parsed:
                        formatted_social_media.append(parsed)
        elif isinstance(social_media_raw, str):
            # Single string, parse it
            parsed = self._parse_social_media_string(social_media_raw)
            if parsed:
                formatted_social_media.append(parsed)
        
        return formatted_social_media
    
    def _parse_social_media_string(self, social_str: str) -> Optional[Dict[str, str]]:
        """Parse a social media string to extract platform and URL"""
        if not social_str or not isinstance(social_str, str):
            return None
        
        social_str = social_str.strip()
        
        # Common patterns
        patterns = [
            # Twitter/X patterns
            (r'(?:https?://)?(?:www\.)?(?:twitter|x)\.com/(\w+)', 'twitter'),
            (r'@(\w+).*twitter', 'twitter'),
            (r'twitter.*@(\w+)', 'twitter'),
            # Instagram patterns
            (r'(?:https?://)?(?:www\.)?instagram\.com/(\w+)', 'instagram'),
            (r'@(\w+).*instagram', 'instagram'),
            (r'instagram.*@(\w+)', 'instagram'),
            # LinkedIn patterns
            (r'(?:https?://)?(?:www\.)?linkedin\.com/in/([\w-]+)', 'linkedin'),
            # YouTube patterns
            (r'(?:https?://)?(?:www\.)?youtube\.com/(?:c|channel|user)/([\w-]+)', 'youtube'),
            # Facebook patterns
            (r'(?:https?://)?(?:www\.)?facebook\.com/([\w.]+)', 'facebook'),
            # TikTok patterns
            (r'(?:https?://)?(?:www\.)?tiktok\.com/@([\w.]+)', 'tiktok'),
            (r'@(\w+).*tiktok', 'tiktok'),
            # GitHub patterns
            (r'(?:https?://)?(?:www\.)?github\.com/([\w-]+)', 'github'),
            # Medium patterns
            (r'(?:https?://)?(?:www\.)?medium\.com/@([\w.]+)', 'medium'),
        ]
        
        # Try to find a URL in the string
        url_match = re.search(r'https?://[^\s]+', social_str)
        url = url_match.group(0) if url_match else None
        
        # Try each pattern
        for pattern, platform in patterns:
            match = re.search(pattern, social_str, re.IGNORECASE)
            if match:
                if not url:
                    # Construct URL if we only have handle
                    handle = match.group(1) if match.groups() else None
                    if handle:
                        if platform == 'twitter':
                            url = f"https://twitter.com/{handle}"
                        elif platform == 'instagram':
                            url = f"https://instagram.com/{handle}"
                        elif platform == 'linkedin':
                            url = f"https://linkedin.com/in/{handle}"
                        elif platform == 'youtube':
                            url = f"https://youtube.com/c/{handle}"
                        elif platform == 'facebook':
                            url = f"https://facebook.com/{handle}"
                        elif platform == 'tiktok':
                            url = f"https://tiktok.com/@{handle}"
                        elif platform == 'github':
                            url = f"https://github.com/{handle}"
                        elif platform == 'medium':
                            url = f"https://medium.com/@{handle}"
                
                if url:
                    return {
                        'platform': platform,
                        'url': url
                    }
        
        # If no specific pattern matched but we have a URL, try to extract platform from URL
        if url:
            for platform in ['twitter', 'x', 'instagram', 'linkedin', 'youtube', 
                           'facebook', 'tiktok', 'github', 'medium']:
                if platform in url.lower():
                    return {
                        'platform': platform if platform != 'x' else 'twitter',
                        'url': url
                    }
        
        # Generic format: "Platform: @handle" or "Platform: URL"
        generic_match = re.match(r'^(\w+):\s*(.+)$', social_str)
        if generic_match:
            platform = generic_match.group(1).lower()
            value = generic_match.group(2).strip()
            
            # If it's a URL, use it directly
            if value.startswith('http'):
                return {
                    'platform': platform,
                    'url': value
                }
            # If it's a handle, try to construct URL
            elif value.startswith('@'):
                handle = value[1:]
                # For unknown platforms, just return what we have
                return {
                    'platform': platform,
                    'url': f"@{handle}"  # Keep as handle since we don't know the URL format
                }
        
        # Last resort: if we can identify platform keyword, return it
        social_keywords = ['twitter', 'instagram', 'linkedin', 'facebook', 
                          'youtube', 'tiktok', 'github', 'medium', 'substack']
        
        social_str_lower = social_str.lower()
        for keyword in social_keywords:
            if keyword in social_str_lower:
                return {
                    'platform': keyword,
                    'url': social_str  # Use the full string as URL
                }
        
        # If nothing matched, return as generic social media
        return {
            'platform': 'other',
            'url': social_str
        }