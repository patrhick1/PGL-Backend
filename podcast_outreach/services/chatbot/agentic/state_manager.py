# podcast_outreach/services/chatbot/agentic/state_manager.py

from typing import Dict, List, Any, Optional, TypedDict
from datetime import datetime
from dataclasses import dataclass, field
import json
import logging
from uuid import UUID

from .bucket_definitions import INFORMATION_BUCKETS, validate_bucket_data

logger = logging.getLogger(__name__)

@dataclass
class Message:
    """Represents a single message in the conversation"""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class BucketEntry:
    """Represents a single entry in a bucket"""
    value: Any
    confidence: float = 1.0
    source_message_index: Optional[int] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    is_corrected: bool = False
    previous_value: Optional[Any] = None

@dataclass 
class Correction:
    """Tracks a correction made by the user"""
    bucket_id: str
    old_value: Any
    new_value: Any
    message_index: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    reason: Optional[str] = None

class ChatbotState(TypedDict):
    """Complete state of the chatbot conversation"""
    # Core conversation data
    conversation_id: str
    campaign_id: str
    person_id: int
    
    # Bucket data - the main information collection
    buckets: Dict[str, List[BucketEntry]]
    
    # Conversation history
    messages: List[Message]
    
    # Tracking and metadata
    user_corrections: List[Correction]
    completion_signals: List[str]  # Phrases indicating user wants to complete
    
    # Context management
    context_summary: str  # Compressed summary of conversation
    last_updated: datetime
    
    # User preferences detected
    communication_style: Dict[str, str]  # formal/informal, brief/detailed, etc.
    
    # State flags
    is_reviewing: bool  # User is reviewing collected data
    awaiting_confirmation: Optional[str]  # Waiting for user to confirm something
    completion_confirmed: bool  # User confirmed they want to complete

