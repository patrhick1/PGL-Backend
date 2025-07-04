# podcast_outreach/services/chatbot/conversation_engine.py

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.queries import chatbot_conversations as conv_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor
from podcast_outreach.services.chatbot.improved_conversation_flows import ImprovedConversationFlowManager
from podcast_outreach.services.chatbot.mock_interview_generator import MockInterviewGenerator
from podcast_outreach.services.chatbot.data_merger import DataMerger
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.services.chatbot.linkedin_analyzer import LinkedInAnalyzer
from podcast_outreach.services.campaigns.angles_generator import AnglesProcessorPG

logger = get_logger(__name__)

class ConversationEngine:
    def __init__(self, gemini_service: GeminiService = None):
        self.gemini_service = gemini_service or GeminiService()
        self.nlp_processor = EnhancedNLPProcessor()
        self.flow_manager = ImprovedConversationFlowManager()
        self.interview_generator = MockInterviewGenerator()
        self.data_merger = DataMerger()
        self.model_name = "gemini-2.0-flash"
        # Track asked questions per conversation
        self.conversation_states = {}
    
    async def create_conversation(self, campaign_id: str, person_id: int) -> Dict:
        """Create a new conversation session"""
        try:
            # Validate campaign exists
            campaign = await campaign_queries.get_campaign_by_id(UUID(campaign_id))
            if not campaign:
                raise ValueError("Campaign not found")
            
            # Create conversation
            conversation = await conv_queries.create_conversation(
                UUID(campaign_id), person_id, 'active', 'introduction'
            )
            
            if not conversation:
                raise ValueError("Failed to create conversation")
            
            # Get person info for personalization
            person = await people_queries.get_person_by_id_from_db(person_id)
            
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
            
            # Parse existing data
            messages = json.loads(conv['messages'])
            extracted_data = json.loads(conv['extracted_data'])
            metadata = json.loads(conv['conversation_metadata'])
            
            # Add user message
            messages.append({
                "type": "user",
                "content": message,
                "timestamp": datetime.utcnow().isoformat(),
                "phase": conv['conversation_phase']
            })
            
            # Process with NLP
            nlp_results = await self.nlp_processor.process(
                message, 
                messages, 
                extracted_data,
                conv.get('campaign_keywords') or []
            )
            
            # Check if this is a correction
            correction_indicators = ['for my', 'actually', 'correction', 'i meant', 'let me clarify', 'to be clear']
            is_correction = any(indicator in message.lower() for indicator in correction_indicators)
            
            # Update extracted data
            if is_correction and 'achievement' in message.lower():
                # Clear old achievements if this is a correction
                extracted_data['achievements'] = []
                extracted_data['stories'] = []  # Also clear stories as they might be related
            
            extracted_data = self._merge_extracted_data(extracted_data, nlp_results)
            
            # Store recent user responses for better context
            if 'recent_responses' not in extracted_data:
                extracted_data['recent_responses'] = []
            extracted_data['recent_responses'].append(message)
            # Keep only last 5 responses
            extracted_data['recent_responses'] = extracted_data['recent_responses'][-5:]
            
            # Check if user wants to complete the conversation
            completion_phrases = ['complete', 'done', 'finish', 'that\'s all', 'awesome', 'perfect', 'great']
            state = self._get_conversation_state(conversation_id)
            if (state["phase_states"].get("confirmation", {}).get("complete", False) and 
                any(phrase in message.lower() for phrase in completion_phrases)):
                # Complete the conversation
                await self.complete_conversation(conversation_id)
                return {
                    "bot_message": "Thank you! Your media kit is being created and we'll start finding podcast matches for you. You'll receive updates via email as we find great opportunities!",
                    "extracted_data": extracted_data,
                    "progress": 100,
                    "phase": "complete",
                    "completed": True,
                    "keywords_found": len(extracted_data.get('keywords', {}).get('explicit', [])),
                    "quick_replies": []
                }
            
            # Check for LinkedIn URL and analyze if not done yet
            linkedin_url = self._extract_linkedin_from_social(nlp_results)
            linkedin_processed = False
            
            if linkedin_url and not metadata.get('linkedin_analyzed'):
                # Add a processing message
                processing_message = {
                    "type": "bot",
                    "content": "I see you've shared your LinkedIn profile! Let me analyze it quickly to learn more about your expertise... This will just take a moment.",
                    "timestamp": datetime.utcnow().isoformat(),
                    "phase": conv['conversation_phase'],
                    "is_processing": True
                }
                messages.append(processing_message)
                
                # Update conversation to show processing
                await conv_queries.update_conversation(
                    UUID(conversation_id),
                    messages,
                    extracted_data,
                    metadata,
                    conv['conversation_phase'],
                    self.nlp_processor.calculate_progress(extracted_data)
                )
                
                try:
                    # Analyze LinkedIn profile
                    linkedin_analyzer = LinkedInAnalyzer()
                    linkedin_data = await linkedin_analyzer.analyze_profile(linkedin_url)
                    
                    if linkedin_data and linkedin_data.get('analysis_complete'):
                        # Remove processing message
                        messages = [msg for msg in messages if not msg.get('is_processing')]
                        
                        # Merge LinkedIn data
                        extracted_data = self._merge_linkedin_insights(extracted_data, linkedin_data)
                        metadata['linkedin_analyzed'] = True
                        metadata['linkedin_analysis_timestamp'] = datetime.utcnow().isoformat()
                        linkedin_processed = True
                        
                except Exception as e:
                    logger.error(f"LinkedIn analysis failed: {e}")
                    # Remove processing message and continue normally
                    messages = [msg for msg in messages if not msg.get('is_processing')]
            
            # Save insights to separate table for analysis
            await self._save_insights(conversation_id, nlp_results)
            
            # Generate next question based on phase and gaps
            next_message, new_phase, progress = await self._generate_next_question(
                conversation_id,
                conv['conversation_phase'],
                messages,
                extracted_data,
                metadata,
                conv['full_name']
            )
            
            # If LinkedIn was just processed, create a detailed feedback message
            if linkedin_processed:
                linkedin_insights = self._format_linkedin_insights(extracted_data.get('linkedin_analysis', {}))
                linkedin_success = f"Great! I've analyzed your LinkedIn profile. Here's what I learned about you:\n\n{linkedin_insights}\n\nIf any of this needs updating, just let me know! Otherwise, let me continue with a few more specific questions.\n\n"
                next_message = linkedin_success + next_message
            
            # Add bot message
            messages.append({
                "type": "bot",
                "content": next_message,
                "timestamp": datetime.utcnow().isoformat(),
                "phase": new_phase
            })
            
            # Update conversation
            await conv_queries.update_conversation(
                UUID(conversation_id),
                messages,
                extracted_data,
                metadata,
                new_phase,
                progress
            )
            
            # Auto-save to campaign if enough data
            if len(messages) % 10 == 0:
                await self._auto_save_to_campaign(conv['campaign_id'], extracted_data)
            
            return {
                "bot_message": next_message,
                "extracted_data": extracted_data,
                "progress": progress,
                "phase": new_phase,
                "keywords_found": len(extracted_data.get('keywords', {}).get('explicit', [])),
                "quick_replies": self._get_quick_replies(new_phase, extracted_data)
            }
            
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
            current_phase, messages_in_phase, extracted_data, completeness
        )
        
        if should_transition:
            current_phase = next_phase
            messages_in_phase = 0
        
        # Calculate progress with LinkedIn bonus
        progress = self.nlp_processor.calculate_progress(extracted_data)
        if has_linkedin:
            progress = min(progress + 15, 95)  # Add 15% bonus for LinkedIn
        
        # Check if confirmation phase is complete
        state = self._get_conversation_state(conversation_id)
        if state["phase_states"].get("confirmation", {}).get("complete", False):
            progress = 100
        
        # Check if we can complete early
        completion_readiness = self.nlp_processor.evaluate_completion_readiness(
            extracted_data, len(messages)
        )
        
        # Lower the message threshold if we have LinkedIn data
        if has_linkedin and len(messages) >= 8:  # Instead of 10
            completion_readiness["can_complete"] = True
        
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
    
    def _mark_question_asked(self, conversation_id: str, question: str, topic: str):
        """Mark a question as asked"""
        state = self._get_conversation_state(conversation_id)
        state["asked_questions"].add(question.lower()[:100])  # First 100 chars
        state["asked_topics"].add(topic.lower())
    
    def _check_if_data_exists(self, extracted_data: Dict, data_type: str) -> bool:
        """Check if we already have this type of data"""
        if data_type == "metrics":
            stories = extracted_data.get('stories', [])
            return any(
                story.get('metrics') or 
                any(char.isdigit() for char in story.get('result', '')) or
                '$' in story.get('result', '') or '%' in story.get('result', '')
                for story in stories
            )
        elif data_type == "email":
            return bool(extracted_data.get('contact_info', {}).get('email'))
        elif data_type == "promotion":
            # Check various places where promotion info might be stored
            return (
                bool(extracted_data.get('promotion_preferences')) or
                any('promot' in str(msg).lower() for msg in extracted_data.get('messages', [])) or
                any('book' in str(msg).lower() or 'course' in str(msg).lower() or 'service' in str(msg).lower() 
                    for msg in extracted_data.get('recent_responses', []))
            )
        elif data_type == "contact_preference":
            # Check if scheduling preference exists
            return (
                bool(extracted_data.get('scheduling_preference')) or
                'calendly' in str(extracted_data).lower() or
                'calendar' in str(extracted_data).lower()
            )
        return False
    
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
            
            # Check for duplicates before adding
            existing_stories = {(s.get('subject', ''), s.get('result', '')) for s in existing['stories']}
            for story in new_results['stories']:
                story_key = (story.get('subject', ''), story.get('result', ''))
                if story_key not in existing_stories:
                    existing['stories'].append(story)
                    existing_stories.add(story_key)
        
        # Append achievements with deduplication
        if 'achievements' in new_results:
            if 'achievements' not in existing:
                existing['achievements'] = []
            
            # Check for duplicates before adding
            existing_descs = {a.get('description', '') for a in existing['achievements']}
            for achievement in new_results['achievements']:
                if achievement.get('description', '') not in existing_descs:
                    existing['achievements'].append(achievement)
                    existing_descs.add(achievement.get('description', ''))
        
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
            existing_story_keys = {(s.get('subject', ''), s.get('result', '')) for s in existing_stories}
            
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
                if story.get('result'):
                    achievement_list.append(f"• {story['result']}")
            for achievement in achievements[:2]:
                if achievement.get('description'):
                    achievement_list.append(f"• {achievement['description']}")
            
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
        # Extract key information
        keywords = self._extract_all_keywords(extracted_data)[:10]
        stories = extracted_data.get('stories', [])
        expertise = extracted_data.get('keywords', {}).get('explicit', [])
        
        prompt = f"""Based on this conversation data, create a brief ideal podcast description (2-3 sentences):

Keywords: {', '.join(keywords)}
Expertise areas: {', '.join(expertise[:5])}
Number of stories shared: {len(stories)}

Create a compelling description that would help match this person with relevant podcasts:"""
        
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
        
        # Fallback description
        return f"Expert in {', '.join(expertise[:3])} with experience in {', '.join(keywords[:5])}"
    
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