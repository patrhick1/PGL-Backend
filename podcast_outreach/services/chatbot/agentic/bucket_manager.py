# podcast_outreach/services/chatbot/agentic/bucket_manager.py

from typing import Dict, List, Tuple, Optional, Any, Set
from datetime import datetime
from dataclasses import dataclass
import re

from podcast_outreach.logging_config import get_logger
from .bucket_definitions import INFORMATION_BUCKETS, BucketDefinition
from .state_manager import StateManager, BucketEntry
from .message_classifier import ClassificationResult
from .data_models import process_social_media_value

logger = get_logger(__name__)

@dataclass
class UpdateResult:
    """Result of a bucket update operation"""
    success: bool
    updated_buckets: List[str]
    failed_buckets: Dict[str, str]  # bucket_id -> error message
    duplicates_prevented: List[str]
    corrections_applied: List[str]
    
class BucketManager:
    """Manages bucket updates with validation, deduplication, and correction handling"""
    
    def __init__(self):
        # Similarity threshold for duplicate detection
        self.similarity_threshold = 0.85
        
        # Normalizers for data cleaning
        self.normalizers = {
            'email': self._normalize_email,
            'phone': self._normalize_phone,
            'linkedin_url': self._normalize_linkedin_url,
            'website': self._normalize_website,
            'full_name': self._normalize_name
        }
    
    async def process_classification(
        self,
        classification: ClassificationResult,
        state: StateManager,
        user_message: str
    ) -> UpdateResult:
        """
        Process a classification result and update buckets accordingly
        
        Args:
            classification: Result from message classifier
            state: Current conversation state
            user_message: Original user message for context
            
        Returns:
            UpdateResult with details of what was updated
        """
        updated_buckets = []
        failed_buckets = {}
        duplicates_prevented = []
        corrections_applied = []
        
        # Handle different intents
        if classification.user_intent == 'correction':
            # Process as corrections
            correction_results = await self._process_corrections(
                classification, state, user_message
            )
            corrections_applied.extend(correction_results)
        
        # Process each bucket update
        for bucket_id, (value, confidence) in classification.bucket_updates.items():
            # Skip if confidence too low
            if confidence < 0.6:
                logger.info(f"Skipping {bucket_id} update due to low confidence: {confidence}")
                continue
            
            # Validate bucket exists
            if bucket_id not in INFORMATION_BUCKETS:
                failed_buckets[bucket_id] = "Unknown bucket"
                continue
            
            bucket_def = INFORMATION_BUCKETS[bucket_id]
            
            # Determine if this is a correction early
            is_correction = (
                classification.user_intent == 'correction' or
                self._is_implicit_correction(bucket_id, state, user_message)
            )
            
            # Handle list values for multi-entry buckets
            if bucket_def.allow_multiple and isinstance(value, list):
                # Handle empty list (user has none)
                if len(value) == 0:
                    # Mark bucket as "none" to indicate user explicitly said they have none
                    success = state.update_bucket(
                        bucket_id, 
                        "none",  # Special marker for "user has none"
                        confidence=confidence,
                        is_correction=is_correction
                    )
                    if success:
                        updated_buckets.append(bucket_id)
                        logger.info(f"User indicated they have no {bucket_id}")
                    continue
                
                # Special handling for social media bucket
                if bucket_id == 'social_media':
                    # Process social media values using the extractor
                    processed_profiles = process_social_media_value(value)
                    if processed_profiles:
                        # Store processed profiles
                        for profile in processed_profiles:
                            success = state.update_bucket(
                                bucket_id,
                                profile,
                                confidence=confidence,
                                is_correction=is_correction
                            )
                        if success:
                            updated_buckets.append(bucket_id)
                            logger.info(f"Processed {len(processed_profiles)} social media profiles")
                    continue
                
                # Process each item in the list
                list_success = True
                for item in value:
                    # Normalize individual item if normalizer exists
                    if bucket_id in self.normalizers:
                        item = self.normalizers[bucket_id](item)
                    
                    # Check for duplicates
                    if self._is_duplicate(bucket_id, item, state):
                        duplicates_prevented.append(bucket_id)
                        logger.info(f"Prevented duplicate entry for {bucket_id}: {item}")
                        continue
                    
                    # Validate individual item
                    if not bucket_def.validate(item):
                        failed_buckets[bucket_id] = f"Validation failed for item: {item}"
                        logger.warning(f"Validation failed for {bucket_id} item: {item}")
                        list_success = False
                        continue
                    
                    # Update bucket with individual item
                    success = state.update_bucket(
                        bucket_id, 
                        item, 
                        confidence=confidence,
                        is_correction=is_correction
                    )
                    
                    if not success:
                        list_success = False
                
                if list_success and value:  # At least one item was added
                    updated_buckets.append(bucket_id)
                    if is_correction:
                        corrections_applied.append(bucket_id)
                elif not list_success:
                    failed_buckets[bucket_id] = "Some items failed to update"
                continue
            
            # Single value processing (original logic)
            # Normalize value if normalizer exists
            if bucket_id in self.normalizers:
                value = self.normalizers[bucket_id](value)
            
            # Check for duplicates
            if self._is_duplicate(bucket_id, value, state):
                duplicates_prevented.append(bucket_id)
                logger.info(f"Prevented duplicate entry for {bucket_id}: {value}")
                continue
            
            # Validate value
            if not bucket_def.validate(value):
                failed_buckets[bucket_id] = "Validation failed"
                logger.warning(f"Validation failed for {bucket_id}: {value}")
                
                # Check if this is a negative response for an optional field
                if not bucket_def.required and classification.user_intent == 'provide_info':
                    # Check if user is saying they don't have this
                    negative_indicators = ["don't have", "dont have", "do not have", "no ", "none", "not applicable", "n/a"]
                    message_lower = user_message.lower()
                    if any(indicator in message_lower for indicator in negative_indicators):
                        logger.info(f"User indicated they don't have {bucket_id} - marking as skipped")
                        state.mark_optional_bucket_skipped(bucket_id)
                        # Remove from failed buckets since it's intentionally skipped
                        del failed_buckets[bucket_id]
                        updated_buckets.append(bucket_id)  # Count as "handled"
                
                continue
            
            # Special handling for social media strings
            if bucket_id == 'social_media' and isinstance(value, str):
                # Process social media string using the extractor
                processed_profiles = process_social_media_value(value)
                if processed_profiles:
                    # Store processed profiles
                    for profile in processed_profiles:
                        success = state.update_bucket(
                            bucket_id,
                            profile,
                            confidence=confidence,
                            is_correction=is_correction
                        )
                    if success:
                        updated_buckets.append(bucket_id)
                        logger.info(f"Processed {len(processed_profiles)} social media profiles from string")
                continue
            
            # Update bucket
            success = state.update_bucket(
                bucket_id, 
                value, 
                confidence=confidence,
                is_correction=is_correction
            )
            
            if success:
                updated_buckets.append(bucket_id)
                if is_correction:
                    corrections_applied.append(bucket_id)
            else:
                failed_buckets[bucket_id] = "Update failed"
        
        # Log the update
        self._log_update(state, updated_buckets, classification.user_intent)
        
        return UpdateResult(
            success=len(updated_buckets) > 0,
            updated_buckets=updated_buckets,
            failed_buckets=failed_buckets,
            duplicates_prevented=duplicates_prevented,
            corrections_applied=corrections_applied
        )
    
    def _normalize_email(self, email: str) -> str:
        """Normalize email address"""
        if isinstance(email, str):
            return email.lower().strip()
        return email
    
    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number"""
        if not isinstance(phone, str):
            return phone
        
        # Remove all non-numeric characters
        digits = re.sub(r'\D', '', phone)
        
        # Format as XXX-XXX-XXXX if US number
        if len(digits) == 10:
            return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            # Remove country code
            return f"{digits[1:4]}-{digits[4:7]}-{digits[7:]}"
        
        return phone  # Return original if can't normalize
    
    def _normalize_linkedin_url(self, url: str) -> str:
        """Normalize LinkedIn URL"""
        if not isinstance(url, str):
            return url
        
        url = url.strip()
        
        # Add protocol if missing
        if not url.startswith('http'):
            url = f'https://{url}'
        
        # Ensure it's the full URL
        if 'linkedin.com/in/' in url:
            # Extract the profile part and rebuild
            match = re.search(r'linkedin\.com/in/([\w-]+)', url)
            if match:
                return f'https://www.linkedin.com/in/{match.group(1)}'
        
        return url
    
    def _normalize_website(self, url: str) -> str:
        """Normalize website URL"""
        if not isinstance(url, str):
            return url
        
        url = url.strip()
        
        # Add protocol if missing
        if not url.startswith('http'):
            url = f'https://{url}'
        
        return url
    
    def _normalize_name(self, name: str) -> str:
        """Normalize name"""
        if not isinstance(name, str):
            return name
        
        # Clean up extra spaces
        name = ' '.join(name.strip().split())
        
        # Handle titles specially
        titles = ['Dr.', 'Mr.', 'Ms.', 'Mrs.', 'Prof.', 'Dr', 'Mr', 'Ms', 'Mrs', 'Prof']
        words = name.split()
        
        result = []
        for i, word in enumerate(words):
            if word in titles or word in [t.lower() for t in titles]:
                # Keep title as-is but ensure it has a period
                if not word.endswith('.'):
                    result.append(word.capitalize() + '.')
                else:
                    result.append(word.capitalize())
            else:
                # Capitalize other words
                result.append(word.capitalize())
        
        return ' '.join(result)
    
    def _is_duplicate(self, bucket_id: str, value: Any, state: StateManager) -> bool:
        """Check if value is duplicate of existing bucket entry"""
        current_value = state.get_bucket_value(bucket_id)
        
        if current_value is None:
            return False
        
        # Handle list buckets
        if isinstance(current_value, list):
            # Check each item in the list
            for existing_item in current_value:
                if self._values_similar(existing_item, value):
                    return True
            return False
        
        # Single value bucket
        return self._values_similar(current_value, value)
    
    def _values_similar(self, val1: Any, val2: Any) -> bool:
        """Check if two values are similar enough to be duplicates"""
        
        # Exact match
        if val1 == val2:
            return True
        
        # String similarity
        if isinstance(val1, str) and isinstance(val2, str):
            # Normalize for comparison
            norm1 = val1.lower().strip()
            norm2 = val2.lower().strip()
            
            if norm1 == norm2:
                return True
            
            # Check for subset (one contains the other)
            if norm1 in norm2 or norm2 in norm1:
                return True
            
            # TODO: Add fuzzy matching for typos
        
        # Dict similarity (for stories, achievements)
        if isinstance(val1, dict) and isinstance(val2, dict):
            # Check if key fields match
            key_fields = ['subject', 'description', 'result']
            for field in key_fields:
                if field in val1 and field in val2:
                    if self._values_similar(val1[field], val2[field]):
                        return True
        
        return False
    
    def _is_implicit_correction(
        self, 
        bucket_id: str, 
        state: StateManager,
        user_message: str
    ) -> bool:
        """Detect if this is an implicit correction"""
        
        # Check if bucket already has a value
        current_value = state.get_bucket_value(bucket_id)
        if current_value is None:
            return False
        
        # Check recent messages for correction indicators
        recent_messages = state.get_recent_messages(3)
        if len(recent_messages) >= 2:
            # Check if assistant just asked about this bucket
            last_bot_message = None
            for msg in reversed(recent_messages):
                if msg.role == 'assistant':
                    last_bot_message = msg.content.lower()
                    break
            
            if last_bot_message:
                bucket_def = INFORMATION_BUCKETS[bucket_id]
                # Check if bot asked about this specific bucket
                if bucket_def.name.lower() in last_bot_message:
                    # User is providing new value after bot asked = likely correction
                    return True
        
        # Check for correction phrases even without explicit markers
        message_lower = user_message.lower()
        soft_correction_phrases = [
            'it\'s actually',
            'i meant',
            'should be',
            'make that',
            'change it to'
        ]
        
        for phrase in soft_correction_phrases:
            if phrase in message_lower:
                return True
        
        return False
    
    async def _process_corrections(
        self,
        classification: ClassificationResult,
        state: StateManager,
        user_message: str
    ) -> List[str]:
        """Process corrections specifically"""
        corrected_buckets = []
        
        # Look for what the user is correcting
        # Often corrections reference the previous value
        message_lower = user_message.lower()
        
        # Try to identify which bucket is being corrected
        for bucket_id in classification.bucket_updates:
            current_value = state.get_bucket_value(bucket_id)
            
            if current_value is not None:
                # This bucket has a value and user is providing new one
                corrected_buckets.append(bucket_id)
                logger.info(f"Correction detected for {bucket_id}: {current_value} -> {classification.bucket_updates[bucket_id][0]}")
        
        # If no specific bucket identified, check message for clues
        if not corrected_buckets:
            # Check which buckets were recently discussed
            recent_updates = self._get_recent_bucket_updates(state)
            for bucket_id in recent_updates:
                if bucket_id in classification.bucket_updates:
                    corrected_buckets.append(bucket_id)
        
        return corrected_buckets
    
    def _get_recent_bucket_updates(self, state: StateManager) -> List[str]:
        """Get buckets that were recently updated"""
        recent_buckets = []
        
        # Look at buckets updated in last 3 messages
        recent_message_indices = set()
        messages = state.state['messages']
        if len(messages) >= 3:
            recent_message_indices = {len(messages) - 1, len(messages) - 2, len(messages) - 3}
        
        for bucket_id, entries in state.state['buckets'].items():
            for entry in entries:
                if hasattr(entry, 'source_message_index'):
                    if entry.source_message_index in recent_message_indices:
                        recent_buckets.append(bucket_id)
                        break
        
        return recent_buckets
    
    def _log_update(
        self, 
        state: StateManager,
        updated_buckets: List[str],
        user_intent: str
    ) -> None:
        """Log the update for debugging and analytics"""
        
        filled_count = len(state.get_filled_buckets())
        required_remaining = len(state.get_empty_required_buckets())
        
        logger.info(
            f"Bucket update - Intent: {user_intent}, "
            f"Updated: {updated_buckets}, "
            f"Filled: {filled_count}/20, "
            f"Required remaining: {required_remaining}"
        )
    
    def suggest_next_buckets(self, state: StateManager) -> List[str]:
        """Suggest which buckets to ask about next"""
        
        # Priority order:
        # 1. Required buckets that are empty
        # 2. Optional buckets related to filled buckets
        # 3. Other optional buckets
        
        suggestions = []
        
        # Get empty required buckets
        empty_required = state.get_empty_required_buckets()
        if empty_required:
            # Prioritize certain required buckets
            priority_order = [
                'full_name', 'email', 'current_role', 'professional_bio',
                'expertise_keywords', 'success_stories', 'podcast_topics'
            ]
            
            for bucket_id in priority_order:
                if bucket_id in empty_required:
                    suggestions.append(bucket_id)
                    if len(suggestions) >= 3:
                        break
            
            # Add any remaining required
            for bucket_id in empty_required:
                if bucket_id not in suggestions:
                    suggestions.append(bucket_id)
                    if len(suggestions) >= 3:
                        break
        
        # If less than 3 suggestions, add related optional buckets
        if len(suggestions) < 3:
            filled = state.get_filled_buckets()
            
            # Related bucket mapping
            related_buckets = {
                'email': ['phone', 'linkedin_url'],
                'current_role': ['company', 'years_experience'],
                'success_stories': ['achievements'],
                'podcast_topics': ['speaking_experience', 'target_audience']
            }
            
            for filled_bucket in filled:
                if filled_bucket in related_buckets:
                    for related in related_buckets[filled_bucket]:
                        if related not in filled and related not in suggestions:
                            suggestions.append(related)
                            if len(suggestions) >= 3:
                                return suggestions[:3]
        
        return suggestions[:3]
    
    def get_bucket_quality_score(self, state: StateManager) -> Dict[str, float]:
        """Calculate quality scores for each filled bucket"""
        scores = {}
        
        for bucket_id, entries in state.state['buckets'].items():
            if not entries:
                continue
            
            bucket_def = INFORMATION_BUCKETS.get(bucket_id)
            if not bucket_def:
                continue
            
            # Calculate score based on:
            # - Confidence of entries
            # - Completeness (for multi-entry buckets)
            # - No corrections needed
            
            avg_confidence = sum(e.confidence for e in entries) / len(entries)
            
            # Completeness score
            if bucket_def.allow_multiple:
                if bucket_def.min_entries:
                    completeness = min(1.0, len(entries) / bucket_def.min_entries)
                else:
                    completeness = 1.0
            else:
                completeness = 1.0
            
            # Correction penalty
            corrections = state.get_corrections_for_bucket(bucket_id)
            correction_penalty = 0.1 * len(corrections)
            
            # Final score
            score = (avg_confidence * 0.7 + completeness * 0.3) - correction_penalty
            scores[bucket_id] = max(0.0, min(1.0, score))
        
        return scores