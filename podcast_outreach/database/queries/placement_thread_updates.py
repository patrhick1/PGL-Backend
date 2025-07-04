# podcast_outreach/database/queries/placement_thread_updates.py
"""
Functions for updating email threads in placements
"""
import logging
from typing import Any, Dict, Optional
import json
from datetime import datetime, timezone

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool

logger = get_logger(__name__)

async def append_to_email_thread(placement_id: int, new_message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Append a new message to an existing placement's email thread.
    
    Args:
        placement_id: The placement to update
        new_message: Dict with keys: timestamp, direction, from, to, subject, body_text, body_html, instantly_data
    
    Returns:
        Updated placement record or None
    """
    query = """
    UPDATE placements 
    SET email_thread = email_thread || $1::jsonb
    WHERE placement_id = $2
    RETURNING *;
    """
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Ensure the message has required fields
            if 'timestamp' not in new_message:
                new_message['timestamp'] = datetime.now(timezone.utc).isoformat()
                
            row = await conn.fetchrow(
                query,
                json.dumps([new_message]),  # Wrap in array for concatenation
                placement_id
            )
            
            if row:
                logger.info(f"Appended message to placement {placement_id} email thread")
                return dict(row)
            else:
                logger.warning(f"Placement {placement_id} not found")
                return None
                
        except Exception as e:
            logger.exception(f"Error appending to email thread for placement {placement_id}: {e}")
            raise

async def get_email_thread(placement_id: int) -> Optional[list]:
    """
    Get the email thread for a specific placement.
    
    Args:
        placement_id: The placement ID
        
    Returns:
        List of email messages or None
    """
    query = "SELECT email_thread FROM placements WHERE placement_id = $1;"
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, placement_id)
            if row and row['email_thread']:
                return row['email_thread']
            return []
            
        except Exception as e:
            logger.exception(f"Error fetching email thread for placement {placement_id}: {e}")
            return []

async def update_thread_for_subsequent_reply(webhook_data: Dict[str, Any], placement_id: int) -> Optional[Dict[str, Any]]:
    """
    Helper function to handle subsequent replies in a thread.
    
    Args:
        webhook_data: The Instantly webhook data
        placement_id: The placement to update
        
    Returns:
        Updated placement or None
    """
    new_message = {
        "timestamp": webhook_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
        "direction": "received",
        "from": webhook_data.get('email', ''),
        "to": webhook_data.get('email_account', 'aidrian@digitalpodcastguest.com'),
        "subject": webhook_data.get('reply_subject', ''),
        "body_text": webhook_data.get('reply_text', webhook_data.get('reply_text_snippet', '')),
        "body_html": webhook_data.get('reply_html', ''),
        "message_id": webhook_data.get('email_id'),
        "instantly_data": {
            "unibox_url": webhook_data.get('unibox_url'),
            "is_first": webhook_data.get('is_first', False),
            "reply_text_snippet": webhook_data.get('reply_text_snippet'),
            "event_type": webhook_data.get('event_type')
        }
    }
    
    return await append_to_email_thread(placement_id, new_message)

async def update_thread_for_sent_email(webhook_data: Dict[str, Any], placement_id: int) -> Optional[Dict[str, Any]]:
    """
    Helper function to handle adding sent emails to the thread (e.g., when we reply back).
    
    Args:
        webhook_data: The Instantly webhook data for sent email
        placement_id: The placement to update
        
    Returns:
        Updated placement or None
    """
    new_message = {
        "timestamp": webhook_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
        "direction": "sent",
        "from": webhook_data.get('email_account', 'aidrian@digitalpodcastguest.com'),
        "to": webhook_data.get('email', ''),
        "subject": webhook_data.get('email_subject', webhook_data.get('Subject', '')),
        "body_text": webhook_data.get('personalization', ''),
        "body_html": webhook_data.get('email_html', ''),
        "instantly_data": {
            "campaign_id": webhook_data.get('campaign_id'),
            "instantly_campaign_id": webhook_data.get('campaign'),
            "pitch_gen_id": webhook_data.get('pitch_gen_id'),
            "event_type": webhook_data.get('event_type'),
            "step": webhook_data.get('step'),
            "variant": webhook_data.get('variant')
        }
    }
    
    return await append_to_email_thread(placement_id, new_message)