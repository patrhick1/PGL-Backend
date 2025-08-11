# podcast_outreach/services/inbox/booking_assistant.py
"""
BookingAssistant Integration Service
Connects to the live BookingAssistant API for intelligent email processing
"""

import os
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class BookingAssistantService:
    """
    Client for BookingAssistant API running on Render
    Handles email classification, draft generation, and intelligent responses
    """
    
    def __init__(self):
        # Get URL from environment variable with fallback
        self.base_url = os.getenv('BOOKING_ASSISTANT_URL', 'https://booking-assistant-82xm.onrender.com')
        
        # Log warning if using default
        if not os.getenv('BOOKING_ASSISTANT_URL'):
            logger.warning(
                "BOOKING_ASSISTANT_URL not set in environment. Using default: %s. "
                "Please add BOOKING_ASSISTANT_URL to your .env file for production.", 
                self.base_url
            )
        
        # Remove trailing slash if present
        self.base_url = self.base_url.rstrip('/')
        
        self.api_key = os.getenv('BOOKING_ASSISTANT_API_KEY')
        self.timeout = aiohttp.ClientTimeout(total=30)  # 30 seconds timeout as per API guide
        
        logger.info(f"BookingAssistant client initialized with URL: {self.base_url}")
    
    async def process_email(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send email to BookingAssistant for processing
        
        Args:
            email_data: Dictionary containing:
                - email_text: The email body content (or 'email' or 'body' for compatibility)
                - subject: Email subject line
                - sender_email: Sender's email address (REQUIRED)
                - sender_name: Sender's name (optional)
                - thread_id: Optional thread ID for context
                - message_id: Optional message ID
        
        Returns:
            Dictionary containing:
                - status: Processing status
                - classification: Email category
                - draft: Generated response draft
                - confidence: Classification confidence
                - context_used: Whether historical context was used
        """
        
        # Prepare the request payload
        # API expects 'email' field (not 'body' or 'email_text')
        # We support multiple field names for backward compatibility
        email_content = email_data.get("email_text") or email_data.get("email") or email_data.get("body", "")
        
        payload = {
            "email": email_content,  # API expects 'email' field
            "subject": email_data.get("subject", ""),
            "sender_email": email_data.get("sender_email", ""),  # REQUIRED by API
            "sender_name": email_data.get("sender_name", "Unknown"),
        }
        
        # Add optional fields if present
        if email_data.get("thread_id"):
            payload["thread_id"] = email_data["thread_id"]
        if email_data.get("message_id"):
            payload["message_id"] = email_data["message_id"]
        
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    f"{self.base_url}/start_agent_v2",
                    json=payload,
                    headers=headers
                ) as response:
                    
                    if response.status == 200:
                        result = await response.json()
                        
                        # Check if email was already processed (duplicate detection)
                        if result.get("status") == "skipped":
                            logger.info(f"Email already processed: {result.get('message', 'Duplicate detected')}")
                            return {
                                "status": "skipped",
                                "message": result.get("message", "Email already processed"),
                                "classification": "duplicate",
                                "duplicate": True
                            }
                        
                        # Handle the new standardized response format
                        # API now returns classification at top level AND in result object
                        classification = result.get("classification")
                        confidence = result.get("confidence", 0.95)
                        draft = result.get("generated_response")
                        
                        # Fallback to result object if top-level fields missing
                        if not classification and "result" in result and isinstance(result["result"], dict):
                            inner_result = result["result"]
                            classification = inner_result.get("label", inner_result.get("classification"))
                            confidence = inner_result.get("confidence", confidence)
                            draft = draft or inner_result.get("final_draft", inner_result.get("draft"))
                        
                        # Extract additional fields
                        relevant_threads = []
                        draft_id = None
                        if "result" in result and isinstance(result["result"], dict):
                            relevant_threads = result["result"].get("relevant_threads", [])
                            # Extract draft ID from draft_status if present
                            draft_status = result["result"].get("draft_status", "")
                            if "Draft created with ID:" in draft_status:
                                draft_id = draft_status.split("ID:")[1].strip()
                        
                        # Log if no classification returned
                        if not classification:
                            logger.warning(f"No classification returned from BookingAssistant for email: {email_data.get('subject', 'No subject')}")
                            classification = "unknown"
                            confidence = 0.0
                        
                        return {
                            "status": result.get("status", "success"),
                            "classification": classification,
                            "draft": draft,
                            "draft_id": draft_id,
                            "confidence": confidence,
                            "context_used": result.get("context_used", False),
                            "relevant_threads": relevant_threads,
                            "processing_time": result.get("processing_time_ms", 0),
                            "session_id": result.get("session_id"),
                            "raw_response": result,
                            "sender_email": email_data.get("sender_email"),
                            "sender_name": email_data.get("sender_name"),
                            "subject": email_data.get("subject")
                        }
                    
                    elif response.status == 400:
                        error_data = await response.json()
                        error_detail = error_data.get("detail", "Bad request")
                        
                        # Provide helpful error messages for common issues
                        if "email" in str(error_detail).lower() and "required" in str(error_detail).lower():
                            logger.error("Missing required 'email' field. Make sure to pass email content.")
                            error_detail = "Missing required email content. Pass 'email_text' or 'email' field."
                        elif "sender_email" in str(error_detail).lower() and "required" in str(error_detail).lower():
                            logger.error("Missing required 'sender_email' field.")
                            error_detail = "Missing required sender_email field."
                        
                        logger.warning(f"Bad request to BookingAssistant: {error_data}")
                        return {
                            "status": "error",
                            "error": error_detail,
                            "classification": "unknown",
                            "hint": "Check that email content and sender_email are provided"
                        }
                    
                    elif response.status == 503:
                        logger.error("BookingAssistant service unavailable")
                        return {
                            "status": "error",
                            "error": "BookingAssistant service unavailable",
                            "classification": "unknown"
                        }
                    
                    else:
                        logger.error(f"Unexpected status from BookingAssistant: {response.status}")
                        return {
                            "status": "error",
                            "error": f"Unexpected status: {response.status}",
                            "classification": "unknown"
                        }
                        
        except aiohttp.ClientError as e:
            # Check if it's a timeout error
            if "timeout" in str(e).lower():
                logger.warning(f"BookingAssistant API timeout (30s). The API may be processing. Error: {e}")
                return {
                    "status": "error",
                    "error": "API timeout - processing may take longer than expected",
                    "classification": "unknown",
                    "hint": "Try again or check API status at https://booking-assistant-82xm.onrender.com/"
                }
            else:
                logger.error(f"Network error calling BookingAssistant: {e}")
                return {
                    "status": "error",
                    "error": f"Network error: {str(e)}",
                    "classification": "unknown"
                }
        except Exception as e:
            logger.exception(f"Unexpected error calling BookingAssistant: {e}")
            return {
                "status": "error",
                "error": f"Unexpected error: {str(e)}",
                "classification": "unknown"
            }
    
    async def get_classification(self, email_text: str, subject: str = "") -> Dict[str, Any]:
        """
        Get just the classification for an email without generating a draft
        
        Args:
            email_text: The email body content
            subject: Email subject line
        
        Returns:
            Dictionary containing classification and confidence
        """
        
        # Use the main process_email but we'll just extract classification
        result = await self.process_email({
            "email_text": email_text,
            "subject": subject,
            "sender_email": "classification@request.com",
            "sender_name": "Classification Request"
        })
        
        return {
            "classification": result.get("classification", "unknown"),
            "confidence": result.get("confidence", 0.0),
            "status": result.get("status")
        }
    
    async def health_check(self) -> bool:
        """
        Check if BookingAssistant service is healthy
        
        Returns:
            True if service is available, False otherwise
        """
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                # Try the root endpoint since /health might have dependencies
                async with session.get(f"{self.base_url}/") as response:
                    # Accept 200 or 500 (500 might mean some services aren't ready but API is up)
                    return response.status in [200, 500]
        except:
            return False
    
    async def get_dashboard_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        Get dashboard statistics from BookingAssistant
        
        Args:
            days: Number of days to analyze
        
        Returns:
            Dictionary containing dashboard statistics
        """
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    f"{self.base_url}/api/overview",
                    params={"days": days}
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return {}
        except Exception as e:
            logger.error(f"Error fetching dashboard stats: {e}")
            return {}


# Classification mappings for podcast outreach context
CLASSIFICATION_MAPPINGS = {
    # BookingAssistant classifications -> Podcast Outreach actions
    "booking": "podcast_booking",  # Confirmed booking
    "accepted": "podcast_booking",  # Accepted invitation
    "guest acceptance": "podcast_booking",  # Guest accepts
    "schedule request": "scheduling",  # Wants to schedule
    "client_followup": "guest_followup",  # Follow-up from guest
    "follow up": "guest_followup",  # Follow-up category
    "follow up information requested": "question",  # Needs more info
    "rejection": "rejection",  # Not interested
    "polite_rejection": "rejection",  # Polite no
    "not interested": "rejection",  # Not interested category
    "needs_more_info": "question",  # Needs human response
    "information request": "question",  # Asking for info
    "question": "question",  # Direct question
    "spam": "spam",  # Spam or irrelevant
    "out_of_office": "out_of_office",  # Auto-responder
    "interested": "interested",  # Shows interest
    "general": "general",  # General email
    "others": "other",  # Others category from API
    "none": "unknown",  # No classification
    None: "unknown",  # Null classification
}


def map_classification(booking_assistant_classification: str) -> str:
    """
    Map BookingAssistant classification to podcast outreach context
    
    Args:
        booking_assistant_classification: Classification from BookingAssistant
    
    Returns:
        Mapped classification for podcast outreach system
    """
    if not booking_assistant_classification:
        return "unknown"
    
    return CLASSIFICATION_MAPPINGS.get(
        booking_assistant_classification.lower(), 
        "unknown"
    )


# Singleton instance
booking_assistant_service = BookingAssistantService()


# Synchronous wrapper for non-async code
def classify_email_sync(email_content: str, subject: str, sender_email: str, sender_name: str = None) -> Dict[str, Any]:
    """
    Synchronous wrapper for email classification.
    
    This is a convenience function for code that doesn't use async/await.
    
    Args:
        email_content: The email body text (REQUIRED)
        subject: Email subject line
        sender_email: Sender's email address (REQUIRED)
        sender_name: Sender's name (optional)
    
    Returns:
        Dictionary containing classification results
    
    Example:
        result = classify_email_sync(
            email_content="I'd love to be on your podcast!",
            subject="Re: Podcast Invitation",
            sender_email="guest@example.com",
            sender_name="John Doe"
        )
        print(f"Classification: {result['classification']}")
    """
    import asyncio
    
    async def _process():
        service = BookingAssistantService()
        return await service.process_email({
            "email": email_content,  # Use correct field name
            "subject": subject,
            "sender_email": sender_email,
            "sender_name": sender_name or ""
        })
    
    # Run the async function in a new event loop if needed
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running (e.g., in Jupyter), create a new task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _process())
                return future.result(timeout=35)  # 35 seconds to account for API timeout
        else:
            return loop.run_until_complete(_process())
    except RuntimeError:
        # No event loop exists, create one
        return asyncio.run(_process())