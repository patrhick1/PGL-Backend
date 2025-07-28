# podcast_outreach/services/chatbot/agentic/response_strategies.py

from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from podcast_outreach.logging_config import get_logger
import re

from .state_manager import StateManager
from .bucket_definitions import INFORMATION_BUCKETS, BucketDefinition
from .graph_state import GraphState

class ConversationStyle(Enum):
    """User's communication style"""
    VERBOSE = "verbose"      # Provides lots of detail
    CONCISE = "concise"      # Short, direct answers
    TECHNICAL = "technical"  # Uses jargon, detailed
    CASUAL = "casual"        # Informal, friendly
    FORMAL = "formal"        # Professional, structured
    UNCERTAIN = "uncertain"  # Unsure, needs guidance

class ResponseStrategy(Enum):
    """Response strategies based on context"""
    WARM_WELCOME = "warm_welcome"
    GATHER_REQUIRED = "gather_required"
    GATHER_OPTIONAL = "gather_optional"
    CLARIFY_AMBIGUOUS = "clarify_ambiguous"
    ACKNOWLEDGE_PROGRESS = "acknowledge_progress"
    GENTLE_GUIDANCE = "gentle_guidance"
    COMPLETION_READY = "completion_ready"
    COMPLETION_BLOCKED = "completion_blocked"
    ERROR_RECOVERY = "error_recovery"
    CONVERSATION_RESCUE = "conversation_rescue"

@dataclass
class StrategyContext:
    """Context for strategy selection"""
    strategy: ResponseStrategy
    priority_buckets: List[str]
    group_questions: bool
    show_progress: bool
    offer_examples: bool
    acknowledge_previous: bool
    style_adjustment: Optional[ConversationStyle]
    reasoning: str

class ResponseStrategyEngine:
    """
    Determines optimal response strategies based on conversation state
    """
    
    def __init__(self):
        # Bucket groupings for natural questions
        self.bucket_groups = {
            'contact': ['email', 'phone', 'linkedin_url'],
            'background': ['current_role', 'company', 'years_experience'],
            'expertise': ['expertise_keywords', 'podcast_topics', 'unique_perspective'],
            'credibility': ['success_stories', 'achievements', 'speaking_experience'],
            'content': ['professional_bio', 'interesting_hooks', 'controversial_takes']
        }
        
        # Question limits based on style
        self.style_question_limits = {
            ConversationStyle.VERBOSE: 3,     # Can handle multiple questions
            ConversationStyle.CONCISE: 1,     # One at a time
            ConversationStyle.TECHNICAL: 2,   # Appreciates efficiency
            ConversationStyle.CASUAL: 2,      # Keep it light
            ConversationStyle.FORMAL: 2,      # Structured approach
            ConversationStyle.UNCERTAIN: 1    # Don't overwhelm
        }
    
    def analyze_conversation_state(
        self,
        state: GraphState,
        state_manager: StateManager
    ) -> StrategyContext:
        """
        Analyze current state and determine best response strategy
        
        Args:
            state: Current graph state
            state_manager: State manager with conversation history
            
        Returns:
            StrategyContext with recommended approach
        """
        # Detect conversation style
        style = self._detect_conversation_style(state, state_manager)
        
        # Get conversation metrics
        filled_buckets = state_manager.get_filled_buckets()
        empty_required = state_manager.get_empty_required_buckets()
        total_messages = len(state_manager.state['messages'])
        
        logger = get_logger(__name__)
        logger.info(f"Strategy analysis - Filled: {len(filled_buckets)}, Empty required: {len(empty_required)}, Messages: {total_messages}")
        
        # Check conversation momentum
        momentum = state.get('conversation_momentum', 'starting')
        frustration = state.get('frustration_indicators', 0)
        
        # First message - warm welcome
        if total_messages <= 2:
            return StrategyContext(
                strategy=ResponseStrategy.WARM_WELCOME,
                priority_buckets=['full_name'],
                group_questions=False,
                show_progress=False,
                offer_examples=True,
                acknowledge_previous=False,
                style_adjustment=style,
                reasoning="First interaction - warm welcome"
            )
        
        # High frustration - rescue mode
        if frustration > 3 or momentum == 'stalled':
            return StrategyContext(
                strategy=ResponseStrategy.CONVERSATION_RESCUE,
                priority_buckets=self._get_absolute_minimum_buckets(empty_required),
                group_questions=False,
                show_progress=True,
                offer_examples=True,
                acknowledge_previous=True,
                style_adjustment=ConversationStyle.CASUAL,
                reasoning="High frustration detected - switching to rescue mode"
            )
        
        # Completion requested
        if state.get('completion_requested', False):
            if empty_required:
                return StrategyContext(
                    strategy=ResponseStrategy.COMPLETION_BLOCKED,
                    priority_buckets=empty_required[:2],
                    group_questions=False,
                    show_progress=True,
                    offer_examples=False,
                    acknowledge_previous=True,
                    style_adjustment=style,
                    reasoning="Completion requested but missing required fields"
                )
            else:
                return StrategyContext(
                    strategy=ResponseStrategy.COMPLETION_READY,
                    priority_buckets=[],
                    group_questions=False,
                    show_progress=True,
                    offer_examples=False,
                    acknowledge_previous=False,
                    style_adjustment=style,
                    reasoning="Ready for completion"
                )
        
        # Need clarification
        if state.get('requires_verification', False):
            return StrategyContext(
                strategy=ResponseStrategy.CLARIFY_AMBIGUOUS,
                priority_buckets=[],
                group_questions=False,
                show_progress=False,
                offer_examples=True,
                acknowledge_previous=False,
                style_adjustment=style,
                reasoning="Ambiguous input needs clarification"
            )
        
        # Good progress - acknowledge and continue
        if len(filled_buckets) > 0 and momentum == 'flowing':
            next_buckets = self._get_next_logical_buckets(
                filled_buckets, empty_required, style
            )
            
            # If no next buckets from logical flow, check required first then optional
            if not next_buckets:
                if empty_required:
                    next_buckets = self._prioritize_required_buckets(
                        empty_required, filled_buckets
                    )[:1]  # Just one at a time
                else:
                    # No required left, suggest optional
                    optional = self._suggest_optional_buckets(filled_buckets, state_manager)
                    next_buckets = optional[:1] if optional else []
            
            return StrategyContext(
                strategy=ResponseStrategy.ACKNOWLEDGE_PROGRESS,
                priority_buckets=next_buckets,
                group_questions=self._should_group_questions(style, next_buckets),
                show_progress=len(filled_buckets) % 5 == 0,  # Every 5 buckets
                offer_examples=style == ConversationStyle.UNCERTAIN,
                acknowledge_previous=True,
                style_adjustment=style,
                reasoning="Good momentum - acknowledge and continue"
            )
        
        # Still gathering required info
        if empty_required:
            next_required = self._prioritize_required_buckets(
                empty_required, filled_buckets
            )
            
            return StrategyContext(
                strategy=ResponseStrategy.GATHER_REQUIRED,
                priority_buckets=next_required,
                group_questions=self._should_group_questions(style, next_required),
                show_progress=False,
                offer_examples=len(filled_buckets) < 3,
                acknowledge_previous=len(filled_buckets) > 0,
                style_adjustment=style,
                reasoning="Gathering required information"
            )
        
        # Move to optional buckets
        optional_buckets = self._suggest_optional_buckets(filled_buckets, state_manager)
        if optional_buckets:
            return StrategyContext(
                strategy=ResponseStrategy.GATHER_OPTIONAL,
                priority_buckets=optional_buckets,
                group_questions=True,  # Group optional questions
                show_progress=True,
                offer_examples=False,
                acknowledge_previous=True,
                style_adjustment=style,
                reasoning="Required fields complete - gathering optional"
            )
        
        # All done!
        return StrategyContext(
            strategy=ResponseStrategy.COMPLETION_READY,
            priority_buckets=[],
            group_questions=False,
            show_progress=True,
            offer_examples=False,
            acknowledge_previous=True,
            style_adjustment=style,
            reasoning="All information gathered"
        )
    
    def _detect_conversation_style(
        self,
        state: GraphState,
        state_manager: StateManager
    ) -> ConversationStyle:
        """Detect user's communication style from their messages"""
        
        # Get user messages
        user_messages = [
            msg for msg in state_manager.state['messages']
            if (msg.role if hasattr(msg, 'role') else msg.get('role')) == 'user'
        ]
        
        if not user_messages:
            return ConversationStyle.UNCERTAIN
        
        # Analyze message characteristics
        total_length = sum(len(msg.content if hasattr(msg, 'content') else msg.get('content', '')) for msg in user_messages)
        avg_length = total_length / len(user_messages) if user_messages else 0
        
        # Check for technical indicators
        technical_terms = ['api', 'sdk', 'framework', 'architecture', 'algorithm',
                          'optimization', 'scalability', 'infrastructure']
        technical_count = sum(
            1 for msg in user_messages
            for term in technical_terms
            if term in (msg.content if hasattr(msg, 'content') else msg.get('content', '')).lower()
        )
        
        # Check formality
        formal_indicators = ['regards', 'sincerely', 'please find', 'kindly',
                           'would like to', 'i would appreciate']
        formal_count = sum(
            1 for msg in user_messages
            for indicator in formal_indicators
            if indicator in (msg.content if hasattr(msg, 'content') else msg.get('content', '')).lower()
        )
        
        # Check for uncertainty
        uncertain_phrases = ['not sure', 'i think', 'maybe', 'possibly',
                           'what should i', 'do i need to', 'is this right']
        uncertain_count = sum(
            1 for msg in user_messages
            for phrase in uncertain_phrases
            if phrase in (msg.content if hasattr(msg, 'content') else msg.get('content', '')).lower()
        )
        
        # Determine style
        if uncertain_count > len(user_messages) * 0.3:
            return ConversationStyle.UNCERTAIN
        elif avg_length > 100:
            return ConversationStyle.VERBOSE
        elif avg_length < 30:
            return ConversationStyle.CONCISE
        elif technical_count > 2:
            return ConversationStyle.TECHNICAL
        elif formal_count > 1:
            return ConversationStyle.FORMAL
        else:
            return ConversationStyle.CASUAL
    
    def _should_group_questions(
        self,
        style: ConversationStyle,
        buckets: List[str]
    ) -> bool:
        """Determine if questions should be grouped"""
        
        if not buckets:
            return False
        
        # Check if buckets are in same group
        for group_name, group_buckets in self.bucket_groups.items():
            if all(b in group_buckets for b in buckets):
                # All in same group - good to combine
                limit = self.style_question_limits.get(style, 2)
                return len(buckets) <= limit
        
        return False
    
    def _get_next_logical_buckets(
        self,
        filled: Dict[str, Any],
        empty_required: List[str],
        style: ConversationStyle
    ) -> List[str]:
        """Get next logical buckets based on what's filled"""
        
        # If we have name but not contact, prioritize contact
        if 'full_name' in filled and not any(b in filled for b in ['email', 'phone']):
            contact_buckets = [b for b in ['email', 'phone'] if b in empty_required]
            if contact_buckets:
                return contact_buckets[:1]  # Just email first
        
        # CRITICAL: If we have email but not LinkedIn, ALWAYS suggest LinkedIn next
        if 'email' in filled and 'linkedin_url' not in filled:
            # LinkedIn is our top priority after email for profile analysis
            return ['linkedin_url']
        
        # After LinkedIn analysis, we need current role
        if 'linkedin_url' in filled and 'current_role' not in filled and 'current_role' in empty_required:
            return ['current_role']
        
        # After we have role and LinkedIn, ask for key message
        if 'current_role' in filled and 'key_message' not in filled and 'key_message' in empty_required:
            return ['key_message']
        
        # If we have role but not company/experience
        if 'current_role' in filled:
            related = [b for b in ['company', 'years_experience'] if b in empty_required]
            if related:
                limit = self.style_question_limits.get(style, 2)
                return related[:limit]
        
        # If we have some expertise, get more
        if any(b in filled for b in ['expertise_keywords', 'podcast_topics']):
            expertise_buckets = [
                b for b in ['unique_perspective', 'target_audience']
                if b in empty_required
            ]
            if expertise_buckets:
                return expertise_buckets[:1]
        
        # Default: next required bucket
        if empty_required:
            return empty_required[:1]
        
        return []
    
    def _prioritize_required_buckets(
        self,
        empty_required: List[str],
        filled: Dict[str, Any]
    ) -> List[str]:
        """Prioritize which required buckets to ask for"""
        
        # Priority order
        priority_order = [
            'full_name',
            'email',
            'current_role',
            'professional_bio',
            'expertise_keywords',
            'podcast_topics',
            'success_stories'
        ]
        
        # Get buckets in priority order
        prioritized = []
        for bucket in priority_order:
            if bucket in empty_required:
                prioritized.append(bucket)
        
        # Add any remaining
        for bucket in empty_required:
            if bucket not in prioritized:
                prioritized.append(bucket)
        
        return prioritized
    
    def _suggest_optional_buckets(
        self,
        filled: Dict[str, Any],
        state_manager: Optional['StateManager'] = None
    ) -> List[str]:
        """Suggest relevant optional buckets"""
        
        suggestions = []
        
        # Get all optional buckets
        from .bucket_definitions import INFORMATION_BUCKETS
        all_optional = [bid for bid, bdef in INFORMATION_BUCKETS.items() if not bdef.required]
        
        # Filter out already filled buckets
        empty_optional = [bid for bid in all_optional if bid not in filled]
        
        # Also filter out skipped buckets if state_manager is provided
        if state_manager:
            skipped = state_manager.state.get('skipped_optional_buckets', [])
            empty_optional = [bid for bid in empty_optional if bid not in skipped]
        
        # Priority order for optional buckets
        priority_order = [
            'linkedin_url',  # LinkedIn is highly valuable
            'phone',         # Contact info
            'years_experience',  # Credibility
            'speaking_experience',  # Past experience
            'media_experience',     # Media appearances
            'achievements',    # Concrete results
            'ideal_podcast',   # User's podcast preferences (important for matching)
            'interesting_hooks',  # Engaging content
            'controversial_takes',  # Thought-provoking content
            'fun_fact',       # Personal touch
            'website',        # Additional info
            'scheduling_preference',  # Logistics
            'promotion_items',  # What to promote
            'social_media'    # Other profiles
        ]
        
        # Sort empty optional buckets by priority
        for bucket in priority_order:
            if bucket in empty_optional:
                suggestions.append(bucket)
        
        # Add any remaining optional buckets not in priority list
        for bucket in empty_optional:
            if bucket not in suggestions:
                suggestions.append(bucket)
        
        return suggestions  # Return all suggestions, let caller decide how many to use
    
    def _get_absolute_minimum_buckets(
        self,
        empty_required: List[str]
    ) -> List[str]:
        """Get absolute minimum buckets for rescue mode"""
        
        critical = ['full_name', 'email', 'professional_bio']
        return [b for b in critical if b in empty_required][:1]
    
    def get_bucket_context(
        self,
        bucket_id: str,
        state_manager: StateManager
    ) -> Dict[str, Any]:
        """Get context about a specific bucket for question generation"""
        
        bucket_def = INFORMATION_BUCKETS.get(bucket_id)
        if not bucket_def:
            return {}
        
        filled = state_manager.get_filled_buckets()
        
        context = {
            'bucket_id': bucket_id,
            'bucket_name': bucket_def.name,
            'description': bucket_def.description,
            'examples': bucket_def.example_inputs[:2],
            'allows_multiple': bucket_def.allow_multiple,
            'related_filled': []
        }
        
        # Add related filled buckets for context
        for group_name, group_buckets in self.bucket_groups.items():
            if bucket_id in group_buckets:
                for other_bucket in group_buckets:
                    if other_bucket in filled and other_bucket != bucket_id:
                        context['related_filled'].append({
                            'bucket': other_bucket,
                            'value': filled[other_bucket]
                        })
        
        return context