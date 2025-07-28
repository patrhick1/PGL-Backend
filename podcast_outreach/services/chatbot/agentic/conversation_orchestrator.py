# podcast_outreach/services/chatbot/agentic/conversation_orchestrator.py

from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import json
import logging

from .graph_builder import compile_conversation_graph
from .graph_state import GraphState, create_initial_graph_state
from .state_manager import StateManager, ChatbotState

logger = logging.getLogger(__name__)

class ConversationOrchestrator:
    """
    Main orchestrator for agentic chatbot conversations using LangGraph
    
    This class:
    - Manages conversation flow through the graph
    - Handles state persistence
    - Provides async interface for message processing
    - Tracks analytics and performance
    """
    
    def __init__(self):
        """Initialize the conversation orchestrator"""
        self.graph = compile_conversation_graph()
        self._active_sessions: Dict[str, GraphState] = {}
    
    async def process_message(
        self,
        message: str,
        person_id: int,
        company_id: str,
        session_id: Optional[str] = None,
        existing_state: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Process a user message through the conversation graph
        
        Args:
            message: The user's message
            person_id: The person's ID
            company_id: The company ID
            session_id: Optional session ID for conversation continuity
            existing_state: Optional existing conversation state to restore
            
        Returns:
            Tuple of (response_message, updated_state_dict)
        """
        try:
            # Get or create session
            if session_id and session_id in self._active_sessions:
                graph_state = self._active_sessions[session_id]
                logger.info(f"Resuming session {session_id}")
            else:
                # Create new or restore from existing state
                if existing_state:
                    # Restore from saved state
                    logger.info(f"Existing state keys: {list(existing_state.keys())}")
                    if 'buckets' in existing_state:
                        bucket_count = len(existing_state.get('buckets', {}))
                        logger.info(f"Existing state has {bucket_count} buckets: {list(existing_state['buckets'].keys())[:5]}...")
                    
                    # Ensure all buckets are present
                    from .bucket_definitions import INFORMATION_BUCKETS
                    if 'buckets' not in existing_state:
                        existing_state['buckets'] = {}
                    
                    # Initialize missing buckets
                    for bucket_id in INFORMATION_BUCKETS:
                        if bucket_id not in existing_state['buckets']:
                            existing_state['buckets'][bucket_id] = []
                    
                    logger.info(f"After initialization, state has {len(existing_state['buckets'])} buckets")
                    
                    chatbot_state = ChatbotState(**existing_state)
                    graph_state = create_initial_graph_state(
                        person_id, company_id, chatbot_state
                    )
                    # Preserve db_extracted_data if available
                    if 'db_extracted_data' in existing_state:
                        graph_state['db_extracted_data'] = existing_state['db_extracted_data']
                    logger.info(f"Restored state for person {person_id}")
                else:
                    # Brand new conversation
                    graph_state = create_initial_graph_state(person_id, company_id)
                    logger.info(f"Started new conversation for person {person_id}")
                
                # Cache the session
                if session_id:
                    self._active_sessions[session_id] = graph_state
            
            # Update current message
            graph_state['current_message'] = message
            graph_state['current_message_timestamp'] = datetime.utcnow()
            graph_state['total_messages'] += 1
            
            # Add message to conversation history
            state_manager = StateManager(
                conversation_id=session_id or graph_state['chatbot_state']['session_id'],
                campaign_id=company_id,
                person_id=person_id
            )
            state_manager.state = graph_state['chatbot_state']
            state_manager.add_message("user", message)
            graph_state['chatbot_state'] = state_manager.state
            
            # Process through graph
            logger.info(f"Processing message through graph: '{message[:50]}...'")
            result = await self.graph.ainvoke(graph_state)
            
            # Extract response
            response = result.get('generated_response', "I'm sorry, I couldn't process that message. Could you please try again?")
            
            # Add assistant message to history
            state_manager.state = result['chatbot_state']
            state_manager.add_message("assistant", response)
            result['chatbot_state'] = state_manager.state
            
            # Update momentum
            result['conversation_momentum'] = self._calculate_momentum(result)
            
            # Cache updated state
            if session_id:
                self._active_sessions[session_id] = result
            
            # Prepare state for serialization
            serializable_state = self._prepare_state_for_storage(result['chatbot_state'])
            
            # Log analytics
            self._log_analytics(result)
            
            return response, serializable_state
            
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            
            # Return graceful error response
            error_response = (
                "I apologize, but I encountered an error processing your message. "
                "Your information has been saved, and you can continue where you left off."
            )
            
            # Return existing state if available
            if existing_state:
                return error_response, existing_state
            else:
                # Create minimal state
                minimal_state = {
                    'person_id': person_id,
                    'company_id': company_id,
                    'buckets': {},
                    'messages': [],
                    'last_updated': datetime.utcnow().isoformat()
                }
                return error_response, minimal_state
    
    async def get_conversation_summary(
        self,
        person_id: int,
        company_id: str,
        state_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Get a summary of the conversation state
        
        Args:
            person_id: The person's ID
            company_id: The company ID
            state_dict: The conversation state dictionary
            
        Returns:
            Summary dictionary with key information
        """
        try:
            # Create state manager to analyze
            state_manager = StateManager("summary", company_id, person_id)
            state_manager.state = ChatbotState(**state_dict)
            
            # Get filled buckets
            filled_buckets = state_manager.get_filled_buckets()
            empty_required = state_manager.get_empty_required_buckets()
            
            # Calculate completion percentage
            total_required = len([b for b in INFORMATION_BUCKETS.values() if b.required])
            filled_required = total_required - len(empty_required)
            completion_percentage = (filled_required / total_required * 100) if total_required > 0 else 0
            
            # Get quality scores
            from .bucket_manager import BucketManager
            bucket_manager = BucketManager()
            quality_scores = bucket_manager.get_bucket_quality_score(state_manager)
            
            # Build summary
            summary = {
                'person_id': person_id,
                'company_id': company_id,
                'completion_percentage': round(completion_percentage, 1),
                'filled_buckets': len(filled_buckets),
                'total_buckets': len(INFORMATION_BUCKETS),
                'empty_required_buckets': empty_required,
                'corrections_made': len(state_manager.state.get('user_corrections', [])),
                'messages_exchanged': len(state_manager.state.get('messages', [])),
                'is_complete': state_manager.state.get('is_complete', False),
                'key_information': {
                    'name': filled_buckets.get('full_name'),
                    'email': filled_buckets.get('email'),
                    'role': filled_buckets.get('current_role'),
                    'company': filled_buckets.get('company')
                },
                'quality_scores': {
                    bucket_id: round(score, 2) 
                    for bucket_id, score in quality_scores.items()
                },
                'last_updated': state_manager.state.get('last_updated', datetime.utcnow()).isoformat()
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return {
                'error': str(e),
                'person_id': person_id,
                'company_id': company_id
            }
    
    def clear_session(self, session_id: str) -> None:
        """Clear a cached session"""
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
            logger.info(f"Cleared session {session_id}")
    
    def clear_old_sessions(self, hours: int = 24) -> int:
        """Clear sessions older than specified hours"""
        cutoff = datetime.utcnow().timestamp() - (hours * 3600)
        cleared = 0
        
        for session_id in list(self._active_sessions.keys()):
            state = self._active_sessions[session_id]
            last_update = state.get('current_message_timestamp', datetime.utcnow())
            
            if last_update.timestamp() < cutoff:
                del self._active_sessions[session_id]
                cleared += 1
        
        logger.info(f"Cleared {cleared} old sessions")
        return cleared
    
    # Private helper methods
    
    def _calculate_momentum(self, state: GraphState) -> str:
        """Calculate conversation momentum"""
        from .graph_state import GraphStateManager
        return GraphStateManager.check_conversation_momentum(state)
    
    def _prepare_state_for_storage(self, chatbot_state: ChatbotState) -> Dict[str, Any]:
        """Prepare state for JSON serialization"""
        # Convert to dict
        state_dict = dict(chatbot_state)
        
        # Handle datetime serialization
        for key in ['created_at', 'last_updated']:
            if key in state_dict and isinstance(state_dict[key], datetime):
                state_dict[key] = state_dict[key].isoformat()
        
        # Handle bucket entries
        if 'buckets' in state_dict:
            serialized_buckets = {}
            for bucket_id, entries in state_dict['buckets'].items():
                serialized_entries = []
                for entry in entries:
                    if hasattr(entry, '__dict__'):
                        entry_dict = entry.__dict__.copy()
                        if 'timestamp' in entry_dict and isinstance(entry_dict['timestamp'], datetime):
                            entry_dict['timestamp'] = entry_dict['timestamp'].isoformat()
                        serialized_entries.append(entry_dict)
                    else:
                        serialized_entries.append(entry)
                serialized_buckets[bucket_id] = serialized_entries
            state_dict['buckets'] = serialized_buckets
        
        # Handle messages
        if 'messages' in state_dict:
            serialized_messages = []
            for msg in state_dict['messages']:
                if hasattr(msg, '__dict__'):
                    msg_dict = msg.__dict__.copy()
                    if 'timestamp' in msg_dict and isinstance(msg_dict['timestamp'], datetime):
                        msg_dict['timestamp'] = msg_dict['timestamp'].isoformat()
                    serialized_messages.append(msg_dict)
                else:
                    serialized_messages.append(msg)
            state_dict['messages'] = serialized_messages
        
        return state_dict
    
    def _log_analytics(self, state: GraphState) -> None:
        """Log analytics for monitoring"""
        logger.info(
            f"Conversation analytics - "
            f"Total messages: {state['total_messages']}, "
            f"Successful extractions: {state['successful_extractions']}, "
            f"Corrections: {state['corrections_made']}, "
            f"Momentum: {state['conversation_momentum']}, "
            f"Errors: {state['error_count']}"
        )