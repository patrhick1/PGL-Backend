# podcast_outreach/api/routers/webhooks.py

from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import JSONResponse
import logging

# Import the new webhook processing functions from attio.py
from podcast_outreach.integrations.attio import update_attio_when_email_sent, update_correspondent_on_attio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

@router.post("/instantly-email-sent", status_code=status.HTTP_200_OK, summary="Instantly.ai Email Sent Webhook")
async def instantly_email_sent_webhook(request: Request):
    """
    Webhook endpoint to receive 'email sent' events from Instantly.ai.
    Processes the event to update relevant records in Attio.
    """
    try:
        data = await request.json()
    except Exception as e:
        logger.warning(f"Invalid JSON received at /webhooks/instantly-email-sent: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    logger.info(f"Received Instantly 'email sent' webhook: {data.get('event', 'N/A')} for lead {data.get('lead_id', 'N/A')}")
    
    try:
        # Call the new function in integrations/attio.py
        # The webhook data structure needs to be mapped correctly for update_attio_when_email_sent
        # Assuming 'airID' in the old src/attio_email_sent.py maps to 'attio_record_id' in the new data.
        # And 'personalization' is the message content.
        # This mapping needs to be precise based on actual Instantly webhook payload.
        # For now, I'll pass the raw data and let the attio function handle mapping.
        await update_attio_when_email_sent(data)
        return JSONResponse(content={"status": "success", "message": "Email sent webhook processed."})
    except Exception as e:
        logger.exception(f"Error processing Instantly 'email sent' webhook: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process webhook: {str(e)}")

@router.post("/instantly-reply-received", status_code=status.HTTP_200_OK, summary="Instantly.ai Reply Received Webhook")
async def instantly_reply_received_webhook(request: Request):
    """
    Webhook endpoint to receive 'reply received' events from Instantly.ai.
    Processes the event to update relevant records in Attio.
    """
    try:
        data = await request.json()
    except Exception as e:
        logger.warning(f"Invalid JSON received at /webhooks/instantly-reply-received: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    logger.info(f"Received Instantly 'reply received' webhook: {data.get('event', 'N/A')} for lead {data.get('lead_id', 'N/A')}")

    try:
        # Call the new function in integrations/attio.py
        # Assuming 'airID' maps to 'attio_record_id' and 'reply_text_snippet' is available.
        await update_correspondent_on_attio(data)
        return JSONResponse(content={"status": "success", "message": "Reply received webhook processed."})
    except Exception as e:
        logger.exception(f"Error processing Instantly 'reply received' webhook: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process webhook: {str(e)}")
