# podcast_outreach/services/chatbot/agentic/graph_state.py

from typing import TypedDict, Optional, Dict, Any, List
from datetime import datetime

from .state_manager import ChatbotState
from .message_classifier import ClassificationResult
from .bucket_manager import UpdateResult

class GraphState(TypedDict):
    """
    Enhanced state for LangGraph conversation orchestration
    
    This state flows through the graph nodes and accumulates
    information as the conversation progresses.
    """
    # Core conversation state from Phase 1
    chatbot_state: ChatbotState
    
    # Current interaction data
    current_message: str
    current_message_timestamp: datetime
    
    # Classification results from Phase 2
    classification_result: Optional[ClassificationResult]
    
    # Bucket update results
    update_result: Optional[UpdateResult]
    
    # Response generation
    response_strategy: Optional[str]  # 'ask_required', 'ask_related', 'clarify', 'confirm', 'complete'
    generated_response: Optional[str]
    suggested_questions: Optional[List[str]]
    
    # Flow control
    next_action: str  # 'classify', 'update', 'generate_response', 'verify', 'complete', 'error'
    requires_verification: bool
    verification_context: Optional[Dict[str, Any]]
    
    # Error handling
    error: Optional[str]
    error_count: int
    last_error_timestamp: Optional[datetime]
    
    # Completion tracking
    completion_requested: bool
    completion_feasible: bool
    missing_required: Optional[List[str]]
    
    # User experience tracking
    frustration_indicators: int  # Count of potential frustration signals
    conversation_momentum: str  # 'starting', 'flowing', 'stalled', 'completing'
    
    # Analytics
    total_messages: int
    successful_extractions: int
    corrections_made: int
    clarifications_needed: int
    
    # Database data (for complete summaries)
    db_extracted_data: Optional[Dict[str, Any]]


def create_initial_graph_state(
    person_id: int,
    company_id: str,
    chatbot_state: Optional[ChatbotState] = None
) -> GraphState:
    """
    Create initial graph state for a new conversation
    
    Args:
        person_id: The person's ID
        company_id: The company ID 
        chatbot_state: Optional existing chatbot state to restore
        
    Returns:
        Initialized GraphState
    """
    return GraphState(
        chatbot_state=chatbot_state or ChatbotState(
            buckets={},
            messages=[],
            user_corrections=[],
            completion_signals=[],
            context_summary="",
            person_id=person_id,
            company_id=company_id,
            session_id=f"{person_id}_{datetime.utcnow().isoformat()}",
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow(),
            is_complete=False,
            completion_confirmed=False,
            is_reviewing=False,
            awaiting_confirmation=None,
            communication_style={}
        ),
        current_message="",
        current_message_timestamp=datetime.utcnow(),
        classification_result=None,
        update_result=None,
        response_strategy=None,
        generated_response=None,
        suggested_questions=None,
        next_action='classify',
        requires_verification=False,
        verification_context=None,
        error=None,
        error_count=0,
        last_error_timestamp=None,
        completion_requested=False,
        completion_feasible=False,
        missing_required=None,
        frustration_indicators=0,
        conversation_momentum='starting',
        total_messages=0,
        successful_extractions=0,
        corrections_made=0,
        clarifications_needed=0,
        db_extracted_data=None
    )


class GraphStateManager:
    """Helper class for managing graph state updates"""
    
    @staticmethod
    def update_after_classification(
        state: GraphState,
        classification: ClassificationResult
    ) -> GraphState:
        """Update state after classification"""
        state['classification_result'] = classification
        
        # Determine next action based on classification
        if classification.ambiguous or classification.needs_clarification:
            state['next_action'] = 'verify'
            state['requires_verification'] = True
            state['clarifications_needed'] += 1
        elif classification.user_intent == 'completion':
            # Only allow completion if user has confirmed the profile review
            chatbot_state = state.get('chatbot_state', {})
            if chatbot_state.get('completion_confirmed'):
                state['next_action'] = 'check_completion'
                state['completion_requested'] = True
            else:
                # User said "complete" but hasn't reviewed yet - show review first
                state['next_action'] = 'generate_response'
                state['response_strategy'] = 'review'
        elif classification.user_intent == 'review':
            state['next_action'] = 'generate_response'
            state['response_strategy'] = 'review'
        elif classification.bucket_updates:
            state['next_action'] = 'update'
        else:
            state['next_action'] = 'generate_response'
        
        # Track frustration indicators
        if classification.user_intent == 'correction':
            state['frustration_indicators'] += 1
        
        return state
    
    @staticmethod
    def update_after_bucket_update(
        state: GraphState,
        update_result: UpdateResult
    ) -> GraphState:
        """Update state after bucket updates"""
        state['update_result'] = update_result
        
        if update_result.success:
            state['successful_extractions'] += len(update_result.updated_buckets)
            state['corrections_made'] += len(update_result.corrections_applied)
            
            # Good momentum if we're successfully extracting data
            if len(update_result.updated_buckets) >= 2:
                state['conversation_momentum'] = 'flowing'
        
        # Always generate response after update
        state['next_action'] = 'generate_response'
        
        return state
    
    @staticmethod
    def update_after_response_generation(
        state: GraphState,
        response: str,
        strategy: str
    ) -> GraphState:
        """Update state after generating response"""
        state['generated_response'] = response
        state['response_strategy'] = strategy
        state['next_action'] = 'complete'  # End of this interaction cycle
        
        return state
    
    @staticmethod
    def check_conversation_momentum(state: GraphState) -> str:
        """Analyze conversation momentum"""
        # Check various factors
        recent_success = state['successful_extractions'] > state['total_messages'] * 0.5
        low_errors = state['error_count'] < 2
        low_frustration = state['frustration_indicators'] < 3
        
        if state['completion_requested']:
            return 'completing'
        elif recent_success and low_errors and low_frustration:
            return 'flowing'
        elif state['error_count'] > 3 or state['frustration_indicators'] > 5:
            return 'stalled'
        else:
            return 'starting'
    
    @staticmethod
    def should_offer_help(state: GraphState) -> bool:
        """Determine if we should offer help or alternative approaches"""
        return (
            state['conversation_momentum'] == 'stalled' or
            state['frustration_indicators'] > 3 or
            state['error_count'] > 2 or
            state['clarifications_needed'] > 3
        )