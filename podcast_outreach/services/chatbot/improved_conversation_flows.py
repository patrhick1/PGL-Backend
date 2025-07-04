# podcast_outreach/services/chatbot/improved_conversation_flows.py

from typing import Dict, List, Optional, Tuple

class ImprovedConversationFlowManager:
    """
    Improved conversation flow manager that focuses on data collection
    efficiency rather than message count.
    """
    
    def __init__(self):
        # Dramatically reduced message requirements - targeting 14-23 total messages
        self.phases = {
            "introduction": {
                "min_messages": 2,
                "max_messages": 4,
                "required_data": ["name", "email", "current_work"],
                "next_phase": "core_discovery",
                "progress_weight": 0.20,
                "description": "Quick introduction and contact info"
            },
            "core_discovery": {
                "min_messages": 6,
                "max_messages": 10,
                "required_data": ["success_story", "expertise_keywords", "achievements"],
                "next_phase": "media_focus",
                "progress_weight": 0.40,
                "description": "Core expertise and success stories"
            },
            "media_focus": {
                "min_messages": 4,
                "max_messages": 6,
                "required_data": ["podcast_topics", "target_audience", "unique_value"],
                "next_phase": "confirmation",
                "progress_weight": 0.30,
                "description": "Media positioning and topics"
            },
            "confirmation": {
                "min_messages": 2,
                "max_messages": 3,
                "required_data": ["confirmation"],
                "next_phase": "complete",
                "progress_weight": 0.10,
                "description": "Final confirmation and missing details"
            }
        }
        
        self.phase_order = ["introduction", "core_discovery", "media_focus", "confirmation"]
        
        # Data-driven questions for each phase
        self.phase_questions = {
            "introduction": {
                "opener": "Hi {name}! I'm excited to help you create an amazing media kit. To get started, what's your full name and email address? Also, if you have a LinkedIn profile, please share the URL - I can analyze it to learn more about your expertise and save us both time!",
                "follow_up": [
                    "Great! Do you have a LinkedIn profile? If yes, please share your LinkedIn URL - I can analyze it to learn more about your expertise and save us both time!",
                    "What about other social media or your website? Please share any Twitter, website, or other professional links you'd like in your media kit.",
                    "Can you tell me briefly what you do professionally and what company you work with?"
                ]
            },
            "core_discovery": {
                "opener": "Perfect! Now I'd love to hear about your expertise. Can you share ONE specific success story where you made a significant impact? Please include any metrics or results.",
                "follow_up": [
                    "That's fascinating! Based on what you've shared, what would you say are your top 3-5 areas of expertise?",
                    "What makes your approach or perspective unique in your field?",
                    "What's been your biggest professional achievement so far? Any specific numbers or outcomes you can share?",
                    "How do you measure success in your work?"
                ]
            },
            "media_focus": {
                "opener": "Excellent insights! Now let's position you for podcast success. What 2-3 topics are you most passionate about discussing on podcasts?",
                "follow_up": [
                    "Who is your ideal audience - who would benefit most from hearing your insights?",
                    "Have you been on podcasts before? If yes, which ones?",
                    "What's the main message or transformation you want listeners to experience?"
                ]
            },
            "confirmation": {
                "opener": "We're almost done! Here's what I've gathered so far. Is there anything specific you'd like to promote (book, course, service)?",
                "follow_up": [
                    "What's the best way for podcast hosts to contact you for scheduling?",
                    "Any final thoughts or unique angles you'd like me to include in your media kit?"
                ]
            }
        }
    
    def get_next_question(self, phase: str, message_count_in_phase: int, 
                         extracted_data: Dict, missing_data: List[str]) -> str:
        """Get the next appropriate question based on phase and missing data"""
        
        questions = self.phase_questions.get(phase, {})
        
        # First message in phase - use opener
        if message_count_in_phase == 0:
            opener = questions.get("opener", "Tell me more about that.")
            # Personalize with name if available
            name = extracted_data.get("contact_info", {}).get("fullName", "there")
            
            # Special case: if we already have the name but not email, adjust the opener
            if phase == "introduction" and name != "there" and "email" in missing_data:
                return f"Great! I'll need your email address to include in the media kit. What's the best email for podcast hosts to reach you? Also, if you have a LinkedIn profile, please share the URL - I can analyze it to learn more about your expertise and save us both time!"
            
            # Special case: if we already have metrics/success story from LinkedIn, adjust core_discovery opener
            if phase == "core_discovery":
                stories = extracted_data.get('stories', [])
                has_metrics = any(
                    story.get('metrics') or 
                    any(char.isdigit() for char in story.get('result', '')) or
                    '$' in story.get('result', '') or '%' in story.get('result', '')
                    for story in stories
                )
                if has_metrics:
                    # Skip metrics request, ask about expertise instead
                    return "Great! Based on your impressive achievements, what would you say are your top 3-5 areas of expertise?"
            
            return opener.format(name=name)
        
        # Special handling for confirmation phase to avoid loops
        if phase == "confirmation":
            follow_ups = questions.get("follow_up", [])
            # Use follow-up questions in order, but don't repeat
            if message_count_in_phase - 1 < len(follow_ups) and message_count_in_phase > 0:
                return follow_ups[message_count_in_phase - 1]
            elif message_count_in_phase == len(follow_ups) + 1:
                # If we've asked all questions, transition to completion
                return "Excellent! I have everything needed to create your media kit and start finding podcast matches."
            elif message_count_in_phase > len(follow_ups) + 1:
                # Force transition if we're past all questions
                return self.get_transition_message("confirmation", "complete")
        
        # Special handling for introduction phase to ensure LinkedIn is asked early
        if phase == "introduction" and message_count_in_phase <= 3:
            follow_ups = questions.get("follow_up", [])
            # Check if we should ask LinkedIn question (index 0 in follow_ups)
            if message_count_in_phase == 1 and not self._has_social_media(extracted_data):
                return follow_ups[0]  # LinkedIn question
            # For other early introduction questions, use follow-ups in order
            elif message_count_in_phase - 1 < len(follow_ups):
                return follow_ups[message_count_in_phase - 1]
        
        # Check for missing critical data first
        if missing_data:
            # Avoid asking the same question twice by checking recent messages
            for data_point in missing_data:
                question = self._create_targeted_question(data_point, extracted_data)
                # If this isn't a generic fallback question, use it
                if not question.startswith("Can you tell me more about"):
                    return question
            # If all questions are generic, use the first one but make it more specific
            if missing_data:
                return self._create_targeted_question(missing_data[0], extracted_data)
        
        # Use follow-up questions
        follow_ups = questions.get("follow_up", [])
        question_index = min(message_count_in_phase - 1, len(follow_ups) - 1)
        if question_index >= 0 and question_index < len(follow_ups):
            return follow_ups[question_index]
        
        # Default to phase transition
        return self.get_transition_message(phase, self.phases[phase]["next_phase"])
    
    def _create_targeted_question(self, missing_data_point: str, context: Dict) -> str:
        """Create a specific question to collect missing data"""
        
        # Check if we already have LinkedIn
        has_linkedin = self._has_linkedin(context)
        
        targeted_questions = {
            "name": "What's your full name?",
            "email": "Perfect! I'll need your email address to include in the media kit. What's the best email for podcast hosts to reach you?" + (
                " Also, do you have a LinkedIn profile? If yes, please share your LinkedIn URL - I can analyze it to learn more about your expertise!" if not has_linkedin else ""
            ),
            "website": "Do you have a website? If yes, please share the full URL (e.g., www.yoursite.com).",
            "professional bio": "Can you tell me more about what you do professionally and your background?",
            "success story": "Can you share a specific example where your work made a measurable impact? Numbers and outcomes really help!",
            "expertise keywords": "Based on your experience, what are the main topics or areas of expertise you're known for?",
            "podcast topics": "What specific topics would you love to discuss on podcasts?",
            "target audience": "Who is your ideal listener - who would benefit most from your insights?",
            "achievements": "What's one achievement you're most proud of? Specific metrics make it compelling!",
            "unique value": "What unique perspective or approach do you bring that sets you apart?",
            "their success story or case study": "Can you share ONE specific success story where you made a significant impact? Please include any metrics or results.",
            "social media": "Do you have any professional social media profiles (LinkedIn, Twitter, etc.) you'd like to include? Please share the full URLs or handles."
        }
        
        return targeted_questions.get(missing_data_point, 
                                     f"Can you tell me more about {missing_data_point}?")
    
    def should_transition(self, current_phase: str, messages_count: int, 
                         extracted_data: Dict, completeness: Dict[str, bool]) -> Tuple[bool, Optional[str]]:
        """Determine if conversation should move to next phase based on data completeness"""
        
        phase_config = self.phases.get(current_phase)
        if not phase_config:
            return False, None
        
        # Get phase-specific completeness
        phase_complete = self._check_phase_data_complete(current_phase, completeness)
        
        # Force transition at max messages
        if messages_count >= phase_config["max_messages"]:
            return True, phase_config["next_phase"]
        
        # Transition if we have required data and minimum messages
        if phase_complete and messages_count >= phase_config["min_messages"]:
            return True, phase_config["next_phase"]
        
        return False, None
    
    def _check_phase_data_complete(self, phase: str, completeness: Dict[str, bool]) -> bool:
        """Check if phase-specific data requirements are met"""
        
        requirements = {
            "introduction": ["has_name", "has_email", "has_professional_bio"],
            "core_discovery": ["has_success_story", "has_expertise_keywords"],
            "media_focus": ["has_podcast_topics", "has_target_audience"],
            "confirmation": []  # No specific requirements for confirmation
        }
        
        phase_reqs = requirements.get(phase, [])
        if not phase_reqs:
            return True
        
        # Need at least 2/3 of requirements for phase completion
        met_requirements = sum(completeness.get(req, False) for req in phase_reqs)
        return met_requirements >= len(phase_reqs) * 0.66
    
    def calculate_progress(self, current_phase: str, completeness: Dict[str, bool]) -> int:
        """Calculate progress based on data completeness, not message count"""
        
        # Define critical data points and their weights
        data_weights = {
            "has_name": 5,
            "has_email": 10,
            "has_professional_bio": 15,
            "has_success_story": 15,
            "has_expertise_keywords": 10,
            "has_achievements": 10,
            "has_podcast_topics": 15,
            "has_target_audience": 10,
            "has_website": 5,
            "ready_for_media_kit": 5
        }
        
        # Calculate progress from data completeness
        total_progress = 0
        for data_point, weight in data_weights.items():
            if completeness.get(data_point, False):
                total_progress += weight
        
        # Add phase bonus
        if current_phase in self.phase_order:
            phase_index = self.phase_order.index(current_phase)
            # Add 5% for each completed phase
            total_progress += phase_index * 5
        
        return min(total_progress, 95)  # Cap at 95 until actually complete
    
    def get_transition_message(self, from_phase: str, to_phase: str) -> str:
        """Get a smooth transition message between phases"""
        
        transitions = {
            ("introduction", "core_discovery"): 
                "Great start! Now let's dive into what makes you an amazing podcast guest.",
            
            ("core_discovery", "media_focus"): 
                "Your expertise is impressive! Let's talk about how to position you for podcasts.",
            
            ("media_focus", "confirmation"): 
                "Perfect! Just a few final details to make your media kit complete.",
            
            ("confirmation", "complete"): 
                "Excellent! I have everything needed to create your media kit and start finding podcast matches."
        }
        
        return transitions.get((from_phase, to_phase), 
                              "Great! Let's move on to the next section.")
    
    def get_missing_critical_data(self, completeness: Dict[str, bool]) -> List[str]:
        """Get list of missing critical data points in priority order"""
        
        critical_order = [
            "has_name",
            "has_email", 
            "has_professional_bio",
            "has_success_story",
            "has_expertise_keywords",
            "has_podcast_topics",
            "has_target_audience",
            "has_achievements"
        ]
        
        missing = []
        for data_point in critical_order:
            if not completeness.get(data_point, False):
                # Convert to human-readable form
                readable = data_point.replace("has_", "").replace("_", " ")
                missing.append(readable)
        
        return missing
    
    def _has_social_media(self, extracted_data: Dict) -> bool:
        """Check if user has already provided social media links"""
        social_media = extracted_data.get('contact_info', {}).get('socialMedia', [])
        return len(social_media) > 0
    
    def _has_linkedin(self, extracted_data: Dict) -> bool:
        """Check if user has already provided LinkedIn URL"""
        social_media = extracted_data.get('contact_info', {}).get('socialMedia', [])
        for url in social_media:
            if 'linkedin.com' in url.lower():
                return True
        # Also check if LinkedIn was analyzed
        return bool(extracted_data.get('linkedin_analysis', {}).get('analysis_complete', False))
    
    def should_complete_early(self, completeness: Dict[str, bool], 
                            messages_count: int) -> bool:
        """Check if we can complete the conversation early"""
        
        # Need minimum data for early completion
        required_for_early = [
            completeness.get("has_name", False),
            completeness.get("has_email", False),
            completeness.get("has_professional_bio", False),
            completeness.get("has_expertise_keywords", False),
            completeness.get("has_success_story", False) or completeness.get("has_achievements", False),
            completeness.get("has_podcast_topics", False)
        ]
        
        # Need at least 10 messages and 90% of critical data
        has_enough_data = sum(required_for_early) >= len(required_for_early) * 0.9
        has_enough_messages = messages_count >= 10
        
        return has_enough_data and has_enough_messages