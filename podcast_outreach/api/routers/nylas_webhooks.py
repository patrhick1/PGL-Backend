# podcast_outreach/api/routers/nylas_webhooks.py

from fastapi import APIRouter, Request, HTTPException, status, Header
from fastapi.responses import JSONResponse
import logging
import hmac
import hashlib
from datetime import datetime, timezone
from typing import Optional
import json

from podcast_outreach.services.pitches.sender import PitchSenderService
from podcast_outreach.services.email.monitor import NylasEmailMonitor
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import placements as placement_queries
from podcast_outreach.integrations.attio import update_attio_when_email_sent, update_correspondent_on_attio
import os

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/nylas", tags=["Nylas Webhooks"])

# Get webhook secret from environment
NYLAS_WEBHOOK_SECRET = os.getenv("NYLAS_WEBHOOK_SECRET")


def verify_nylas_signature(request_body: bytes, signature: str) -> bool:
    """
    Verify Nylas webhook signature for security.
    
    Args:
        request_body: Raw request body bytes
        signature: X-Nylas-Signature header value
        
    Returns:
        bool: True if signature is valid
    """
    if not NYLAS_WEBHOOK_SECRET:
        logger.warning("NYLAS_WEBHOOK_SECRET not configured, skipping signature verification")
        return True
    
    expected_signature = hmac.new(
        NYLAS_WEBHOOK_SECRET.encode('utf-8'),
        request_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)


@router.post("/challenge", status_code=status.HTTP_200_OK, summary="Nylas Webhook Challenge")
async def nylas_webhook_challenge(request: Request):
    """
    Handle Nylas webhook challenge for verification.
    This endpoint is called when setting up a new webhook.
    """
    try:
        data = await request.json()
        challenge = data.get("challenge")
        
        if challenge:
            logger.info(f"Responding to Nylas webhook challenge: {challenge}")
            return JSONResponse(content={"challenge": challenge})
        else:
            logger.error("No challenge found in Nylas webhook verification request")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No challenge found in request"
            )
    except Exception as e:
        logger.exception(f"Error handling Nylas webhook challenge: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/events", status_code=status.HTTP_200_OK, summary="Nylas Webhook Events")
