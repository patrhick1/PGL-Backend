# podcast_outreach/services/events/processor.py

"""
Event Processor Service for Nylas Webhooks
Handles event persistence, deduplication, and automation triggers
"""

import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import asyncio
from uuid import uuid4

from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import pitches_nylas
from podcast_outreach.database.connection import get_db_async
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)


class EventProcessor:
    """
    Processes Nylas webhook events with deduplication and persistence.
    Ensures idempotent processing and triggers automation rules.
    """
    
    def __init__(self):
        self.processed_events = set()  # In-memory cache for quick dedup
        self._automation_handlers = {}
        self._setup_automation_handlers()
    
    def _setup_automation_handlers(self):
        """Setup automation handler mappings."""
        self._automation_handlers = {
            'message.bounce_detected': self._handle_bounce_automation,
            'message.opened': self._handle_open_automation,
            'message.link_clicked': self._handle_click_automation,
            'message.replied': self._handle_reply_automation,
            'message.send_failed': self._handle_send_failure_automation
        }
    
    async def process_webhook_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single webhook event with deduplication.
        
        Args:
            event_data: Raw webhook event data from Nylas
            
        Returns:
            Processing result with success status
        """
        result = {
            "success": False,
            "event_id": None,
            "duplicate": False,
            "message": ""
        }
        
        try:
            # Extract event details
            event_type = event_data.get('type')
            event_id = event_data.get('id')
            obj = event_data.get('data', {}) or {}
            
            # v3: message_id appears in different places depending on event
            message_id = (
                obj.get('message_id') or          # tracking events (opened, link_clicked, thread.replied)
                obj.get('id') or                  # message.created / updated / send_success / send_failed
                (obj.get('origin') or {}).get('id') or  # bounce_detected original message id
                obj.get('root_message_id')        # thread.replied original tracked message id (fallback)
            )
            
            # Ensure we keep the event time correctly
            event_time = event_data.get('time')  # set by router
            if not event_time:
                # tracking puts timestamp under message_data; messages have `date`
                event_time = (obj.get('message_data') or {}).get('timestamp') or obj.get('date')
            
            if not event_id:
                # Generate event ID if not provided
                event_id = str(uuid4())
                event_data['id'] = event_id
            
            result["event_id"] = event_id
            
            # Check for duplicate in memory first (fast check)
            if event_id in self.processed_events:
                result["duplicate"] = True
                result["message"] = f"Event {event_id} already processed (memory cache)"
                logger.info(result["message"])
                return result
            
            # Check for duplicate in database (authoritative check)
            is_duplicate = await self._check_duplicate_in_db(event_id)
            if is_duplicate:
                # Add to memory cache for future fast checks
                self.processed_events.add(event_id)
                result["duplicate"] = True
                result["message"] = f"Event {event_id} already processed (database)"
                logger.info(result["message"])
                return result
            
            # Find associated pitch if message_id exists
            pitch_id = None
            if message_id:
                pitch_record = await pitches_nylas.get_pitch_by_nylas_message_id(message_id)
                if pitch_record:
                    pitch_id = pitch_record.get('pitch_id')
            
            # Persist the event
            await self._persist_event(
                event_id=event_id,
                message_id=message_id,
                pitch_id=pitch_id,
                event_type=event_type,
                event_data=event_data,
                event_time=event_time
            )
            
            # Add to memory cache
            self.processed_events.add(event_id)
            
            # Update aggregate counts on pitch if applicable
            if pitch_id:
                await self._update_pitch_metrics(pitch_id, event_type, event_data)
            
            # Trigger automation rules
            if event_type in self._automation_handlers:
                await self._automation_handlers[event_type](event_data, pitch_id)
            
            result["success"] = True
            result["message"] = f"Event {event_id} processed successfully"
            logger.info(f"Processed {event_type} event: {event_id}")
            
        except Exception as e:
            logger.exception(f"Error processing webhook event: {e}")
            result["message"] = f"Error processing event: {str(e)}"
        
        return result
    
    async def _check_duplicate_in_db(self, event_id: str) -> bool:
        """Check if event already exists in database."""
        async with get_db_async() as db:
            query = """
                SELECT event_id 
                FROM message_events 
                WHERE event_id = $1 
                LIMIT 1
            """
            result = await db.fetch_one(query, event_id)
            return result is not None
    
    async def _persist_event(self, 
                            event_id: str,
                            message_id: Optional[str],
                            pitch_id: Optional[int],
                            event_type: str,
                            event_data: Dict[str, Any],
                            event_time: Optional[float] = None):
        """Persist event to message_events table."""
        async with get_db_async() as db:
            # Extract additional fields from event data
            data = event_data.get('data', {})
            
            # Use the computed event_time, fall back to now if not available
            if event_time:
                timestamp = (
                    datetime.fromtimestamp(event_time, timezone.utc)
                    if isinstance(event_time, (int, float)) 
                    else datetime.now(timezone.utc)
                )
            else:
                timestamp = datetime.now(timezone.utc)
            
            # Extract IP and user agent for opens/clicks
            ip_address = None
            user_agent = None
            link_url = None
            
            if event_type == 'message.opened':
                # Nylas provides IP and user agent in recents array
                recents = data.get('recents', [])
                if recents:
                    latest = recents[-1]  # Get most recent
                    ip_address = latest.get('ip')
                    user_agent = latest.get('user_agent')
            elif event_type == 'message.link_clicked':
                # v3: link_data is a list with {url, count}
                link_items = data.get('link_data', [])
                link_url = link_items[0].get('url') if link_items else None
                recents = data.get('recents', [])
                if recents:
                    latest = recents[-1]  # Get most recent
                    ip_address = latest.get('ip')
                    user_agent = latest.get('user_agent')
            
            query = """
                INSERT INTO message_events (
                    event_id, message_id, pitch_id, event_type,
                    timestamp, payload_json, ip_address, user_agent,
                    link_url, is_duplicate, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            """
            
            await db.execute(
                query,
                event_id,
                message_id,
                pitch_id,
                event_type,
                timestamp,
                json.dumps(event_data),
                ip_address,
                user_agent,
                link_url,
                False  # is_duplicate
            )
    
    async def _update_pitch_metrics(self, pitch_id: int, event_type: str, event_data: Dict[str, Any]):
        """Update aggregate metrics on pitch record."""
        update_data = {}
        
        if event_type == 'message.opened':
            # Increment open count
            async with get_db_async() as db:
                await db.execute("""
                    UPDATE pitches 
                    SET open_count = COALESCE(open_count, 0) + 1,
                        pitch_state = CASE 
                            WHEN pitch_state NOT IN ('replied', 'clicked', 'bounced') 
                            THEN 'opened' 
                            ELSE pitch_state 
                        END
                    WHERE pitch_id = $1
                """, pitch_id)
                
        elif event_type == 'message.link_clicked':
            # Increment click count
            async with get_db_async() as db:
                await db.execute("""
                    UPDATE pitches 
                    SET click_count = COALESCE(click_count, 0) + 1,
                        pitch_state = CASE 
                            WHEN pitch_state NOT IN ('replied', 'bounced') 
                            THEN 'clicked' 
                            ELSE pitch_state 
                        END,
                        clicked_ts = COALESCE(clicked_ts, NOW())
                    WHERE pitch_id = $1
                """, pitch_id)
        
        elif event_type == 'message.bounce_detected':
            # Update bounce info
            data = event_data.get('data', {})
            bounce_type = data.get('bounce_type', 'unknown')
            bounce_reason = data.get('reason', 'Unknown reason')
            
            async with get_db_async() as db:
                await db.execute("""
                    UPDATE pitches 
                    SET pitch_state = 'bounced',
                        bounce_type = $2,
                        bounce_reason = $3,
                        bounced_ts = NOW()
                    WHERE pitch_id = $1
                """, pitch_id, bounce_type, bounce_reason)
    
    async def _handle_bounce_automation(self, event_data: Dict[str, Any], pitch_id: Optional[int]):
        """Handle automation for bounce events."""
        data = event_data.get('data', {})
        recipient_email = data.get('recipient_email')
        bounce_type = data.get('bounce_type', 'unknown')
        bounce_reason = data.get('reason', 'Unknown reason')
        
        if recipient_email:
            # Update contact status using helper function
            async with get_db_async() as db:
                await db.execute(
                    "SELECT update_contact_bounce_status($1, $2, $3)",
                    recipient_email.lower(),
                    bounce_type,
                    bounce_reason
                )
            
            logger.info(f"Updated contact status for {recipient_email} after {bounce_type} bounce")
            
            # If hard bounce, we should stop all future sends to this email
            if bounce_type == 'hard_bounce' and pitch_id:
                # Mark any pending pitches to this email as cancelled
                async with get_db_async() as db:
                    await db.execute("""
                        UPDATE pitches p
                        SET pitch_state = 'cancelled',
                            send_status = 'cancelled'
                        FROM media m
                        WHERE p.media_id = m.media_id
                        AND LOWER(m.contact_email) = LOWER($1)
                        AND p.pitch_state IN ('draft', 'pending')
                    """, recipient_email)
    
    async def _handle_open_automation(self, event_data: Dict[str, Any], pitch_id: Optional[int]):
        """Handle automation for open events."""
        # Log the open event
        if pitch_id:
            logger.info(f"Email opened for pitch {pitch_id}")
        
        # Could trigger follow-up scheduling here if no click within X hours
        # This would check automation_rules table for configured rules
    
    async def _handle_click_automation(self, event_data: Dict[str, Any], pitch_id: Optional[int]):
        """Handle automation for click events."""
        data = event_data.get('data', {})
        link_url = data.get('link_url')
        
        if pitch_id:
            logger.info(f"Link clicked for pitch {pitch_id}: {link_url}")
            
            # High-value action - could create priority task
            # Check if we should create a review task
            async with get_db_async() as db:
                # Get campaign_id from pitch
                result = await db.fetch_one("""
                    SELECT campaign_id, media_id 
                    FROM pitches 
                    WHERE pitch_id = $1
                """, pitch_id)
                
                if result:
                    # Could create a high-priority review task here
                    logger.info(f"High-value engagement detected for campaign {result['campaign_id']}")
    
    async def _handle_reply_automation(self, event_data: Dict[str, Any], pitch_id: Optional[int]):
        """Handle automation for reply events."""
        # Reply handling is already done by email monitor
        # This is for additional automation rules
        if pitch_id:
            logger.info(f"Reply received for pitch {pitch_id}")
            
            # Stop any scheduled follow-ups
            async with get_db_async() as db:
                await db.execute("""
                    UPDATE send_queue 
                    SET status = 'cancelled'
                    WHERE pitch_id = $1 
                    AND status = 'pending'
                """, pitch_id)
    
    async def _handle_send_failure_automation(self, event_data: Dict[str, Any], pitch_id: Optional[int]):
        """Handle automation for send failure events."""
        data = event_data.get('data', {})
        error_message = data.get('error', 'Unknown error')
        
        if pitch_id:
            # Update pitch status
            async with get_db_async() as db:
                await db.execute("""
                    UPDATE pitches 
                    SET send_status = 'failed',
                        pitch_state = 'failed'
                    WHERE pitch_id = $1
                """, pitch_id)
            
            logger.error(f"Send failed for pitch {pitch_id}: {error_message}")
            
            # Could implement retry logic here based on error type
    
    async def process_batch_events(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process multiple webhook events in batch.
        
        Args:
            events: List of webhook events
            
        Returns:
            Summary of processing results
        """
        results = {
            "total": len(events),
            "processed": 0,
            "duplicates": 0,
            "errors": 0,
            "details": []
        }
        
        for event in events:
            try:
                result = await self.process_webhook_event(event)
                
                if result["success"]:
                    results["processed"] += 1
                elif result["duplicate"]:
                    results["duplicates"] += 1
                else:
                    results["errors"] += 1
                
                results["details"].append(result)
                
            except Exception as e:
                logger.exception(f"Error processing event in batch: {e}")
                results["errors"] += 1
                results["details"].append({
                    "success": False,
                    "error": str(e)
                })
        
        return results
    
    def clear_memory_cache(self):
        """Clear in-memory event cache (for maintenance)."""
        cache_size = len(self.processed_events)
        self.processed_events.clear()
        logger.info(f"Cleared {cache_size} events from memory cache")
        return cache_size


# Singleton instance
event_processor = EventProcessor()