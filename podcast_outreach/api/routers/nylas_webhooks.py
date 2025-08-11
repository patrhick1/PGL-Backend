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
from podcast_outreach.services.events.processor import event_processor
from podcast_outreach.services.inbox.booking_assistant import BookingAssistantService, map_classification
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import placements as placement_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.connection import get_db_async
from podcast_outreach.integrations.attio import update_attio_when_email_sent, update_correspondent_on_attio
import os
from typing import Dict, Any

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
        
        # Process events using the event processor for deduplication and persistence
        processed_count = 0
        duplicate_count = 0
        
        for event in events:
            event_type = event.get("type")
            
            logger.info(f"Processing Nylas webhook event: {event_type}")
            
            # Use event processor for deduplication and persistence
            result = await event_processor.process_webhook_event(event)
            
            if result.get("duplicate"):
                duplicate_count += 1
                continue
            
            if result.get("success"):
                processed_count += 1
                
                # Also run legacy handlers for specific event types
                # These will be phased out once event processor handles everything
                event_data = event.get("data", {})
                
                if event_type == "message.sent":
                    await handle_message_sent(event_data)
                elif event_type == "message.replied":
                    await handle_message_replied(event_data)
                # Opens, clicks, and bounces are now fully handled by event processor
        
        return JSONResponse(content={
            "status": "success", 
            "events_received": len(events),
            "events_processed": processed_count,
            "duplicates_skipped": duplicate_count
        })
        
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
    """Handle message.replied event with BookingAssistant integration."""
    
    original_message_id = event_data.get("original_message_id")
    reply_message_id = event_data.get("reply_message_id")
    thread_id = event_data.get("thread_id")
    
    if not original_message_id:
        return
    
    # Get the reply message details
    monitor = NylasEmailMonitor()
    reply_message = monitor.nylas_client.get_message(reply_message_id)
    
    if not reply_message:
        logger.warning(f"Could not fetch reply message: {reply_message_id}")
        return
    
    # Get pitch record first
    pitch_record = await pitch_queries.get_pitch_by_nylas_message_id(original_message_id)
    
    if not pitch_record:
        logger.warning(f"No pitch found for message ID: {original_message_id}")
        return
    
    # Process through BookingAssistant
    booking_assistant = BookingAssistantService()
    classification_result = await booking_assistant.process_email({
        "email_text": reply_message.get("snippet", ""),
        "subject": reply_message.get("subject", ""),
        "sender_email": reply_message.get("from", [{}])[0].get("email", ""),
        "sender_name": reply_message.get("from", [{}])[0].get("name", ""),
        "thread_id": thread_id,
        "message_id": reply_message_id
    })
    
    # Store classification in database
    await store_email_classification(
        message_id=reply_message_id,
        thread_id=thread_id,
        classification_result=classification_result
    )
    
    # Map classification to action
    classification = classification_result.get("classification")
    mapped_action = map_classification(classification)
    
    # Execute automated actions based on classification
    if mapped_action == "podcast_booking":
        await handle_booking_confirmation(pitch_record, reply_message, classification_result)
    elif mapped_action == "rejection":
        await handle_rejection(pitch_record, reply_message, classification_result)
    elif mapped_action == "question":
        await handle_question(pitch_record, reply_message, classification_result)
    elif mapped_action == "guest_followup":
        await handle_followup(pitch_record, reply_message, classification_result)
    elif mapped_action == "scheduling":
        # Treat scheduling requests as questions that need human response
        await handle_question(pitch_record, reply_message, classification_result)
    elif mapped_action in ["unknown", "other", "general"]:
        # For unknown/unclear emails, create a review task
        logger.info(f"Unknown/unclear classification for pitch {pitch_record['pitch_id']}: {classification}")
        await create_review_task({
            "task_type": "review_unclear_reply",
            "related_id": pitch_record['pitch_id'],
            "campaign_id": pitch_record['campaign_id'],
            "priority": "normal",
            "notes": f"Unclear reply from {reply_message.get('from', [{}])[0].get('email', '')}. Classification: {classification}"
        })
    else:
        logger.warning(f"Unhandled classification action: {mapped_action} for pitch {pitch_record['pitch_id']}")
    
    # Continue with existing reply processing for placement creation
    result = await monitor.process_reply(reply_message)
    
    if result.get("success"):
        logger.info(f"Processed reply via webhook: {result}")
        
        # Update Attio
        try:
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


