# podcast_outreach/services/pitches/sender_v2.py

"""
Enhanced pitch sender service that supports both Nylas and Instantly.
This version allows gradual migration from Instantly to Nylas.
"""

import json
import logging
from typing import Any, Dict, Optional, List, Tuple
import uuid
from datetime import datetime, timezone
import asyncio
from enum import Enum

# Project imports
from podcast_outreach.logging_config import get_logger
from podcast_outreach.integrations.instantly import InstantlyAPIClient
from podcast_outreach.integrations.nylas import NylasAPIClient
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import pitch_generations as pitch_gen_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries

logger = get_logger(__name__)


class EmailProvider(Enum):
    """Supported email providers."""
    INSTANTLY = "instantly"
    NYLAS = "nylas"


class PitchSenderServiceV2:
    """
    Enhanced pitch sender that supports multiple email providers.
    Allows campaigns to use either Instantly or Nylas for sending.
    """
    
    def __init__(self):
        self.instantly_client = InstantlyAPIClient()
        self.nylas_clients = {}  # Cache of Nylas clients by grant_id
        logger.info("PitchSenderServiceV2 initialized with multi-provider support")
    
    def _get_nylas_client(self, grant_id: str) -> NylasAPIClient:
        """Get or create a Nylas client for a specific grant ID."""
        if grant_id not in self.nylas_clients:
            self.nylas_clients[grant_id] = NylasAPIClient(grant_id=grant_id)
        return self.nylas_clients[grant_id]
    
    async def send_pitch(self, pitch_gen_id: int) -> Dict[str, Any]:
        """
        Send a pitch using the appropriate email provider.
        
        Args:
            pitch_gen_id: ID of the pitch generation to send
            
        Returns:
            Dict with success status and details
        """
        logger.info(f"Attempting to send pitch generation {pitch_gen_id}")
        result = {"success": False, "message": "Failed to send pitch.", "provider": None}
        
        try:
            # Get pitch generation details
            pitch_gen = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
            if not pitch_gen:
                result["message"] = f"Pitch generation {pitch_gen_id} not found."
                return result
            
            if not pitch_gen.get('send_ready_bool'):
                result["message"] = f"Pitch generation {pitch_gen_id} is not marked as send-ready."
                return result
            
            # Get related data
            campaign_id = pitch_gen['campaign_id']
            media_id = pitch_gen['media_id']
            
            campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
            media_data = await media_queries.get_media_by_id_from_db(media_id)
            
            if not campaign_data or not media_data:
                result["message"] = "Related campaign or media data not found."
                return result
            
            # Determine email provider
            email_provider = EmailProvider(campaign_data.get('email_provider', 'instantly'))
            result["provider"] = email_provider.value
            
            # Get or create pitch record
            pitch_record = await pitch_queries.get_pitch_by_pitch_gen_id(pitch_gen_id)
            if not pitch_record:
                # Create new pitch record
                pitch_data = {
                    "campaign_id": campaign_id,
                    "media_id": media_id,
                    "pitch_gen_id": pitch_gen_id,
                    "subject_line": self._generate_subject_line(pitch_gen, campaign_data, media_data),
                    "body_snippet": (pitch_gen.get('final_text') or pitch_gen.get('draft_text'))[:500],
                    "pitch_state": "draft",
                    "email_provider": email_provider.value,
                    "created_by": "system"
                }
                pitch_record = await pitch_queries.create_pitch_in_db(pitch_data)
            
            # Send using appropriate provider
            if email_provider == EmailProvider.NYLAS:
                result = await self._send_via_nylas(
                    pitch_gen, pitch_record, campaign_data, media_data
                )
            else:
                result = await self._send_via_instantly(
                    pitch_gen, pitch_record, campaign_data, media_data
                )
            
        except Exception as e:
            logger.exception(f"Error sending pitch {pitch_gen_id}: {e}")
            result["message"] = f"Failed to send pitch: {str(e)}"
        
        return result
    
    async def _send_via_nylas(self, 
                             pitch_gen: Dict[str, Any],
                             pitch_record: Dict[str, Any],
                             campaign_data: Dict[str, Any],
                             media_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send pitch using Nylas."""
        result = {"success": False, "message": "", "provider": "nylas"}
        
        # Get Nylas grant ID
        grant_id = campaign_data.get('nylas_grant_id')
        if not grant_id:
            result["message"] = "No Nylas grant ID configured for campaign"
            return result
        
        # Get recipient email
        recipient_email = media_data.get('contact_email')
        if not recipient_email:
            result["message"] = f"No contact email found for media {media_data.get('media_id')}"
            return result
        
        # Parse multiple emails if comma-separated
        email_list = [e.strip() for e in recipient_email.split(',') if e.strip()]
        if not email_list:
            result["message"] = f"No valid email addresses found for media {media_data.get('media_id')}"
            return result
        
        primary_email = email_list[0]
        
        # Prepare email content
        subject = pitch_record.get('subject_line')
        body = pitch_gen.get('final_text') or pitch_gen.get('draft_text')
        
        # Add tracking headers
        custom_headers = {
            "X-PGL-Campaign-ID": str(campaign_data.get('campaign_id')),
            "X-PGL-Media-ID": str(media_data.get('media_id')),
            "X-PGL-Pitch-Gen-ID": str(pitch_gen.get('pitch_gen_id')),
            "X-PGL-Pitch-ID": str(pitch_record.get('pitch_id'))
        }
        
        # Get host name
        host_names = media_data.get('host_names', [])
        host_name = host_names[0] if host_names else None
        
        # Generate tracking label for this campaign
        campaign_name = campaign_data.get('campaign_name', 'unknown')
        tracking_label = f"campaign-{campaign_data.get('campaign_id')}-{campaign_name}"
        
        # Send email with comprehensive tracking
        nylas_client = self._get_nylas_client(grant_id)
        success, send_result = nylas_client.send_email(
            to_email=primary_email,
            to_name=host_name,
            subject=subject,
            body=body,
            custom_headers=custom_headers,
            tracking_options={
                "opens": True, 
                "links": True,
                "thread_replies": True,
                "label": tracking_label
            }
        )
        
        if success:
            # Update pitch record with tracking info
            update_data = {
                "send_ts": datetime.now(timezone.utc),
                "pitch_state": "sent",
                "nylas_message_id": send_result.get("message_id"),
                "nylas_thread_id": send_result.get("thread_id"),
                "nylas_draft_id": send_result.get("draft_id"),
                "tracking_label": tracking_label,
                "send_status": "sent"
            }
            await pitch_queries.update_pitch_in_db(pitch_record['pitch_id'], update_data)
            
            result["success"] = True
            result["message"] = f"Pitch sent successfully via Nylas to {primary_email}"
            result["nylas_message_id"] = send_result.get("message_id")
            
            logger.info(f"Pitch {pitch_record['pitch_id']} sent via Nylas. Message ID: {send_result.get('message_id')}")
        else:
            result["message"] = f"Nylas send failed: {send_result.get('error', 'Unknown error')}"
            logger.error(result["message"])
        
        return result
    
    async def _send_via_instantly(self,
                                pitch_gen: Dict[str, Any],
                                pitch_record: Dict[str, Any],
                                campaign_data: Dict[str, Any],
                                media_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send pitch using Instantly (original implementation)."""
        result = {"success": False, "message": "", "provider": "instantly"}
        
        instantly_campaign_id = campaign_data.get('instantly_campaign_id')
        if not instantly_campaign_id:
            result["message"] = f"Instantly Campaign ID not found for campaign {campaign_data.get('campaign_id')}"
            return result
        
        recipient_email = media_data.get('contact_email')
        if not recipient_email:
            result["message"] = f"No contact email found for media {media_data.get('media_id')}"
            return result
        
        email_list = [e.strip() for e in recipient_email.split(',') if e.strip()]
        if not email_list:
            result["message"] = f"No valid email addresses found for media {media_data.get('media_id')}"
            return result
        
        primary_email = email_list[0]
        
        # Prepare Instantly API data
        api_data = await self._prepare_instantly_api_data(
            campaign_data, media_data, pitch_gen, pitch_record, primary_email
        )
        
        logger.info(f"Sending pitch {pitch_gen.get('pitch_gen_id')} to Instantly for {primary_email}...")
        
        try:
            response_data = await asyncio.to_thread(self.instantly_client.add_lead_v2, api_data)
            
            if response_data and response_data.get('id'):
                lead_id = response_data['id']
                
                # Update pitch record
                await pitch_queries.update_pitch_in_db(
                    pitch_record['pitch_id'],
                    {
                        "send_ts": datetime.now(timezone.utc),
                        "pitch_state": "sent",
                        "instantly_lead_id": lead_id
                    }
                )
                
                result["success"] = True
                result["message"] = f"Pitch sent successfully via Instantly. Lead ID: {lead_id}"
                result["instantly_lead_id"] = lead_id
                
                logger.info(f"Pitch {pitch_record['pitch_id']} sent via Instantly. Lead ID: {lead_id}")
            else:
                result["message"] = f"Instantly API did not return a lead ID for pitch {pitch_gen.get('pitch_gen_id')}"
                logger.error(result["message"])
                
        except Exception as e:
            result["message"] = f"Instantly API error: {str(e)}"
            logger.error(result["message"])
        
        return result
    
    async def _prepare_instantly_api_data(self,
                                       campaign_data: Dict[str, Any],
                                       media_data: Dict[str, Any],
                                       pitch_gen_data: Dict[str, Any],
                                       pitch_data: Dict[str, Any],
                                       recipient_email: str) -> Dict[str, Any]:
        """Prepare data for Instantly API (original implementation)."""
        instantly_campaign_id = campaign_data.get('instantly_campaign_id')
        client_name = campaign_data.get('campaign_name')
        podcast_name = media_data.get('name')
        host_name = media_data.get('host_names', [''])[0] if media_data.get('host_names') else ''
        subject_line = pitch_data.get('subject_line') or "No Subject"
        pitch_body = pitch_gen_data.get('final_text') or pitch_gen_data.get('draft_text')
        
        custom_variables = {
            "Client_Name": client_name,
            "Subject": subject_line,
            "pitch_gen_id": pitch_gen_data.get('pitch_gen_id'),
            "campaign_id": str(campaign_data.get('campaign_id')),
            "media_id": media_data.get('media_id')
        }
        
        data = {
            "campaign": instantly_campaign_id,
            "skip_if_in_campaign": True,
            "email": recipient_email,
            "first_name": host_name,
            "company_name": podcast_name,
            "personalization": pitch_body,
            "verify_leads_for_lead_finder": True,
            "verify_leads_on_import": True,
            "custom_variables": custom_variables
        }
        
        return data
    
    def _generate_subject_line(self,
                             pitch_gen: Dict[str, Any],
                             campaign_data: Dict[str, Any],
                             media_data: Dict[str, Any]) -> str:
        """Generate a subject line if not already present."""
        # You can implement custom subject line generation logic here
        # For now, use a simple template
        client_name = campaign_data.get('campaign_name', 'Guest')
        podcast_name = media_data.get('name', 'your podcast')
        
        return f"{client_name} - Perfect Guest for {podcast_name}"
    
    async def record_response(self,
                            lead_id: Optional[str] = None,
                            message_id: Optional[str] = None,
                            response_type: str = "replied",
                            timestamp: Optional[datetime] = None,
                            content_snippet: Optional[str] = None) -> Dict[str, Any]:
        """
        Record an email response for either Instantly or Nylas.
        
        Args:
            lead_id: Instantly lead ID
            message_id: Nylas message ID
            response_type: Type of response (opened, replied, clicked)
            timestamp: When the response occurred
            content_snippet: Preview of response content
            
        Returns:
            Dict with processing results
        """
        if not timestamp:
            timestamp = datetime.now(timezone.utc)
        
        result = {"success": False, "message": "Failed to record response."}
        
        try:
            # Find the pitch record
            pitch_record = None
            
            if lead_id:
                pitch_record = await pitch_queries.get_pitch_by_instantly_lead_id(lead_id)
            elif message_id:
                pitch_record = await pitch_queries.get_pitch_by_nylas_message_id(message_id)
            
            if not pitch_record:
                result["message"] = f"No pitch record found for lead_id={lead_id}, message_id={message_id}"
                logger.warning(result["message"])
                return result
            
            # Update pitch based on response type
            pitch_id = pitch_record['pitch_id']
            update_data = {}
            
            if response_type == 'opened':
                update_data['pitch_state'] = 'opened'
                update_data['opened_ts'] = timestamp
            elif response_type == 'replied':
                update_data['pitch_state'] = 'replied'
                update_data['reply_bool'] = True
                update_data['reply_ts'] = timestamp
            elif response_type == 'clicked':
                update_data['pitch_state'] = 'clicked'
                update_data['clicked_ts'] = timestamp
            elif response_type == 'bounced':
                update_data['pitch_state'] = 'bounced'
                update_data['bounced_ts'] = timestamp
            else:
                result["message"] = f"Unknown response type: {response_type}"
                return result
            
            updated_pitch = await pitch_queries.update_pitch_in_db(pitch_id, update_data)
            
            if updated_pitch:
                result["success"] = True
                result["message"] = f"Pitch {pitch_id} updated with {response_type} status"
                result["pitch_id"] = pitch_id
                logger.info(result["message"])
            else:
                result["message"] = f"Failed to update pitch {pitch_id} in database"
                
        except Exception as e:
            logger.exception(f"Error recording response: {e}")
            result["message"] = f"Failed to record response: {str(e)}"
        
        return result


# Singleton instance for backward compatibility
pitch_sender_service = PitchSenderServiceV2()