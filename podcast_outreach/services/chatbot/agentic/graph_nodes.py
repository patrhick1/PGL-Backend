# podcast_outreach/services/chatbot/agentic/graph_nodes.py

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from .graph_state import GraphState, GraphStateManager
from .state_manager import StateManager
from .message_classifier import MessageClassifier, ClassificationResult
from .bucket_manager import BucketManager
from .bucket_definitions import INFORMATION_BUCKETS
from .response_builder import ResponseBuilder

logger = logging.getLogger(__name__)

# Node functions for LangGraph

async def classification_node(state: GraphState) -> GraphState:
    """
    Classify the current message to extract intents and bucket updates
    
    This node:
    1. Takes the current message
    2. Runs it through the MessageClassifier
    3. Updates the state with classification results
    4. Determines the next action
    """
    try:
        # Initialize classifier
        classifier = MessageClassifier()
        
        # Create state manager from chatbot state
        state_manager = StateManager(
            conversation_id=state['chatbot_state'].get('session_id', 'default'),
            campaign_id=state['chatbot_state'].get('company_id', 'default'),
            person_id=state['chatbot_state']['person_id']
        )
        state_manager.state = state['chatbot_state']
        
        # Classify the message
        classification = await classifier.classify_message(
            message=state['current_message'],
            state=state_manager,
            context_window=5
        )
        
        # Update graph state
        state = GraphStateManager.update_after_classification(state, classification)
        
        # Log classification
        logger.info(
            f"Classified message - Intent: {classification.user_intent}, "
            f"Buckets: {list(classification.bucket_updates.keys())}, "
            f"Ambiguous: {classification.ambiguous}"
        )
        
        return state
        
    except Exception as e:
        logger.error(f"Error in classification node: {e}")
        state['error'] = f"Classification error: {str(e)}"
        state['error_count'] += 1
        state['last_error_timestamp'] = datetime.utcnow()
        state['next_action'] = 'error'
        return state


