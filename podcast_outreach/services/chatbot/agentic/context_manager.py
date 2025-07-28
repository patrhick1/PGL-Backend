# podcast_outreach/services/chatbot/agentic/context_manager.py

from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import re

from .state_manager import Message, StateManager
from .bucket_definitions import INFORMATION_BUCKETS

@dataclass
class CompressedContext:
    """Compressed conversation context"""
    summary: str
    key_facts: Dict[str, Any]
    recent_messages: List[Message]
    total_messages: int
    compression_ratio: float

class ContextCompressionManager:
    """
    Manages context compression for token optimization
    
    Strategies:
    - Keep recent messages in full
    - Summarize older conversations
    - Extract and preserve key facts
    - Remove redundant information
    """
    
    def __init__(self, max_context_messages: int = 10):
        self.max_context_messages = max_context_messages
        self.always_preserve_messages = 4  # Always keep last N messages
        
    def compress_conversation_history(
        self,
        state_manager: StateManager,
        target_token_estimate: int = 2000
    ) -> CompressedContext:
        """
        Compress conversation history to fit within token limits
        
        Args:
            state_manager: Current conversation state
            target_token_estimate: Target token count (rough estimate)
            
        Returns:
            CompressedContext with optimized history
        """
        messages = state_manager.state['messages']
        total_messages = len(messages)
        
        if total_messages <= self.max_context_messages:
            # No compression needed
            return CompressedContext(
                summary="",
                key_facts={},
                recent_messages=messages,
                total_messages=total_messages,
                compression_ratio=1.0
            )
        
        # Split messages into old and recent
        recent_messages = messages[-self.always_preserve_messages:]
        older_messages = messages[:-self.always_preserve_messages]
        
        # Extract key facts from older messages
        key_facts = self._extract_key_facts(older_messages, state_manager)
        
        # Create summary of older conversation
        summary = self._create_conversation_summary(older_messages, key_facts)
        
        # Calculate compression ratio
        original_length = sum(len(m.content) for m in messages)
        compressed_length = len(summary) + sum(len(m.content) for m in recent_messages)
        compression_ratio = compressed_length / original_length if original_length > 0 else 1.0
        
        return CompressedContext(
            summary=summary,
            key_facts=key_facts,
            recent_messages=recent_messages,
            total_messages=total_messages,
            compression_ratio=compression_ratio
        )
    
    def _extract_key_facts(
        self,
        messages: List[Message],
        state_manager: StateManager
    ) -> Dict[str, Any]:
        """Extract important facts from messages"""
        
        key_facts = {
            'corrections_made': [],
            'frustration_moments': [],
            'provided_info': [],
            'preferences_shown': []
        }
        
        # Track corrections
        for i, msg in enumerate(messages):
            if msg.role == 'user':
                content_lower = msg.content.lower()
                if any(phrase in content_lower for phrase in [
                    'actually', 'no it\'s', 'i meant', 'correction'
                ]):
                    key_facts['corrections_made'].append({
                        'message_index': i,
                        'snippet': msg.content[:50]
                    })
        
        # Track frustration
        frustration_phrases = [
            'already told you', 'i said', 'asked this', 'repeating',
            'mentioned', 'why are you asking again'
        ]
        for i, msg in enumerate(messages):
            if msg.role == 'user':
                content_lower = msg.content.lower()
                if any(phrase in content_lower for phrase in frustration_phrases):
                    key_facts['frustration_moments'].append({
                        'message_index': i,
                        'snippet': msg.content[:50]
                    })
        
        # Track what info was provided early
        filled_buckets = state_manager.get_filled_buckets()
        for bucket_id, value in filled_buckets.items():
            # Find when this was first provided
            for i, msg in enumerate(messages):
                if msg.role == 'user' and str(value).lower() in msg.content.lower():
                    key_facts['provided_info'].append({
                        'bucket': bucket_id,
                        'message_index': i,
                        'value': value
                    })
                    break
        
        # Track preferences (verbose vs concise)
        user_message_lengths = [
            len(msg.content) for msg in messages if msg.role == 'user'
        ]
        if user_message_lengths:
            avg_length = sum(user_message_lengths) / len(user_message_lengths)
            if avg_length > 100:
                key_facts['preferences_shown'].append('verbose_responses')
            elif avg_length < 30:
                key_facts['preferences_shown'].append('concise_responses')
        
        return key_facts
    
    def _create_conversation_summary(
        self,
        messages: List[Message],
        key_facts: Dict[str, Any]
    ) -> str:
        """Create a concise summary of older conversation"""
        
        summary_parts = []
        
        # Basic stats
        user_messages = [m for m in messages if m.role == 'user']
        bot_messages = [m for m in messages if m.role == 'assistant']
        
        summary_parts.append(
            f"Previous conversation: {len(user_messages)} user messages, "
            f"{len(bot_messages)} bot responses."
        )
        
        # Corrections
        if key_facts['corrections_made']:
            summary_parts.append(
                f"User made {len(key_facts['corrections_made'])} corrections."
            )
        
        # Frustration
        if key_facts['frustration_moments']:
            summary_parts.append(
                "User showed signs of frustration with repetitive questions."
            )
        
        # Communication style
        if 'verbose_responses' in key_facts['preferences_shown']:
            summary_parts.append("User prefers detailed communication.")
        elif 'concise_responses' in key_facts['preferences_shown']:
            summary_parts.append("User prefers concise communication.")
        
        # Information provided
        if key_facts['provided_info']:
            early_buckets = [
                info['bucket'] for info in key_facts['provided_info'][:5]
            ]
            bucket_names = [
                INFORMATION_BUCKETS[bid].name for bid in early_buckets
                if bid in INFORMATION_BUCKETS
            ]
            if bucket_names:
                summary_parts.append(
                    f"Early in conversation, user provided: {', '.join(bucket_names)}"
                )
        
        return ' '.join(summary_parts)
    
    def get_relevant_context(
        self,
        state_manager: StateManager,
        focus_bucket: Optional[str] = None
    ) -> List[Message]:
        """
        Get relevant context messages for a specific focus
        
        Args:
            state_manager: Current conversation state
            focus_bucket: Optional bucket to focus context on
            
        Returns:
            List of relevant messages
        """
        messages = state_manager.state['messages']
        
        if not focus_bucket:
            # Return recent messages
            return messages[-self.max_context_messages:]
        
        # Find messages related to the focus bucket
        relevant_messages = []
        bucket_def = INFORMATION_BUCKETS.get(focus_bucket)
        
        if not bucket_def:
            return messages[-self.max_context_messages:]
        
        # Keywords to look for
        keywords = [
            bucket_def.name.lower(),
            focus_bucket.replace('_', ' ')
        ]
        
        # Add example keywords
        for example in bucket_def.example_inputs[:3]:
            if isinstance(example, str):
                keywords.extend(example.lower().split()[:2])
        
        # Find relevant messages
        for msg in messages:
            content_lower = msg.content.lower()
            if any(keyword in content_lower for keyword in keywords):
                relevant_messages.append(msg)
        
        # Always include recent messages
        recent = messages[-self.always_preserve_messages:]
        for msg in recent:
            if msg not in relevant_messages:
                relevant_messages.append(msg)
        
        # Limit total messages
        if len(relevant_messages) > self.max_context_messages:
            # Keep first few and last few
            keep_start = 2
            keep_end = self.max_context_messages - keep_start
            relevant_messages = (
                relevant_messages[:keep_start] + 
                relevant_messages[-keep_end:]
            )
        
        return relevant_messages
    
    def estimate_tokens(self, text: str) -> int:
        """
        Rough estimate of token count
        
        Note: This is a very rough estimate. In production,
        use the actual tokenizer for the model being used.
        """
        # Rough estimate: ~4 characters per token
        return len(text) // 4
    
    def should_compress(
        self,
        messages: List[Message],
        token_limit: int = 3000
    ) -> bool:
        """Determine if compression is needed"""
        
        total_text = ' '.join(msg.content for msg in messages)
        estimated_tokens = self.estimate_tokens(total_text)
        
        return estimated_tokens > token_limit or len(messages) > self.max_context_messages