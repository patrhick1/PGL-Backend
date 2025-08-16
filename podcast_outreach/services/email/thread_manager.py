"""
Email Thread Manager Service
Handles fetching, storing, and tracking complete email conversation threads
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import json

from podcast_outreach.database.connection import get_db_async
from podcast_outreach.database.queries import pitches_nylas
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import placements as placement_queries
from podcast_outreach.integrations.nylas import NylasAPIClient
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)


class EmailThreadManager:
    """
    Manages email conversation threads between clients and podcast hosts.
    Fetches complete threads, stores messages, and tracks conversations.
    """
    
    def __init__(self, grant_id: Optional[str] = None):
        self.grant_id = grant_id
        self.nylas = NylasAPIClient(grant_id) if grant_id else None
    
    async def process_thread_reply(
        self,
        nylas_thread_id: str,
        new_message_id: str,
        pitch_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process a reply in an email thread.
        Fetches the complete thread, stores all messages, and creates placement if needed.
        
        Args:
            nylas_thread_id: The Nylas thread ID
            new_message_id: The ID of the new reply message
            pitch_id: Optional pitch ID if known
            
        Returns:
            Dictionary with processing results
        """
        result = {
            "success": False,
            "thread_id": None,
            "placement_id": None,
            "message": ""
        }
        
        try:
            # Get or create thread record
            thread_record = await self._get_or_create_thread(nylas_thread_id, pitch_id)
            result["thread_id"] = thread_record["thread_id"]
            
            # Fetch complete thread from Nylas
            if self.nylas:
                thread_messages = await self._fetch_thread_messages(nylas_thread_id)
                
                # Store all messages
                await self._store_thread_messages(thread_record["thread_id"], thread_messages)
                
                # Analyze thread for placement creation
                should_create_placement = await self._should_create_placement(
                    thread_record, 
                    thread_messages
                )
                
                if should_create_placement and not thread_record.get("placement_id"):
                    # Create placement record
                    placement = await self._create_placement_from_thread(
                        thread_record, 
                        thread_messages
                    )
                    if placement:
                        result["placement_id"] = placement["placement_id"]
                        
                        # Update thread with placement reference
                        await self._update_thread_placement(
                            thread_record["thread_id"], 
                            placement["placement_id"]
                        )
                
                # Update thread statistics
                await self._update_thread_stats(thread_record["thread_id"], thread_messages)
                
                result["success"] = True
                result["message"] = f"Processed thread with {len(thread_messages)} messages"
                
            else:
                # No Nylas client, just mark the reply
                await self._mark_thread_replied(thread_record["thread_id"])
                result["success"] = True
                result["message"] = "Thread marked as replied (no Nylas access)"
            
            logger.info(f"Successfully processed thread {nylas_thread_id}: {result['message']}")
            
        except Exception as e:
            logger.error(f"Error processing thread reply: {e}")
            result["message"] = str(e)
        
        return result
    
    async def _get_or_create_thread(
        self, 
        nylas_thread_id: str, 
        pitch_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get existing thread or create new one."""
        async with get_db_async() as db:
            # Check if thread exists
            query = """
                SELECT * FROM email_threads 
                WHERE nylas_thread_id = $1
            """
            thread = await db.fetch_one(query, nylas_thread_id)
            
            if thread:
                return dict(thread)
            
            # Create new thread
            pitch_data = {}
            if pitch_id:
                # Get pitch details
                pitch_query = """
                    SELECT p.*, c.campaign_id, m.media_id
                    FROM pitches p
                    JOIN campaigns c ON p.campaign_id = c.campaign_id
                    JOIN media m ON p.media_id = m.media_id
                    WHERE p.pitch_id = $1
                """
                pitch = await db.fetch_one(pitch_query, pitch_id)
                if pitch:
                    pitch_data = dict(pitch)
            
            insert_query = """
                INSERT INTO email_threads (
                    nylas_thread_id, pitch_id, campaign_id, media_id,
                    thread_status, created_at
                )
                VALUES ($1, $2, $3, $4, 'active', NOW())
                RETURNING *
            """
            
            new_thread = await db.fetch_one(
                insert_query,
                nylas_thread_id,
                pitch_data.get("pitch_id"),
                pitch_data.get("campaign_id"),
                pitch_data.get("media_id")
            )
            
            return dict(new_thread)
    
    async def _fetch_thread_messages(self, nylas_thread_id: str) -> List[Dict[str, Any]]:
        """Fetch all messages in a thread from Nylas."""
        if not self.nylas:
            return []
        
        try:
            # Get thread details
            thread = self.nylas.get_thread(nylas_thread_id)
            
            # Get all messages in thread
            messages = self.nylas.get_thread_messages(nylas_thread_id)
            
            # Sort by date
            messages.sort(key=lambda m: m.get("date", 0))
            
            return messages
            
        except Exception as e:
            logger.error(f"Error fetching thread messages: {e}")
            return []
    
    async def _store_thread_messages(
        self, 
        thread_id: int, 
        messages: List[Dict[str, Any]]
    ):
        """Store all messages from a thread."""
        async with get_db_async() as db:
            for message in messages:
                # Check if message already exists
                check_query = """
                    SELECT message_id FROM email_messages 
                    WHERE nylas_message_id = $1
                """
                existing = await db.fetch_one(check_query, message.get("id"))
                
                if not existing:
                    # Determine direction based on sender
                    from_email = (message.get("from") or [{}])[0].get("email", "").lower()
                    
                    # Check if sender is our client
                    client_check = """
                        SELECT 1 FROM people p
                        JOIN campaigns c ON p.person_id = c.person_id
                        JOIN email_threads et ON et.campaign_id = c.campaign_id
                        WHERE et.thread_id = $1 
                        AND LOWER(p.email) = $2
                    """
                    is_client = await db.fetch_one(client_check, thread_id, from_email)
                    direction = "outbound" if is_client else "inbound"
                    
                    # Extract recipients
                    to_emails = [r.get("email") for r in message.get("to", [])]
                    cc_emails = [r.get("email") for r in message.get("cc", [])]
                    bcc_emails = [r.get("email") for r in message.get("bcc", [])]
                    
                    # Insert message
                    insert_query = """
                        INSERT INTO email_messages (
                            nylas_message_id, thread_id, sender_email, sender_name,
                            recipient_emails, cc_emails, bcc_emails,
                            subject, body_text, body_html, snippet,
                            message_date, direction, is_reply, raw_message
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    """
                    
                    await db.execute(
                        insert_query,
                        message.get("id"),
                        thread_id,
                        from_email,
                        (message.get("from") or [{}])[0].get("name"),
                        to_emails,
                        cc_emails,
                        bcc_emails,
                        message.get("subject"),
                        message.get("body_text") or message.get("snippet"),
                        message.get("body_html"),
                        message.get("snippet"),
                        datetime.fromtimestamp(message.get("date", 0), timezone.utc),
                        direction,
                        "Re:" in (message.get("subject") or ""),
                        json.dumps(message)
                    )
                    
                    # Update participants
                    await self._update_thread_participants(thread_id, message)
    
    async def _update_thread_participants(self, thread_id: int, message: Dict[str, Any]):
        """Update thread participants based on message."""
        async with get_db_async() as db:
            # Add sender
            sender = (message.get("from") or [{}])[0]
            if sender.get("email"):
                await self._upsert_participant(
                    db, thread_id, 
                    sender.get("email"), 
                    sender.get("name"),
                    message.get("date")
                )
            
            # Add recipients
            for recipient in message.get("to", []):
                if recipient.get("email"):
                    await self._upsert_participant(
                        db, thread_id,
                        recipient.get("email"),
                        recipient.get("name"),
                        message.get("date")
                    )
    
    async def _upsert_participant(
        self, 
        db, 
        thread_id: int, 
        email: str, 
        name: Optional[str],
        message_date: Optional[int]
    ):
        """Insert or update thread participant."""
        message_timestamp = datetime.fromtimestamp(
            message_date, timezone.utc
        ) if message_date else datetime.now(timezone.utc)
        
        query = """
            INSERT INTO thread_participants (
                thread_id, email, name, first_message_at, 
                last_message_at, message_count
            )
            VALUES ($1, $2, $3, $4, $4, 1)
            ON CONFLICT (thread_id, email) DO UPDATE
            SET last_message_at = EXCLUDED.last_message_at,
                message_count = thread_participants.message_count + 1,
                name = COALESCE(thread_participants.name, EXCLUDED.name)
        """
        
        await db.execute(query, thread_id, email.lower(), name, message_timestamp)
    
    async def _should_create_placement(
        self, 
        thread_record: Dict[str, Any],
        messages: List[Dict[str, Any]]
    ) -> bool:
        """
        Determine if a placement should be created based on thread content.
        A placement is created when the podcast host shows interest or confirms booking.
        """
        if not messages:
            return False
        
        # Check if there's already a placement
        if thread_record.get("placement_id"):
            return False
        
        # Look for replies from non-client addresses
        async with get_db_async() as db:
            # Get client email
            client_query = """
                SELECT p.email FROM people p
                JOIN campaigns c ON p.person_id = c.person_id
                WHERE c.campaign_id = $1
            """
            client_result = await db.fetch_one(client_query, thread_record.get("campaign_id"))
            client_email = client_result["email"].lower() if client_result else None
            
            # Check for host replies
            for message in messages:
                from_email = (message.get("from") or [{}])[0].get("email", "").lower()
                
                # If message is from someone other than the client, it's likely the host
                if from_email and from_email != client_email:
                    # This is a reply from the podcast host
                    return True
        
        return False
    
    async def _create_placement_from_thread(
        self,
        thread_record: Dict[str, Any],
        messages: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Create a placement record from thread data."""
        try:
            # Build email thread summary
            thread_summary = []
            for msg in messages:
                thread_summary.append({
                    "date": datetime.fromtimestamp(
                        msg.get("date", 0), timezone.utc
                    ).isoformat(),
                    "from": (msg.get("from") or [{}])[0].get("email"),
                    "subject": msg.get("subject"),
                    "snippet": msg.get("snippet")
                })
            
            placement_data = {
                "campaign_id": thread_record["campaign_id"],
                "media_id": thread_record["media_id"],
                "pitch_id": thread_record["pitch_id"],
                "current_status": "in_discussion",
                "status_ts": datetime.now(timezone.utc),
                "notes": "Auto-created from email reply",
                "email_thread": thread_summary,
                "email_thread_id": thread_record["thread_id"]
            }
            
            placement = await placement_queries.create_placement_in_db(placement_data)
            
            if placement:
                # Update pitch with placement reference
                await pitches_nylas.update_pitch_in_db(
                    thread_record["pitch_id"],
                    {"placement_id": placement["placement_id"]}
                )
                
                logger.info(f"Created placement {placement['placement_id']} from thread {thread_record['nylas_thread_id']}")
            
            return placement
            
        except Exception as e:
            logger.error(f"Error creating placement from thread: {e}")
            return None
    
    async def _update_thread_placement(self, thread_id: int, placement_id: int):
        """Update thread with placement reference."""
        async with get_db_async() as db:
            query = """
                UPDATE email_threads 
                SET placement_id = $2, updated_at = NOW()
                WHERE thread_id = $1
            """
            await db.execute(query, thread_id, placement_id)
    
    async def _update_thread_stats(self, thread_id: int, messages: List[Dict[str, Any]]):
        """Update thread statistics based on messages."""
        if not messages:
            return
        
        async with get_db_async() as db:
            # Get participant emails
            participants = set()
            for msg in messages:
                from_email = (msg.get("from") or [{}])[0].get("email")
                if from_email:
                    participants.add(from_email.lower())
                for recipient in msg.get("to", []):
                    if recipient.get("email"):
                        participants.add(recipient["email"].lower())
            
            # Update thread
            update_query = """
                UPDATE email_threads
                SET message_count = $2,
                    participant_emails = $3,
                    last_message_at = $4,
                    subject = COALESCE(subject, $5),
                    updated_at = NOW()
                WHERE thread_id = $1
            """
            
            last_message = messages[-1] if messages else {}
            
            await db.execute(
                update_query,
                thread_id,
                len(messages),
                list(participants),
                datetime.fromtimestamp(last_message.get("date", 0), timezone.utc),
                last_message.get("subject")
            )
    
    async def _mark_thread_replied(self, thread_id: int):
        """Mark thread as having received a reply."""
        async with get_db_async() as db:
            query = """
                UPDATE email_threads
                SET first_reply_at = COALESCE(first_reply_at, NOW()),
                    last_reply_at = NOW(),
                    updated_at = NOW()
                WHERE thread_id = $1
            """
            await db.execute(query, thread_id)
    
    async def get_thread_conversation(self, thread_id: int) -> Dict[str, Any]:
        """
        Get complete conversation for a thread.
        
        Returns:
            Dictionary with thread details and all messages
        """
        async with get_db_async() as db:
            # Get thread details
            thread_query = """
                SELECT et.*, p.subject_line, p.body_snippet,
                       pl.placement_id, pl.current_status as placement_status
                FROM email_threads et
                LEFT JOIN pitches p ON et.pitch_id = p.pitch_id
                LEFT JOIN placements pl ON et.placement_id = pl.placement_id
                WHERE et.thread_id = $1
            """
            thread = await db.fetch_one(thread_query, thread_id)
            
            if not thread:
                return None
            
            # Get all messages
            messages_query = """
                SELECT * FROM email_messages
                WHERE thread_id = $1
                ORDER BY message_date ASC
            """
            messages = await db.fetch_all(messages_query, thread_id)
            
            # Get participants
            participants_query = """
                SELECT * FROM thread_participants
                WHERE thread_id = $1
                ORDER BY message_count DESC
            """
            participants = await db.fetch_all(participants_query, thread_id)
            
            return {
                "thread": dict(thread),
                "messages": [dict(m) for m in messages],
                "participants": [dict(p) for p in participants]
            }


# Singleton instance
thread_manager = EmailThreadManager()