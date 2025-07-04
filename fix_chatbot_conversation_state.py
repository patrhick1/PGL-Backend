#!/usr/bin/env python3
"""
Comprehensive fix for chatbot conversation state management
This script demonstrates the issues and implements solutions
"""

import json
from typing import Dict, List, Set, Optional, Tuple

class ImprovedConversationStateManager:
    """
    Manages conversation state to prevent duplicate questions and improve flow
    """
    
    def __init__(self):
        self.asked_questions: Set[str] = set()
        self.answered_topics: Set[str] = set()
        self.extracted_data_points: Set[str] = set()
        self.phase_states = {
            "introduction": {"messages": 0, "summary_shown": False},
            "core_discovery": {"messages": 0, "summary_shown": False},
            "media_focus": {"messages": 0, "summary_shown": False},
            "confirmation": {"messages": 0, "summary_shown": False, "final_summary_shown": False}
        }
        
    def mark_question_asked(self, question: str, topic: str):
        """Mark a question as asked and its topic"""
        self.asked_questions.add(question.lower()[:50])  # Store first 50 chars
        self.answered_topics.add(topic)
        
    def has_asked_about(self, topic: str) -> bool:
        """Check if we've already asked about this topic"""
        return topic in self.answered_topics
        
    def mark_data_extracted(self, data_type: str):
        """Mark that we've extracted this type of data"""
        self.extracted_data_points.add(data_type)
        
    def has_data_for(self, data_type: str) -> bool:
        """Check if we already have this data"""
        return data_type in self.extracted_data_points
        
    def update_phase_state(self, phase: str, key: str, value):
        """Update phase-specific state"""
        if phase in self.phase_states:
            self.phase_states[phase][key] = value
            
    def get_phase_state(self, phase: str, key: str):
        """Get phase-specific state"""
        return self.phase_states.get(phase, {}).get(key)

class DynamicQuestionSelector:
    """
    Selects questions based on missing data, not message count
    """
    
    def __init__(self):
        # Question pool organized by data type
        self.question_pool = {
            "metrics": [
                "Can you share specific metrics or numbers from one of your biggest wins?",
                "What measurable impact have you achieved in your work?",
                "Do you have any specific ROI or performance numbers you can share?"
            ],
            "expertise": [
                "What would you say are your top 3-5 areas of expertise?",
                "What topics are you most knowledgeable about?",
                "What are your core competencies?"
            ],
            "unique_value": [
                "What makes your approach or perspective unique in your field?",
                "What sets you apart from others in your industry?",
                "What's your unique value proposition?"
            ],
            "success_story": [
                "Can you share ONE specific success story where you made a significant impact?",
                "Tell me about a time you solved a major challenge for a client or company.",
                "What's your proudest professional achievement?"
            ],
            "podcast_topics": [
                "What 2-3 topics are you most passionate about discussing on podcasts?",
                "What subjects could you talk about for hours?",
                "What topics would make for the most engaging podcast conversations?"
            ],
            "target_audience": [
                "Who is your ideal audience - who would benefit most from hearing your insights?",
                "Who do you typically help with your work?",
                "What type of listeners would find your expertise most valuable?"
            ],
            "promotion": [
                "Is there anything specific you'd like to promote (book, course, service)?",
                "Do you have any offerings you'd like to mention to podcast audiences?",
                "What should listeners know about your products or services?"
            ],
            "contact_preference": [
                "What's the best way for podcast hosts to contact you for scheduling?",
                "How should interested hosts reach out to book you?",
                "What's your preferred method for scheduling podcast appearances?"
            ]
        }
        
    def get_next_question(self, 
                         missing_data: List[str], 
                         state_manager: ImprovedConversationStateManager,
                         extracted_data: Dict) -> Optional[str]:
        """
        Get the next question based on what data is actually missing
        """
        for data_type in missing_data:
            # Skip if we already have this data
            if state_manager.has_data_for(data_type):
                continue
                
            # Skip if we've already asked about this
            if state_manager.has_asked_about(data_type):
                continue
                
            # Get questions for this data type
            questions = self.question_pool.get(data_type, [])
            
            # Find a question we haven't asked yet
            for question in questions:
                question_key = question.lower()[:50]
                if question_key not in state_manager.asked_questions:
                    return question
                    
        return None