async def bucket_update_node(state: GraphState) -> GraphState:
    """
    Update buckets based on classification results
    
    This node:
    1. Takes classification results
    2. Updates the appropriate buckets
    3. Handles duplicates and corrections
    4. Updates the state with results
    5. Analyzes LinkedIn profile if provided
    """
    try:
        if not state['classification_result']:
            state['next_action'] = 'generate_response'
            return state
        
        # Initialize bucket manager
        manager = BucketManager()
        
        # Create state manager
        state_manager = StateManager(
            conversation_id=state['chatbot_state'].get('session_id', 'default'),
            campaign_id=state['chatbot_state'].get('company_id', 'default'),
            person_id=state['chatbot_state']['person_id']
        )
        
        # Restore state properly without losing bucket initialization
        if 'buckets' in state['chatbot_state']:
            from podcast_outreach.services.chatbot.agentic.state_manager import BucketEntry
            
            # Log what buckets we have from database
            db_buckets = list(state['chatbot_state']['buckets'].keys()) if state['chatbot_state']['buckets'] else []
            logger.info(f"Database has {len(db_buckets)} buckets: {db_buckets[:5]}...")
            logger.info(f"StateManager initialized with {len(state_manager.state['buckets'])} buckets")
            
            # Only update buckets that have data, keeping empty initialized buckets
            if state['chatbot_state']['buckets']:
                for bucket_id, entries in state['chatbot_state']['buckets'].items():
                    if bucket_id in state_manager.state['buckets'] and entries:
                        # Convert dict entries to BucketEntry objects
                        converted_entries = []
                        for entry in entries:
                            if isinstance(entry, dict):
                                converted_entries.append(BucketEntry(
                                    value=entry.get('value'),
                                    confidence=entry.get('confidence', 1.0),
                                    timestamp=datetime.fromisoformat(entry.get('timestamp', datetime.utcnow().isoformat())),
                                    source_message_index=entry.get('source_message_index', 0),
                                    is_corrected=entry.get('is_corrected', False)
                                ))
                            else:
                                converted_entries.append(entry)
                        state_manager.state['buckets'][bucket_id] = converted_entries
        
        # Copy other state fields
        for key in ['user_corrections', 'completion_signals', 'context_summary',
                    'last_updated', 'communication_style', 'is_reviewing', 
                    'awaiting_confirmation', 'completion_confirmed']:
            if key in state['chatbot_state']:
                state_manager.state[key] = state['chatbot_state'][key]
        
        # Convert messages from dicts to Message objects if needed
        if 'messages' in state['chatbot_state']:
            from podcast_outreach.services.chatbot.agentic.state_manager import Message
            converted_messages = []
            for msg in state['chatbot_state']['messages']:
                if isinstance(msg, dict):
                    converted_messages.append(Message(
                        role=msg.get('role', 'user'),
                        content=msg.get('content', ''),
                        timestamp=datetime.fromisoformat(msg.get('timestamp', datetime.utcnow().isoformat())),
                        metadata=msg.get('metadata', {})
                    ))
                else:
                    converted_messages.append(msg)
            state_manager.state['messages'] = converted_messages
        
        # Process the classification
        update_result = await manager.process_classification(
            classification=state['classification_result'],
            state=state_manager,
            user_message=state['current_message']
        )
        
        # Update chatbot state with new bucket values
        state['chatbot_state'] = state_manager.state
        
        # Update graph state
        state = GraphStateManager.update_after_bucket_update(state, update_result)
        
        # Log update results
        logger.info(
            f"Bucket update - Success: {update_result.success}, "
            f"Updated: {update_result.updated_buckets}, "
            f"Failed: {list(update_result.failed_buckets.keys())}, "
            f"Duplicates: {update_result.duplicates_prevented}"
        )
        
        # Check if LinkedIn URL was just provided
        if 'linkedin_url' in update_result.updated_buckets:
            linkedin_url = state_manager.get_bucket_value('linkedin_url')
            if linkedin_url:
                logger.info(f"LinkedIn URL provided: {linkedin_url}. Analyzing profile...")
                
                # Import LinkedIn analyzer
                from podcast_outreach.services.chatbot.linkedin_analyzer import LinkedInAnalyzer
                analyzer = LinkedInAnalyzer()
                
                try:
                    # Analyze the LinkedIn profile
                    analysis_results = await analyzer.analyze_profile(linkedin_url)
                    
                    if analysis_results:
                        logger.info(f"LinkedIn analysis successful. Extracted data: {list(analysis_results.keys())}")
                        
                        # Pre-fill buckets with LinkedIn data
                        linkedin_updates = {}
                        
                        # Map LinkedIn data to buckets
                        if analysis_results.get('professional_bio'):
                            linkedin_updates['professional_bio'] = analysis_results['professional_bio']
                        
                        if analysis_results.get('expertise_keywords'):
                            linkedin_updates['expertise_keywords'] = analysis_results['expertise_keywords']
                        
                        if analysis_results.get('years_experience'):
                            linkedin_updates['years_experience'] = analysis_results['years_experience']
                        
                        if analysis_results.get('success_stories'):
                            linkedin_updates['success_stories'] = analysis_results['success_stories']
                        
                        if analysis_results.get('podcast_topics'):
                            linkedin_updates['podcast_topics'] = analysis_results['podcast_topics']
                        
                        if analysis_results.get('unique_perspective'):
                            linkedin_updates['unique_perspective'] = analysis_results['unique_perspective']
                        
                        if analysis_results.get('target_audience'):
                            linkedin_updates['target_audience'] = analysis_results['target_audience']
                        
                        if analysis_results.get('key_achievements'):
                            linkedin_updates['achievements'] = analysis_results['key_achievements']
                        
                        # Update buckets with LinkedIn data
                        for bucket_id, value in linkedin_updates.items():
                            if bucket_id in INFORMATION_BUCKETS and not state_manager.get_bucket_value(bucket_id):
                                # Only update if bucket is empty
                                state_manager.update_bucket(bucket_id, value, confidence=0.8)
                                logger.info(f"Pre-filled {bucket_id} from LinkedIn analysis")
                        
                        # Store analysis results in chatbot state metadata for response generation
                        state_manager.state['linkedin_analysis'] = analysis_results
                        state_manager.state['linkedin_prefilled_buckets'] = list(linkedin_updates.keys())
                        
                        # Update chatbot state
                        state['chatbot_state'] = state_manager.state
                        
                        # Update successful extractions count
                        state['successful_extractions'] += len(linkedin_updates)
                    else:
                        logger.warning("LinkedIn analysis returned no results")
                        
                except Exception as e:
                    logger.error(f"Error analyzing LinkedIn profile: {e}")
                    # Continue without LinkedIn data
        
        return state
        
    except Exception as e:
        logger.error(f"Error in bucket update node: {e}")
        state['error'] = f"Bucket update error: {str(e)}"
        state['error_count'] += 1
        state['last_error_timestamp'] = datetime.utcnow()
        state['next_action'] = 'error'
        return state


