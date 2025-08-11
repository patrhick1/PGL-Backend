# podcast_outreach/integrations/nylas.py

import os
import logging
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
from nylas import Client
from nylas.models.errors import NylasApiError
from nylas.models.messages import Message
from nylas.models.drafts import Draft

from podcast_outreach.utils.exceptions import APIClientError

logger = logging.getLogger(__name__)

class NylasAPIClient:
    """
    Nylas API client for email sending and management in the PGL system.
    Handles email sending, thread management, and message tracking.
    """
    
    def __init__(self, grant_id: Optional[str] = None):
        """
        Initialize Nylas client.
        
        Args:
            grant_id: Optional grant ID. If not provided, uses NYLAS_GRANT_ID from env
        """
        self.api_key = os.getenv('NYLAS_API_KEY')
        self.api_uri = os.getenv('NYLAS_API_URI', 'https://api.us.nylas.com')
        self.grant_id = grant_id or os.getenv('NYLAS_GRANT_ID')
        
        if not self.api_key:
            logger.error("NYLAS_API_KEY not set.")
            raise ValueError("NYLAS_API_KEY environment variable not set.")
            
        if not self.grant_id:
            logger.warning("NYLAS_GRANT_ID not set. Grant ID must be provided for operations.")
        
        self.client = Client(
            api_key=self.api_key,
            api_uri=self.api_uri
        )
        logger.info("NylasAPIClient initialized")
    
    def send_email(self, 
                   to_email: str,
                   subject: str,
                   body: str,
                   to_name: Optional[str] = None,
                   cc_emails: Optional[List[Dict[str, str]]] = None,
                   bcc_emails: Optional[List[Dict[str, str]]] = None,
                   reply_to_message_id: Optional[str] = None,
                   attachments: Optional[List[Dict[str, Any]]] = None,
                   tracking_options: Optional[Dict[str, bool]] = None,
                   custom_headers: Optional[Dict[str, str]] = None,
                   send_at: Optional[int] = None) -> Tuple[bool, Dict[str, Any]]:
        """
        Send an email using Nylas.
        
        Args:
            to_email: Recipient email address
            subject: Email subject
            body: Email body (HTML or plain text)
            to_name: Recipient name
            cc_emails: List of CC recipients [{"email": "...", "name": "..."}]
            bcc_emails: List of BCC recipients
            reply_to_message_id: Message ID if this is a reply
            attachments: List of attachment data
            tracking_options: {"opens": bool, "links": bool, "thread_replies": bool}
            custom_headers: Custom email headers for tracking
            send_at: Unix timestamp for scheduled send (optional)
            
        Returns:
            Tuple of (success: bool, result: dict with message_id, thread_id, or error)
        """
        try:
            # Prepare recipients
            to_list = [{"email": to_email}]
            if to_name:
                to_list[0]["name"] = to_name
            
            # Build request body according to Nylas v3 API spec
            request_body = {
                "to": to_list,
                "subject": subject,
                "body": body
            }
            
            # Add optional fields
            if cc_emails:
                request_body["cc"] = cc_emails
            if bcc_emails:
                request_body["bcc"] = bcc_emails
            if reply_to_message_id:
                request_body["reply_to_message_id"] = reply_to_message_id
            if attachments:
                request_body["attachments"] = attachments
            
            # Add custom headers for tracking
            if custom_headers:
                request_body["headers"] = custom_headers  # v3 uses "headers" not "custom_headers"
            
            # Add tracking options (Nylas v3 format)
            if tracking_options:
                # For Nylas v3, tracking_options is a direct field
                request_body["tracking_options"] = {
                    "opens": tracking_options.get("opens", False),
                    "links": tracking_options.get("links", False),
                    "thread_replies": tracking_options.get("thread_replies", False),
                    "label": tracking_options.get("label", "pgl-tracking")
                }
            
            # Add scheduled send time if provided
            if send_at:
                request_body["send_at"] = send_at  # Unix timestamp for scheduled send
            
            # Create and send the message
            logger.info(f"Sending email to {to_email} with subject: {subject}")
            
            # Clean up request body - remove None values
            request_body = {k: v for k, v in request_body.items() if v is not None}
            
            # Debug: Log the request body
            logger.info(f"Request body for draft: {json.dumps(request_body, indent=2)}")
            
            try:
                # First create a draft
                draft_response = self.client.drafts.create(
                    self.grant_id,
                    request_body=request_body
                )
            except Exception as e:
                logger.error(f"Draft creation failed. Grant ID: {self.grant_id}")
                logger.error(f"Request body type: {type(request_body)}")
                logger.error(f"Request body keys: {list(request_body.keys())}")
                raise
            
            # Then send the draft
            message = self.client.drafts.send(
                self.grant_id,
                draft_response.data.id
            )
            
            logger.info(f"Email sent successfully. Message ID: {message.data.id}")
            
            return True, {
                "message_id": message.data.id,
                "thread_id": message.data.thread_id,
                "draft_id": draft_response.data.id
            }
            
        except NylasApiError as e:
            logger.error(f"Nylas API error sending email: {e}")
            error_details = {
                "error": str(e),
                "error_type": getattr(e, 'error_type', 'unknown'),
                "request_id": getattr(e, 'request_id', None)
            }
            return False, error_details
        except Exception as e:
            logger.exception(f"Unexpected error sending email: {e}")
            return False, {"error": str(e)}
    
    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific message by ID."""
        try:
            message = self.client.messages.find(
                self.grant_id,
                message_id
            )
            return self._message_to_dict(message.data)
        except NylasApiError as e:
            logger.error(f"Error fetching message {message_id}: {e}")
            return None
    
    def get_thread(self, thread_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get all messages in a thread."""
        try:
            messages = self.client.messages.list(
                self.grant_id,
                query_params={
                    "thread_id": thread_id,
                    "limit": 100
                }
            )
            return [self._message_to_dict(msg) for msg in messages.data]
        except NylasApiError as e:
            logger.error(f"Error fetching thread {thread_id}: {e}")
            return None
    
    def search_messages(self, 
                       search_query: Optional[str] = None,
                       from_email: Optional[str] = None,
                       to_email: Optional[str] = None,
                       subject: Optional[str] = None,
                       after_date: Optional[datetime] = None,
                       before_date: Optional[datetime] = None,
                       has_attachment: Optional[bool] = None,
                       limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search messages with various filters.
        """
        try:
            query_params = {"limit": limit}
            
            if search_query:
                query_params["q"] = search_query
            if from_email:
                query_params["from"] = from_email
            if to_email:
                query_params["to"] = to_email
            if subject:
                query_params["subject"] = subject
            if after_date:
                query_params["received_after"] = int(after_date.timestamp())
            if before_date:
                query_params["received_before"] = int(before_date.timestamp())
            if has_attachment is not None:
                query_params["has_attachment"] = has_attachment
            
            messages = self.client.messages.list(
                self.grant_id,
                query_params=query_params
            )
            
            return [self._message_to_dict(msg) for msg in messages.data]
            
        except NylasApiError as e:
            logger.error(f"Error searching messages: {e}")
            return []
    
    def create_draft(self, 
                    to_email: str,
                    subject: str,
                    body: str,
                    to_name: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
        """Create a draft email without sending."""
        try:
            to_list = [{"email": to_email}]
            if to_name:
                to_list[0]["name"] = to_name
            
            draft_response = self.client.drafts.create(
                self.grant_id,
                request_body={
                    "to": to_list,
                    "subject": subject,
                    "body": body
                }
            )
            
            return True, {
                "draft_id": draft_response.data.id,
                "message_id": draft_response.data.id
            }
            
        except NylasApiError as e:
            logger.error(f"Error creating draft: {e}")
            return False, {"error": str(e)}
    
    def update_message_folder(self, message_id: str, folder_id: str) -> bool:
        """Move a message to a different folder."""
        try:
            self.client.messages.update(
                self.grant_id,
                message_id,
                request_body={"folder_id": folder_id}
            )
            return True
        except NylasApiError as e:
            logger.error(f"Error updating message folder: {e}")
            return False
    
    def _message_to_dict(self, message: Message) -> Dict[str, Any]:
        """Convert Nylas Message object to dictionary."""
        return {
            "id": message.id,
            "thread_id": message.thread_id,
            "subject": message.subject,
            "from": self._parse_participants(message.from_),
            "to": self._parse_participants(message.to),
            "cc": self._parse_participants(message.cc) if message.cc else [],
            "bcc": self._parse_participants(message.bcc) if message.bcc else [],
            "date": message.date,
            "snippet": message.snippet,
            "body": message.body,
            "unread": message.unread,
            "starred": message.starred,
            "attachments": [
                {
                    "id": att.id,
                    "filename": att.filename,
                    "content_type": att.content_type,
                    "size": att.size
                } for att in (message.attachments or [])
            ] if hasattr(message, 'attachments') else []
        }
    
    def _parse_participants(self, participants: Optional[List[Any]]) -> List[Dict[str, str]]:
        """Parse email participants into a consistent format."""
        if not participants:
            return []
        
        result = []
        for participant in participants:
            if isinstance(participant, dict):
                result.append({
                    "email": participant.get("email", ""),
                    "name": participant.get("name", "")
                })
            else:
                result.append({
                    "email": getattr(participant, "email", ""),
                    "name": getattr(participant, "name", "")
                })
        return result
    
    def test_connection(self) -> bool:
        """Test if the Nylas connection and grant are valid."""
        try:
            # Try to list a single message to verify connection
            messages = self.client.messages.list(
                self.grant_id,
                query_params={"limit": 1}
            )
            logger.info("Nylas API connection successful")
            return True
        except NylasApiError as e:
            logger.error(f"Nylas API connection failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error testing Nylas connection: {e}")
            return False

    def get_folders(self) -> List[Dict[str, Any]]:
        """Get all folders/labels for the account."""
        try:
            folders = self.client.folders.list(self.grant_id)
            return [
                {
                    "id": folder.id,
                    "name": folder.name,
                    "system_folder": getattr(folder, "system_folder", None)
                }
                for folder in folders.data
            ]
        except NylasApiError as e:
            logger.error(f"Error fetching folders: {e}")
            return []