class DataCompletenessChecker:
    """
    Checks what data we actually have vs hardcoded requirements
    """
    
    def __init__(self):
        self.required_data = {
            "introduction": ["name", "email", "professional_bio"],
            "core_discovery": ["success_story", "expertise", "metrics"],
            "media_focus": ["podcast_topics", "target_audience"],
            "confirmation": []  # No specific requirements
        }
        
    def check_extracted_data(self, extracted_data: Dict) -> Dict[str, bool]:
        """
        Check what data has actually been extracted
        """
        completeness = {}
        
        # Contact info
        contact = extracted_data.get('contact_info', {})
        completeness['name'] = bool(contact.get('fullName'))
        completeness['email'] = bool(contact.get('email'))
        
        # Professional info
        prof_bio = extracted_data.get('professional_bio', {})
        completeness['professional_bio'] = bool(prof_bio.get('about_work'))
        
        # Success stories and metrics
        stories = extracted_data.get('stories', [])
        completeness['success_story'] = len(stories) > 0
        completeness['metrics'] = any(
            story.get('metrics') or story.get('result', '').lower().count('%') > 0 or
            any(char.isdigit() for char in story.get('result', ''))
            for story in stories
        )
        
        # Expertise
        keywords = extracted_data.get('keywords', {}).get('explicit', [])
        completeness['expertise'] = len(keywords) >= 3
        
        # Podcast topics
        topics = extracted_data.get('topics', {}).get('suggested', [])
        linkedin_topics = extracted_data.get('linkedin_analysis', {}).get('podcast_topics', [])
        completeness['podcast_topics'] = len(topics) > 0 or len(linkedin_topics) > 0
        
        # Target audience
        completeness['target_audience'] = bool(extracted_data.get('target_audience'))
        
        # Unique value
        completeness['unique_value'] = bool(extracted_data.get('unique_value'))
        
        # Promotion
        promo = extracted_data.get('promotion_preferences', {})
        completeness['promotion'] = bool(promo) or 'promotion' in str(extracted_data).lower()
        
        # Contact preference
        completeness['contact_preference'] = bool(
            extracted_data.get('scheduling_preference') or
            'calendly' in str(extracted_data).lower() or
            'calendar' in str(extracted_data).lower()
        )
        
        return completeness
        
    def get_missing_data(self, phase: str, completeness: Dict[str, bool]) -> List[str]:
        """
        Get list of missing data for current phase
        """
        missing = []
        
        # Get phase requirements
        phase_reqs = self.required_data.get(phase, [])
        
        # Check required data
        for req in phase_reqs:
            if not completeness.get(req, False):
                missing.append(req)
                
        # Add optional data that's commonly needed
        if phase == "confirmation":
            if not completeness.get('promotion', False):
                missing.append('promotion')
            if not completeness.get('contact_preference', False):
                missing.append('contact_preference')
                
        return missing

# Example usage showing how to fix the conversation flow
def demonstrate_fixed_flow():
    """
    Show how the improved system would handle the conversation
    """
    print("IMPROVED CONVERSATION FLOW DEMONSTRATION")
    print("=" * 60)
    
    # Initialize components
    state_manager = ImprovedConversationStateManager()
    question_selector = DynamicQuestionSelector()
    completeness_checker = DataCompletenessChecker()
    
    # Simulate the problematic conversation
    extracted_data = {
        "contact_info": {
            "fullName": "Michael Greenberg",
            "socialMedia": ["https://www.linkedin.com/in/gentoftech"]
        },
        "linkedin_analysis": {
            "analysis_complete": True,
            "expertise_keywords": ["AI", "Automation", "Digital Operations"],
            "success_stories": [{"title": "Founded 3rd Brain"}]
        },
        "stories": [
            {
                "subject": "Startup Exit",
                "result": "Co-founded a startup that raised $1.5M, and successfully exited"
            }
        ]
    }
    
    # Check completeness
    completeness = completeness_checker.check_extracted_data(extracted_data)
    
    print("\nData Completeness Check:")
    for key, value in completeness.items():
        print(f"  {key}: {'YES' if value else 'NO'}")
    
    # Simulate core_discovery phase
    print("\n\nCORE DISCOVERY PHASE:")
    print("-" * 40)
    
    # The system would see we already have metrics from the story
    missing_data = completeness_checker.get_missing_data("core_discovery", completeness)
    print(f"Missing data: {missing_data}")
    
    # Mark that we've extracted metrics
    state_manager.mark_data_extracted("metrics")
    state_manager.mark_data_extracted("success_story")
    
    # Get next question (should skip metrics since we have it)
    next_q = question_selector.get_next_question(missing_data, state_manager, extracted_data)
    print(f"Next question: {next_q}")
    
    # Simulate confirmation phase
    print("\n\nCONFIRMATION PHASE:")
    print("-" * 40)
    
    # Check if summary was shown
    if not state_manager.get_phase_state("confirmation", "final_summary_shown"):
        print("Showing summary (first time only)")
        state_manager.update_phase_state("confirmation", "final_summary_shown", True)
    else:
        print("Summary already shown, moving to follow-up questions")
    
    # After user responds to summary
    missing_data = ["promotion", "contact_preference"]
    
    # Ask about promotion
    if not state_manager.has_asked_about("promotion"):
        print("Asking about promotion")
        state_manager.mark_question_asked("Is there anything specific you'd like to promote?", "promotion")
    
    # User says "Let's leave it at this" - system recognizes this as answered
    state_manager.mark_data_extracted("promotion")
    
    # Ask about contact preference
    if not state_manager.has_asked_about("contact_preference"):
        print("Asking about contact preference")
        state_manager.mark_question_asked("What's the best way for podcast hosts to contact you?", "contact_preference")
    
    # User provides calendly - system recognizes this
    state_manager.mark_data_extracted("contact_preference")
    
    # Check if we need more questions
    if state_manager.has_data_for("promotion") and state_manager.has_data_for("contact_preference"):
        print("\nAll data collected - ready to complete conversation!")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    demonstrate_fixed_flow()