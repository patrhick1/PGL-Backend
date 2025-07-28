# podcast_outreach/services/chatbot/agentic/agentic_adapter.py

from typing import Dict, List, Optional, Any, Tuple
from uuid import UUID
from datetime import datetime
import json
import logging
import os

from .conversation_orchestrator import ConversationOrchestrator
from .state_converter import StateConverter
from .fallback_handler import FallbackHandler
# from ..enhanced_nlp_processor import EnhancedNLPProcessor  # REMOVED - not needed

logger = logging.getLogger(__name__)

class AgenticChatbotAdapter:
    """
    Adapter that integrates the new agentic chatbot system with the existing
    ConversationEngine infrastructure.
    
    This adapter:
    - Provides a compatible interface for the existing system
    - Manages state conversion between old and new formats
    - Handles graceful fallback to the old system
    - Maintains API compatibility
    """
    
    def __init__(
        self,
        gemini_service: Any = None,
        use_agentic: Optional[bool] = None,
        fallback_enabled: bool = True
    ):
        """
        Initialize the adapter
        
        Args:
            gemini_service: Gemini AI service instance
            use_agentic: Force enable/disable agentic system (None = use env var)
            fallback_enabled: Whether to fallback to old system on errors
        """
        # Determine if agentic system should be used
        if use_agentic is None:
            use_agentic_env = os.getenv('USE_AGENTIC_CHATBOT', 'false')
            logger.info(f"USE_AGENTIC_CHATBOT env var: {use_agentic_env}")
            use_agentic = use_agentic_env.lower() == 'true'
        
        self.use_agentic = use_agentic
        logger.info(f"Agentic adapter initialized with use_agentic={self.use_agentic}")
        self.fallback_enabled = fallback_enabled
        
        # Initialize components
        if self.use_agentic:
            try:
                self.orchestrator = ConversationOrchestrator()
                self.state_converter = StateConverter()
                self.fallback_handler = FallbackHandler()
                logger.info("Agentic chatbot system initialized")
            except Exception as e:
                logger.error(f"Failed to initialize agentic system: {e}")
                self.use_agentic = False
                if not self.fallback_enabled:
                    raise
        
        # Keep reference to legacy processor for compatibility
        # self.nlp_processor = EnhancedNLPProcessor()  # REMOVED - not needed
    
    async def create_conversation(
        self,
        campaign_id: str,
        person_id: int,
        person_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new conversation using the agentic system
        
        Args:
            campaign_id: Campaign ID
            person_id: Person ID
            person_data: Person information
            
        Returns:
            Initial conversation data in legacy format
        """
        if not self.use_agentic:
            return None  # Let legacy system handle it
        
        try:
            # Generate initial message using agentic system
            initial_message = self._generate_agentic_greeting(person_data)
            
            # Create initial state
            initial_state = {
                'person_id': person_id,
                'campaign_id': campaign_id,
                'buckets': {},
                'messages': [],
                'phase': 'introduction',
                'is_agentic': True
            }
            
            return {
                'initial_message': initial_message,
                'state': initial_state,
                'use_agentic': True
            }
            
        except Exception as e:
            logger.error(f"Error in agentic conversation creation: {e}")
            if self.fallback_enabled:
                return None  # Fallback to legacy
            raise
    
    async def process_message(
        self,
        conversation_id: str,
        message: str,
        conversation_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Process a message using the agentic system
        
        Args:
            conversation_id: Conversation ID
            message: User message
            conversation_data: Current conversation data
            
        Returns:
            Response in legacy format
        """
        # Check if this conversation should use agentic
        if not self._should_use_agentic(conversation_data):
            return None  # Let legacy system handle it
        
        try:
            # Convert legacy state to agentic format
            agentic_state = self.state_converter.legacy_to_agentic(
                conversation_data
            )
            
            # Process through agentic system
            response, new_state = await self.orchestrator.process_message(
                message=message,
                person_id=conversation_data['person_id'],
                company_id=conversation_data['campaign_id'],
                session_id=str(conversation_id),
                existing_state=agentic_state
            )
            
            # Convert back to legacy format
            legacy_response = self.state_converter.agentic_to_legacy_response(
                response=response,
                new_state=new_state,
                old_conversation_data=conversation_data
            )
            
            # Debug logging
            logger.info(f"Agentic adapter - bot_message has {legacy_response['bot_message'].count(chr(10))} newlines")
            logger.info(f"Agentic adapter - first 200 chars: {repr(legacy_response['bot_message'][:200])}")
            
            return legacy_response
            
        except Exception as e:
            logger.error(f"Error in agentic message processing: {e}")
            
            if self.fallback_enabled:
                # Try to recover with fallback
                return await self.fallback_handler.handle_error(
                    error=e,
                    conversation_id=conversation_id,
                    message=message,
                    conversation_data=conversation_data
                )
            raise
    
    async def complete_conversation(
        self,
        conversation_id: str,
        conversation_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Complete a conversation using the agentic system
        
        Args:
            conversation_id: Conversation ID
            conversation_data: Current conversation data
            
        Returns:
            Completion data in legacy format
        """
        if not self._should_use_agentic(conversation_data):
            return None  # Let legacy system handle it
        
        try:
            # Get summary from agentic system
            agentic_state = self.state_converter.legacy_to_agentic(
                conversation_data
            )
            
            summary = await self.orchestrator.get_conversation_summary(
                person_id=conversation_data['person_id'],
                company_id=conversation_data['campaign_id'],
                state_dict=agentic_state
            )
            
            # Convert to legacy format
            return self.state_converter.agentic_summary_to_legacy(summary)
            
        except Exception as e:
            logger.error(f"Error in agentic conversation completion: {e}")
            if self.fallback_enabled:
                return None  # Fallback to legacy
            raise
    
    # REMOVED: extract_keywords_and_topics method - unused and references non-existent method
    
    def _should_use_agentic(self, conversation_data: Dict[str, Any]) -> bool:
        """Check if a conversation should use the agentic system"""
        if not self.use_agentic:
            return False
        
        # Check if conversation was started with agentic
        if conversation_data.get('metadata', {}).get('is_agentic'):
            return True
        
        # Check rollout percentage
        rollout_percentage = int(os.getenv('AGENTIC_ROLLOUT_PERCENTAGE', '0'))
        if rollout_percentage > 0:
            # Use deterministic hash for consistent routing
            import hashlib
            conv_hash = int(hashlib.md5(
                str(conversation_data.get('conversation_id', '')).encode()
            ).hexdigest()[:8], 16)
            return (conv_hash % 100) < rollout_percentage
        
        return False
    
    def _generate_agentic_greeting(self, person_data: Dict[str, Any]) -> str:
        """Generate an intelligent greeting using person data"""
        name = person_data.get('full_name', 'there')
        
        if person_data.get('linkedin_url'):
            return (
                f"Hi {name}! I'm here to help you create a compelling podcast "
                f"guest profile. I see you have a LinkedIn profile - this will "
                f"help us showcase your expertise effectively. Let's start by "
                f"confirming a few details. What's the best email for podcast "
                f"hosts to reach you?"
            )
        else:
            return (
                f"Welcome {name}! I'll help you create your podcast guest profile. "
                f"This usually takes about 15-20 minutes, and I'll guide you through "
                f"everything step by step. Let's begin - what's the best email "
                f"address for podcast hosts to contact you?"
            )
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of the agentic system"""
        return {
            'agentic_enabled': self.use_agentic,
            'fallback_enabled': self.fallback_enabled,
            'rollout_percentage': os.getenv('AGENTIC_ROLLOUT_PERCENTAGE', '0'),
            'components': {
                'orchestrator': hasattr(self, 'orchestrator'),
                'state_converter': hasattr(self, 'state_converter'),
                'fallback_handler': hasattr(self, 'fallback_handler')
            }
        }