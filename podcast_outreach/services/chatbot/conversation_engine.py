# podcast_outreach/services/chatbot/conversation_engine.py

import asyncio
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.queries import chatbot_conversations as conv_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import people as people_queries
# from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor  # REMOVED - legacy system
# from podcast_outreach.services.chatbot.improved_conversation_flows import ImprovedConversationFlowManager  # REMOVED - legacy system
from podcast_outreach.services.chatbot.mock_interview_generator import MockInterviewGenerator
from podcast_outreach.services.chatbot.data_merger import DataMerger
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.services.chatbot.linkedin_analyzer import LinkedInAnalyzer
from podcast_outreach.services.campaigns.angles_generator import AnglesProcessorPG

logger = get_logger(__name__)

class ConversationEngine:
    def __init__(self, gemini_service: GeminiService = None, use_ai: bool = False):
        self.gemini_service = gemini_service or GeminiService()
        # self.nlp_processor = EnhancedNLPProcessor()  # REMOVED - legacy system
        # self.flow_manager = ImprovedConversationFlowManager()  # REMOVED - legacy system
        self.interview_generator = MockInterviewGenerator()
        self.data_merger = DataMerger()
        self.model_name = "gemini-2.0-flash"
        # Track asked questions per conversation
        self.conversation_states = {}
        
        # AI integration layer removed - using agentic system exclusively
        
        # Initialize agentic adapter
        try:
            from podcast_outreach.services.chatbot.agentic.agentic_adapter import AgenticChatbotAdapter
            self.agentic_adapter = AgenticChatbotAdapter(
                gemini_service=self.gemini_service,
                fallback_enabled=True
            )
            logger.info("Agentic adapter initialized")
        except Exception as e:
            logger.warning(f"Could not initialize agentic adapter: {e}")
            self.agentic_adapter = None
    
    async def create_conversation(self, campaign_id: str, person_id: int) -> Dict:
        """Create a new conversation session"""
        try:
            # Validate campaign exists
            campaign = await campaign_queries.get_campaign_by_id(UUID(campaign_id))
            if not campaign:
                raise ValueError("Campaign not found")
            
            # Get person info
            person = await people_queries.get_person_by_id_from_db(person_id)
            
            # Try agentic system first
            if self.agentic_adapter:
                logger.info(f"Attempting to create conversation with agentic adapter for person {person_id}")
                agentic_result = await self.agentic_adapter.create_conversation(
                    campaign_id=campaign_id,
                    person_id=person_id,
                    person_data=person
                )
                
                if agentic_result:
                    logger.info(f"Agentic conversation created successfully")
                    # Create conversation with agentic data
                    conversation = await conv_queries.create_conversation(
                        UUID(campaign_id), person_id, 'active', 'introduction'
                    )
                    
                    if not conversation:
                        raise ValueError("Failed to create conversation")
                    
                    # Add initial message and metadata
                    messages = [{
                        "type": "bot",
                        "content": agentic_result['initial_message'],
                        "timestamp": datetime.utcnow().isoformat(),
                        "phase": "introduction"
                    }]
                    
                    metadata = {
                        "start_time": datetime.utcnow().isoformat(),
                        "is_agentic": True,
                        "use_agentic": agentic_result.get('use_agentic', True)
                    }
                    
                    await conv_queries.update_conversation(
                        conversation['conversation_id'],
                        messages,
                        {},  # extracted_data
                        metadata,
                        'introduction',
                        0  # progress
                    )
                    
                    return {
                        "conversation_id": str(conversation['conversation_id']),
                        "initial_message": agentic_result['initial_message'],
                        "estimated_time": "15-20 minutes"
                    }
                else:
                    logger.warning("Agentic adapter returned None, falling back to legacy")
            
            # Continue with legacy conversation creation
            logger.info("Creating conversation with legacy system")
            # Create conversation
            conversation = await conv_queries.create_conversation(
                UUID(campaign_id), person_id, 'active', 'introduction'
            )
            
            if not conversation:
                raise ValueError("Failed to create conversation")
            
            initial_message = self._generate_initial_message(
                person.get('full_name', 'there'),
                campaign.get('campaign_name', 'your campaign')
            )
            
            # Add initial message to conversation
            messages = [{
                "type": "bot",
                "content": initial_message,
                "timestamp": datetime.utcnow().isoformat(),
                "phase": "introduction"
            }]
            
            await conv_queries.update_conversation(
                conversation['conversation_id'],
                messages,
                {},  # extracted_data
                {"start_time": datetime.utcnow().isoformat()},  # metadata
                'introduction',
                0  # progress
            )
            
            return {
                "conversation_id": str(conversation['conversation_id']),
                "initial_message": initial_message,
                "estimated_time": "15-20 minutes"
            }
            
        except Exception as e:
            logger.exception(f"Error creating conversation: {e}")
            raise
    
    async def process_message(self, conversation_id: str, message: str) -> Dict:
        """Process a user message and generate response"""
        try:
            # Load conversation with campaign data
            conv = await conv_queries.get_conversation_with_campaign_data(UUID(conversation_id))
            if not conv:
                raise ValueError("Active conversation not found")
            
            # Try agentic system first
            if self.agentic_adapter:
                agentic_response = await self.agentic_adapter.process_message(
                    conversation_id=conversation_id,
                    message=message,
                    conversation_data=conv
                )
                
                if agentic_response:
                    # Update conversation with agentic response
                    messages = json.loads(conv['messages'])
                    messages.extend([
                        {
                            "type": "user",
                            "content": message,
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        {
                            "type": "bot",
                            "content": agentic_response['bot_message'],
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    ])
                    
                    # Update metadata with state flags from agentic response
                    metadata = json.loads(conv.get('conversation_metadata', '{}'))
                    
                    # Get metadata from agentic response
                    response_metadata = agentic_response.get('metadata', {})
                    
                    # Simple update - merge response metadata into existing metadata
                    # This preserves existing fields and adds/updates from response
                    metadata.update(response_metadata)
                    
                    # Also check top-level fields for backward compatibility
                    if 'awaiting_confirmation' in agentic_response:
                        metadata['awaiting_confirmation'] = agentic_response['awaiting_confirmation']
                    
                    await conv_queries.update_conversation(
                        UUID(conversation_id),
                        messages,
                        agentic_response.get('extracted_data', {}),
                        metadata,
                        agentic_response.get('phase', 'processing'),
                        agentic_response.get('progress', 0)
                    )
                    
                    return agentic_response
            
            # Agentic system is required
            raise ValueError("Agentic adapter not available")
            
        except Exception as e:
            logger.exception(f"Error processing message: {e}")
            raise
    
    async def complete_conversation(self, conversation_id: str) -> Dict:
        """Complete the conversation and process final data"""
        try:
            # Get full conversation
            conv = await conv_queries.get_conversation_by_id(UUID(conversation_id))
            if not conv:
                raise ValueError("Conversation not found")
            
            # Check if already completed
            if conv.get('status') == 'completed':
                logger.info(f"Conversation {conversation_id} is already completed")
                return {
                    "status": "already_completed",
                    "message": "This conversation has already been completed",
                    "keywords_extracted": 0,
                    "bio_generation_status": "skipped",
                    "bio_generation_message": "Skipped - conversation already completed",
                    "next_steps": ["view_media_kit"]
                }
            
            messages = json.loads(conv['messages'])
            extracted_data = json.loads(conv['extracted_data'])
            
            # Generate mock interview transcript
            transcript = await self.interview_generator.generate_transcript(
                messages, extracted_data
            )
            
            # Convert to questionnaire format for compatibility
            questionnaire_data = self._to_questionnaire_format(extracted_data)
            
            # Extract final keywords
            all_keywords = self._extract_all_keywords(extracted_data)
            questionnaire_keywords = all_keywords[:20]  # Limit to 20
            
            # Generate ideal podcast description
            ideal_description = await self._generate_ideal_podcast_description(
                extracted_data, transcript
            )
            
            # Update campaign with all data
            await campaign_queries.update_campaign_questionnaire_data(
                str(conv['campaign_id']),
                questionnaire_data,
                transcript,
                questionnaire_keywords,
                ideal_description
            )
            
            # Mark conversation as completed
            await conv_queries.complete_conversation(UUID(conversation_id))
            
            # Trigger bio and angles generation
            angles_processor = AnglesProcessorPG()
            bio_generation_result = None
            try:
                logger.info(f"Triggering bio/angles generation for campaign {conv['campaign_id']}")
                bio_generation_result = await angles_processor.process_campaign(str(conv['campaign_id']))
                bio_status = bio_generation_result.get("status", "error")
                bio_message = bio_generation_result.get("reason") or bio_generation_result.get("bio_doc_link") or "Processing completed."
                if bio_status == "success":
                    bio_message = f"Successfully generated Bio & Angles for campaign {conv['campaign_id']}"
                logger.info(f"Bio generation result: {bio_status} - {bio_message}")
            except Exception as bio_error:
                logger.error(f"Error generating bio/angles: {bio_error}")
                bio_message = f"Note: Bio generation failed - {str(bio_error)}"
                bio_status = "error"
            finally:
                angles_processor.cleanup()
            
            return {
                "status": "completed",
                "mock_interview_transcript": transcript,
                "keywords_extracted": len(questionnaire_keywords),
                "bio_generation_status": bio_status if bio_generation_result else "not_triggered",
                "bio_generation_message": bio_message if bio_generation_result else "Bio generation not triggered",
                "next_steps": ["create_media_kit"] if bio_status == "success" else ["generate_angles_bio", "create_media_kit"]
            }
            
        except Exception as e:
            logger.exception(f"Error completing conversation: {e}")
            raise
    
    def _generate_initial_message(self, name: str, campaign_name: str) -> str:
        """Generate personalized initial message"""
        return f"""Hi {name}! I'm excited to help you create an amazing media kit and find perfect podcast opportunities for {campaign_name}. 

This conversation will take about 15-20 minutes. I'll be asking about your work, expertise, and what makes you a great podcast guest. 

Feel free to share as much detail as you'd like - the more I learn about you, the better I can help position you for success!

Ready to get started?"""
    
    async def _generate_next_question(self, conversation_id: str, current_phase: str, 
                                    messages: List[Dict], extracted_data: Dict, 
                                    metadata: Dict, user_name: str) -> Tuple[str, str, int]:
        """Generate the next question based on conversation state and missing data"""
        
        # Check if LinkedIn data is available
        has_linkedin = bool(extracted_data.get('linkedin_analysis', {}).get('analysis_complete'))
        
        # Check data completeness with LinkedIn bonus
        completeness = await self.nlp_processor.check_data_completeness(extracted_data)
        
        # If we have LinkedIn data, mark certain fields as complete
        if has_linkedin:
            linkedin_data = extracted_data.get('linkedin_analysis', {})
            if linkedin_data.get('professional_bio'):
                completeness['has_professional_bio'] = True
            if linkedin_data.get('expertise_keywords'):
                completeness['has_expertise_keywords'] = True
            if linkedin_data.get('success_stories'):
                completeness['has_success_story'] = True
            if linkedin_data.get('podcast_topics'):
                completeness['has_podcast_topics'] = True
        
        # Check if we should transition phases
        messages_in_phase = self._count_messages_in_phase(messages, current_phase)
        should_transition, next_phase = self.flow_manager.should_transition(
            current_phase, extracted_data, metadata
        )
        
        if should_transition:
            current_phase = next_phase
            messages_in_phase = 0
        
        # Calculate progress with LinkedIn bonus
        progress = self.nlp_processor.calculate_progress(extracted_data)
        if has_linkedin:
            # LinkedIn helps with data but doesn't skip phases
            progress = min(progress + 10, 95)  # Reduced from 15
            
            # Track that we have LinkedIn data
            metadata['has_linkedin_data'] = True
            
            # DO NOT mark as ready to complete early
            # DO NOT skip to confirmation
        
        # Check if confirmation phase is complete
        state = self._get_conversation_state(conversation_id)
        if state["phase_states"].get("confirmation", {}).get("complete", False):
            progress = 100
        
        # Check if we can complete early
        completion_readiness = self.nlp_processor.evaluate_completion_readiness(
            extracted_data, len(messages)
        )
        
        # Remove aggressive LinkedIn completion logic
        # LinkedIn should enhance the conversation, not skip phases
        
        if completion_readiness["can_complete"] and current_phase != "confirmation":
            current_phase = "confirmation"
            messages_in_phase = 0
        
        # Get missing data for smart question generation
        missing_data = self.flow_manager.get_missing_critical_data(completeness)
        
        # Filter out data already provided by LinkedIn
        if has_linkedin:
            linkedin_provided = self._get_linkedin_provided_fields(extracted_data)
            missing_data = [item for item in missing_data if item not in linkedin_provided]
        
        # Generate smart question based on phase and missing data
        # First try flow manager with our enhanced checking
        logger.info(f"Getting next question for phase: {current_phase}, should_transition: {should_transition}, next_phase: {next_phase if should_transition else 'N/A'}")
        next_question = self.flow_manager.get_next_question(
            current_phase, messages, extracted_data, metadata, self._should_ask_question
        )
        
        # If flow manager returns a generic question, use smart question generation
        if not next_question or "What's your full name?" in next_question:
            # Check if we already have the name
            if self._check_if_data_exists(extracted_data, 'name'):
                # Skip to next question type
                next_question = self._get_smart_question(
                    conversation_id, current_phase, messages_in_phase, extracted_data, missing_data, has_linkedin
                )
            else:
                next_question = self._get_smart_question(
                    conversation_id, current_phase, messages_in_phase, extracted_data, missing_data, has_linkedin
                )
        
        return next_question, current_phase, progress
    
    def _count_messages_in_phase(self, messages: List[Dict], current_phase: str) -> int:
        """Count bot messages in the current phase"""
        count = 0
        
        # Count backwards from the most recent message
        for msg in reversed(messages):
            # Stop counting if we hit a different phase
            if msg.get("phase") and msg["phase"] != current_phase:
                break
            # Count bot messages in the current phase
            if msg.get("phase") == current_phase and msg["type"] == "bot":
                count += 1
        
        return count
    
    def _get_fallback_question(self, phase: str, extracted_data: Dict) -> str:
        """Get a fallback question if generation fails"""
        fallback_questions = {
            "introduction": [
                "What's the most exciting project you're working on right now?",
                "Tell me about your professional background.",
                "What inspired you to get into your field?"
            ],
            "core_discovery": [
                "Can you share a specific example of a challenge you've overcome?",
                "What's your biggest professional achievement so far?",
                "What unique insights do you bring to your industry?"
            ],
            "media_focus": [
                "Have you been on any podcasts before? How did it go?",
                "What topics do you feel most passionate about discussing?",
                "Who is your ideal audience or listener?"
            ],
            "confirmation": [
                "Is there anything else you'd like to add about your expertise?",
                "What's the main message you want podcast listeners to take away?",
                "How can podcast hosts best reach you?"
            ]
        }
        
        questions = fallback_questions.get(phase, fallback_questions["introduction"])
        # Select question based on what's missing
        return questions[len(extracted_data.get('stories', [])) % len(questions)]
    
    def _get_linkedin_provided_fields(self, extracted_data: Dict) -> List[str]:
        """Get list of fields already provided by LinkedIn"""
        linkedin_data = extracted_data.get('linkedin_analysis', {})
        provided_fields = []
        
        if linkedin_data.get('professional_bio'):
            provided_fields.extend(['professional bio', 'current work'])
        if linkedin_data.get('expertise_keywords'):
            provided_fields.append('expertise keywords')
        if linkedin_data.get('success_stories'):
            provided_fields.append('success story')
        if linkedin_data.get('podcast_topics'):
            provided_fields.append('podcast topics')
        if linkedin_data.get('unique_perspective'):
            provided_fields.append('unique value')
        if linkedin_data.get('target_audience'):
            provided_fields.append('target audience')
        
        return provided_fields
    
    def _get_conversation_state(self, conversation_id: str) -> Dict:
        """Get or create conversation state"""
        if conversation_id not in self.conversation_states:
            self.conversation_states[conversation_id] = {
                "asked_questions": set(),
                "asked_topics": set(),
                "phase_states": {
                    "introduction": {"summary_shown": False},
                    "core_discovery": {"summary_shown": False},
                    "media_focus": {"summary_shown": False},
                    "confirmation": {"summary_shown": False, "questions_asked": 0}
                }
            }
        return self.conversation_states[conversation_id]
    
    def _has_asked_about(self, conversation_id: str, topic: str) -> bool:
        """Check if we've already asked about this topic"""
        state = self._get_conversation_state(conversation_id)
        return topic.lower() in state["asked_topics"]
    
    def _mark_question_asked(self, conversation_id: str, question: str, topic: str, metadata: Dict = None):
        """Mark a question as asked with enhanced tracking"""
        state = self._get_conversation_state(conversation_id)
        state["asked_questions"].add(question.lower()[:100])  # First 100 chars
        state["asked_topics"].add(topic.lower())
        
        # Enhanced tracking in metadata
        if metadata is not None:
            if 'questions_asked' not in metadata:
                metadata['questions_asked'] = {}
            
            if topic not in metadata['questions_asked']:
                metadata['questions_asked'][topic] = {
                    'count': 0,
                    'first_asked': datetime.utcnow().isoformat(),
                    'responses': []
                }
            
            metadata['questions_asked'][topic]['count'] += 1
            metadata['questions_asked'][topic]['last_asked'] = datetime.utcnow().isoformat()
            metadata['questions_asked'][topic]['last_question'] = question
    
    # Define comprehensive mapping of question types to data fields
    QUESTION_TO_DATA_MAP = {
        'name': ['contact_info.fullName', 'fullName', 'professional_bio.fullName'],
        'email': ['contact_info.email', 'email'],
        'achievements': ['achievements', 'stories', 'linkedin_analysis.key_achievements'],
        'expertise': ['expertise_keywords', 'professional_bio.expertise_topics', 'linkedin_analysis.expertise_keywords'],
        'unique_value': ['unique_value', 'unique_perspective', 'linkedin_analysis.unique_perspective'],
        'podcast_topics': ['topics.suggested', 'topics_can_discuss', 'linkedin_analysis.podcast_topics', 'topics'],
        'target_audience': ['target_audience', 'linkedin_analysis.target_audience'],
        'professional_bio': ['professional_bio.about_work', 'linkedin_analysis.professional_bio'],
        'metrics': ['metrics', 'stories'],
        'promotion': ['promotion_preferences'],
        'contact_preference': ['scheduling_preference', 'contact_preference'],
        'linkedin': ['linkedin_analysis.analysis_complete', 'contact_info.linkedin_url'],
        'success_story': ['stories', 'linkedin_analysis.success_stories']
    }
    
    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """Get value from nested dictionary using dot notation"""
        keys = path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value
    
    def _check_if_data_exists(self, extracted_data: Dict, data_type: str) -> bool:
        """Check if we already have this type of data - comprehensive version"""
        # First check the mapping
        paths = self.QUESTION_TO_DATA_MAP.get(data_type, [])
        
        for path in paths:
            value = self._get_nested_value(extracted_data, path)
            if value:
                # Check if it's meaningful data
                if isinstance(value, list) and len(value) > 0:
                    # For achievements/stories, check if they have content
                    if data_type in ['achievements', 'success_story']:
                        return any(
                            (isinstance(item, dict) and (item.get('description') or item.get('result'))) or
                            (isinstance(item, str) and item.strip())
                            for item in value
                        )
                    return True
                elif isinstance(value, str) and value.strip():
                    return True
                elif isinstance(value, dict) and any(value.values()):
                    return True
        
        # Legacy specific checks
        if data_type == "metrics":
            stories = extracted_data.get('stories', [])
            for story in stories:
                if isinstance(story, dict):
                    result = story.get('result', '')
                    if any(char.isdigit() for char in str(result)) or '$' in str(result) or '%' in str(result):
                        return True
        
        return False
    
    def _should_ask_question(self, question_type: str, extracted_data: Dict, metadata: Dict) -> bool:
        """Determine if we should ask a specific question"""
        # Check if data already exists
        if self._check_if_data_exists(extracted_data, question_type):
            return False
        
        # Check if marked as unavailable
        if question_type in metadata.get('unavailable_fields', []):
            return False
        
        # Check attempt limit
        questions_asked = metadata.get('questions_asked', {})
        if question_type in questions_asked:
            attempts = questions_asked[question_type]['count']
            # Check if user explicitly declined
            if questions_asked[question_type].get('user_declined', False):
                return False
            # Required fields: 3 attempts, Optional fields: 2 attempts
            is_required = self._is_required_field(question_type)
            max_attempts = 3 if is_required else 2
            if attempts >= max_attempts:
                return False
        
        return True
    
    def _is_required_field(self, field_type: str) -> bool:
        """Check if a field is required"""
        required_fields = ['name', 'email', 'professional_bio', 'expertise', 'unique_value']
        return field_type in required_fields
    
    def _determine_field_from_context(self, message: str, current_phase: str, messages: List[Dict]) -> Optional[str]:
        """Determine which field the user is referring to based on context"""
        message_lower = message.lower()
        
        # Look at the last bot question to understand context
        last_bot_question = ""
        for msg in reversed(messages[-5:]):  # Check last 5 messages
            if msg.get('type') == 'bot':
                last_bot_question = msg.get('content', '').lower()
                break
        
        # Map keywords to field types
        field_indicators = {
            'achievements': ['achievement', 'accomplish', 'proud of', 'success', 'win'],
            'metrics': ['metric', 'number', 'measure', 'specific', 'result', 'statistic'],
            'podcast_topics': ['topic', 'discuss', 'talk about', 'podcast'],
            'expertise': ['expertise', 'expert', 'specialize', 'skill'],
            'unique_value': ['unique', 'different', 'perspective', 'approach'],
            'promotion': ['promote', 'book', 'course', 'service', 'product'],
            'experience': ['experience', 'previous', 'speaking', 'podcast experience'],
            'linkedin': ['linkedin', 'profile', 'social media', 'online presence']
        }
        
        # Check message and last question for field indicators
        for field_type, keywords in field_indicators.items():
            if any(keyword in message_lower for keyword in keywords):
                return field_type
            if any(keyword in last_bot_question for keyword in keywords):
                return field_type
        
        # Phase-specific defaults
        if current_phase == 'core_discovery' and 'achievement' in last_bot_question:
            return 'achievements'
        elif current_phase == 'media_focus' and 'topic' in last_bot_question:
            return 'podcast_topics'
        
        return None
    
    def _get_smart_question(self, conversation_id: str, phase: str, messages_in_phase: int, 
                           extracted_data: Dict, missing_data: List[str], 
                           has_linkedin: bool) -> str:
        """Generate intelligent questions based on LinkedIn data and gaps"""
        
        state = self._get_conversation_state(conversation_id)
        phase_state = state["phase_states"].get(phase, {})
        
        # If we're in confirmation phase, handle summary and follow-ups properly
        if phase == "confirmation":
            # Show summary only once
            if messages_in_phase == 0 and not phase_state.get("summary_shown", False):
                summary = self._generate_conversation_summary(extracted_data)
                if summary:
                    state["phase_states"][phase]["summary_shown"] = True
                    return f"We're almost done! Here's a summary of what I've learned about you for your media kit:\n\n{summary}\n\nIs there anything you'd like to add or change?"
            
            # After summary, ask follow-up questions if needed
            questions_asked = phase_state.get("questions_asked", 0)
            
            # Check if we need promotion info
            if not self._check_if_data_exists(extracted_data, "promotion") and not self._has_asked_about(conversation_id, "promotion"):
                self._mark_question_asked(conversation_id, "promotion question", "promotion")
                state["phase_states"][phase]["questions_asked"] = questions_asked + 1
                return "Is there anything specific you'd like to promote (book, course, service)?"
            
            # Check if we need contact preference
            if not self._check_if_data_exists(extracted_data, "contact_preference") and not self._has_asked_about(conversation_id, "contact_preference"):
                self._mark_question_asked(conversation_id, "contact preference", "contact_preference")
                state["phase_states"][phase]["questions_asked"] = questions_asked + 1
                return "What's the best way for podcast hosts to contact you for scheduling?"
            
            # All done - mark phase as complete
            state["phase_states"][phase]["complete"] = True
            return "Excellent! I have everything needed to create your media kit and start finding podcast matches. Type 'complete' to finalize your information, or let me know if you'd like to add anything else."
        
        # If we have LinkedIn, check if we should ask about metrics
        if has_linkedin and phase == "core_discovery":
            linkedin_data = extracted_data.get('linkedin_analysis', {})
            
            # Only ask for metrics if we don't already have them
            if (linkedin_data.get('success_stories') and 
                not self._check_if_data_exists(extracted_data, "metrics") and
                not self._has_asked_about(conversation_id, "metrics")):
                self._mark_question_asked(conversation_id, "metrics question", "metrics")
                return "I see from your LinkedIn profile that you've had some impressive experiences. Can you share specific metrics or numbers from one of your biggest wins?"
            
            # Ask for deeper insights only if not asked before
            if (linkedin_data.get('expertise_keywords') and 
                messages_in_phase < 3 and 
                not self._has_asked_about(conversation_id, "insights")):
                keywords = linkedin_data['expertise_keywords'][:3]
                self._mark_question_asked(conversation_id, "insights question", "insights")
                return f"Based on your expertise in {', '.join(keywords)}, what's one counterintuitive insight you've gained that most people miss?"
        
        # Otherwise use the standard flow
        return self.flow_manager.get_next_question(
            phase, messages_in_phase, extracted_data, missing_data
        )
    
    def _merge_extracted_data(self, existing: Dict, new_results: Dict) -> Dict:
        """Merge newly extracted data with existing data"""
        # The enhanced NLP processor returns data in the legacy format already
        # so we just need to merge intelligently
        
        # Merge keywords
        if 'keywords' in new_results:
            if 'keywords' not in existing:
                existing['keywords'] = {'explicit': [], 'implicit': [], 'contextual': []}
            
            for ktype in ['explicit', 'implicit', 'contextual']:
                if ktype in new_results['keywords']:
                    existing['keywords'][ktype].extend(new_results['keywords'][ktype])
                    # Remove duplicates while preserving order
                    existing['keywords'][ktype] = list(dict.fromkeys(existing['keywords'][ktype]))[:20]
        
        # Merge contact info
        if 'contact_info' in new_results:
            if 'contact_info' not in existing:
                existing['contact_info'] = {}
            existing['contact_info'].update(new_results['contact_info'])
        
        # Merge professional bio
        if 'professional_bio' in new_results:
            if 'professional_bio' not in existing:
                existing['professional_bio'] = {}
            existing['professional_bio'].update(new_results['professional_bio'])
        
        # Append stories with deduplication
        if 'stories' in new_results:
            if 'stories' not in existing:
                existing['stories'] = []
            
            # Ensure existing stories is a list
            if not isinstance(existing['stories'], list):
                existing['stories'] = []
            
            # Check for duplicates before adding
            existing_stories = set()
            for s in existing['stories']:
                if isinstance(s, dict):
                    existing_stories.add((s.get('subject', ''), s.get('result', '')))
                elif isinstance(s, str):
                    # Convert string to dict format
                    existing['stories'][existing['stories'].index(s)] = {'subject': s, 'result': ''}
                    existing_stories.add((s, ''))
            
            for story in new_results['stories']:
                if isinstance(story, dict):
                    story_key = (story.get('subject', ''), story.get('result', ''))
                    if story_key not in existing_stories:
                        existing['stories'].append(story)
                        existing_stories.add(story_key)
                elif isinstance(story, str) and (story, '') not in existing_stories:
                    # Convert string to dict format
                    existing['stories'].append({'subject': story, 'result': ''})
                    existing_stories.add((story, ''))
        
        # Append achievements with deduplication
        if 'achievements' in new_results:
            if 'achievements' not in existing:
                existing['achievements'] = []
            
            # Ensure existing achievements is a list
            if not isinstance(existing['achievements'], list):
                existing['achievements'] = []
            
            # Check for duplicates before adding
            existing_descs = set()
            for a in existing['achievements']:
                if isinstance(a, dict) and 'description' in a:
                    existing_descs.add(a['description'])
                elif isinstance(a, str):
                    # Convert string to dict format
                    existing['achievements'][existing['achievements'].index(a)] = {'description': a}
                    existing_descs.add(a)
            
            for achievement in new_results['achievements']:
                if isinstance(achievement, dict):
                    desc = achievement.get('description', '')
                    if desc and desc not in existing_descs:
                        existing['achievements'].append(achievement)
                        existing_descs.add(desc)
                elif isinstance(achievement, str) and achievement not in existing_descs:
                    # Convert string to dict format
                    existing['achievements'].append({'description': achievement})
                    existing_descs.add(achievement)
        
        # Update topics
        if 'topics' in new_results:
            if 'topics' not in existing:
                existing['topics'] = {'suggested': [], 'key_messages': ''}
            if 'suggested' in new_results['topics']:
                existing['topics']['suggested'].extend(new_results['topics']['suggested'])
                existing['topics']['suggested'] = list(set(existing['topics']['suggested']))
        
        # Update other fields
        for key in ['target_audience', 'unique_value', 'media_experience', 
                    'sample_questions', 'social_proof', 'promotion_preferences']:
            if key in new_results and new_results[key]:
                existing[key] = new_results[key]
        
        return existing
    
    async def _save_insights(self, conversation_id: str, nlp_results: Dict):
        """Save extracted insights for later analysis"""
        insights_to_save = []
        
        # Save keywords
        for keyword_type, keywords in nlp_results.get('keywords', {}).items():
            for keyword in keywords:
                insights_to_save.append({
                    'type': 'keyword',
                    'content': {"type": keyword_type, "value": keyword},
                    'confidence': nlp_results.get('confidence', 0.8)
                })
        
        # Save stories
        for story in nlp_results.get('stories', []):
            insights_to_save.append({
                'type': 'story',
                'content': story,
                'confidence': story.get('confidence', 0.7)
            })
        
        # Save insights if any
        if insights_to_save:
            await conv_queries.save_conversation_insights(UUID(conversation_id), insights_to_save)
    
    def _extract_linkedin_from_social(self, nlp_results: Dict) -> Optional[str]:
        """Extract LinkedIn URL from NLP results"""
        social_media = nlp_results.get('contact_info', {}).get('socialMedia', [])
        for url in social_media:
            if 'linkedin.com/in/' in url.lower():
                return url
        return None
    
    def _merge_linkedin_insights(self, extracted_data: Dict, linkedin_data: Dict) -> Dict:
        """Merge LinkedIn analysis results into extracted data"""
        if not linkedin_data:
            return extracted_data
        
        # Store the full analysis
        extracted_data['linkedin_analysis'] = linkedin_data
        
        # Update specific fields with LinkedIn data
        if linkedin_data.get('professional_bio') and not extracted_data.get('professional_bio', {}).get('about_work'):
            extracted_data.setdefault('professional_bio', {})['about_work'] = linkedin_data['professional_bio']
        
        if linkedin_data.get('expertise_keywords'):
            existing_keywords = extracted_data.get('keywords', {}).get('explicit', [])
            new_keywords = list(set(existing_keywords + linkedin_data['expertise_keywords']))[:20]
            extracted_data.setdefault('keywords', {})['explicit'] = new_keywords
        
        if linkedin_data.get('success_stories'):
            # Add stories without duplication
            existing_stories = extracted_data.setdefault('stories', [])
            existing_story_keys = set()
            for s in existing_stories:
                if isinstance(s, dict):
                    existing_story_keys.add((s.get('subject', ''), s.get('result', '')))
            
            for story in linkedin_data['success_stories']:
                new_story = {
                    'subject': story.get('title', ''),
                    'challenge': story.get('description', ''),
                    'result': story.get('impact', ''),
                    'confidence': 0.9  # High confidence from LinkedIn
                }
                story_key = (new_story['subject'], new_story['result'])
                if story_key not in existing_story_keys:
                    existing_stories.append(new_story)
                    existing_story_keys.add(story_key)
        
        if linkedin_data.get('podcast_topics'):
            extracted_data.setdefault('topics', {})['suggested'] = linkedin_data['podcast_topics']
        
        if linkedin_data.get('target_audience'):
            extracted_data['target_audience'] = linkedin_data['target_audience']
        
        if linkedin_data.get('unique_perspective'):
            extracted_data['unique_value'] = linkedin_data['unique_perspective']
        
        # CRITICAL: Merge LinkedIn achievements into achievements array
        if linkedin_data.get('key_achievements'):
            # Convert LinkedIn achievements to proper format
            achievements = extracted_data.setdefault('achievements', [])
            existing_descs = set()
            
            # Get existing descriptions
            for a in achievements:
                if isinstance(a, dict):
                    existing_descs.add(a.get('description', ''))
                elif isinstance(a, str):
                    existing_descs.add(a)
            
            # Add LinkedIn achievements
            for achievement_text in linkedin_data['key_achievements']:
                if achievement_text and achievement_text not in existing_descs:
                    achievements.append({
                        'description': achievement_text,
                        'source': 'linkedin',
                        'confidence': 0.9
                    })
                    existing_descs.add(achievement_text)
        
        return extracted_data
    
    def _format_linkedin_insights(self, linkedin_data: Dict) -> str:
        """Format LinkedIn insights for user feedback"""
        if not linkedin_data or not linkedin_data.get('analysis_complete'):
            return ""
        
        insights = []
        
        # Professional bio
        if linkedin_data.get('professional_bio'):
            insights.append(f"**Professional Background:**\n{linkedin_data['professional_bio']}")
        
        # Expertise areas
        if linkedin_data.get('expertise_keywords'):
            keywords = ", ".join(linkedin_data['expertise_keywords'][:5])
            insights.append(f"**Key Expertise Areas:** {keywords}")
        
        # Years of experience
        if linkedin_data.get('years_experience'):
            insights.append(f"**Years of Experience:** {linkedin_data['years_experience']}")
        
        # Key achievements
        if linkedin_data.get('key_achievements'):
            achievements = "\n• ".join(linkedin_data['key_achievements'][:3])
            insights.append(f"**Notable Achievements:**\n• {achievements}")
        
        # Podcast topics
        if linkedin_data.get('podcast_topics'):
            topics = "\n• ".join(linkedin_data['podcast_topics'][:3])
            insights.append(f"**Potential Podcast Topics:**\n• {topics}")
        
        # Target audience
        if linkedin_data.get('target_audience'):
            insights.append(f"**Target Audience:** {linkedin_data['target_audience']}")
        
        return "\n\n".join(insights)
    
    def _generate_conversation_summary(self, extracted_data: Dict) -> str:
        """Generate a comprehensive summary of collected data for user review"""
        summary_parts = []
        
        # Contact Information
        contact_info = extracted_data.get('contact_info', {})
        if contact_info:
            contact_summary = []
            if contact_info.get('fullName'):
                contact_summary.append(f"**Name:** {contact_info['fullName']}")
            if contact_info.get('email'):
                contact_summary.append(f"**Email:** {contact_info['email']}")
            if contact_info.get('website'):
                contact_summary.append(f"**Website:** {contact_info['website']}")
            if contact_info.get('socialMedia'):
                social_links = ", ".join(contact_info['socialMedia'][:3])
                contact_summary.append(f"**Social Media:** {social_links}")
            
            if contact_summary:
                summary_parts.append("**Contact Information:**\n" + "\n".join(contact_summary))
        
        # Professional Background
        prof_bio = extracted_data.get('professional_bio', {})
        if prof_bio.get('about_work'):
            summary_parts.append(f"**Professional Background:**\n{prof_bio['about_work']}")
        
        # Expertise & Keywords
        keywords = extracted_data.get('keywords', {}).get('explicit', [])
        if keywords:
            keyword_list = ", ".join(keywords[:8])
            summary_parts.append(f"**Areas of Expertise:**\n{keyword_list}")
        
        # Key Achievements & Stories
        stories = extracted_data.get('stories', [])
        achievements = extracted_data.get('achievements', [])
        
        if stories or achievements:
            achievement_list = []
            for story in stories[:2]:
                if isinstance(story, dict) and story.get('result'):
                    achievement_list.append(f"• {story['result']}")
                elif isinstance(story, str) and story:
                    achievement_list.append(f"• {story}")
            for achievement in achievements[:2]:
                if isinstance(achievement, dict) and achievement.get('description'):
                    achievement_list.append(f"• {achievement['description']}")
                elif isinstance(achievement, str) and achievement:
                    achievement_list.append(f"• {achievement}")
            
            if achievement_list:
                summary_parts.append("**Key Achievements:**\n" + "\n".join(achievement_list[:3]))
        
        # Podcast Topics
        topics = extracted_data.get('topics', {}).get('suggested', [])
        if not topics and extracted_data.get('linkedin_analysis', {}).get('podcast_topics'):
            topics = extracted_data['linkedin_analysis']['podcast_topics']
        
        if topics:
            topic_list = "\n".join([f"• {topic}" for topic in topics[:5]])
            summary_parts.append(f"**Podcast Topics:**\n{topic_list}")
        
        # Target Audience
        target_audience = extracted_data.get('target_audience')
        if target_audience:
            summary_parts.append(f"**Target Audience:**\n{target_audience}")
        
        # Unique Value Proposition
        unique_value = extracted_data.get('unique_value')
        if unique_value:
            summary_parts.append(f"**Unique Value:**\n{unique_value}")
        
        # Media Experience
        media_exp = extracted_data.get('media_experience', {})
        if media_exp.get('previous_podcasts'):
            summary_parts.append(f"**Previous Podcast Experience:**\n{media_exp['previous_podcasts']}")
        
        return "\n\n".join(summary_parts) if summary_parts else ""
    
    def _get_quick_replies(self, phase: str, extracted_data: Dict) -> List[str]:
        """Generate quick reply options based on conversation state"""
        if phase == "introduction":
            return ["Yes, let's start!", "Tell me more about the process", "How long will this take?"]
        elif phase == "core_discovery":
            return ["I have more examples", "That's all for now", "Can you give me an example?"]
        elif phase == "media_focus":
            return ["Yes, I've been on podcasts", "No podcast experience yet", "I do public speaking"]
        elif phase == "confirmation":
            return ["Looks good!", "I'd like to add something", "What happens next?"]
        return []
    
    def _to_questionnaire_format(self, extracted_data: Dict) -> Dict:
        """Convert chatbot data to existing questionnaire format"""
        return self.data_merger.merge_conversation_to_questionnaire(extracted_data)
    
    def _extract_all_keywords(self, extracted_data: Dict) -> List[str]:
        """Extract all unique keywords from the conversation"""
        all_keywords = []
        
        # Get keywords from all types
        for ktype in ['explicit', 'implicit', 'contextual']:
            keywords = extracted_data.get('keywords', {}).get(ktype, [])
            all_keywords.extend(keywords)
        
        # Add keywords from stories
        for story in extracted_data.get('stories', []):
            if 'keywords' in story:
                all_keywords.extend(story['keywords'])
        
        # Remove duplicates and return
        return list(dict.fromkeys(all_keywords))
    
    async def _generate_ideal_podcast_description(self, extracted_data: Dict, 
                                                transcript: str) -> str:
        """Generate ideal podcast description from conversation data"""
        # Check if user provided their ideal podcast description
        user_ideal_podcast = extracted_data.get('ideal_podcast', '')
        
        # Extract comprehensive information
        keywords = self._extract_all_keywords(extracted_data)[:10]
        stories = extracted_data.get('stories', [])
        expertise = extracted_data.get('keywords', {}).get('explicit', [])
        podcast_topics = extracted_data.get('podcast_topics', [])
        target_audience = extracted_data.get('target_audience', '')
        key_message = extracted_data.get('key_message', '')
        speaking_experience = extracted_data.get('speaking_experience', '')
        expertise_keywords = extracted_data.get('expertise_keywords', [])
        
        # Build comprehensive prompt
        prompt = f"""Create a specific 2-3 sentence description of the ideal podcast for this guest.

Guest Profile:
- Expertise: {', '.join(expertise_keywords[:5]) if expertise_keywords else ', '.join(expertise[:5])}
- Topics They Want to Discuss: {', '.join(podcast_topics[:5]) if podcast_topics else ', '.join(keywords[:5])}
- Their Target Audience: {target_audience or 'Not specified'}
- Core Message: {key_message or 'Not specified'}
- Speaking Experience: {speaking_experience or 'New to podcasting'}
"""

        # Add user's ideal podcast preference if provided
        if user_ideal_podcast:
            prompt += f"\nUser's Ideal Podcast Preference: {user_ideal_podcast}\n"
            prompt += "\nUse the user's preference as the foundation, but enhance it with specific details about show format, audience level, and host characteristics."
        else:
            prompt += "\nGenerate a description that specifies:"
            prompt += "\n1. The podcast's target audience and niche"
            prompt += "\n2. The show format that best suits their expertise (interview, panel, educational, etc.)"
            prompt += "\n3. The type of host/show that would create the best conversation"

        prompt += "\n\nBe specific about podcast characteristics, not just topic keywords."
        prompt += '\nExample: "Business podcasts targeting mid-level managers seeking practical leadership strategies, particularly interview-format shows that dive deep into real-world case studies and actionable frameworks. Ideal hosts are those who can facilitate discussions about organizational challenges and innovative management approaches."'
        
        try:
            response = await self.gemini_service.create_message(
                prompt=prompt,
                model=self.model_name,
                workflow="chatbot_ideal_description"
            )
            
            if response:
                return response.strip()
        except Exception as e:
            logger.error(f"Error generating ideal description: {e}")
        
        # Better fallback that uses user input if available
        if user_ideal_podcast:
            return user_ideal_podcast
        
        # Improved fallback description
        if podcast_topics and target_audience:
            return f"Podcasts focusing on {', '.join(podcast_topics[:3])} for {target_audience}, particularly shows that explore {key_message or 'practical insights and strategies'}."
        
        return f"Podcasts specializing in {', '.join(expertise[:3])} with audiences interested in {', '.join(keywords[:5])}"
    
    async def _auto_save_to_campaign(self, campaign_id: UUID, extracted_data: Dict):
        """Auto-save progress to campaign"""
        try:
            # Extract current keywords
            keywords = self._extract_all_keywords(extracted_data)[:10]
            
            # Update campaign keywords
            await campaign_queries.update_campaign_keywords(str(campaign_id), keywords)
            
            logger.info(f"Auto-saved {len(keywords)} keywords to campaign {campaign_id}")
        except Exception as e:
            logger.error(f"Error auto-saving to campaign: {e}")
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Get health status of chatbot systems"""
        health = {
            'legacy_system': 'operational',
            'agentic_system': 'not_initialized',
            'timestamp': datetime.utcnow().isoformat()
        }
        
        if self.agentic_adapter:
            health['agentic_system'] = 'operational'
            health['agentic_details'] = self.agentic_adapter.get_health_status()
        
        return health