# podcast_outreach/api/routers/webhooks.py

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse
import logging
from datetime import datetime, timezone

# Import the new webhook processing functions from attio.py
from podcast_outreach.integrations.attio import update_attio_when_email_sent, update_correspondent_on_attio
from podcast_outreach.services.pitches.sender import PitchSenderService
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import placements as placement_queries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

@router.post("/instantly-email-sent", status_code=status.HTTP_200_OK, summary="Instantly.ai Email Sent Webhook")
async def instantly_email_sent_webhook(request: Request):
    """
    Webhook endpoint to receive 'email sent' events from Instantly.ai.
    Updates pitch state to 'sent' and processes Attio integration.
    """
    try:
        data = await request.json()
    except Exception as e:
        logger.warning(f"Invalid JSON received at /webhooks/instantly-email-sent: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    logger.info(f"Received Instantly 'email sent' webhook for email: {data.get('email', 'N/A')}")
    
    try:
        # Extract the pitch_gen_id from custom variables
        pitch_gen_id = data.get('pitch_gen_id')
        if not pitch_gen_id:
            logger.warning(f"No pitch_gen_id found in webhook data: {data}")
            
        # Update pitch state using pitch_gen_id
        if pitch_gen_id:
            pitch_record = await pitch_queries.get_pitch_by_pitch_gen_id(int(pitch_gen_id))
            if pitch_record:
                # Update pitch to 'sent' state
                update_data = {
                    "pitch_state": "sent",
                    "send_ts": datetime.now(timezone.utc)
                }
                await pitch_queries.update_pitch_in_db(pitch_record['pitch_id'], update_data)
                logger.info(f"Updated pitch {pitch_record['pitch_id']} to 'sent' state")
            else:
                logger.warning(f"No pitch found for pitch_gen_id: {pitch_gen_id}")
        
        # Update Attio
        try:
            await update_attio_when_email_sent(data)
        except Exception as attio_error:
            logger.warning(f"Failed to update Attio: {attio_error}")
            # Don't fail the whole webhook if Attio update fails
            
        return JSONResponse(content={"status": "success", "message": "Email sent webhook processed."})
    except Exception as e:
        logger.exception(f"Error processing Instantly 'email sent' webhook: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process webhook: {str(e)}")

@router.post("/instantly-reply-received", status_code=status.HTTP_200_OK, summary="Instantly.ai Reply Received Webhook")
async def instantly_reply_received_webhook(request: Request):
    """
    Webhook endpoint to receive 'reply received' events from Instantly.ai.
    Updates pitch state to 'replied', creates placement record, and processes Attio.
    """
    try:
        data = await request.json()
    except Exception as e:
        logger.warning(f"Invalid JSON received at /webhooks/instantly-reply-received: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    logger.info(f"Received Instantly 'reply received' webhook for email: {data.get('email', 'N/A')}")

    try:
        # Extract pitch_gen_id from webhook data
        pitch_gen_id = data.get('pitch_gen_id')
        if not pitch_gen_id:
            # Try to get from custom variables or other fields
            custom_vars = data.get('custom_variables', {})
            pitch_gen_id = custom_vars.get('pitch_gen_id')
            
        campaign_id = data.get('campaign_id') or data.get('custom_variables', {}).get('campaign_id')
        media_id = data.get('media_id') or data.get('custom_variables', {}).get('media_id')
        
        if pitch_gen_id:
            pitch_record = await pitch_queries.get_pitch_by_pitch_gen_id(int(pitch_gen_id))
            if pitch_record:
                # Check if this is the first reply or subsequent reply
                is_first_reply = pitch_record.get('pitch_state') != 'replied'
                
                if is_first_reply:
                    # First reply - update pitch state and create placement
                    update_data = {
                        "pitch_state": "replied",
                        "reply_bool": True,
                        "reply_ts": datetime.now(timezone.utc)
                    }
                    await pitch_queries.update_pitch_in_db(pitch_record['pitch_id'], update_data)
                    logger.info(f"Updated pitch {pitch_record['pitch_id']} to 'replied' state (first reply)")
                    
                    # Create placement record for the booking conversation
                    if campaign_id and media_id:
                        # Build email thread with initial pitch and reply
                        email_thread = []
                        
                        # Add the original sent email if we have it
                        if pitch_record.get('send_ts'):
                            email_thread.append({
                                "timestamp": pitch_record['send_ts'].isoformat() if hasattr(pitch_record['send_ts'], 'isoformat') else str(pitch_record['send_ts']),
                                "direction": "sent",
                                "from": data.get('email_account', 'aidrian@digitalpodcastguest.com'),
                                "to": data.get('email', ''),
                                "subject": data.get('Subject', pitch_record.get('subject_line', '')),
                                "body_text": data.get('personalization', ''),
                                "instantly_data": {
                                    "campaign_id": data.get('campaign_id'),
                                    "instantly_campaign_id": data.get('campaign'),
                                    "pitch_gen_id": data.get('pitch_gen_id')
                                }
                            })
                        
                        # Add the reply
                        email_thread.append({
                            "timestamp": data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                            "direction": "received",
                            "from": data.get('email', ''),
                            "to": data.get('email_account', 'aidrian@digitalpodcastguest.com'),
                            "subject": data.get('reply_subject', ''),
                            "body_text": data.get('reply_text', data.get('reply_text_snippet', '')),
                            "body_html": data.get('reply_html', ''),
                            "message_id": data.get('email_id'),
                            "instantly_data": {
                                "unibox_url": data.get('unibox_url'),
                                "is_first": data.get('is_first', True),
                                "reply_text_snippet": data.get('reply_text_snippet')
                            }
                        })
                        
                        placement_data = {
                            "campaign_id": campaign_id,
                            "media_id": int(media_id),
                            "pitch_id": pitch_record['pitch_id'],
                            "current_status": "initial_reply",
                            "status_ts": datetime.now(timezone.utc),
                            "notes": f"Initial reply received from {data.get('email', 'podcast host')}",
                            "email_thread": email_thread
                        }
                        
                        try:
                            placement = await placement_queries.create_placement(placement_data)
                            logger.info(f"Created placement record {placement['placement_id']} for replied pitch")
                            
                            # Update pitch with placement_id
                            await pitch_queries.update_pitch_in_db(
                                pitch_record['pitch_id'], 
                                {"placement_id": placement['placement_id']}
                            )
                        except Exception as placement_error:
                            logger.error(f"Failed to create placement: {placement_error}")
                else:
                    # Subsequent reply - update existing placement's email thread
                    logger.info(f"Processing subsequent reply for pitch {pitch_record['pitch_id']}")
                    
                    # Get the placement associated with this pitch
                    if pitch_record.get('placement_id'):
                        from podcast_outreach.database.queries.placement_thread_updates import update_thread_for_subsequent_reply
                        
                        try:
                            updated_placement = await update_thread_for_subsequent_reply(data, pitch_record['placement_id'])
                            if updated_placement:
                                logger.info(f"Updated email thread for placement {pitch_record['placement_id']}")
                                
                                # Optionally update placement status if needed
                                if data.get('reply_text_snippet', '').lower().find('yes') != -1:
                                    # Example: update status based on reply content
                                    await placement_queries.update_placement_in_db(
                                        pitch_record['placement_id'],
                                        {"current_status": "confirmed_interest"}
                                    )
                            else:
                                logger.warning(f"Failed to update email thread for placement {pitch_record['placement_id']}")
                        except Exception as thread_error:
                            logger.error(f"Error updating email thread: {thread_error}")
                    else:
                        logger.warning(f"Pitch {pitch_record['pitch_id']} is marked as replied but has no placement_id")
            else:
                logger.warning(f"No pitch found for pitch_gen_id: {pitch_gen_id}")
        else:
            logger.warning(f"No pitch_gen_id found in reply webhook data")
        
        # Update Attio
        try:
            await update_correspondent_on_attio(data)
        except Exception as attio_error:
            logger.warning(f"Failed to update Attio: {attio_error}")
            # Don't fail the whole webhook if Attio update fails
            
        return JSONResponse(content={"status": "success", "message": "Reply received webhook processed."})
    except Exception as e:
        logger.exception(f"Error processing Instantly 'reply received' webhook: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process webhook: {str(e)}")