async def store_email_classification(
    message_id: str,
    thread_id: str,
    classification_result: Dict[str, Any]
):
    """Store email classification results in database."""
    
    async with get_db_async() as db:
        query = """
            INSERT INTO email_classifications (
                message_id, thread_id, sender_email, sender_name,
                subject, classification, confidence_score,
                draft_generated, booking_assistant_session_id,
                raw_response, processed_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            ON CONFLICT (message_id) DO UPDATE SET
                classification = EXCLUDED.classification,
                confidence_score = EXCLUDED.confidence_score,
                processed_at = NOW()
        """
        
        await db.execute(
            query,
            message_id,
            thread_id,
            classification_result.get("sender_email"),
            classification_result.get("sender_name"),
            classification_result.get("subject"),
            classification_result.get("classification"),
            classification_result.get("confidence", 0.0),
            classification_result.get("draft") is not None,
            classification_result.get("session_id"),
            json.dumps(classification_result.get("raw_response", {}))
        )
        
        # Store draft if generated
        if classification_result.get("draft"):
            await store_email_draft(
                thread_id=thread_id,
                message_id=message_id,
                draft_content=classification_result["draft"],
                context=classification_result.get("relevant_threads", [])
            )


async def store_email_draft(
    thread_id: str,
    message_id: str,
    draft_content: str,
    context: list = None,
    pitch_id: int = None,
    campaign_id: str = None
):
    """Store AI-generated email draft."""
    
    async with get_db_async() as db:
        query = """
            INSERT INTO email_drafts (
                thread_id, message_id, draft_content,
                context, pitch_id, campaign_id,
                status, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, 'pending', NOW())
            RETURNING draft_id
        """
        
        draft_id = await db.fetch_val(
            query,
            thread_id,
            message_id,
            draft_content,
            json.dumps(context or []),
            pitch_id,
            campaign_id
        )
        
        return draft_id


async def handle_booking_confirmation(
    pitch_record: Dict[str, Any],
    reply_message: Dict[str, Any],
    classification_result: Dict[str, Any]
):
    """Handle emails classified as booking confirmations."""
    
    logger.info(f"Processing booking confirmation for pitch {pitch_record['pitch_id']}")
    
    # Check if placement already exists
    existing_placement = await placement_queries.get_placement_by_id(
        pitch_record.get('placement_id')
    ) if pitch_record.get('placement_id') else None
    
    if existing_placement:
        logger.info(f"Placement already exists for pitch {pitch_record['pitch_id']}")
        # Update existing placement with new information
        await placement_queries.update_placement_in_db(
            existing_placement['placement_id'],
            {
                "current_status": "confirmed",
                "notes": f"Booking confirmed via email classification: {classification_result.get('classification')}"
            }
        )
        return existing_placement
    
    # Build email thread
    monitor = NylasEmailMonitor()
    email_thread = await monitor._build_email_thread(pitch_record, reply_message)
    
    # Create new placement
    placement_data = {
        "campaign_id": pitch_record['campaign_id'],
        "media_id": pitch_record['media_id'],
        "pitch_id": pitch_record['pitch_id'],
        "current_status": "confirmed",
        "status_ts": datetime.now(timezone.utc),
        "notes": f"Auto-created from email classification: {classification_result.get('classification')}",
        "email_thread": email_thread,
        "outreach_topic": pitch_record.get('body_snippet', '')[:200]  # First 200 chars
    }
    
    placement = await placement_queries.create_placement_in_db(placement_data)
    
    # Update pitch with placement_id
    await pitch_queries.update_pitch_in_db(
        pitch_record['pitch_id'],
        {
            "placement_id": placement['placement_id'],
            "pitch_state": "booked",
            "reply_bool": True,
            "reply_ts": datetime.now(timezone.utc)
        }
    )
    
    # Create status history entry
    await create_status_history(
        placement_id=placement['placement_id'],
        old_status=None,
        new_status="confirmed",
        changed_by="BookingAssistant"
    )
    
    # Create review task for human verification
    await create_review_task({
        "task_type": "verify_booking",
        "related_id": placement['placement_id'],
        "campaign_id": pitch_record['campaign_id'],
        "notes": f"Please verify auto-created booking from {reply_message.get('from', [{}])[0].get('email', '')}"
    })
    
    logger.info(f"Created placement {placement['placement_id']} for pitch {pitch_record['pitch_id']}")
    return placement


async def handle_rejection(
    pitch_record: Dict[str, Any],
    reply_message: Dict[str, Any],
    classification_result: Dict[str, Any]
):
    """Handle emails classified as rejections."""
    
    logger.info(f"Processing rejection for pitch {pitch_record['pitch_id']}")
    
    # Update pitch status
    await pitch_queries.update_pitch_in_db(
        pitch_record['pitch_id'],
        {
            "pitch_state": "rejected",
            "reply_bool": True,
            "reply_ts": datetime.now(timezone.utc)
        }
    )
    
    # Check if we should stop the campaign
    campaign_id = pitch_record['campaign_id']
    
    # Count rejections for this campaign
    rejection_count = await count_campaign_rejections(campaign_id)
    
    if rejection_count >= 5:  # Threshold for auto-stopping
        # Create review task instead of auto-stopping
        await create_review_task({
            "task_type": "high_rejection_rate",
            "related_id": campaign_id,
            "campaign_id": campaign_id,
            "notes": f"Campaign has {rejection_count} rejections. Consider pausing or adjusting strategy."
        })
    
    # Update contact status to prevent future outreach
    media_record = await media_queries.get_media_by_id_from_db(pitch_record['media_id'])
    if media_record and media_record.get('contact_email'):
        await update_contact_status(
            email=media_record['contact_email'],
            status="do_not_contact",
            reason=f"Rejected outreach: {classification_result.get('classification')}"
        )
    
    logger.info(f"Marked pitch {pitch_record['pitch_id']} as rejected")


