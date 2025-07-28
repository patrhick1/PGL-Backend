# podcast_outreach/services/chatbot/agentic/fallback_handler.py

from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
import traceback

logger = logging.getLogger(__name__)

class FallbackHandler:
    """
    Handles fallback scenarios when the agentic system encounters errors
    or when specific conditions require using the legacy system.
    
    Provides:
    - Graceful error recovery
    - System health monitoring
    - Intelligent routing decisions
    - Error pattern detection
    """
    
    def __init__(self):
        # Track errors for pattern detection
        self.error_history = []
        self.max_error_history = 100
        
        # Error thresholds
        self.error_threshold_per_conversation = 3
        self.global_error_threshold = 10
        self.time_window_minutes = 5
        
        # Fallback strategies
        self.strategies = {
            'timeout': self._handle_timeout,
            'api_error': self._handle_api_error,
            'state_error': self._handle_state_error,
            'validation_error': self._handle_validation_error,
            'unknown': self._handle_unknown_error
        }
    
    async def handle_error(
        self,
        error: Exception,
        conversation_id: str,
        message: str,
        conversation_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Handle an error from the agentic system
        
        Args:
            error: The exception that occurred
            conversation_id: Conversation ID
            message: User message that caused the error
            conversation_data: Current conversation data
            
        Returns:
            Fallback response or None to use legacy system
        """
        try:
            # Log the error
            self._log_error(error, conversation_id)
            
            # Determine error type
            error_type = self._classify_error(error)
            
            # Check if we should disable agentic globally
            if self._should_disable_globally():
                logger.error("Too many errors - disabling agentic system globally")
                return None
            
            # Check if we should disable for this conversation
            if self._should_disable_for_conversation(conversation_id):
                logger.warning(f"Too many errors for conversation {conversation_id} - falling back")
                return None
            
            # Try error-specific recovery strategy
            strategy = self.strategies.get(error_type, self._handle_unknown_error)
            recovery_response = await strategy(error, message, conversation_data)
            
            if recovery_response:
                return recovery_response
            
            # Default: fallback to legacy system
            return None
            
        except Exception as e:
            logger.error(f"Error in fallback handler: {e}")
            return None
    
    def should_use_agentic_for_message(
        self,
        message: str,
        conversation_data: Dict[str, Any]
    ) -> bool:
        """
        Determine if a specific message should use the agentic system
        
        Args:
            message: User message
            conversation_data: Current conversation data
            
        Returns:
            True if agentic should be used, False otherwise
        """
        # Check for specific patterns that work better with legacy
        legacy_patterns = [
            # Very long messages might timeout
            lambda m: len(m) > 1000,
            # Multiple questions in one message
            lambda m: m.count('?') > 3,
            # Specific commands
            lambda m: m.lower().strip() in ['help', 'reset', 'start over']
        ]
        
        for pattern in legacy_patterns:
            if pattern(message):
                logger.info("Message matches legacy pattern - using legacy system")
                return False
        
        # Check conversation history
        error_count = self._get_conversation_error_count(
            conversation_data.get('conversation_id', '')
        )
        
        if error_count >= self.error_threshold_per_conversation:
            return False
        
        return True
    
    def get_health_metrics(self) -> Dict[str, Any]:
        """Get current health metrics for monitoring"""
        
        recent_errors = self._get_recent_errors()
        error_rate = len(recent_errors) / max(1, len(self.error_history))
        
        return {
            'total_errors': len(self.error_history),
            'recent_errors': len(recent_errors),
            'error_rate': error_rate,
            'is_healthy': len(recent_errors) < self.global_error_threshold,
            'error_types': self._get_error_type_distribution(),
            'recommendations': self._get_recommendations()
        }
    
    def _log_error(self, error: Exception, conversation_id: str):
        """Log error for tracking"""
        error_entry = {
            'timestamp': datetime.utcnow(),
            'conversation_id': conversation_id,
            'error_type': type(error).__name__,
            'error_message': str(error),
            'traceback': traceback.format_exc()
        }
        
        self.error_history.append(error_entry)
        
        # Maintain history size
        if len(self.error_history) > self.max_error_history:
            self.error_history.pop(0)
    
    def _classify_error(self, error: Exception) -> str:
        """Classify error type for appropriate handling"""
        
        error_name = type(error).__name__
        error_msg = str(error).lower()
        
        if 'timeout' in error_msg or 'timed out' in error_msg:
            return 'timeout'
        elif 'api' in error_msg or 'gemini' in error_msg:
            return 'api_error'
        elif 'state' in error_msg or 'dict' in error_msg:
            return 'state_error'
        elif 'validation' in error_msg or 'invalid' in error_msg:
            return 'validation_error'
        else:
            return 'unknown'
    
    def _should_disable_globally(self) -> bool:
        """Check if agentic should be disabled globally"""
        recent_errors = self._get_recent_errors()
        return len(recent_errors) >= self.global_error_threshold
    
    def _should_disable_for_conversation(self, conversation_id: str) -> bool:
        """Check if agentic should be disabled for specific conversation"""
        count = self._get_conversation_error_count(conversation_id)
        return count >= self.error_threshold_per_conversation
    
    def _get_recent_errors(self) -> List[Dict[str, Any]]:
        """Get errors within time window"""
        cutoff = datetime.utcnow()
        recent = []
        
        for error in reversed(self.error_history):
            time_diff = cutoff - error['timestamp']
            if time_diff.total_seconds() <= self.time_window_minutes * 60:
                recent.append(error)
            else:
                break
        
        return recent
    
    def _get_conversation_error_count(self, conversation_id: str) -> int:
        """Get error count for specific conversation"""
        return sum(
            1 for e in self.error_history
            if e['conversation_id'] == conversation_id
        )
    
    def _get_error_type_distribution(self) -> Dict[str, int]:
        """Get distribution of error types"""
        distribution = {}
        for error in self.error_history:
            error_type = error['error_type']
            distribution[error_type] = distribution.get(error_type, 0) + 1
        return distribution
    
    def _get_recommendations(self) -> List[str]:
        """Get recommendations based on error patterns"""
        recommendations = []
        
        recent_errors = self._get_recent_errors()
        if len(recent_errors) > 5:
            recommendations.append("High error rate detected - consider reducing rollout percentage")
        
        error_types = self._get_error_type_distribution()
        if error_types.get('timeout', 0) > 3:
            recommendations.append("Multiple timeouts - check API response times")
        
        if error_types.get('state_error', 0) > 3:
            recommendations.append("State errors detected - review state conversion logic")
        
        return recommendations
    
    # Error-specific handlers
    
    async def _handle_timeout(
        self,
        error: Exception,
        message: str,
        conversation_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Handle timeout errors"""
        logger.warning("Handling timeout error with generic response")
        
        return {
            'bot_message': (
                "I apologize, but I'm experiencing some delays. "
                "Let me try a simpler approach. Could you tell me "
                "one thing at a time about yourself?"
            ),
            'extracted_data': conversation_data.get('extracted_data', {}),
            'progress': conversation_data.get('progress', 0),
            'phase': conversation_data.get('phase', 'introduction'),
            'keywords_found': 0,
            'quick_replies': ["Let's continue", "Start over", "Skip this"]
        }
    
    async def _handle_api_error(
        self,
        error: Exception,
        message: str,
        conversation_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Handle API errors"""
        logger.error(f"API error: {error}")
        
        # For API errors, fallback to legacy is usually best
        return None
    
    async def _handle_state_error(
        self,
        error: Exception,
        message: str,
        conversation_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Handle state-related errors"""
        logger.error(f"State error: {error}")
        
        # Try to recover with a generic response
        phase = conversation_data.get('phase', 'introduction')
        
        responses = {
            'introduction': "Let's start fresh. What's your name?",
            'basic_info': "Could you tell me about your current role?",
            'experience': "What's your area of expertise?",
            'achievements': "What achievements are you most proud of?",
            'podcast_fit': "What topics would you like to discuss on podcasts?"
        }
        
        return {
            'bot_message': responses.get(phase, "Let's continue. What would you like to share?"),
            'extracted_data': conversation_data.get('extracted_data', {}),
            'progress': conversation_data.get('progress', 0),
            'phase': phase,
            'keywords_found': 0,
            'quick_replies': []
        }
    
    async def _handle_validation_error(
        self,
        error: Exception,
        message: str,
        conversation_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Handle validation errors"""
        
        return {
            'bot_message': (
                "I didn't quite understand that. Could you rephrase "
                "or provide a bit more detail?"
            ),
            'extracted_data': conversation_data.get('extracted_data', {}),
            'progress': conversation_data.get('progress', 0),
            'phase': conversation_data.get('phase', 'introduction'),
            'keywords_found': 0,
            'quick_replies': ["Skip this question", "Give an example", "Help"]
        }
    
    async def _handle_unknown_error(
        self,
        error: Exception,
        message: str,
        conversation_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Handle unknown errors"""
        logger.error(f"Unknown error: {error}")
        
        # For unknown errors, fallback to legacy
        return None