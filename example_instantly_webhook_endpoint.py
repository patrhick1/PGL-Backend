"""
Example FastAPI endpoint for receiving Instantly webhooks
Add this to your routers or main.py
"""

from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional, Dict, Any
import hmac
import hashlib
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Your Instantly webhook secret (set this in environment variables)
INSTANTLY_WEBHOOK_SECRET = "your_webhook_secret_here"

def verify_instantly_signature(payload: bytes, signature: str) -> bool:
    """Verify the webhook signature from Instantly"""
    expected_signature = hmac.new(
        INSTANTLY_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)

@router.post("/api/webhooks/instantly")
async def instantly_webhook(
    request: Request,
    x_instantly_signature: Optional[str] = Header(None)
):
    """
    Receive webhooks from Instantly
    
    Instantly sends webhooks for events like:
    - Campaign started/completed
    - Email sent/opened/clicked/replied
    - Email bounced
    - Lead unsubscribed
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        
        # Verify signature in production
        # if x_instantly_signature:
        #     if not verify_instantly_signature(body, x_instantly_signature):
        #         raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse JSON payload
        payload = await request.json()
        
        event_type = payload.get("event")
        logger.info(f"Received Instantly webhook: {event_type}")
        logger.debug(f"Payload: {payload}")
        
        # Handle different event types
        if event_type == "email_replied":
            # Handle reply
            campaign_id = payload.get("campaign_id")
            lead_email = payload.get("lead", {}).get("email")
            reply_body = payload.get("reply", {}).get("body")
            
            logger.info(f"Reply received from {lead_email} for campaign {campaign_id}")
            # TODO: Update your database, create tasks, etc.
            
        elif event_type == "email_opened":
            # Handle email open
            campaign_id = payload.get("campaign_id")
            lead_email = payload.get("lead", {}).get("email")
            
            logger.info(f"Email opened by {lead_email} for campaign {campaign_id}")
            # TODO: Update metrics
            
        elif event_type == "email_bounced":
            # Handle bounce
            lead_email = payload.get("lead", {}).get("email")
            bounce_type = payload.get("bounce_details", {}).get("type")
            
            logger.warning(f"Email bounced for {lead_email}: {bounce_type}")
            # TODO: Mark email as invalid, update campaign
            
        elif event_type == "campaign_completed":
            # Handle campaign completion
            campaign_id = payload.get("campaign", {}).get("id")
            stats = payload.get("stats", {})
            
            logger.info(f"Campaign {campaign_id} completed with stats: {stats}")
            # TODO: Update campaign status, generate reports
        
        # Return success
        return {
            "status": "success",
            "message": f"Webhook {event_type} processed",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error processing Instantly webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Webhook processing failed")