async def handle_question(
    pitch_record: Dict[str, Any],
    reply_message: Dict[str, Any],
    classification_result: Dict[str, Any]
):
    """Handle emails classified as questions needing human response."""
    
    logger.info(f"Processing question for pitch {pitch_record['pitch_id']}")
    
    # Update pitch status
    await pitch_queries.update_pitch_in_db(
        pitch_record['pitch_id'],
        {
            "pitch_state": "needs_response",
            "reply_bool": True,
            "reply_ts": datetime.now(timezone.utc)
        }
    )
    
    # Store the AI-generated draft if available
    draft_id = None
    if classification_result.get("draft"):
        draft_id = await store_email_draft(
            thread_id=reply_message.get("thread_id"),
            message_id=reply_message.get("id"),
            draft_content=classification_result["draft"],
            pitch_id=pitch_record['pitch_id'],
            campaign_id=str(pitch_record['campaign_id'])
        )
    
    # Create high-priority review task
    await create_review_task({
        "task_type": "respond_to_question",
        "related_id": pitch_record['pitch_id'],
        "campaign_id": pitch_record['campaign_id'],
        "priority": "high",
        "notes": f"Question from {reply_message.get('from', [{}])[0].get('email', '')}. "
                 f"Draft available: {'Yes' if draft_id else 'No'}"
    })
    
    logger.info(f"Created review task for question on pitch {pitch_record['pitch_id']}")


async def handle_followup(
    pitch_record: Dict[str, Any],
    reply_message: Dict[str, Any],
    classification_result: Dict[str, Any]
):
    """Handle emails classified as follow-ups from guests."""
    
    logger.info(f"Processing follow-up for pitch {pitch_record['pitch_id']}")
    
    # Update pitch status
    await pitch_queries.update_pitch_in_db(
        pitch_record['pitch_id'],
        {
            "pitch_state": "followup_received",
            "reply_bool": True,
            "reply_ts": datetime.now(timezone.utc)
        }
    )
    
    # Store the AI-generated draft if available
    if classification_result.get("draft"):
        await store_email_draft(
            thread_id=reply_message.get("thread_id"),
            message_id=reply_message.get("id"),
            draft_content=classification_result["draft"],
            pitch_id=pitch_record['pitch_id'],
            campaign_id=str(pitch_record['campaign_id'])
        )
    
    logger.info(f"Processed follow-up for pitch {pitch_record['pitch_id']}")


async def create_status_history(
    placement_id: int,
    old_status: str,
    new_status: str,
    changed_by: str
):
    """Create status history entry for placement."""
    
    async with get_db_async() as db:
        query = """
            INSERT INTO status_history (
                placement_id, old_status, new_status,
                changed_by, created_at
            ) VALUES ($1, $2, $3, $4, NOW())
        """
        
        await db.execute(
            query,
            placement_id,
            old_status,
            new_status,
            changed_by
        )


async def create_review_task(task_data: Dict[str, Any]):
    """Create a review task for human verification."""
    
    async with get_db_async() as db:
        query = """
            INSERT INTO review_tasks (
                task_type, related_id, campaign_id,
                priority, notes, status, created_at
            ) VALUES ($1, $2, $3, $4, $5, 'pending', NOW())
            RETURNING task_id
        """
        
        task_id = await db.fetch_val(
            query,
            task_data['task_type'],
            str(task_data['related_id']),
            str(task_data.get('campaign_id')),
            task_data.get('priority', 'normal'),
            task_data.get('notes', '')
        )
        
        logger.info(f"Created review task {task_id}: {task_data['task_type']}")
        return task_id


async def count_campaign_rejections(campaign_id: str) -> int:
    """Count number of rejections for a campaign."""
    
    async with get_db_async() as db:
        query = """
            SELECT COUNT(*) 
            FROM pitches 
            WHERE campaign_id = $1::uuid 
            AND pitch_state = 'rejected'
        """
        
        count = await db.fetch_val(query, campaign_id)
        return count or 0


async def update_contact_status(email: str, status: str, reason: str):
    """Update contact status in media table."""
    
    async with get_db_async() as db:
        query = """
            UPDATE media 
            SET contact_status = $2,
                contact_status_reason = $3,
                updated_at = NOW()
            WHERE LOWER(contact_email) = LOWER($1)
        """
        
        await db.execute(query, email, status, reason)


@router.get("/health", status_code=status.HTTP_200_OK, summary="Webhook Health Check")
async def webhook_health():
    """Health check endpoint for Nylas webhooks."""
    return {
        "status": "healthy",
        "webhook_type": "nylas",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }