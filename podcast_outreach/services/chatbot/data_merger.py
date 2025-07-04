# podcast_outreach/services/chatbot/data_merger.py

from typing import Dict, List, Optional
from pydantic import BaseModel

class DataMerger:
    """
    Merges and converts chatbot extracted data to questionnaire format
    for compatibility with existing bio and angles generation.
    """
    
    def merge_conversation_to_questionnaire(self, extracted_data: Dict) -> Dict:
        """Convert chatbot extracted data to questionnaire format"""
        
        # Extract contact info
        contact_info = extracted_data.get("contact_info", {})
        
        # Map chatbot fields to questionnaire structure
        questionnaire_data = {
            "contactInfo": {
                "fullName": contact_info.get("fullName") or contact_info.get("name", ""),
                "email": contact_info.get("email", ""),
                "phone": contact_info.get("phone", ""),
                "website": contact_info.get("website", ""),
                "socialMedia": contact_info.get("socialMedia", [])
            },
            "professionalBio": {
                "aboutWork": extracted_data.get("professional_bio", {}).get("about_work", ""),
                "expertiseTopics": ", ".join(extracted_data.get("keywords", {}).get("explicit", [])),
                "achievements": self._format_achievements(extracted_data.get("achievements", [])),
                "uniquePerspectives": extracted_data.get("unique_value", "") or 
                                     extracted_data.get("professional_bio", {}).get("unique_perspectives", "")
            },
            "suggestedTopics": {
                "topics": ", ".join(extracted_data.get("topics", {}).get("suggested", [])),
                "keyStoriesOrMessages": self._format_stories(extracted_data.get("stories", []))
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
            })
        }
        
        # Only include non-empty fields
        return self._clean_empty_fields(questionnaire_data)
    
    def _format_achievements(self, achievements: List[Dict]) -> str:
        """Format achievements for questionnaire"""
        if not achievements:
            return ""
        
        formatted = []
        for a in achievements:
            if isinstance(a, dict):
                text = a.get("description", "")
                if a.get("metric"):
                    text += f" ({a['metric']})"
                if text:
                    formatted.append(text)
        
        return " | ".join(formatted)
    
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