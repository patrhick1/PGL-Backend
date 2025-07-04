# podcast_outreach/services/pitches/sender.py

import json
import logging
from typing import Any, Dict, Optional, List
import uuid
from datetime import datetime
import asyncio
 
# Project imports
from podcast_outreach.logging_config import get_logger
from podcast_outreach.integrations.instantly import InstantlyAPIClient
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import pitch_generations as pitch_gen_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries
 
logger = get_logger(__name__)
 
class PitchSenderService:
    """
    Handles sending approved pitches via Instantly.ai and recording the outcome.
    """
    def __init__(self):
        self.instantly_client = InstantlyAPIClient()
        logger.info("PitchSenderService initialized.")
 
    async def _prepare_instantly_api_data(
        self,
        campaign_data: Dict[str, Any],
        media_data: Dict[str, Any],
        pitch_gen_data: Dict[str, Any],
        pitch_data: Dict[str, Any],
        recipient_email: str
    ) -> Dict[str, Any]:
        """
        Prepares the payload for Instantly.ai's add_lead_v2 API.
        """
        instantly_campaign_id = campaign_data.get('instantly_campaign_id')
        if not instantly_campaign_id:
            logger.error(f"Instantly Campaign ID not found for campaign {campaign_data.get('campaign_id')}. Cannot prepare lead data.")
            raise ValueError("Instantly Campaign ID is required to send pitches.")
 
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
 
    async def send_pitch_to_instantly(self, pitch_gen_id: int) -> Dict[str, Any]:
        """
        Sends an approved pitch generation to Instantly.ai.
        """
        logger.info(f"Attempting to send pitch generation {pitch_gen_id} to Instantly.ai.")
        result = {"success": False, "message": "Failed to send pitch."}
 
        try:
            pitch_gen = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
            if not pitch_gen:
                result["message"] = f"Pitch generation {pitch_gen_id} not found."
                return result
            
            if not pitch_gen.get('send_ready_bool'):
                result["message"] = f"Pitch generation {pitch_gen_id} is not marked as send-ready."
                return result
 
            campaign_id = pitch_gen['campaign_id']
            media_id = pitch_gen['media_id']
 
            campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
            media_data = await media_queries.get_media_by_id_from_db(media_id)
 
            if not campaign_data or not media_data:
                result["message"] = "Related campaign or media data not found."
                return result
 
            recipient_email = media_data.get('contact_email')
            if not recipient_email:
                result["message"] = f"No contact email found for media {media_id}. Cannot send pitch."
                return result
            
            email_list = [e.strip() for e in recipient_email.split(',') if e.strip()]
            if not email_list:
                result["message"] = f"No valid email addresses found for media {media_id}."
                return result
            
            primary_recipient_email = email_list[0]
            
            # Get the pitch record to get subject_line
            pitch_record = await pitch_queries.get_pitch_by_pitch_gen_id(pitch_gen_id)
            if not pitch_record:
                result["message"] = f"No pitch record found for pitch_gen_id {pitch_gen_id}."
                return result
 
            api_data = await self._prepare_instantly_api_data(
                campaign_data, media_data, pitch_gen, pitch_record, primary_recipient_email
            )
 
            logger.info(f"Sending pitch {pitch_gen_id} to Instantly for {primary_recipient_email}...")
            response_data = await asyncio.to_thread(self.instantly_client.add_lead_v2, api_data)
            
            if response_data and response_data.get('id'):
                lead_id = response_data['id']
                logger.info(f"Pitch {pitch_gen_id} successfully sent to Instantly. Lead ID: {lead_id}")
                
                await pitch_queries.update_pitch_in_db(
                    pitch_record['pitch_id'],
                    {
                        "send_ts": datetime.utcnow(),
                        "pitch_state": "sent",
                        "instantly_lead_id": lead_id
                    }
                )
                result["success"] = True
                result["message"] = f"Pitch {pitch_record['pitch_id']} sent successfully to Instantly. Lead ID: {lead_id}"
 
            else:
                result["message"] = f"Instantly API did not return a lead ID or response was unexpected for pitch {pitch_gen_id}."
                logger.error(f"Instantly API response for pitch {pitch_gen_id} was unexpected: {response_data}")
 
        except Exception as e:
            logger.exception(f"Error sending pitch {pitch_gen_id} to Instantly: {e}")
            result["message"] = f"Failed to send pitch: {str(e)}"
        
        return result
 
    async def record_response(self, instantly_lead_id: str, response_type: str, timestamp: datetime, content_snippet: Optional[str] = None) -> Dict[str, Any]:
        """
        Records an email response (open, reply, click) from Instantly webhooks.
        """
        logger.info(f"Recording Instantly response for lead {instantly_lead_id}: {response_type}")
        result = {"success": False, "message": "Failed to record response."}
 
        try:
            pitch_record = await pitch_queries.get_pitch_by_instantly_lead_id(instantly_lead_id)
            if not pitch_record:
                result["message"] = f"No pitch record found for Instantly lead ID {instantly_lead_id}."
                logger.warning(result["message"])
                return result
            
            pitch_id = pitch_record['pitch_id']
            update_data = {}
 
            if response_type == 'opened':
                update_data['pitch_state'] = 'opened'
            elif response_type == 'replied':
                update_data['pitch_state'] = 'replied'
                update_data['reply_bool'] = True
                update_data['reply_ts'] = timestamp
            elif response_type == 'clicked':
                update_data['pitch_state'] = 'clicked'
            else:
                result["message"] = f"Unknown response type: {response_type}."
                return result
 
            updated_pitch = await pitch_queries.update_pitch_in_db(pitch_id, update_data)
            if updated_pitch:
                result["success"] = True
                result["message"] = f"Pitch {pitch_id} updated with {response_type} status."
                logger.info(result["message"])
            else:
                result["message"] = f"Failed to update pitch {pitch_id} in DB for {response_type}."
 
        except Exception as e:
            logger.exception(f"Error recording Instantly response for lead {instantly_lead_id}: {e}")
            result["message"] = f"Failed to record response: {str(e)}"
        
        return result