async def nylas_webhook_events(
    request: Request,
    x_nylas_signature: Optional[str] = Header(None)
):
    """
    Handle Nylas webhook events for email tracking.
    
    Supported events:
    - message.sent: Email was sent
    - message.opened: Email was opened
    - message.link_clicked: Link in email was clicked
    - message.replied: Email received a reply
    - message.bounced: Email bounced
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        
        # Verify signature if configured
        if NYLAS_WEBHOOK_SECRET and x_nylas_signature:
            if not verify_nylas_signature(body, x_nylas_signature):
                logger.warning("Invalid Nylas webhook signature")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature"
                )
        
        # Parse JSON
        data = json.loads(body)
        
        # Process each event in the webhook payload
        events = data.get("data", [])
        
        for event in events:
            event_type = event.get("type")
            event_data = event.get("data", {})
            
            logger.info(f"Processing Nylas webhook event: {event_type}")
            
            if event_type == "message.sent":
                await handle_message_sent(event_data)
            elif event_type == "message.opened":
                await handle_message_opened(event_data)
            elif event_type == "message.link_clicked":
                await handle_link_clicked(event_data)
            elif event_type == "message.replied":
                await handle_message_replied(event_data)
            elif event_type == "message.bounced":
                await handle_message_bounced(event_data)
            else:
                logger.warning(f"Unhandled Nylas event type: {event_type}")
        
        return JSONResponse(content={"status": "success", "events_processed": len(events)})
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in Nylas webhook")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
    except Exception as e:
        logger.exception(f"Error processing Nylas webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process webhook: {str(e)}"
        )


async def handle_message_sent(event_data: dict):
    """Handle message.sent event."""
    message_id = event_data.get("message_id")
    thread_id = event_data.get("thread_id")
    
    if not message_id:
        logger.warning("No message_id in message.sent event")
        return
    
    # Find pitch by Nylas message ID
    pitch_record = await pitch_queries.get_pitch_by_nylas_message_id(message_id)
    
    if pitch_record:
        # Update pitch state to sent
        update_data = {
            "pitch_state": "sent",
            "send_ts": datetime.now(timezone.utc),
            "nylas_thread_id": thread_id
        }
        await pitch_queries.update_pitch_in_db(pitch_record['pitch_id'], update_data)
        logger.info(f"Updated pitch {pitch_record['pitch_id']} to 'sent' state")
        
        # Update Attio if configured
        try:
            # Convert to format expected by Attio integration
            attio_data = {
                "pitch_gen_id": pitch_record.get("pitch_gen_id"),
                "campaign_id": str(pitch_record.get("campaign_id")),
                "media_id": str(pitch_record.get("media_id")),
                "email": event_data.get("recipient_email", ""),
                "Subject": pitch_record.get("subject_line", "")
            }
            await update_attio_when_email_sent(attio_data)
        except Exception as e:
            logger.warning(f"Failed to update Attio: {e}")
    else:
        logger.warning(f"No pitch found for Nylas message ID: {message_id}")


async def handle_message_opened(event_data: dict):
    """Handle message.opened event."""
    message_id = event_data.get("message_id")
    opened_at = event_data.get("timestamp")
    
    if not message_id:
        return
    
    pitch_record = await pitch_queries.get_pitch_by_nylas_message_id(message_id)
    
    if pitch_record and pitch_record.get("pitch_state") != "replied":
        # Only update to opened if not already replied
        update_data = {"pitch_state": "opened"}
        if opened_at:
            update_data["opened_ts"] = datetime.fromtimestamp(opened_at)
        
        await pitch_queries.update_pitch_in_db(pitch_record['pitch_id'], update_data)
        logger.info(f"Updated pitch {pitch_record['pitch_id']} to 'opened' state")


async def handle_link_clicked(event_data: dict):
    """Handle message.link_clicked event."""
    message_id = event_data.get("message_id")
    link_url = event_data.get("link_url")
    clicked_at = event_data.get("timestamp")
    
    if not message_id:
        return
    
    pitch_record = await pitch_queries.get_pitch_by_nylas_message_id(message_id)
    
    if pitch_record:
        # Update pitch state to clicked if not already in a more advanced state
        if pitch_record.get("pitch_state") not in ["replied", "clicked"]:
            update_data = {
                "pitch_state": "clicked",
                "clicked_ts": datetime.fromtimestamp(clicked_at) if clicked_at else datetime.now(timezone.utc)
            }
            await pitch_queries.update_pitch_in_db(pitch_record['pitch_id'], update_data)
            logger.info(f"Updated pitch {pitch_record['pitch_id']} to 'clicked' state (link: {link_url})")


async def handle_message_replied(event_data: dict):
    """Handle message.replied event."""
    # This is handled by the email monitor service, but we can process it here too
    original_message_id = event_data.get("original_message_id")
    reply_message_id = event_data.get("reply_message_id")
    thread_id = event_data.get("thread_id")
    
    if not original_message_id:
        return
    
    # Use the email monitor to process the reply
    monitor = NylasEmailMonitor()
    
    # Get the reply message details
    reply_message = monitor.nylas_client.get_message(reply_message_id)
    
    if reply_message:
        result = await monitor.process_reply(reply_message)
        
        if result.get("success"):
            logger.info(f"Processed reply via webhook: {result}")
            
            # Update Attio
            try:
                # Get pitch details for Attio update
                pitch_record = await pitch_queries.get_pitch_by_nylas_message_id(original_message_id)
                if pitch_record:
                    attio_data = {
                        "pitch_gen_id": pitch_record.get("pitch_gen_id"),
                        "campaign_id": str(pitch_record.get("campaign_id")),
                        "media_id": str(pitch_record.get("media_id")),
                        "email": reply_message.get("from", [{}])[0].get("email", ""),
                        "reply_text_snippet": reply_message.get("snippet", "")
                    }
                    await update_correspondent_on_attio(attio_data)
            except Exception as e:
                logger.warning(f"Failed to update Attio for reply: {e}")
        else:
            logger.warning(f"Failed to process reply: {result}")


async def handle_message_bounced(event_data: dict):
    """Handle message.bounced event."""
    message_id = event_data.get("message_id")
    bounce_type = event_data.get("bounce_type")  # hard_bounce or soft_bounce
    bounce_reason = event_data.get("reason")
    
    if not message_id:
        return
    
    pitch_record = await pitch_queries.get_pitch_by_nylas_message_id(message_id)
    
    if pitch_record:
        # Update pitch state to bounced
        update_data = {
            "pitch_state": "bounced",
            "bounce_type": bounce_type,
            "bounce_reason": bounce_reason,
            "bounced_ts": datetime.now(timezone.utc)
        }
        await pitch_queries.update_pitch_in_db(pitch_record['pitch_id'], update_data)
        logger.warning(f"Pitch {pitch_record['pitch_id']} bounced: {bounce_type} - {bounce_reason}")
        
        # You might want to update the media record to mark the email as invalid
        # This prevents future pitches to this email


@router.get("/health", status_code=status.HTTP_200_OK, summary="Webhook Health Check")
async def webhook_health():
    """Health check endpoint for Nylas webhooks."""
    return {
        "status": "healthy",
        "webhook_type": "nylas",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }