# podcast_outreach/services/email/monitor.py

import asyncio
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone, timedelta
import json

from podcast_outreach.integrations.nylas import NylasAPIClient
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import placements as placement_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries.placement_thread_updates import update_thread_for_subsequent_reply
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)


class NylasEmailMonitor:
    """
    Monitors email accounts via Nylas for replies to pitches and updates the system accordingly.
    Can run continuously or be triggered on-demand.
    """
    
    def __init__(self, grant_id: Optional[str] = None, check_interval: int = 60):
        """
        Initialize the email monitor.
        
        Args:
            grant_id: Nylas grant ID for the email account
            check_interval: Seconds between checks when running continuously
        """
        self.nylas_client = NylasAPIClient(grant_id=grant_id)
        self.check_interval = check_interval
        self.processed_message_ids: Set[str] = set()
        self._running = False
        logger.info(f"NylasEmailMonitor initialized with check interval: {check_interval}s")
    
    async def process_reply(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a reply message and update the appropriate pitch/placement records.
        
        Args:
            message: Nylas message dictionary
            
        Returns:
            Dict with processing results
        """
        result = {
            "success": False,
            "message_id": message.get("id"),
            "action": None,
            "details": {}
        }
        
        try:
            # Extract sender information
            from_participants = message.get("from", [])
            if not from_participants:
                result["details"]["error"] = "No sender information"
                return result
            
            sender_email = from_participants[0].get("email", "").lower()
            sender_name = from_participants[0].get("name", "")
            
            # Try to find the pitch this is replying to
            # First, check if this is part of an existing thread
            thread_id = message.get("thread_id")
            
            pitch_record = None
            placement_record = None
            
            if thread_id:
                # Search for pitches with this thread ID
                pitch_record = await pitch_queries.get_pitch_by_nylas_thread_id(thread_id)
            
            # If not found by thread, try to match by email
            if not pitch_record:
                # Get recent pitches sent to this email
                recent_pitches = await pitch_queries.get_recent_pitches_by_recipient_email(
                    sender_email, 
                    days_back=30
                )
                if recent_pitches:
                    pitch_record = recent_pitches[0]  # Use most recent
            
            if not pitch_record:
                result["details"]["error"] = f"No pitch found for reply from {sender_email}"
                logger.warning(result["details"]["error"])
                return result
            
            # Check if this is the first reply or subsequent
            is_first_reply = pitch_record.get("pitch_state") != "replied"
            
            if is_first_reply:
                # First reply - update pitch state and create placement
                logger.info(f"Processing first reply for pitch {pitch_record['pitch_id']}")
                
                # Update pitch state
                update_data = {
                    "pitch_state": "replied",
                    "reply_bool": True,
                    "reply_ts": datetime.now(timezone.utc),
                    "nylas_thread_id": thread_id
                }
                await pitch_queries.update_pitch_in_db(pitch_record['pitch_id'], update_data)
                
                # Create placement record
                campaign_id = pitch_record.get("campaign_id")
                media_id = pitch_record.get("media_id")
                
                if campaign_id and media_id:
                    # Build email thread
                    email_thread = await self._build_email_thread(pitch_record, message)
                    
                    placement_data = {
                        "campaign_id": campaign_id,
                        "media_id": media_id,
                        "pitch_id": pitch_record['pitch_id'],
                        "current_status": "initial_reply",
                        "status_ts": datetime.now(timezone.utc),
                        "notes": f"Initial reply received from {sender_email}",
                        "email_thread": email_thread
                    }
                    
                    placement = await placement_queries.create_placement(placement_data)
                    
                    # Update pitch with placement_id
                    await pitch_queries.update_pitch_in_db(
                        pitch_record['pitch_id'],
                        {"placement_id": placement['placement_id']}
                    )
                    
                    result["success"] = True
                    result["action"] = "created_placement"
                    result["details"] = {
                        "pitch_id": pitch_record['pitch_id'],
                        "placement_id": placement['placement_id'],
                        "status": "initial_reply"
                    }
                else:
                    result["details"]["error"] = "Missing campaign_id or media_id"
            else:
                # Subsequent reply - update existing placement
                logger.info(f"Processing subsequent reply for pitch {pitch_record['pitch_id']}")
                
                if pitch_record.get('placement_id'):
                    # Convert message to format expected by placement update
                    instantly_format_data = self._convert_to_instantly_format(message, pitch_record)
                    
                    updated_placement = await update_thread_for_subsequent_reply(
                        instantly_format_data,
                        pitch_record['placement_id']
                    )
                    
                    if updated_placement:
                        # Analyze reply content for status updates
                        reply_text = message.get("snippet", "").lower()
                        new_status = self._analyze_reply_for_status(reply_text)
                        
                        if new_status and new_status != updated_placement.get("current_status"):
                            await placement_queries.update_placement_in_db(
                                pitch_record['placement_id'],
                                {
                                    "current_status": new_status,
                                    "status_ts": datetime.now(timezone.utc)
                                }
                            )
                        
                        result["success"] = True
                        result["action"] = "updated_thread"
                        result["details"] = {
                            "pitch_id": pitch_record['pitch_id'],
                            "placement_id": pitch_record['placement_id'],
                            "new_status": new_status
                        }
                    else:
                        result["details"]["error"] = "Failed to update placement thread"
                else:
                    result["details"]["error"] = "Pitch marked as replied but has no placement_id"
            
            # Mark message as processed
            self.processed_message_ids.add(message.get("id"))
            
        except Exception as e:
            logger.exception(f"Error processing reply: {e}")
            result["details"]["error"] = str(e)
        
        return result
    
    async def check_for_replies(self, 
                              since_timestamp: Optional[datetime] = None,
                              limit: int = 50) -> List[Dict[str, Any]]:
        """
        Check for new email replies.
        
        Args:
            since_timestamp: Only check emails after this timestamp
            limit: Maximum number of messages to process
            
        Returns:
            List of processing results
        """
        if not since_timestamp:
            since_timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
        
        logger.info(f"Checking for replies since {since_timestamp}")
        
        # Search for messages in inbox
        messages = self.nylas_client.search_messages(
            after_date=since_timestamp,
            limit=limit
        )
        
        results = []
        new_replies = 0
        
        for message in messages:
            # Skip if already processed
            if message.get("id") in self.processed_message_ids:
                continue
            
            # Skip if this is an outbound message (sent by us)
            if self._is_outbound_message(message):
                continue
            
            # Process the reply
            result = await self.process_reply(message)
            results.append(result)
            
            if result.get("success"):
                new_replies += 1
        
        logger.info(f"Processed {new_replies} new replies out of {len(messages)} messages")
        return results
    
    async def run_continuous(self):
        """Run the monitor continuously."""
        logger.info("Starting continuous email monitoring")
        self._running = True
        
        last_check = datetime.now(timezone.utc) - timedelta(minutes=5)
        
        while self._running:
            try:
                # Check for new replies
                results = await self.check_for_replies(since_timestamp=last_check)
                
                # Update last check time
                last_check = datetime.now(timezone.utc)
                
                # Log summary
                successful = sum(1 for r in results if r.get("success"))
                if successful > 0:
                    logger.info(f"Successfully processed {successful} replies")
                
                # Wait before next check
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in continuous monitoring: {e}")
                await asyncio.sleep(self.check_interval)
    
    def stop(self):
        """Stop continuous monitoring."""
        logger.info("Stopping email monitor")
        self._running = False
    
    def _is_outbound_message(self, message: Dict[str, Any]) -> bool:
        """Check if a message was sent by us (outbound)."""
        # You can customize this based on your email setup
        our_email_domains = ["digitalpodcastguest.com"]  # Add your domains
        
        from_participants = message.get("from", [])
        if from_participants:
            sender_email = from_participants[0].get("email", "").lower()
            for domain in our_email_domains:
                if domain in sender_email:
                    return True
        return False
    
    def _analyze_reply_for_status(self, reply_text: str) -> Optional[str]:
        """Analyze reply text to determine if status should be updated."""
        reply_lower = reply_text.lower()
        
        # Define keywords for different statuses
        status_keywords = {
            "confirmed_interest": ["yes", "interested", "let's schedule", "sounds good", "i'm in"],
            "scheduling": ["calendar", "availability", "schedule", "book", "time slot"],
            "declined": ["not interested", "no thank you", "decline", "pass"],
            "needs_info": ["more information", "questions", "tell me more", "details"]
        }
        
        for status, keywords in status_keywords.items():
            if any(keyword in reply_lower for keyword in keywords):
                return status
        
        return None
    
    async def _build_email_thread(self, 
                                pitch_record: Dict[str, Any], 
                                reply_message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build email thread array for placement record."""
        email_thread = []
        
        # Add the original pitch
        if pitch_record.get('send_ts'):
            campaign = await campaign_queries.get_campaign_by_id(pitch_record['campaign_id'])
            
            email_thread.append({
                "timestamp": pitch_record['send_ts'].isoformat() if hasattr(pitch_record['send_ts'], 'isoformat') else str(pitch_record['send_ts']),
                "direction": "sent",
                "from": "aidrian@digitalpodcastguest.com",  # Update with your sender
                "to": reply_message.get("from", [{}])[0].get("email", ""),
                "subject": pitch_record.get('subject_line', ''),
                "body_text": pitch_record.get('body_snippet', ''),
                "nylas_data": {
                    "message_id": pitch_record.get('nylas_message_id'),
                    "thread_id": pitch_record.get('nylas_thread_id')
                }
            })
        
        # Add the reply
        email_thread.append({
            "timestamp": datetime.fromtimestamp(reply_message.get("date", 0)).isoformat(),
            "direction": "received",
            "from": reply_message.get("from", [{}])[0].get("email", ""),
            "to": reply_message.get("to", [{}])[0].get("email", ""),
            "subject": reply_message.get("subject", ""),
            "body_text": reply_message.get("snippet", ""),
            "body_html": reply_message.get("body", ""),
            "message_id": reply_message.get("id"),
            "nylas_data": {
                "message_id": reply_message.get("id"),
                "thread_id": reply_message.get("thread_id")
            }
        })
        
        return email_thread
    
    def _convert_to_instantly_format(self, 
                                   message: Dict[str, Any], 
                                   pitch_record: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Nylas message to format expected by existing placement update function."""
        return {
            "timestamp": datetime.fromtimestamp(message.get("date", 0)).isoformat(),
            "email": message.get("from", [{}])[0].get("email", ""),
            "email_account": message.get("to", [{}])[0].get("email", ""),
            "reply_subject": message.get("subject", ""),
            "reply_text": message.get("snippet", ""),
            "reply_html": message.get("body", ""),
            "email_id": message.get("id"),
            "pitch_gen_id": pitch_record.get("pitch_gen_id"),
            "campaign_id": str(pitch_record.get("campaign_id")),
            "media_id": str(pitch_record.get("media_id"))
        }