# podcast_outreach/services/chatbot/agentic/response_builder.py

from typing import Dict, List, Optional, Any, Tuple
import re
import logging

from .response_strategies import (
    ResponseStrategyEngine, 
    ResponseStrategy, 
    ConversationStyle,
    StrategyContext
)
from .question_generator import IntelligentQuestionGenerator, GeneratedQuestion
from .response_templates import ResponseTemplates
from .state_manager import StateManager
from .graph_state import GraphState
from .bucket_definitions import INFORMATION_BUCKETS

logger = logging.getLogger(__name__)

class ResponseBuilder:
    """
    Builds complete, context-aware responses by combining strategies,
    questions, and templates
    """
    
    def __init__(self):
        self.strategy_engine = ResponseStrategyEngine()
        self.question_generator = IntelligentQuestionGenerator()
        self.templates = ResponseTemplates()
    
    def _build_complete_summary(self, filled_buckets: Dict[str, Any]) -> str:
        """Build a complete summary showing all collected information"""
        summary_parts = []
        
        # Track what we've added to avoid duplicates
        added_buckets = set()
        
        # CONTACT INFORMATION
        contact_info = []
        contact_buckets = ['full_name', 'email', 'phone', 'linkedin_url', 'website', 'social_media']
        for bucket_id in contact_buckets:
            if bucket_id in filled_buckets and filled_buckets[bucket_id] != "none":
                value = filled_buckets[bucket_id]
                bucket_name = INFORMATION_BUCKETS[bucket_id].name
                display_value = self._format_bucket_value(bucket_id, value)
                contact_info.append(f"• {bucket_name}: {display_value}")
                added_buckets.add(bucket_id)
        
        if contact_info:
            summary_parts.append("CONTACT INFORMATION:")
            summary_parts.extend(contact_info)
            summary_parts.append("")
        
        # PROFESSIONAL BACKGROUND
        professional_info = []
        professional_buckets = ['current_role', 'company', 'years_experience', 'professional_bio']
        for bucket_id in professional_buckets:
            if bucket_id in filled_buckets and filled_buckets[bucket_id] != "none":
                value = filled_buckets[bucket_id]
                bucket_name = INFORMATION_BUCKETS[bucket_id].name
                display_value = self._format_bucket_value(bucket_id, value)
                professional_info.append(f"• {bucket_name}: {display_value}")
                added_buckets.add(bucket_id)
        
        if professional_info:
            summary_parts.append("PROFESSIONAL BACKGROUND:")
            summary_parts.extend(professional_info)
            summary_parts.append("")
        
        # EXPERTISE & ACCOMPLISHMENTS
        expertise_info = []
        expertise_buckets = ['expertise_keywords', 'success_stories', 'achievements', 'unique_perspective']
        for bucket_id in expertise_buckets:
            if bucket_id in filled_buckets and filled_buckets[bucket_id] != "none":
                value = filled_buckets[bucket_id]
                bucket_name = INFORMATION_BUCKETS[bucket_id].name
                display_value = self._format_bucket_value(bucket_id, value)
                expertise_info.append(f"• {bucket_name}: {display_value}")
                added_buckets.add(bucket_id)
        
        if expertise_info:
            summary_parts.append("EXPERTISE & ACCOMPLISHMENTS:")
            summary_parts.extend(expertise_info)
            summary_parts.append("")
        
        # PODCAST FOCUS
        podcast_info = []
        podcast_buckets = ['podcast_topics', 'target_audience', 'key_message', 'speaking_experience', 'media_experience']
        for bucket_id in podcast_buckets:
            if bucket_id in filled_buckets and filled_buckets[bucket_id] != "none":
                value = filled_buckets[bucket_id]
                bucket_name = INFORMATION_BUCKETS[bucket_id].name
                display_value = self._format_bucket_value(bucket_id, value)
                podcast_info.append(f"• {bucket_name}: {display_value}")
                added_buckets.add(bucket_id)
        
        if podcast_info:
            summary_parts.append("PODCAST FOCUS:")
            summary_parts.extend(podcast_info)
            summary_parts.append("")
        
        # ADDITIONAL INFORMATION
        additional_info = []
        additional_buckets = ['scheduling_preference', 'promotion_items', 'interesting_hooks', 'controversial_takes', 'fun_fact']
        for bucket_id in additional_buckets:
            if bucket_id in filled_buckets and filled_buckets[bucket_id] != "none":
                value = filled_buckets[bucket_id]
                bucket_name = INFORMATION_BUCKETS[bucket_id].name
                display_value = self._format_bucket_value(bucket_id, value)
                additional_info.append(f"• {bucket_name}: {display_value}")
                added_buckets.add(bucket_id)
        
        # Add any remaining buckets that weren't categorized
        for bucket_id, value in filled_buckets.items():
            if bucket_id not in added_buckets and value != "none":
                bucket_name = INFORMATION_BUCKETS.get(bucket_id, {}).name if bucket_id in INFORMATION_BUCKETS else bucket_id
                display_value = self._format_bucket_value(bucket_id, value)
                additional_info.append(f"• {bucket_name}: {display_value}")
        
        if additional_info:
            summary_parts.append("ADDITIONAL INFORMATION:")
            summary_parts.extend(additional_info)
        
        # Remove trailing empty lines
        while summary_parts and summary_parts[-1] == "":
            summary_parts.pop()
        
        return "\n".join(summary_parts)
    
    def _format_bucket_value(self, bucket_id: str, value: Any) -> str:
        """Format a bucket value for display"""
        if value == "none":
            return "None provided"
        elif isinstance(value, list) and len(value) > 0:
            if bucket_id == 'expertise_keywords':
                return ", ".join(str(item) for item in value)
            elif bucket_id == 'podcast_topics':
                return "\n  " + "\n  ".join([f"{i+1}. {str(topic)}" for i, topic in enumerate(value)])
            elif bucket_id in ['success_stories', 'achievements']:
                return "\n  " + "\n  ".join([f"{i+1}. {str(item)}" for i, item in enumerate(value)])
            elif bucket_id == 'social_media':
                return "\n  " + "\n  ".join([f"- {str(item)}" for item in value])
            else:
                return ", ".join(str(item) for item in value)
        else:
            return str(value)
        
    async def build_response(
        self,
        state: GraphState,
        state_manager: StateManager
    ) -> str:
        """
        Build a complete response based on current state
        
        Args:
            state: Current graph state
            state_manager: State manager with conversation history
            
        Returns:
            Complete response string
        """
        # Debug logging
        logger.info(f"build_response - awaiting_confirmation: {state_manager.state.get('awaiting_confirmation')}")
        logger.info(f"build_response - current_message: {state.get('current_message', '')}")
        logger.info(f"build_response - is_reviewing: {state_manager.state.get('is_reviewing')}")
        logger.info(f"build_response - completion_confirmed: {state_manager.state.get('completion_confirmed')}")
        logger.info(f"build_response - state keys: {list(state_manager.state.keys())}")
        classification = state.get('classification_result')
        if classification:
            logger.info(f"build_response - user_intent: {classification.user_intent}")
        
        # Check if we're in a confirmation state and user is responding
        if state_manager.state.get('awaiting_confirmation') == 'profile_review':
            classification = state.get('classification_result')
            if classification:
                # User is responding to the profile review
                if classification.user_intent in ['completion', 'acknowledgment', 'affirmation']:
                    logger.info("User confirmed profile - ready for completion")
                    state_manager.state['completion_confirmed'] = True
                    state_manager.state['awaiting_confirmation'] = None
                    # Update the chatbot state immediately
                    state['chatbot_state'] = state_manager.state
                    return "Perfect! Your profile is now complete. Click the 'Complete' button to finalize your media kit. This will include your professional bio, suggested podcast topics, and all the information needed for podcast hosts. Thank you for taking the time to share your expertise!"
                elif classification.user_intent == 'correction' or classification.bucket_updates:
                    # User wants to make changes
                    state_manager.state['is_reviewing'] = False
                    state_manager.state['awaiting_confirmation'] = None
                    # Update the chatbot state
                    state['chatbot_state'] = state_manager.state
                    # Let the normal flow handle the updates
                    logger.info("User wants to make changes during review")
                else:
                    # User said something else - remind them of the options
                    return "Please review your profile above. If everything looks correct, confirm to finalize. If you'd like to make changes, just tell me what you'd like to update."
        
        # Handle completion intent when not in review state
        classification = state.get('classification_result')
        if classification and classification.user_intent == 'completion' and not state_manager.state.get('awaiting_confirmation'):
            # User wants to complete but we haven't shown the full review yet
            # Check if we have database extracted data (more complete)
            db_data = state.get('db_extracted_data')
            if db_data:
                logger.info(f"User requested completion - showing full review from database")
                from .db_summary_builder import build_complete_summary_from_db
                summary = build_complete_summary_from_db(db_data)
                
                # Set awaiting_confirmation so the next response is handled properly
                state_manager.state['awaiting_confirmation'] = 'profile_review'
                state_manager.state['is_reviewing'] = True
                state['chatbot_state'] = state_manager.state
                
                return f"Here's your complete profile:\n\n{summary}\n\nEverything looks great! Would you like to make any changes or would you like to finalize your media kit?"
            else:
                # Fall back to state data
                filled = state_manager.get_filled_buckets()
                if filled:
                    logger.info(f"User requested completion - showing full review from state")
                    summary = self._build_complete_summary(filled)
                    
                    # Check for missing required
                    empty_required = state_manager.get_empty_required_buckets()
                    
                    if empty_required:
                        missing_names = [INFORMATION_BUCKETS[bid].name for bid in empty_required[:3]]
                        missing_text = ", ".join(missing_names)
                        if len(empty_required) > 3:
                            missing_text += f" (and {len(empty_required) - 3} more)"
                        
                        return f"Here's what I have so far:\n\n{summary}\n\nStill need: {missing_text}\n\nWhat would you like to provide next?"
                    else:
                        # Set awaiting_confirmation
                        state_manager.state['awaiting_confirmation'] = 'profile_review'
                        state_manager.state['is_reviewing'] = True
                        state['chatbot_state'] = state_manager.state
                        
                        return f"Here's your complete profile:\n\n{summary}\n\nEverything looks great! Would you like to make any changes or would you like to finalize your media kit?"
        
        # Check if user is repeating they don't have an optional field
        classification = state.get('classification_result')
        if classification:
            # If no buckets were extracted and user is providing info
            if classification.user_intent == 'provide_info' and not classification.bucket_updates:
                # Check if the message indicates they don't have something
                message_lower = state.get('current_message', '').lower()
                negative_indicators = ["don't have", "dont have", "do not have", "no ", "none", "not applicable", "n/a"]
                
                if any(indicator in message_lower for indicator in negative_indicators):
                    # Get the strategy context to see what buckets we were asking about
                    strategy_context = self.strategy_engine.analyze_conversation_state(
                        state_manager, state, update_result
                    )
                    
                    # If we have priority buckets, mark the first optional one as skipped
                    if strategy_context.priority_buckets:
                        for bucket_id in strategy_context.priority_buckets:
                            bucket_def = INFORMATION_BUCKETS.get(bucket_id)
                            if bucket_def and not bucket_def.required:
                                logger.info(f"User repeated they don't have {bucket_id} - marking as skipped")
                                state_manager.mark_optional_bucket_skipped(bucket_id)
                                # Only mark the first one they're likely responding to
                                break
        
        # Handle review intent - let AI classification handle this
        if classification and classification.user_intent == 'review':
            logger.info("Handling review request - showing collected data")
            
            # Check if we have database extracted data (more complete)
            db_data = state.get('db_extracted_data')
            if db_data:
                logger.info(f"Using database data with {len(db_data)} fields for review")
                from .db_summary_builder import build_complete_summary_from_db
                summary = build_complete_summary_from_db(db_data)
                
                # Debug logging for newlines
                logger.info(f"Summary has {summary.count(chr(10))} newlines")
                logger.info(f"First 200 chars of summary: {repr(summary[:200])}")
                
                # When we have DB data, show complete profile regardless of state buckets
                # Set awaiting_confirmation so the next response is handled properly
                state_manager.state['awaiting_confirmation'] = 'profile_review'
                state_manager.state['is_reviewing'] = True
                
                full_response = f"Here's your complete profile:\n\n{summary}\n\nEverything looks great! Would you like to make any changes? Type 'looks good' or 'complete' to finalize your media kit."
                logger.info(f"Full response has {full_response.count(chr(10))} newlines")
                logger.info(f"First 200 chars of response: {repr(full_response[:200])}")
                
                return full_response
            else:
                # Fall back to state data
                filled = state_manager.get_filled_buckets()
                if filled:
                    logger.info(f"Using state data with {len(filled)} buckets for review")
                    summary = self._build_complete_summary(filled)
                    
                    # Only check for missing required if using state data
                    empty_required = state_manager.get_empty_required_buckets()
                    
                    if empty_required:
                        missing_names = [INFORMATION_BUCKETS[bid].name for bid in empty_required[:3]]
                        missing_text = ", ".join(missing_names)
                        if len(empty_required) > 3:
                            missing_text += f" (and {len(empty_required) - 3} more)"
                        
                        return f"Here's what I have so far:\n\n{summary}\n\nStill need: {missing_text}\n\nWhat would you like to provide next?"
                    else:
                        return f"Here's your complete profile:\n\n{summary}\n\nEverything looks great! Would you like to make any changes?"
                else:
                    return "I haven't collected any information yet. Let's start with your name!"
        
        # Analyze state and determine strategy
        strategy_context = self.strategy_engine.analyze_conversation_state(
            state, state_manager
        )
        logger.info(f"Strategy determined: {strategy_context.strategy}, priority buckets: {strategy_context.priority_buckets}")
        
        # Build response based on strategy
        if strategy_context.strategy == ResponseStrategy.WARM_WELCOME:
            return self._build_welcome_response(strategy_context)
        
        elif strategy_context.strategy == ResponseStrategy.ACKNOWLEDGE_PROGRESS:
            return await self._build_progress_response(
                state, state_manager, strategy_context
            )
        
        elif strategy_context.strategy == ResponseStrategy.GATHER_REQUIRED:
            return await self._build_gather_response(
                state_manager, strategy_context, required=True
            )
        
        elif strategy_context.strategy == ResponseStrategy.GATHER_OPTIONAL:
            return await self._build_gather_response(
                state_manager, strategy_context, required=False
            )
        
        elif strategy_context.strategy == ResponseStrategy.CLARIFY_AMBIGUOUS:
            return self._build_clarification_response(state, strategy_context)
        
        elif strategy_context.strategy == ResponseStrategy.COMPLETION_READY:
            return self._build_completion_response(state_manager, strategy_context)
        
        elif strategy_context.strategy == ResponseStrategy.COMPLETION_BLOCKED:
            return self._build_blocked_completion_response(
                state_manager, strategy_context
            )
        
        elif strategy_context.strategy == ResponseStrategy.ERROR_RECOVERY:
            return self._build_error_response(strategy_context)
        
        elif strategy_context.strategy == ResponseStrategy.CONVERSATION_RESCUE:
            return self._build_rescue_response(state_manager, strategy_context)
        
        else:
            # Default fallback
            return await self._build_gather_response(
                state_manager, strategy_context, required=True
            )
    
    def _build_welcome_response(self, context: StrategyContext) -> str:
        """Build welcome response"""
        return self.templates.get_template(
            'warm_welcome',
            style=context.style_adjustment
        )
    
    async def _build_progress_response(
        self,
        state: GraphState,
        state_manager: StateManager,
        context: StrategyContext
    ) -> str:
        """Build response that acknowledges progress and continues"""
        
        # If user just said "continue" or similar (no update_result), 
        # skip straight to asking the next question
        if not state.get('update_result'):
            if context.priority_buckets:
                logger.info(f"No update result - asking next question for: {context.priority_buckets}")
                question = await self._generate_next_question(state_manager, context)
                return question
            else:
                return "Is there anything else you'd like to add?"
        
        parts = []
        
        logger.info(f"Building progress response with update result")
        
        # Acknowledgment based on what was just provided
        if state.get('update_result'):
            update_result = state['update_result']
            
            # Check if LinkedIn was analyzed
            if 'linkedin_url' in update_result.updated_buckets and state_manager.state.get('linkedin_analysis'):
                # Simplified LinkedIn acknowledgment
                analysis = state_manager.state['linkedin_analysis']
                prefilled = state_manager.state.get('linkedin_prefilled_buckets', [])
                
                # Keep it brief
                parts.append(f"Excellent! I've analyzed your LinkedIn profile and extracted key information about your background and expertise.")
                
                # Log but don't add to response to keep it short
                logger.info(f"LinkedIn analysis prefilled: {prefilled}")
                # Don't return early - continue to ask next question
                
            elif update_result.corrections_applied:
                # Correction was made
                parts.append(self.templates.get_template(
                    'acknowledge_correction',
                    style=context.style_adjustment
                ))
            elif len(update_result.updated_buckets) > 1:
                # Multiple items provided
                bucket_names = [
                    INFORMATION_BUCKETS[bid].name 
                    for bid in update_result.updated_buckets
                ]
                formatted_items = self.templates.format_bucket_list(
                    bucket_names, 
                    context.style_adjustment or ConversationStyle.CASUAL
                )
                parts.append(self.templates.get_template(
                    'acknowledge_multiple',
                    style=context.style_adjustment,
                    items=formatted_items
                ))
            else:
                # Single item
                parts.append(self.templates.get_template(
                    'acknowledge_single',
                    style=context.style_adjustment
                ))
        
        # Progress update if needed
        if context.show_progress:
            filled = len(state_manager.get_filled_buckets())
            total_buckets = len(INFORMATION_BUCKETS)
            # Calculate percentage based on total buckets, not just required
            percent = int((filled / total_buckets) * 100) if total_buckets > 0 else 0
            # Cap at 100% to avoid confusion
            percent = min(100, percent)
            
            parts.append(self.templates.get_template(
                'progress_update',
                style=context.style_adjustment,
                percent=percent
            ))
        
        # Next question - ALWAYS ask if we have priority buckets
        if context.priority_buckets:
            logger.info(f"Generating next question for buckets: {context.priority_buckets}")
            
            # If parts is empty (no acknowledgment), we need to make sure we ask the question
            # This happens when user just says "continue" or similar
            
            question = await self._generate_next_question(
                state_manager, context
            )
            if question:
                parts.append(question)
            else:
                logger.error(f"No question generated for buckets: {context.priority_buckets}")
                # Fallback to direct question
                if context.priority_buckets[0] == 'current_role':
                    parts.append("What's your current role and job title?")
                else:
                    parts.append("Could you provide more information?")
        else:
            # Check if we still have empty required buckets
            empty_required = state_manager.get_empty_required_buckets()
            logger.warning(f"No priority buckets but empty required: {empty_required}")
            if empty_required:
                # Force asking for the next required bucket
                context.priority_buckets = empty_required[:1]
                question = await self._generate_next_question(
                    state_manager, context
                )
                parts.append(question)
            else:
                # Check for empty optional buckets before showing review
                empty_optional = state_manager.get_empty_optional_buckets()
                if empty_optional:
                    # Continue with optional buckets
                    logger.info(f"All required buckets filled - continuing with optional: {empty_optional[:3]}")
                    context.priority_buckets = empty_optional[:1]  # Ask one at a time
                    question = await self._generate_next_question(
                        state_manager, context
                    )
                    parts.append(question)
                else:
                    
                    # All buckets filled - show automatic review
                    logger.info("All buckets (required and optional) filled - showing automatic review")
                    filled = state_manager.get_filled_buckets()
                    logger.info(f"Total filled buckets: {len(filled)}")
                    logger.info(f"Filled bucket IDs: {list(filled.keys())}")
                    
                    if filled:
                        # Use the new complete summary builder
                        summary = self._build_complete_summary(filled)
                        
                        # Mark that we're awaiting confirmation
                        state_manager.state['awaiting_confirmation'] = 'profile_review'
                        state_manager.state['is_reviewing'] = True
                        state['chatbot_state'] = state_manager.state
                        
                        return f"Great! I've collected all the information I need. Here's your complete profile:\n\n{summary}\n\nPlease review everything carefully. If you'd like to make any changes or additions, just let me know! Otherwise, confirm to finalize your media kit."
                    else:
                        parts.append("Is there anything else you'd like to add?")
        
        final_response = ' '.join(parts)
        logger.info(f"Final progress response ({len(parts)} parts): {final_response[:100]}...")
        return final_response
    
    async def _build_gather_response(
        self,
        state_manager: StateManager,
        context: StrategyContext,
        required: bool
    ) -> str:
        """Build response for gathering information"""
        
        parts = []
        
        # Acknowledgment if we have previous info
        if context.acknowledge_previous:
            filled = state_manager.get_filled_buckets()
            if filled:
                parts.append(self.templates.get_template(
                    'acknowledge_single',
                    style=context.style_adjustment
                ))
        
        # Generate question
        question = await self._generate_next_question(state_manager, context)
        
        # Add transition if needed
        if parts and question:
            # We have acknowledgment, question is already a string
            # No need to add transition since _generate_next_question handles that
            parts.append(question)
        else:
            parts.append(question)
        
        return ' '.join(parts)
    
    def _build_clarification_response(
        self,
        state: GraphState,
        context: StrategyContext
    ) -> str:
        """Build clarification response"""
        
        classification = state.get('classification_result')
        if classification and classification.needs_clarification:
            clarification = classification.needs_clarification
        else:
            clarification = "could you provide more details?"
        
        return self.templates.get_template(
            'need_clarification',
            style=context.style_adjustment,
            clarification=clarification
        )
    
    def _build_completion_response(
        self,
        state_manager: StateManager,
        context: StrategyContext
    ) -> str:
        """Build completion confirmation response"""
        
        filled = state_manager.get_filled_buckets()
        # Use the comprehensive summary builder instead of templates.format_summary
        summary = self._build_complete_summary(filled)
        
        return self.templates.get_template(
            'completion_ready',
            style=context.style_adjustment,
            summary=summary
        )
    
    def _build_blocked_completion_response(
        self,
        state_manager: StateManager,
        context: StrategyContext
    ) -> str:
        """Build response when completion is blocked"""
        
        empty_required = state_manager.get_empty_required_buckets()
        
        # Format missing items
        missing_names = [
            INFORMATION_BUCKETS[bid].name
            for bid in empty_required[:3]  # Show max 3
        ]
        
        formatted_missing = self.templates.format_bucket_list(
            missing_names,
            context.style_adjustment or ConversationStyle.CASUAL
        )
        
        if len(empty_required) > 3:
            formatted_missing += f" ({len(empty_required) - 3} more)"
        
        return self.templates.get_template(
            'completion_blocked',
            style=context.style_adjustment,
            missing=formatted_missing
        )
    
    def _build_error_response(self, context: StrategyContext) -> str:
        """Build error recovery response"""
        return self.templates.get_template(
            'error_recovery',
            style=context.style_adjustment
        )
    
    def _build_rescue_response(
        self,
        state_manager: StateManager,
        context: StrategyContext
    ) -> str:
        """Build conversation rescue response"""
        return self.templates.get_template(
            'conversation_rescue',
            style=context.style_adjustment
        )
    
    async def _generate_next_question(
        self,
        state_manager: StateManager,
        context: StrategyContext
    ) -> str:
        """Generate the next question based on context"""
        
        # Check for user hints about specific information they want to provide
        messages = state_manager.state.get('messages', [])
        if messages:
            last_message = messages[-1]
            last_content = last_message.content if hasattr(last_message, 'content') else last_message.get('content', '')
            
            # Check for LinkedIn hint
            if 'linkedin' in last_content.lower():
                filled = state_manager.get_filled_buckets()
                if 'linkedin_url' not in filled:
                    return "Yes! Please share your LinkedIn profile URL - it helps podcast hosts learn more about your professional background."
        
        if not context.priority_buckets:
            # Check if we should proactively suggest LinkedIn
            filled = state_manager.get_filled_buckets()
            if 'email' in filled and 'linkedin_url' not in filled and 'phone' not in filled:
                # Prioritize LinkedIn after email
                return "Would you like to share your LinkedIn profile URL? It's optional but helps podcast hosts learn more about your professional background."
            return "Is there anything else you'd like to share?"
        
        # Get bucket contexts
        bucket_contexts = [
            self.strategy_engine.get_bucket_context(bucket_id, state_manager)
            for bucket_id in context.priority_buckets
        ]
        
        # Generate question
        question = self.question_generator.generate_question(
            context, state_manager, bucket_contexts
        )
        
        # Handle different return types
        if hasattr(question, 'question_text'):
            # It's a GeneratedQuestion object
            question_text = question.question_text
        elif isinstance(question, str):
            # It's already a string
            question_text = question
        else:
            # Fallback
            logger.error(f"Unexpected question type: {type(question)} - {question}")
            question_text = "What other information would you like to share?"
        
        # Ensure we return a string
        if not isinstance(question_text, str):
            logger.error(f"Question text is not a string: {type(question_text)} - {question_text}")
            return "What other information would you like to share?"
        
        return question_text
    
    def ensure_response_quality(self, response: str) -> str:
        """
        Ensure response meets quality standards
        
        - Not too long
        - Proper punctuation
        - No repeated words
        - Natural flow
        """
        # Log input for debugging
        logger.debug(f"ensure_response_quality input has {response.count(chr(10))} newlines")
        
        # Remove extra spaces while preserving newlines
        # Split by lines first, then clean each line
        lines = response.split('\n')
        cleaned_lines = []
        for line in lines:
            # Remove extra spaces within each line
            cleaned_line = ' '.join(line.split())
            cleaned_lines.append(cleaned_line)
        response = '\n'.join(cleaned_lines)
        
        # Log output for debugging
        logger.info(f"ensure_response_quality output has {response.count(chr(10))} newlines")
        logger.info(f"ensure_response_quality first 200 chars: {repr(response[:200])}")
        
        # Ensure ends with punctuation
        if response and response[-1] not in '.!?':
            response += '.'
        
        # Check length - but allow longer responses for summaries/reviews
        # A review/summary can be much longer than 300 chars
        if len(response) > 300 and "Here's your complete profile:" not in response and "Here's what I have so far:" not in response:
            # Find natural break point
            sentences = response.split('. ')
            if len(sentences) > 2:
                # Keep first 2 sentences
                response = '. '.join(sentences[:2]) + '.'
        
        # Remove repeated words while preserving newlines
        # Process each line separately to maintain formatting
        final_lines = []
        for line in response.split('\n'):
            if line.strip():  # Only process non-empty lines
                words = line.split()
                cleaned_words = []
                for i, word in enumerate(words):
                    if i == 0 or word.lower() != words[i-1].lower():
                        cleaned_words.append(word)
                final_lines.append(' '.join(cleaned_words))
            else:
                final_lines.append('')  # Preserve empty lines
        
        response = '\n'.join(final_lines)
        
        return response