class StateManager:
    """Manages the conversation state and provides helper methods"""
    
    def __init__(self, conversation_id: str, campaign_id: str, person_id: int):
        self.state: ChatbotState = {
            'conversation_id': conversation_id,
            'campaign_id': campaign_id,
            'person_id': person_id,
            'buckets': {},
            'messages': [],
            'user_corrections': [],
            'completion_signals': [],
            'context_summary': '',
            'last_updated': datetime.utcnow(),
            'communication_style': {
                'formality': 'neutral',
                'detail_level': 'moderate',
                'preferred_pace': 'normal'
            },
            'is_reviewing': False,
            'awaiting_confirmation': None,
            'completion_confirmed': False,
            'skipped_optional_buckets': []  # Track optional buckets user doesn't have
        }
        
        # Initialize empty buckets
        for bucket_id in INFORMATION_BUCKETS:
            self.state['buckets'][bucket_id] = []
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        """Add a message to the conversation history"""
        message = Message(
            role=role,
            content=content,
            metadata=metadata or {}
        )
        self.state['messages'].append(message)
        self.state['last_updated'] = datetime.utcnow()
    
    def update_bucket(self, bucket_id: str, value: Any, confidence: float = 1.0, 
                     is_correction: bool = False) -> bool:
        """Update a bucket with new data"""
        if bucket_id not in INFORMATION_BUCKETS:
            return False
        
        # Validate the data
        if not validate_bucket_data(bucket_id, value):
            return False
        
        bucket_def = INFORMATION_BUCKETS[bucket_id]
        current_entries = self.state['buckets'][bucket_id]
        
        # Handle corrections
        if is_correction and current_entries:
            last_entry = current_entries[-1]
            if isinstance(last_entry, dict):
                old_value = last_entry.get('value')
            else:
                old_value = last_entry.value
            self.state['user_corrections'].append(
                Correction(
                    bucket_id=bucket_id,
                    old_value=old_value,
                    new_value=value,
                    message_index=len(self.state['messages']) - 1
                )
            )
        
        # Create new entry
        # Get previous value for corrections
        previous_value = None
        if is_correction and current_entries:
            last_entry = current_entries[-1]
            if isinstance(last_entry, dict):
                previous_value = last_entry.get('value')
            else:
                previous_value = last_entry.value
        
        entry = BucketEntry(
            value=value,
            confidence=confidence,
            source_message_index=len(self.state['messages']) - 1,
            is_corrected=is_correction,
            previous_value=previous_value
        )
        
        # Handle single vs multiple entries
        if bucket_def.allow_multiple:
            # Check max entries
            if bucket_def.max_entries and len(current_entries) >= bucket_def.max_entries:
                # Replace oldest entry if at max
                current_entries.pop(0)
            current_entries.append(entry)
        else:
            # Single entry - replace
            self.state['buckets'][bucket_id] = [entry]
        
        self.state['last_updated'] = datetime.utcnow()
        return True
    
    def get_bucket_value(self, bucket_id: str) -> Optional[Any]:
        """Get the current value(s) for a bucket"""
        if bucket_id not in self.state['buckets']:
            return None
        
        entries = self.state['buckets'][bucket_id]
        if not entries:
            return None
        
        bucket_def = INFORMATION_BUCKETS[bucket_id]
        
        # Return list of values if multiple allowed
        if bucket_def.allow_multiple:
            values = []
            for entry in entries:
                if isinstance(entry, dict):
                    values.append(entry.get('value'))
                else:
                    values.append(entry.value)
            return values
        
        # Return single value
        last_entry = entries[-1]
        if isinstance(last_entry, dict):
            return last_entry.get('value')
        else:
            return last_entry.value
    
    def get_empty_required_buckets(self) -> List[str]:
        """Get list of required buckets that are empty"""
        empty_buckets = []
        for bucket_id, bucket_def in INFORMATION_BUCKETS.items():
            if bucket_def.required:
                # Check if bucket exists and is empty
                if bucket_id not in self.state['buckets']:
                    logger.warning(f"Bucket {bucket_id} not found in state buckets")
                    empty_buckets.append(bucket_id)
                elif not self.state['buckets'][bucket_id]:
                    empty_buckets.append(bucket_id)
        return empty_buckets
    
    def get_empty_optional_buckets(self) -> List[str]:
        """Get list of optional buckets that are empty"""
        empty_buckets = []
        skipped = self.state.get('skipped_optional_buckets', [])
        for bucket_id, bucket_def in INFORMATION_BUCKETS.items():
            if not bucket_def.required and not self.state['buckets'][bucket_id] and bucket_id not in skipped:
                empty_buckets.append(bucket_id)
        return empty_buckets
    
    def mark_optional_bucket_skipped(self, bucket_id: str) -> None:
        """Mark an optional bucket as skipped (user doesn't have this)"""
        if 'skipped_optional_buckets' not in self.state:
            self.state['skipped_optional_buckets'] = []
        if bucket_id not in self.state['skipped_optional_buckets']:
            self.state['skipped_optional_buckets'].append(bucket_id)
            logger.info(f"Marked optional bucket '{bucket_id}' as skipped")
    
    def get_filled_buckets(self) -> Dict[str, Any]:
        """Get all buckets that have data"""
        filled = {}
        for bucket_id, entries in self.state['buckets'].items():
            if entries:
                filled[bucket_id] = self.get_bucket_value(bucket_id)
        return filled
    
    def get_bucket_confidence(self, bucket_id: str) -> Optional[float]:
        """Get the confidence score for a bucket's current value"""
        entries = self.state['buckets'].get(bucket_id, [])
        if not entries:
            return None
        return entries[-1].confidence
    
    def mark_completion_signal(self, signal: str) -> None:
        """Track that user indicated they want to complete"""
        self.state['completion_signals'].append(signal)
        self.state['last_updated'] = datetime.utcnow()
    
    def set_reviewing(self, is_reviewing: bool) -> None:
        """Set whether user is currently reviewing data"""
        self.state['is_reviewing'] = is_reviewing
        self.state['last_updated'] = datetime.utcnow()
    
    def set_awaiting_confirmation(self, confirmation_type: Optional[str]) -> None:
        """Set what we're waiting for user to confirm"""
        self.state['awaiting_confirmation'] = confirmation_type
        self.state['last_updated'] = datetime.utcnow()
    
    def update_communication_style(self, style_updates: Dict[str, str]) -> None:
        """Update detected communication style preferences"""
        self.state['communication_style'].update(style_updates)
        self.state['last_updated'] = datetime.utcnow()
    
    def update_context_summary(self, summary: str) -> None:
        """Update the compressed context summary"""
        self.state['context_summary'] = summary
        self.state['last_updated'] = datetime.utcnow()
    
    def get_recent_messages(self, count: int = 10) -> List[Message]:
        """Get the most recent messages"""
        return self.state['messages'][-count:]
    
    def get_corrections_for_bucket(self, bucket_id: str) -> List[Correction]:
        """Get all corrections made for a specific bucket"""
        return [c for c in self.state['user_corrections'] if c.bucket_id == bucket_id]
    
    def is_ready_for_completion(self) -> bool:
        """Check if all required buckets are filled"""
        return len(self.get_empty_required_buckets()) == 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for serialization"""
        # Convert complex objects to serializable format
        return {
            'conversation_id': self.state['conversation_id'],
            'campaign_id': self.state['campaign_id'],
            'person_id': self.state['person_id'],
            'buckets': {
                bucket_id: [
                    {
                        'value': entry.value if hasattr(entry, 'value') else entry.get('value'),
                        'confidence': entry.confidence if hasattr(entry, 'confidence') else entry.get('confidence', 1.0),
                        'timestamp': entry.timestamp.isoformat() if hasattr(entry, 'timestamp') else entry.get('timestamp', datetime.utcnow().isoformat()),
                        'is_corrected': entry.is_corrected if hasattr(entry, 'is_corrected') else entry.get('is_corrected', False)
                    }
                    if isinstance(entry, (BucketEntry, dict)) else entry
                    for entry in entries
                ]
                for bucket_id, entries in self.state['buckets'].items()
            },
            'messages': [
                {
                    'role': msg.role,
                    'content': msg.content,
                    'timestamp': msg.timestamp.isoformat(),
                    'metadata': msg.metadata
                }
                for msg in self.state['messages']
            ],
            'user_corrections': [
                {
                    'bucket_id': corr.bucket_id,
                    'old_value': corr.old_value,
                    'new_value': corr.new_value,
                    'timestamp': corr.timestamp.isoformat()
                }
                for corr in self.state['user_corrections']
            ],
            'completion_signals': self.state['completion_signals'],
            'context_summary': self.state['context_summary'],
            'last_updated': self.state['last_updated'].isoformat(),
            'communication_style': self.state['communication_style'],
            'is_reviewing': self.state['is_reviewing'],
            'awaiting_confirmation': self.state['awaiting_confirmation'],
            'completion_confirmed': self.state['completion_confirmed']
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StateManager':
        """Create StateManager from serialized dictionary"""
        manager = cls(
            conversation_id=data['conversation_id'],
            campaign_id=data['campaign_id'],
            person_id=data['person_id']
        )
        
        # Restore buckets
        for bucket_id, entries_data in data.get('buckets', {}).items():
            for entry_data in entries_data:
                entry = BucketEntry(
                    value=entry_data['value'],
                    confidence=entry_data.get('confidence', 1.0),
                    timestamp=datetime.fromisoformat(entry_data['timestamp']),
                    is_corrected=entry_data.get('is_corrected', False)
                )
                manager.state['buckets'][bucket_id].append(entry)
        
        # Restore messages
        for msg_data in data.get('messages', []):
            msg = Message(
                role=msg_data['role'],
                content=msg_data['content'],
                timestamp=datetime.fromisoformat(msg_data['timestamp']),
                metadata=msg_data.get('metadata', {})
            )
            manager.state['messages'].append(msg)
        
        # Restore corrections
        for corr_data in data.get('user_corrections', []):
            corr = Correction(
                bucket_id=corr_data['bucket_id'],
                old_value=corr_data['old_value'],
                new_value=corr_data['new_value'],
                message_index=0,  # We don't track this in serialization
                timestamp=datetime.fromisoformat(corr_data['timestamp'])
            )
            manager.state['user_corrections'].append(corr)
        
        # Restore other state
        manager.state['completion_signals'] = data.get('completion_signals', [])
        manager.state['context_summary'] = data.get('context_summary', '')
        manager.state['last_updated'] = datetime.fromisoformat(data['last_updated'])
        manager.state['communication_style'] = data.get('communication_style', {})
        manager.state['is_reviewing'] = data.get('is_reviewing', False)
        manager.state['awaiting_confirmation'] = data.get('awaiting_confirmation')
        manager.state['completion_confirmed'] = data.get('completion_confirmed', False)
        
        return manager
    
    def generate_summary(self) -> str:
        """Generate a human-readable summary of collected data"""
        filled_buckets = self.get_filled_buckets()
        summary_parts = []
        
        # Group buckets by category
        categories = {
            'Contact': ['full_name', 'email', 'phone', 'website', 'linkedin_url', 'social_media'],
            'Professional': ['current_role', 'company', 'professional_bio', 'years_experience'],
            'Expertise': ['expertise_keywords', 'success_stories', 'achievements', 'unique_perspective'],
            'Podcast': ['podcast_topics', 'target_audience', 'key_message', 'speaking_experience'],
            'Additional': ['promotion_items', 'scheduling_preference']
        }
        
        for category, bucket_ids in categories.items():
            category_data = []
            for bucket_id in bucket_ids:
                if bucket_id in filled_buckets:
                    bucket_def = INFORMATION_BUCKETS[bucket_id]
                    value = filled_buckets[bucket_id]
                    
                    # Format value based on type
                    if isinstance(value, list):
                        value_str = ', '.join(str(v) for v in value)
                    else:
                        value_str = str(value)
                    
                    category_data.append(f"- {bucket_def.name}: {value_str}")
            
            if category_data:
                summary_parts.append(f"**{category} Information:**\n" + '\n'.join(category_data))
        
        return '\n\n'.join(summary_parts)