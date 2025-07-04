# podcast_outreach/services/chatbot/mock_interview_generator.py

import re
from typing import List, Dict
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

class MockInterviewGenerator:
    """Generates mock interview transcript from conversation"""
    
    async def generate_transcript(self, messages: List[Dict], 
                                 extracted_data: Dict) -> str:
        """Convert conversation into mock interview format"""
        # Filter and process Q&A pairs
        qa_pairs = self._extract_qa_pairs(messages)
        
        # Generate interview format
        transcript = "MOCK INTERVIEW TRANSCRIPT\n"
        transcript += "========================\n\n"
        
        # Add introduction if available
        if extracted_data.get("contact_info", {}).get("name"):
            name = extracted_data["contact_info"]["name"]
            transcript += f"INTERVIEWER: Today we're joined by {name}. Welcome to the show!\n\n"
            transcript += f"GUEST: Thank you for having me!\n\n"
        
        # Process Q&A pairs
        for qa in qa_pairs:
            question = self._clean_question(qa["question"])
            answer = self._clean_answer(qa["answer"])
            
            if question and answer and len(answer) > 20:  # Skip very short exchanges
                transcript += f"INTERVIEWER: {question}\n\n"
                transcript += f"GUEST: {answer}\n\n"
        
        # Add summary section
        transcript += "\nKEY INSIGHTS EXTRACTED:\n"
        transcript += "=====================\n"
        
        # Add expertise areas
        if "keywords" in extracted_data:
            explicit_keywords = extracted_data['keywords'].get('explicit', [])
            if explicit_keywords:
                transcript += f"\nEXPERTISE AREAS: {', '.join(explicit_keywords[:10])}\n"
        
        # Add key achievements
        if "achievements" in extracted_data and extracted_data["achievements"]:
            transcript += "\nKEY ACHIEVEMENTS:\n"
            for achievement in extracted_data["achievements"][:5]:
                if isinstance(achievement, dict):
                    transcript += f"- {achievement.get('text', str(achievement))}\n"
                else:
                    transcript += f"- {achievement}\n"
        
        # Add notable stories
        if "stories" in extracted_data and extracted_data["stories"]:
            transcript += "\nNOTABLE STORIES SHARED:\n"
            for i, story in enumerate(extracted_data["stories"][:3], 1):
                story_type = story.get('type', 'Story').replace('_', ' ').title()
                transcript += f"{i}. {story_type}"
                if story.get('components', {}).get('result'):
                    transcript += f" - Result: {story['components']['result']}"
                transcript += "\n"
        
        # Add contact information
        if extracted_data.get("contact_info"):
            contact = extracted_data["contact_info"]
            transcript += "\nCONTACT INFORMATION:\n"
            if contact.get("email"):
                transcript += f"- Email: {contact['email']}\n"
            if contact.get("website"):
                transcript += f"- Website: {contact['website']}\n"
            if contact.get("social_media"):
                for social in contact["social_media"][:3]:
                    transcript += f"- {social}\n"
        
        return transcript
    
    def _extract_qa_pairs(self, messages: List[Dict]) -> List[Dict]:
        """Extract question-answer pairs from conversation"""
        qa_pairs = []
        
        # Skip initial bot greeting
        start_index = 1 if messages and messages[0]["type"] == "bot" else 0
        
        i = start_index
        while i < len(messages) - 1:
            # Look for bot question followed by user answer
            if messages[i]["type"] == "bot" and messages[i + 1]["type"] == "user":
                qa_pairs.append({
                    "question": messages[i]["content"],
                    "answer": messages[i + 1]["content"]
                })
                i += 2
            else:
                i += 1
        
        return qa_pairs
    
    def _clean_question(self, question: str) -> str:
        """Clean and format question for interview transcript"""
        # Remove chatbot-specific language
        cleaned = question
        
        # Remove greeting phrases
        greeting_patterns = [
            r"^(Hi there!|Hello!|Hey!|Great!|Awesome!|Fantastic!|Excellent!|Perfect!|Wonderful!)\s*",
            r"^(Thanks for sharing\.?|Thank you\.?|I appreciate that\.?)\s*",
            r"^(That's interesting\.?|That's great\.?|That sounds amazing\.?)\s*"
        ]
        
        for pattern in greeting_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        
        # Convert conversational language to interview style
        conversational_replacements = [
            (r"I'd love to (hear|know|learn) more about", "Tell me about"),
            (r"Can you tell me", "Could you share"),
            (r"I'm curious about", "What about"),
            (r"Let's talk about", "Let's discuss"),
            (r"^Now,?\s*", ""),
            (r"^So,?\s*", "")
        ]
        
        for pattern, replacement in conversational_replacements:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        
        # Ensure it ends with proper punctuation
        cleaned = cleaned.strip()
        if cleaned and not cleaned[-1] in '.?!':
            cleaned += "?"
        
        # Skip if too short or not a real question
        if len(cleaned) < 10 or cleaned.count(' ') < 2:
            return ""
        
        return cleaned
    
    def _clean_answer(self, answer: str) -> str:
        """Clean and format answer for interview transcript"""
        # Basic cleaning
        cleaned = answer.strip()
        
        # Remove any email-like signatures
        signature_patterns = [
            r"(?:Best|Regards|Thanks|Sincerely),?\s*\n.*$",
            r"Sent from my.*$"
        ]
        
        for pattern in signature_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
        
        # Ensure proper sentence ending
        if cleaned and not cleaned[-1] in '.?!':
            cleaned += "."
        
        return cleaned
    
    def _format_for_readability(self, text: str, max_line_length: int = 80) -> str:
        """Format text for better readability in transcript"""
        # This is a simple implementation - could be enhanced
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            if current_length + len(word) + 1 > max_line_length:
                lines.append(' '.join(current_line))
                current_line = [word]
                current_length = len(word)
            else:
                current_line.append(word)
                current_length += len(word) + 1
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return '\n'.join(lines)