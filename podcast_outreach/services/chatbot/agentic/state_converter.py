# podcast_outreach/services/chatbot/agentic/state_converter.py

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import json
import logging

from .bucket_definitions import INFORMATION_BUCKETS
from .db_summary_builder import build_complete_summary_from_db

logger = logging.getLogger(__name__)

class StateConverter:
    """
    Converts between legacy chatbot state format and new agentic state format
    
    Legacy format uses:
    - Phases (introduction, basic_info, experience, etc.)
    - Extracted data as flat dictionary
    - Question tracking
    
    Agentic format uses:
    - Buckets with validation and confidence
    - Structured state with corrections
    - Intelligent context
    """
    
    def __init__(self):
        # Phase to bucket mapping
        self.phase_to_buckets = {
            'introduction': ['full_name', 'email'],
            'basic_info': ['current_role', 'company', 'linkedin_url'],
            'experience': ['years_experience', 'expertise_keywords', 'professional_bio'],
            'achievements': ['success_stories', 'achievements'],
            'podcast_fit': ['podcast_topics', 'unique_perspective', 'target_audience'],
            'speaking_experience': ['media_experience', 'speaking_experience'],
            'content_ideas': ['interesting_hooks', 'controversial_takes'],
            'additional_info': ['website', 'fun_fact']
        }
        
        # Legacy field to bucket mapping - comprehensive mapping
        self.field_to_bucket = {
            # Name variations
            'name': 'full_name',
            'full_name': 'full_name',
            
            # Contact info
            'email': 'email',
            'phone': 'phone',
            'linkedin': 'linkedin_url',
            'linkedin_url': 'linkedin_url',
            'website': 'website',
            'social_media': 'social_media',
            
            # Professional info
            'role': 'current_role',
            'current_role': 'current_role',
            'company': 'company',
            'organization': 'company',  # Alternative field name
            'years_experience': 'years_experience',
            'years': 'years_experience',  # Alternative field name
            'bio': 'professional_bio',
            'professional_bio': 'professional_bio',
            
            # Expertise
            'expertise': 'expertise_keywords',
            'expertise_keywords': 'expertise_keywords',
            'achievements': 'achievements',
            'success_stories': 'success_stories',
            'unique_perspective': 'unique_perspective',
            'differentiator': 'unique_perspective',  # Alternative field name
            
            # Podcast focus
            'topics': 'podcast_topics',
            'podcast_topics': 'podcast_topics',
            'audience': 'target_audience',
            'target_audience': 'target_audience',
            'key_message': 'key_message',
            'media_experience': 'media_experience',
            'speaking_experience': 'speaking_experience',
            
            # Additional info
            'hooks': 'interesting_hooks',
            'interesting_hooks': 'interesting_hooks',
            'controversial_takes': 'controversial_takes',
            'fun_fact': 'fun_fact',
            'scheduling_preference': 'scheduling_preference',
            'promotion_items': 'promotion_items',
            'ideal_podcast': 'ideal_podcast'
        }
    
    def legacy_to_agentic(self, legacy_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert legacy conversation data to agentic format
        
        Args:
            legacy_data: Legacy format conversation data
            
        Returns:
            Agentic format state dictionary
        """
        try:
            # Extract core information
            person_id = legacy_data.get('person_id', 0)
            campaign_id = legacy_data.get('campaign_id', '')
            conversation_id = str(legacy_data.get('conversation_id', ''))
            
            # Parse JSON fields if they're strings
            messages = legacy_data.get('messages', [])
            if isinstance(messages, str):
                messages = json.loads(messages)
            
            extracted_data = legacy_data.get('extracted_data', {})
            if isinstance(extracted_data, str):
                extracted_data = json.loads(extracted_data)
                
            conversation_metadata = legacy_data.get('conversation_metadata', {})
            if isinstance(conversation_metadata, str):
                conversation_metadata = json.loads(conversation_metadata)
            
            # Debug logging
            logger.info(f"StateConverter - legacy_data keys: {list(legacy_data.keys())}")
            logger.info(f"StateConverter - conversation_metadata: {conversation_metadata}")
            logger.info(f"StateConverter - awaiting_confirmation from metadata: {conversation_metadata.get('awaiting_confirmation')}")
            logger.info(f"StateConverter - is_reviewing from metadata: {conversation_metadata.get('is_reviewing')}")
            
            # Convert messages
            agentic_messages = self._convert_messages(messages)
            
            # Convert extracted data to buckets
            buckets = self._convert_extracted_data_to_buckets(
                extracted_data,
                legacy_data.get('conversation_phase', 'introduction')
            )
            
            # Build agentic state
            agentic_state = {
                'person_id': person_id,
                'campaign_id': campaign_id,
                'conversation_id': conversation_id,
                'session_id': conversation_id,
                'company_id': campaign_id,  # For compatibility
                'buckets': buckets,
                'messages': agentic_messages,
                'user_corrections': [],
                'completion_signals': [],
                'context_summary': self._generate_context_summary(legacy_data),
                'created_at': legacy_data.get('created_at', datetime.utcnow().isoformat()),
                'last_updated': datetime.utcnow().isoformat(),
                'is_complete': legacy_data.get('status') == 'completed',
                'completion_confirmed': conversation_metadata.get('completion_confirmed', False),
                'is_reviewing': conversation_metadata.get('is_reviewing', False),
                'awaiting_confirmation': conversation_metadata.get('awaiting_confirmation'),
                'communication_style': {},
                'db_extracted_data': extracted_data,  # Preserve original DB data
                'skipped_optional_buckets': conversation_metadata.get('skipped_optional_buckets', [])
            }
            
            return agentic_state
            
        except Exception as e:
            logger.error(f"Error converting legacy to agentic: {e}")
            # Return minimal valid state
            return {
                'person_id': legacy_data.get('person_id', 0),
                'campaign_id': legacy_data.get('campaign_id', ''),
                'buckets': {},
                'messages': [],
                'last_updated': datetime.utcnow().isoformat()
            }
    
    def agentic_to_legacy_response(
        self,
        response: str,
        new_state: Dict[str, Any],
        old_conversation_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert agentic response to legacy format
        
        Args:
            response: Response message from agentic system
            new_state: New agentic state
            old_conversation_data: Previous legacy conversation data
            
        Returns:
            Legacy format response
        """
        try:
            # Extract bucket data
            extracted_data = self._convert_buckets_to_extracted_data(
                new_state.get('buckets', {})
            )
            
            # Determine phase from buckets
            phase = self._determine_phase_from_buckets(
                new_state.get('buckets', {}),
                old_conversation_data.get('phase', 'introduction')
            )
            
            # Calculate progress
            progress = self._calculate_progress(new_state.get('buckets', {}))
            
            # Get keywords and topics
            keywords, topics, keyword_count = self._extract_keywords_topics(
                extracted_data
            )
            
            # Generate quick replies based on context
            quick_replies = self._generate_quick_replies(
                phase,
                new_state.get('buckets', {})
            )
            
            # Debug logging for response
            logger.info(f"State converter - response has {response.count(chr(10))} newlines")
            logger.info(f"State converter - first 200 chars: {repr(response[:200])}")
            
            return {
                'bot_message': response,
                'extracted_data': extracted_data,
                'progress': progress,
                'phase': phase,
                'keywords_found': keyword_count,
                'keywords': keywords,
                'topics': topics,
                'quick_replies': quick_replies,
                'ready_for_completion': new_state.get('completion_confirmed', False),
                'awaiting_confirmation': new_state.get('awaiting_confirmation'),
                'metadata': {
                    'is_agentic': True,
                    'buckets_filled': len([b for b in new_state.get('buckets', {}).values() if b]),
                    'completion_confirmed': new_state.get('completion_confirmed', False),
                    'is_reviewing': new_state.get('is_reviewing', False),
                    'awaiting_confirmation': new_state.get('awaiting_confirmation'),
                    'skipped_optional_buckets': new_state.get('skipped_optional_buckets', [])
                }
            }
            
        except Exception as e:
            logger.error(f"Error converting agentic to legacy response: {e}")
            return {
                'bot_message': response,
                'extracted_data': {},
                'progress': 0,
                'phase': 'error',
                'keywords_found': 0,
                'quick_replies': []
            }
    
    def agentic_summary_to_legacy(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert agentic summary to legacy format
        
        Args:
            summary: Agentic conversation summary
            
        Returns:
            Legacy format summary
        """
        return {
            'completion_percentage': summary.get('completion_percentage', 0),
            'filled_fields': summary.get('filled_buckets', 0),
            'total_fields': summary.get('total_buckets', 20),
            'key_information': summary.get('key_information', {}),
            'quality_scores': summary.get('quality_scores', {}),
            'is_complete': summary.get('completion_percentage', 0) >= 80,
            'metadata': {
                'is_agentic': True,
                'empty_required': summary.get('empty_required_buckets', [])
            }
        }
    
    def _convert_messages(self, legacy_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert legacy messages to agentic format"""
        converted = []
        
        for msg in legacy_messages:
            converted.append({
                'role': 'user' if msg.get('type') == 'user' else 'assistant',
                'content': msg.get('content', ''),
                'timestamp': msg.get('timestamp', datetime.utcnow().isoformat())
            })
        
        return converted
    
    def _convert_extracted_data_to_buckets(
        self,
        extracted_data: Dict[str, Any],
        current_phase: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Convert legacy extracted data to bucket format - handles nested database structures"""
        buckets = {}
        
        # Debug logging
        logger.debug(f"Converting extracted_data to buckets. Keys: {list(extracted_data.keys())}")
        if 'topics' in extracted_data:
            logger.debug(f"Topics structure: {extracted_data['topics']}")
        if 'key_message' in extracted_data:
            logger.debug(f"Direct key_message: {extracted_data['key_message']}")
        
        # Helper function to create bucket entry
        def create_entry(value, source='database'):
            return {
                'value': value,
                'confidence': 0.9,
                'timestamp': datetime.utcnow().isoformat(),
                'source': source,
                'is_corrected': False
            }
        
        # 1. Handle contact_info nested structure
        if 'contact_info' in extracted_data and isinstance(extracted_data['contact_info'], dict):
            contact_info = extracted_data['contact_info']
            if contact_info.get('fullName'):
                buckets['full_name'] = [create_entry(contact_info['fullName'])]
            if contact_info.get('email'):
                buckets['email'] = [create_entry(contact_info['email'])]
            if contact_info.get('phone'):
                buckets['phone'] = [create_entry(contact_info['phone'])]
            if contact_info.get('linkedin_url'):
                buckets['linkedin_url'] = [create_entry(contact_info['linkedin_url'])]
            if contact_info.get('website'):
                buckets['website'] = [create_entry(contact_info['website'])]
            if contact_info.get('socialMedia') and isinstance(contact_info['socialMedia'], list):
                # Preserve the structure of social media data
                buckets['social_media'] = [create_entry(item) for item in contact_info['socialMedia']]
        
        # 2. Handle professional_bio nested structure
        if 'professional_bio' in extracted_data and isinstance(extracted_data['professional_bio'], dict):
            prof_bio = extracted_data['professional_bio']
            if prof_bio.get('about_work'):
                buckets['professional_bio'] = [create_entry(prof_bio['about_work'])]
            if prof_bio.get('expertise_topics') and isinstance(prof_bio['expertise_topics'], list):
                if 'expertise_keywords' not in buckets:
                    buckets['expertise_keywords'] = []
                buckets['expertise_keywords'].extend([create_entry(topic) for topic in prof_bio['expertise_topics']])
            if prof_bio.get('fullName') and 'full_name' not in buckets:
                buckets['full_name'] = [create_entry(prof_bio['fullName'])]
        
        # 3. Handle topics structure
        if 'topics' in extracted_data and isinstance(extracted_data['topics'], dict):
            topics = extracted_data['topics']
            if topics.get('suggested') and isinstance(topics['suggested'], list):
                buckets['podcast_topics'] = [create_entry(topic) for topic in topics['suggested']]
            # Handle both key_messages and key_message
            if topics.get('key_messages'):
                buckets['key_message'] = [create_entry(topics['key_messages'])]
            if topics.get('key_message'):
                buckets['key_message'] = [create_entry(topics['key_message'])]
        
        # 4. Handle stories array
        if 'stories' in extracted_data and isinstance(extracted_data['stories'], list):
            buckets['success_stories'] = []
            for story in extracted_data['stories']:
                if isinstance(story, dict):
                    story_text = story.get('subject', '')
                    if story.get('result'):
                        story_text = f"{story_text} - {story['result']}" if story_text else story['result']
                    if story.get('challenge'):
                        story_text = f"{story_text}. Challenge: {story['challenge']}"
                    if story_text:
                        buckets['success_stories'].append(create_entry(story_text))
                elif isinstance(story, str) and story:
                    buckets['success_stories'].append(create_entry(story))
        
        # 5. Handle achievements array
        if 'achievements' in extracted_data and isinstance(extracted_data['achievements'], list):
            buckets['achievements'] = []
            for achievement in extracted_data['achievements']:
                if isinstance(achievement, dict) and achievement.get('description'):
                    buckets['achievements'].append(create_entry(achievement['description']))
                elif isinstance(achievement, str) and achievement:
                    buckets['achievements'].append(create_entry(achievement))
        
        # 6. Handle keywords structure
        if 'keywords' in extracted_data and isinstance(extracted_data['keywords'], dict):
            keywords = extracted_data['keywords']
            all_keywords = []
            for ktype in ['explicit', 'implicit', 'contextual']:
                if ktype in keywords and isinstance(keywords[ktype], list):
                    all_keywords.extend(keywords[ktype])
            if all_keywords and 'expertise_keywords' not in buckets:
                buckets['expertise_keywords'] = [create_entry(kw) for kw in all_keywords[:10]]
        
        # 7. Handle media_experience structure
        if 'media_experience' in extracted_data and isinstance(extracted_data['media_experience'], dict):
            media_exp = extracted_data['media_experience']
            if media_exp.get('previous_podcasts'):
                buckets['media_experience'] = [create_entry(media_exp['previous_podcasts'])]
            if media_exp.get('speaking_experience'):
                buckets['speaking_experience'] = [create_entry(media_exp['speaking_experience'])]
        
        # 8. Handle direct top-level fields using original mapping
        for field, value in extracted_data.items():
            if value and field in self.field_to_bucket:
                bucket_id = self.field_to_bucket[field]
                # Skip if already populated from nested structure
                if bucket_id not in buckets:
                    if isinstance(value, list):
                        buckets[bucket_id] = [create_entry(item) for item in value if item]
                    else:
                        buckets[bucket_id] = [create_entry(value)]
        
        # 9. Handle special fields that might be stored differently
        if 'unique_value' in extracted_data and extracted_data['unique_value'] and 'unique_perspective' not in buckets:
            buckets['unique_perspective'] = [create_entry(extracted_data['unique_value'])]
        
        if 'topics_can_discuss' in extracted_data and extracted_data['topics_can_discuss']:
            if 'podcast_topics' not in buckets:
                buckets['podcast_topics'] = []
            if isinstance(extracted_data['topics_can_discuss'], list):
                buckets['podcast_topics'].extend([create_entry(topic) for topic in extracted_data['topics_can_discuss']])
            else:
                buckets['podcast_topics'].append(create_entry(extracted_data['topics_can_discuss']))
        
        if 'promotion_preferences' in extracted_data and extracted_data['promotion_preferences'] and 'promotion_items' not in buckets:
            buckets['promotion_items'] = [create_entry(extracted_data['promotion_preferences'])]
        
        # Log restoration for debugging
        if buckets:
            logger.info(f"Restored {len(buckets)} buckets from database after server restart")
            filled_required = sum(1 for bid in ['full_name', 'email', 'current_role', 'professional_bio', 
                                               'expertise_keywords', 'podcast_topics', 'success_stories'] 
                                if bid in buckets and buckets[bid])
            logger.info(f"Restored {filled_required} required buckets")
        
        return buckets
    
    def _convert_buckets_to_extracted_data(
        self,
        buckets: Dict[str, List[Dict[str, Any]]]
    ) -> Dict[str, Any]:
        """Convert agentic buckets back to legacy extracted data"""
        extracted = {}
        
        # Debug logging
        if 'key_message' in buckets:
            logger.info(f"Converting key_message bucket with {len(buckets['key_message'])} entries")
            if buckets['key_message']:
                logger.info(f"Key message value: {buckets['key_message'][-1]}")
        
        # Reverse mapping
        bucket_to_field = {v: k for k, v in self.field_to_bucket.items()}
        
        for bucket_id, entries in buckets.items():
            if entries:
                # Get the latest value
                latest = entries[-1]
                # Handle different entry formats
                if isinstance(latest, dict):
                    value = latest.get('value')
                elif hasattr(latest, 'value'):
                    value = latest.value
                else:
                    value = latest
                
                # Use original field name if available
                field_name = bucket_to_field.get(bucket_id, bucket_id)
                
                # Handle multiple values
                bucket_def = INFORMATION_BUCKETS.get(bucket_id)
                if len(entries) > 1 and bucket_def and bucket_def.allow_multiple:
                    values = []
                    for e in entries:
                        if isinstance(e, dict):
                            values.append(e.get('value'))
                        elif hasattr(e, 'value'):
                            values.append(e.value)
                        else:
                            values.append(e)
                    extracted[field_name] = values
                else:
                    extracted[field_name] = value
                
                # Special handling for key_message - ensure it's stored in topics structure
                if bucket_id == 'key_message' and value:
                    if 'topics' not in extracted:
                        extracted['topics'] = {}
                    extracted['topics']['key_message'] = value
                
                # Special handling for social_media - preserve structure
                if bucket_id == 'social_media':
                    # Don't use the bucket_to_field mapping for social_media
                    # It needs to stay as 'social_media' for the data merger
                    extracted['social_media'] = values if 'values' in locals() else value
        
        return extracted
    
    def _determine_phase_from_buckets(
        self,
        buckets: Dict[str, List[Any]],
        current_phase: str
    ) -> str:
        """Determine the appropriate phase based on filled buckets"""
        
        # Count filled buckets per phase
        phase_completion = {}
        
        for phase, phase_buckets in self.phase_to_buckets.items():
            filled = sum(1 for b in phase_buckets if b in buckets and buckets[b])
            total = len(phase_buckets)
            phase_completion[phase] = (filled, total)
        
        # Find the first incomplete phase
        phase_order = [
            'introduction', 'basic_info', 'experience', 
            'achievements', 'podcast_fit', 'speaking_experience',
            'content_ideas', 'additional_info'
        ]
        
        for phase in phase_order:
            filled, total = phase_completion.get(phase, (0, 1))
            if filled < total:
                return phase
        
        # All phases complete
        return 'review'
    
    def _calculate_progress(self, buckets: Dict[str, List[Any]]) -> int:
        """Calculate overall progress percentage"""
        
        # Count all filled buckets (not just required)
        filled_buckets = sum(
            1 for bid in INFORMATION_BUCKETS
            if bid in buckets and buckets[bid]
        )
        
        total_buckets = len(INFORMATION_BUCKETS)
        
        if not total_buckets:
            return 100
        
        # Calculate based on total buckets and cap at 100%
        progress = int((filled_buckets / total_buckets) * 100)
        return min(100, progress)
    
    def _extract_keywords_topics(
        self,
        extracted_data: Dict[str, Any]
    ) -> Tuple[List[str], List[str], int]:
        """Extract keywords and topics from data"""
        
        keywords = []
        topics = []
        
        # Extract from expertise
        if 'expertise_keywords' in extracted_data:
            expertise = extracted_data['expertise_keywords']
            if isinstance(expertise, list):
                keywords.extend(expertise)
            else:
                keywords.append(str(expertise))
        
        # Extract from topics
        if 'podcast_topics' in extracted_data:
            podcast_topics = extracted_data['podcast_topics']
            if isinstance(podcast_topics, list):
                topics.extend(podcast_topics)
            else:
                topics.append(str(podcast_topics))
        
        return keywords, topics, len(keywords)
    
    def _generate_quick_replies(
        self,
        phase: str,
        buckets: Dict[str, List[Any]]
    ) -> List[str]:
        """Generate context-appropriate quick replies"""
        
        quick_replies = {
            'introduction': [
                "I prefer not to share",
                "Skip this question",
                "Can you clarify?"
            ],
            'basic_info': [
                "I'm self-employed",
                "I work at multiple companies",
                "I don't have a LinkedIn"
            ],
            'experience': [
                "Less than 1 year",
                "5-10 years",
                "Over 20 years"
            ],
            'achievements': [
                "I don't have any major achievements",
                "I prefer not to share",
                "Skip this section"
            ],
            'podcast_fit': [
                "I can talk about multiple topics",
                "I'm not sure",
                "I'm flexible on topics"
            ]
        }
        
        return quick_replies.get(phase, ["Skip", "I'm not sure", "Can you help?"])
    
    def _generate_context_summary(self, legacy_data: Dict[str, Any]) -> str:
        """Generate a context summary from legacy data"""
        
        phase = legacy_data.get('phase', 'introduction')
        progress = legacy_data.get('progress', 0)
        
        return f"Conversation in {phase} phase with {progress}% completion. Migrated from legacy system."