async def response_generation_node(state: GraphState) -> GraphState:
    """
    Generate an appropriate response based on current state
    
    This node:
    1. Analyzes the current conversation state
    2. Determines the best response strategy
    3. Generates a contextual response
    4. Suggests next questions if needed
    """
    try:
        # Create state manager for analysis
        state_manager = StateManager(
            conversation_id=state['chatbot_state'].get('session_id', 'default'),
            campaign_id=state['chatbot_state'].get('company_id', 'default'),
            person_id=state['chatbot_state']['person_id']
        )
        state_manager.state = state['chatbot_state']
        
        # Use the new ResponseBuilder
        response_builder = ResponseBuilder()
        response = await response_builder.build_response(state, state_manager)
        
        # Ensure response is a string
        if not isinstance(response, str):
            logger.error(f"Response is not a string: {type(response)} - {response}")
            response = "Could you please provide your information?"
        
        # Ensure response quality
        response = response_builder.ensure_response_quality(response)
        
        # Update chatbot state from state manager (important for state changes in response builder)
        state['chatbot_state'] = state_manager.state
        
        # Update state
        state = GraphStateManager.update_after_response_generation(
            state, response, 'intelligent'
        )
        
        # Log response for debugging
        logger.info(f"Generated intelligent response (length: {len(response)} chars)")
        logger.info(f"Response has {response.count(chr(10))} newlines")
        logger.info(f"First 300 chars: {repr(response[:300])}")
        
        return state
        
    except Exception as e:
        logger.error(f"Error in response generation node: {e}")
        state['error'] = f"Response generation error: {str(e)}"
        state['error_count'] += 1
        state['last_error_timestamp'] = datetime.utcnow()
        state['next_action'] = 'error'
        return state


async def verification_node(state: GraphState) -> GraphState:
    """
    Verify ambiguous input or confirm user intent
    
    This node:
    1. Generates clarification questions
    2. Confirms critical data
    3. Resolves ambiguities
    """
    try:
        if not state['classification_result']:
            state['next_action'] = 'generate_response'
            return state
        
        classifier = MessageClassifier()
        
        # Generate clarification message
        clarification = classifier.create_clarification_message(
            state['classification_result']
        )
        
        # Set as response
        state['generated_response'] = clarification
        state['response_strategy'] = 'clarify'
        state['requires_verification'] = True
        state['next_action'] = 'complete'
        
        logger.info("Generated clarification request")
        
        return state
        
    except Exception as e:
        logger.error(f"Error in verification node: {e}")
        state['error'] = f"Verification error: {str(e)}"
        state['error_count'] += 1
        state['last_error_timestamp'] = datetime.utcnow()
        state['next_action'] = 'error'
        return state


