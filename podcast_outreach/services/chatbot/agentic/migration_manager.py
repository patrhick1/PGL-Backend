# podcast_outreach/services/chatbot/agentic/migration_manager.py

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from uuid import UUID
import json
import logging
import asyncio

from .state_converter import StateConverter
from .conversation_orchestrator import ConversationOrchestrator

logger = logging.getLogger(__name__)

class MigrationManager:
    """
    Manages migration of conversations from legacy to agentic system
    
    Features:
    - Batch migration of existing conversations
    - Individual conversation migration
    - Progress tracking
    - Rollback capabilities
    - Validation and verification
    """
    
    def __init__(self, db_connection=None):
        self.state_converter = StateConverter()
        self.orchestrator = ConversationOrchestrator()
        self.db = db_connection
        
        # Migration tracking
        self.migration_log = []
        self.batch_size = 100
        self.migration_delay = 0.1  # Seconds between migrations
    
    async def migrate_conversation(
        self,
        conversation_id: str,
        conversation_data: Dict[str, Any],
        validate: bool = True
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Migrate a single conversation to agentic format
        
        Args:
            conversation_id: Conversation ID
            conversation_data: Legacy conversation data
            validate: Whether to validate the migration
            
        Returns:
            Tuple of (success, migrated_data, error_message)
        """
        try:
            # Check if already migrated
            if conversation_data.get('metadata', {}).get('is_agentic'):
                return True, conversation_data, "Already migrated"
            
            # Convert to agentic format
            agentic_state = self.state_converter.legacy_to_agentic(
                conversation_data
            )
            
            # Validate if requested
            if validate:
                is_valid, validation_errors = self._validate_migration(
                    conversation_data, agentic_state
                )
                
                if not is_valid:
                    return False, None, f"Validation failed: {', '.join(validation_errors)}"
            
            # Mark as migrated
            agentic_state['metadata'] = agentic_state.get('metadata', {})
            agentic_state['metadata']['is_agentic'] = True
            agentic_state['metadata']['migration_timestamp'] = datetime.utcnow().isoformat()
            agentic_state['metadata']['migration_version'] = '1.0'
            
            # Log migration
            self._log_migration(conversation_id, 'success')
            
            return True, agentic_state, None
            
        except Exception as e:
            logger.error(f"Error migrating conversation {conversation_id}: {e}")
            self._log_migration(conversation_id, 'failed', str(e))
            return False, None, str(e)
    
    async def migrate_batch(
        self,
        conversations: List[Tuple[str, Dict[str, Any]]],
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Migrate a batch of conversations
        
        Args:
            conversations: List of (conversation_id, conversation_data) tuples
            progress_callback: Optional callback for progress updates
            
        Returns:
            Migration results summary
        """
        results = {
            'total': len(conversations),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'errors': [],
            'start_time': datetime.utcnow(),
            'end_time': None
        }
        
        for i, (conv_id, conv_data) in enumerate(conversations):
            # Migrate conversation
            success, migrated_data, error = await self.migrate_conversation(
                conv_id, conv_data
            )
            
            if success:
                if error == "Already migrated":
                    results['skipped'] += 1
                else:
                    results['successful'] += 1
                    
                    # Save migrated data if database available
                    if self.db and migrated_data:
                        await self._save_migrated_conversation(
                            conv_id, migrated_data
                        )
            else:
                results['failed'] += 1
                results['errors'].append({
                    'conversation_id': conv_id,
                    'error': error
                })
            
            # Progress callback
            if progress_callback:
                progress = (i + 1) / len(conversations) * 100
                await progress_callback(progress, results)
            
            # Rate limiting
            await asyncio.sleep(self.migration_delay)
        
        results['end_time'] = datetime.utcnow()
        results['duration'] = (
            results['end_time'] - results['start_time']
        ).total_seconds()
        
        return results
    
    async def validate_migration_batch(
        self,
        conversation_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Validate a batch of migrated conversations
        
        Args:
            conversation_ids: List of conversation IDs to validate
            
        Returns:
            Validation results
        """
        results = {
            'total': len(conversation_ids),
            'valid': 0,
            'invalid': 0,
            'errors': []
        }
        
        for conv_id in conversation_ids:
            # Load conversation
            if self.db:
                conv_data = await self._load_conversation(conv_id)
                
                if not conv_data:
                    results['invalid'] += 1
                    results['errors'].append({
                        'conversation_id': conv_id,
                        'error': 'Conversation not found'
                    })
                    continue
                
                # Check if migrated
                if not conv_data.get('metadata', {}).get('is_agentic'):
                    results['invalid'] += 1
                    results['errors'].append({
                        'conversation_id': conv_id,
                        'error': 'Not migrated'
                    })
                    continue
                
                # Validate structure
                is_valid = self._validate_agentic_structure(conv_data)
                
                if is_valid:
                    results['valid'] += 1
                else:
                    results['invalid'] += 1
                    results['errors'].append({
                        'conversation_id': conv_id,
                        'error': 'Invalid structure'
                    })
        
        return results
    
    async def rollback_conversation(
        self,
        conversation_id: str,
        backup_data: Dict[str, Any]
    ) -> bool:
        """
        Rollback a conversation to legacy format
        
        Args:
            conversation_id: Conversation ID
            backup_data: Original legacy data
            
        Returns:
            Success boolean
        """
        try:
            # Remove agentic markers
            if 'metadata' in backup_data:
                backup_data['metadata'].pop('is_agentic', None)
                backup_data['metadata'].pop('migration_timestamp', None)
                backup_data['metadata'].pop('migration_version', None)
            
            # Save rollback
            if self.db:
                await self._save_conversation(conversation_id, backup_data)
            
            # Log rollback
            self._log_migration(conversation_id, 'rolled_back')
            
            return True
            
        except Exception as e:
            logger.error(f"Error rolling back conversation {conversation_id}: {e}")
            return False
    
    def get_migration_stats(self) -> Dict[str, Any]:
        """Get migration statistics"""
        
        if not self.migration_log:
            return {
                'total_migrations': 0,
                'successful': 0,
                'failed': 0,
                'rolled_back': 0
            }
        
        stats = {
            'total_migrations': len(self.migration_log),
            'successful': sum(1 for m in self.migration_log if m['status'] == 'success'),
            'failed': sum(1 for m in self.migration_log if m['status'] == 'failed'),
            'rolled_back': sum(1 for m in self.migration_log if m['status'] == 'rolled_back'),
            'recent_migrations': self._get_recent_migrations(hours=24),
            'error_summary': self._get_error_summary()
        }
        
        return stats
    
    def _validate_migration(
        self,
        legacy_data: Dict[str, Any],
        agentic_data: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """Validate a migration"""
        errors = []
        
        # Check required fields
        required_fields = ['person_id', 'buckets', 'messages']
        for field in required_fields:
            if field not in agentic_data:
                errors.append(f"Missing required field: {field}")
        
        # Validate data preservation
        legacy_extracted = legacy_data.get('extracted_data', {})
        agentic_buckets = agentic_data.get('buckets', {})
        
        # Check that all legacy data is preserved
        for field, value in legacy_extracted.items():
            if value and field in self.state_converter.field_to_bucket:
                bucket_id = self.state_converter.field_to_bucket[field]
                if bucket_id not in agentic_buckets:
                    errors.append(f"Lost data for field: {field}")
        
        # Validate message count
        legacy_messages = legacy_data.get('messages', [])
        agentic_messages = agentic_data.get('messages', [])
        
        if len(agentic_messages) != len(legacy_messages):
            errors.append(
                f"Message count mismatch: {len(legacy_messages)} -> {len(agentic_messages)}"
            )
        
        return len(errors) == 0, errors
    
    def _validate_agentic_structure(self, data: Dict[str, Any]) -> bool:
        """Validate agentic data structure"""
        
        required_fields = [
            'person_id', 'campaign_id', 'buckets', 'messages',
            'user_corrections', 'completion_signals'
        ]
        
        for field in required_fields:
            if field not in data:
                return False
        
        # Validate buckets structure
        buckets = data.get('buckets', {})
        if not isinstance(buckets, dict):
            return False
        
        # Validate messages structure
        messages = data.get('messages', [])
        if not isinstance(messages, list):
            return False
        
        return True
    
    def _log_migration(
        self,
        conversation_id: str,
        status: str,
        error: Optional[str] = None
    ):
        """Log migration event"""
        self.migration_log.append({
            'conversation_id': conversation_id,
            'status': status,
            'timestamp': datetime.utcnow(),
            'error': error
        })
    
    def _get_recent_migrations(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get recent migrations"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        return [
            m for m in self.migration_log
            if m['timestamp'] > cutoff
        ]
    
    def _get_error_summary(self) -> Dict[str, int]:
        """Get summary of migration errors"""
        error_counts = {}
        
        for migration in self.migration_log:
            if migration['status'] == 'failed' and migration.get('error'):
                error_type = migration['error'].split(':')[0]
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
        
        return error_counts
    
    # Database operations (implement based on your database)
    
    async def _save_migrated_conversation(
        self,
        conversation_id: str,
        data: Dict[str, Any]
    ):
        """Save migrated conversation to database"""
        # Implement based on your database
        pass
    
    async def _load_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Load conversation from database"""
        # Implement based on your database
        return None
    
    async def _save_conversation(
        self,
        conversation_id: str,
        data: Dict[str, Any]
    ):
        """Save conversation to database"""
        # Implement based on your database
        pass