async def completion_check_node(state: GraphState) -> GraphState:
    """
    Check if conversation can be completed
    
    This node:
    1. Validates all required buckets are filled
    2. Prepares completion summary
    3. Confirms with user
    """
    try:
        # Create state manager
        state_manager = StateManager(
            conversation_id=state['chatbot_state'].get('session_id', 'default'),
            campaign_id=state['chatbot_state'].get('company_id', 'default'),
            person_id=state['chatbot_state']['person_id']
        )
        
        # Restore state properly without losing bucket initialization
        if 'buckets' in state['chatbot_state']:
            from podcast_outreach.services.chatbot.agentic.state_manager import BucketEntry
            
            # Log what buckets we have from database
            db_buckets = list(state['chatbot_state']['buckets'].keys()) if state['chatbot_state']['buckets'] else []
            logger.info(f"Database has {len(db_buckets)} buckets: {db_buckets[:5]}...")
            logger.info(f"StateManager initialized with {len(state_manager.state['buckets'])} buckets")
            
            # Only update buckets that have data, keeping empty initialized buckets
            if state['chatbot_state']['buckets']:
                for bucket_id, entries in state['chatbot_state']['buckets'].items():
                    if bucket_id in state_manager.state['buckets'] and entries:
                        # Convert dict entries to BucketEntry objects
                        converted_entries = []
                        for entry in entries:
                            if isinstance(entry, dict):
                                converted_entries.append(BucketEntry(
                                    value=entry.get('value'),
                                    confidence=entry.get('confidence', 1.0),
                                    timestamp=datetime.fromisoformat(entry.get('timestamp', datetime.utcnow().isoformat())),
                                    source_message_index=entry.get('source_message_index', 0),
                                    is_corrected=entry.get('is_corrected', False)
                                ))
                            else:
                                converted_entries.append(entry)
                        state_manager.state['buckets'][bucket_id] = converted_entries
        
        # Copy other state fields
        for key in ['user_corrections', 'completion_signals', 'context_summary',
                    'last_updated', 'communication_style', 'is_reviewing', 
                    'awaiting_confirmation', 'completion_confirmed']:
            if key in state['chatbot_state']:
                state_manager.state[key] = state['chatbot_state'][key]
        
        # Convert messages from dicts to Message objects if needed
        if 'messages' in state['chatbot_state']:
            from podcast_outreach.services.chatbot.agentic.state_manager import Message
            converted_messages = []
            for msg in state['chatbot_state']['messages']:
                if isinstance(msg, dict):
                    converted_messages.append(Message(
                        role=msg.get('role', 'user'),
                        content=msg.get('content', ''),
                        timestamp=datetime.fromisoformat(msg.get('timestamp', datetime.utcnow().isoformat())),
                        metadata=msg.get('metadata', {})
                    ))
                else:
                    converted_messages.append(msg)
            state_manager.state['messages'] = converted_messages
        
        # Check required buckets
        empty_required = state_manager.get_empty_required_buckets()
        
        if empty_required:
            # Can't complete yet
            state['completion_feasible'] = False
            state['missing_required'] = empty_required
            
            # Generate message about missing info
            missing_names = [
                INFORMATION_BUCKETS[bid].name 
                for bid in empty_required[:3]  # Show max 3
            ]
            
            if len(empty_required) > 3:
                missing_text = ", ".join(missing_names[:2]) + f" and {len(empty_required)-2} more items"
            else:
                missing_text = ", ".join(missing_names[:-1]) + f" and {missing_names[-1]}" if len(missing_names) > 1 else missing_names[0]
            
            response = (
                f"I'd love to submit your information, but I still need a few required details: {missing_text}. "
                f"Would you like to provide these now, or would you prefer to continue later?"
            )
            
            state['generated_response'] = response
            state['response_strategy'] = 'incomplete_completion'
        else:
            # Can complete!
            state['completion_feasible'] = True
            
            # Generate summary
            filled_buckets = state_manager.get_filled_buckets()
            summary_parts = []
            
            # Key information summary
            if 'full_name' in filled_buckets:
                summary_parts.append(f"Name: {filled_buckets['full_name']}")
            if 'email' in filled_buckets:
                summary_parts.append(f"Email: {filled_buckets['email']}")
            if 'current_role' in filled_buckets:
                summary_parts.append(f"Role: {filled_buckets['current_role']}")
            
            summary = "\\n".join(summary_parts[:5])  # Show top 5 items
            
            response = (
                f"Great! I have all the required information. Here's a quick summary:\\n\\n"
                f"{summary}\\n\\n"
                f"Is everything correct? Type 'yes' to submit or let me know if you need to change anything."
            )
            
            state['generated_response'] = response
            state['response_strategy'] = 'confirm_completion'
            state['chatbot_state']['awaiting_confirmation'] = 'completion'
        
        state['next_action'] = 'complete'
        
        return state
        
    except Exception as e:
        logger.error(f"Error in completion check node: {e}")
        state['error'] = f"Completion check error: {str(e)}"
        state['error_count'] += 1
        state['last_error_timestamp'] = datetime.utcnow()
        state['next_action'] = 'error'
        return state


async def error_handling_node(state: GraphState) -> GraphState:
    """
    Handle errors gracefully
    
    This node:
    1. Logs errors
    2. Generates user-friendly error messages
    3. Attempts recovery
    """
    try:
        # Determine error response based on context
        if state['error_count'] > 3:
            response = (
                "I'm having some technical difficulties. "
                "Your information has been saved, and you can continue later. "
                "If this persists, please contact support."
            )
            state['conversation_momentum'] = 'stalled'
        else:
            response = (
                "I didn't quite catch that. Could you please rephrase? "
                "I'm here to collect your information for podcast appearances."
            )
        
        state['generated_response'] = response
        state['response_strategy'] = 'error_recovery'
        state['next_action'] = 'complete'
        
        return state
        
    except Exception as e:
        logger.error(f"Error in error handling node: {e}")
        # Final fallback
        state['generated_response'] = "I apologize, but I'm experiencing technical issues. Please try again later."
        state['next_action'] = 'complete'
        return state


# Helper functions

def _determine_response_strategy(state: GraphState, state_manager: StateManager) -> str:
    """Determine the best response strategy"""
    
    # Check if we should offer help
    if GraphStateManager.should_offer_help(state):
        return 'offer_help'
    
    # Check if reviewing
    if state['chatbot_state']['is_reviewing']:
        return 'review'
    
    # Check update results
    if state['update_result']:
        if state['update_result'].corrections_applied:
            return 'acknowledge_correction'
        elif state['update_result'].duplicates_prevented:
            return 'acknowledge_duplicate'
        elif state['update_result'].success:
            return 'acknowledge_and_continue'
    
    # Check empty buckets
    empty_required = state_manager.get_empty_required_buckets()
    if empty_required:
        return 'ask_required'
    
    # Optional buckets
    bucket_manager = BucketManager()
    suggestions = bucket_manager.suggest_next_buckets(state_manager)
    if suggestions:
        return 'ask_optional'
    
    # Default
    return 'general_prompt'


async def _generate_response(
    state: GraphState,
    state_manager: StateManager,
    strategy: str
) -> str:
    """Generate response based on strategy"""
    
    bucket_manager = BucketManager()
    
    if strategy == 'acknowledge_correction':
        corrected = state['update_result'].corrections_applied
        return f"Got it, I've updated that information. What else would you like to share?"
    
    elif strategy == 'acknowledge_duplicate':
        return "I already have that information, but thank you for confirming! What else can you tell me?"
    
    elif strategy == 'acknowledge_and_continue':
        # Smart acknowledgment based on what was provided
        updated = state['update_result'].updated_buckets
        if 'full_name' in updated:
            name = state_manager.get_bucket_value('full_name')
            return f"Nice to meet you, {name}! What's the best email for podcast hosts to reach you?"
        elif 'email' in updated:
            return "Perfect, I've got your email. Could you tell me about your current role and what you do?"
        else:
            return "Great! I've saved that information. What else would you like to share?"
    
    elif strategy == 'ask_required':
        # Ask for the next required bucket
        empty_required = state_manager.get_empty_required_buckets()
        suggestions = bucket_manager.suggest_next_buckets(state_manager)
        
        if suggestions and suggestions[0] in empty_required:
            bucket_id = suggestions[0]
            bucket_def = INFORMATION_BUCKETS[bucket_id]
            
            # Custom questions for specific buckets
            if bucket_id == 'full_name':
                return "Let's start with your name. What should I call you?"
            elif bucket_id == 'email':
                return "What's the best email address for podcast hosts to contact you?"
            elif bucket_id == 'professional_bio':
                return "Could you share a brief professional bio? Just 2-3 sentences about what you do."
            elif bucket_id == 'expertise_keywords':
                return "What are your main areas of expertise? (Please list 3-5 topics you could speak about)"
            else:
                return f"Could you provide your {bucket_def.name.lower()}?"
    
    elif strategy == 'ask_optional':
        # Ask for optional related information
        suggestions = bucket_manager.suggest_next_buckets(state_manager)
        if suggestions:
            bucket_id = suggestions[0]
            bucket_def = INFORMATION_BUCKETS[bucket_id]
            
            if bucket_id == 'linkedin_url':
                return "Would you like to share your LinkedIn profile URL? (Optional)"
            elif bucket_id == 'achievements':
                return "Any notable achievements or awards you'd like to mention? (Optional)"
            else:
                return f"Would you like to add your {bucket_def.name.lower()}? (Optional)"
    
    elif strategy == 'offer_help':
        return (
            "I notice we might be having some difficulty. Would you like me to guide you through "
            "the information I need step by step, or would you prefer to tell me in your own words?"
        )
    
    elif strategy == 'review':
        filled = state_manager.get_filled_buckets()
        summary_parts = []
        for bucket_id, value in list(filled.items())[:5]:
            bucket_name = INFORMATION_BUCKETS[bucket_id].name
            summary_parts.append(f"• {bucket_name}: {value}")
        
        summary = "\\n".join(summary_parts)
        return f"Here's what I have so far:\\n\\n{summary}\\n\\nWhat would you like to add or change?"
    
    # Default
    return "What other information would you like to share about yourself?"