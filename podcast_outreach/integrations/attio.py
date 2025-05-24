# podcast_outreach/integrations/attio.py

import requests
import os
import time
import logging
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
import html
import re

from podcast_outreach.utils.exceptions import APIClientError
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

class AttioClient:
    def __init__(self, api_key: Optional[str] = None, max_retries: int = 3, retry_delay: int = 2):
        self.api_key = api_key or os.getenv("ATTIO_ACCESS_TOKEN")
        if not self.api_key:
            logger.error("Attio API key not found. Please set ATTIO_ACCESS_TOKEN environment variable or pass api_key parameter.")
            raise ValueError("Attio API key not found.")
        
        self.base_url = "https://api.attio.com/v2"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def create_record(self, object_type: str, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a record in Attio for any object type
        """
        if not object_type:
            raise ValueError("Object type is required")
        if not attributes:
            raise ValueError("At least one attribute value is required")
        
        payload = {
            "data": {
                "values": attributes
            }
        }
        
        endpoint = f"{self.base_url}/objects/{object_type}/records"
        return self._make_api_request("post", endpoint, payload)
    
    def get_record(self, object_type: str, record_id: str) -> Dict[str, Any]:
        """
        Get a record by its ID
        """
        endpoint = f"{self.base_url}/objects/{object_type}/records/{record_id}"
        return self._make_api_request("get", endpoint)
    
    def update_record(self, object_type: str, record_id: str, attributes: Dict[str, Any], overwrite: bool = False) -> Dict[str, Any]:
        """
        Update a record in Attio
        """
        payload = {
            "data": {
                "values": attributes
            }
        }
        
        endpoint = f"{self.base_url}/objects/{object_type}/records/{record_id}"
        method = "put" if overwrite else "patch"
        
        return self._make_api_request(method, endpoint, payload)
    
    def delete_record(self, object_type: str, record_id: str) -> Dict[str, Any]:
        """
        Delete a record by its ID
        """
        endpoint = f"{self.base_url}/objects/{object_type}/records/{record_id}"
        return self._make_api_request("delete", endpoint)
    
    def list_records(self, object_type: str, filters: Optional[Dict[str, Any]] = None, 
                    page: int = 1, limit: int = 100) -> Dict[str, Any]:
        """
        List records of a specific object type, with optional filtering
        """
        payload = {
            "pagination": {
                "page": page,
                "limit": limit
            }
        }
        
        if filters:
            payload["filter"] = filters
        
        endpoint = f"{self.base_url}/objects/{object_type}/records/query"
        return self._make_api_request("post", endpoint, payload)
    
    def _make_api_request(self, method: str, url: str, data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make API request with retry logic and error handling"""
        retries = 0
        while retries <= self.max_retries:
            try:
                logger.info(f"Making {method.upper()} request to {url}")
                if data:
                    logger.debug(f"Payload: {data}") # Use debug for sensitive payload
                
                if method.lower() == "post":
                    response = requests.post(url, json=data, headers=self.headers, timeout=10)
                elif method.lower() == "put":
                    response = requests.put(url, json=data, headers=self.headers, timeout=10)
                elif method.lower() == "patch":
                    response = requests.patch(url, json=data, headers=self.headers, timeout=10)
                elif method.lower() == "delete":
                    response = requests.delete(url, headers=self.headers, timeout=10)
                else:  # Default to GET
                    response = requests.get(url, headers=self.headers, timeout=10)
                
                try:
                    response_data = response.json()
                    logger.info(f"Response status: {response.status_code}")
                    logger.debug(f"Response body: {response_data}") # Use debug for full response body
                except ValueError:
                    logger.info(f"Response status: {response.status_code}")
                    logger.debug(f"Response text: {response.text}") # Use debug for full response text
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', self.retry_delay))
                    logger.warning(f"Rate limited. Retrying after {retry_after} seconds.")
                    time.sleep(retry_after)
                    retries += 1
                    continue
                
                response.raise_for_status()
                
                return response.json()
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {str(e)}")
                if retries >= self.max_retries:
                    logger.error("Max retries reached. Raising exception.")
                    raise
                
                logger.info(f"Retrying in {self.retry_delay} seconds... (Attempt {retries + 1}/{self.max_retries})")
                time.sleep(self.retry_delay)
                retries += 1

    def filter_records(self, object_type: str, attribute_name: str, value: Any, 
                  operator: str = "equals", page: int = 1, limit: int = 100) -> Dict[str, Any]:
        """
        Filter records where a specific attribute has a particular value, using a simple equality check.
        """
        query_filter = None
        if operator.lower() == "equals":
            actual_value = value
            if isinstance(value, list) and len(value) == 1:
                actual_value = value[0]
                logger.debug(f"Simplified filter: Using first element of list for attribute '{attribute_name}'. Value: '{actual_value}'")
            elif isinstance(value, list) and len(value) != 1:
                logger.warning(
                    f"Filtering attribute '{attribute_name}' with operator 'equals' and a list value with multiple items or empty: {value}. "
                    f"This may not behave as expected with Attio's simple filter. Consider using query_records for complex array matching."
                    f"Proceeding with the list as is, but direct scalar or single-item list is preferred for this method."
                )
            query_filter = {attribute_name: actual_value}
        else:
            raise NotImplementedError(
                f"Operator '{operator}' is not supported by filter_records. "
                f"This method only supports 'equals'. For other operators or complex filters, use query_records."
            )

        return self.list_records(object_type, query_filter, page, limit)

    def query_records(self, object_type: str, filters: Dict[str, Any], page: int = 1, limit: int = 100) -> Dict[str, Any]:
        """
        Query records of a specific object type with full control over Attio's filter syntax.
        """
        payload = {
            "pagination": {
                "page": page,
                "limit": limit
            }
        }
        
        if filters:
            payload["filter"] = filters
        
        endpoint = f"{self.base_url}/objects/{object_type}/records/query"
        return self._make_api_request("post", endpoint, payload)

    def create_note(self, parent_object_slug: str, parent_record_id: str, title: str, content: str, created_at: str, note_format: str = "plaintext"):
        """
        Creates a new note for a given record in Attio.
        """
        endpoint = f"{self.base_url}/notes"
        payload = {
            "data": {
                "parent_object": parent_object_slug,
                "parent_record_id": parent_record_id,
                "title": title,
                "format": note_format,
                "content": content,
            }
        }
        if created_at:
            payload["data"]["created_at"] = created_at
        
        logger.info(f"Creating note for record {parent_record_id} in object {parent_object_slug} with title '{title}'")
        try:
            json_response = self._make_api_request("post", endpoint, data=payload)
            
            note_id = json_response.get('data', {}).get('id', {}).get('note_id')
            logger.info(f"Successfully created note for record {parent_record_id}. Note ID: {note_id}")
            return json_response
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error creating note for {parent_record_id} in {parent_object_slug}: {http_err} - {http_err.response.text if http_err.response else 'No response body'}")
            raise
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request error creating note for {parent_record_id} in {parent_object_slug}: {req_err}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in create_note for {parent_record_id} in {parent_object_slug}: {e}")
            raise

# --- Attio Webhook Processors (Moved from src/attio_email_sent.py and src/attio_response.py) ---

# Initialize AttioClient globally for webhook functions
attio_client_for_webhooks = AttioClient() 
ATTIO_PODCAST_OBJECT_SLUG = "podcast" # Assuming this is the correct object slug in Attio

async def update_attio_when_email_sent(data: Dict[str, Any]):
    """
    Updates Attio record when an email is sent via Instantly webhook.
    This function is designed to be called by a FastAPI webhook endpoint.
    
    Args:
        data: The JSON payload from Instantly.ai webhook.
              Expected to contain 'attio_record_id', 'timestamp', 'event_type', 'personalization'.
              The 'attio_record_id' should be the ID of the Attio 'podcast' record.
    """
    attio_record_id = data.get('attio_record_id') # This is expected to be the Attio record_id for the podcast object
    if not attio_record_id:
        logger.warning("attio_record_id not provided in webhook data for email sent event.")
        return {"success": False, "message": "attio_record_id missing."}

    try:
        podcast_record_response = attio_client_for_webhooks.get_record(ATTIO_PODCAST_OBJECT_SLUG, attio_record_id)
        
        if not podcast_record_response or 'data' not in podcast_record_response:
            logger.warning(f"No Attio record found with id {attio_record_id} or error in response for email sent event.")
            return {"success": False, "message": f"Attio record {attio_record_id} not found."}

        podcast_data = podcast_record_response['data']
        current_attributes = podcast_data.get('values', {})
        
        # Assuming 'description' is the slug for Correspondence/Notes field
        current_description = current_attributes.get('description', '') 
        # Assuming 'outreach_date' is the slug for the date field
        existing_outreach_date = current_attributes.get('outreach_date') 

        timestamp_str = data.get('timestamp', datetime.now().isoformat())
        event_type = data.get('event_type', 'EMAIL_SENT') # Default to EMAIL_SENT
        personalization = data.get('personalization', 'No message content provided.') # Message content or summary

        # Append new correspondence entry
        # Ensure a clean separation for new entries
        new_entry_header = f"\n\n--- Entry: {timestamp_str} ---\nEvent Type: {event_type}\n"
        new_correspondence_detail = f"Message: {personalization}"
        
        # Check if current_description is a list (if it's a rich text field or similar) or string
        if isinstance(current_description, list):
            # Handle case where description might be structured (e.g., from rich text)
            # This example converts it to a string. Adjust if Attio returns structured text.
            current_description_text = "\n".join(current_description)
        else:
            current_description_text = current_description or ''

        updated_description = current_description_text + new_entry_header + new_correspondence_detail

        # Prepare fields to update
        today_date = datetime.now().strftime('%Y-%m-%d')
        attributes_to_update = {
            'description': updated_description,
            'outreach_date': today_date  # Set/update the outreach date
        }

        # If 'outreach_date' was not previously set, set 'relationship_stage' to 'Outreached'
        # Attio's 'get_record' returns actual values, so check if existing_outreach_date was None or empty
        if not existing_outreach_date:
            attributes_to_update['relationship_stage'] = 'Outreached' # Assuming 'relationship_stage' is the slug

        # Update the record in Attio
        updated_record = attio_client_for_webhooks.update_record(
            object_type=ATTIO_PODCAST_OBJECT_SLUG,
            record_id=attio_record_id,
            attributes=attributes_to_update
        )

        if updated_record:
            logger.info(f"Attio record {attio_record_id} updated successfully for email sent event.")
            return {"success": True, "message": f"Attio record {attio_record_id} updated."}
        else:
            logger.error(f"Failed to update Attio record {attio_record_id} for email sent event. Check AttioClient logs for details.")
            return {"success": False, "message": f"Failed to update Attio record {attio_record_id}."}

    except Exception as e:
        logger.exception(f"An error occurred while updating Attio record {attio_record_id} for email sent event: {str(e)}")
        raise # Re-raise for the webhook router to catch

async def update_correspondent_on_attio(data: Dict[str, Any]):
    """
    Updates the correspondence field and relationship stage in Attio when an email reply is received.
    
    Args:
        data: The JSON payload from Instantly.ai webhook.
              Expected to contain 'attio_record_id', 'timestamp', 'reply_text_snippet'.
              The 'attio_record_id' should be the ID of the Attio 'podcast' record.
    """
    attio_record_id = data.get('attio_record_id') # Expected to be the Attio record_id
    timestamp_str = data.get('timestamp', datetime.now().isoformat())
    reply_text_snippet = data.get('reply_text_snippet')

    # Validate required fields
    if not attio_record_id or not reply_text_snippet:
        logger.warning("Webhook data missing required fields (attio_record_id or reply_text_snippet) for reply received event.")
        return {"success": False, "message": "Missing required fields."}

    try:
        # Fetch current record from Attio
        podcast_record_response = attio_client_for_webhooks.get_record(ATTIO_PODCAST_OBJECT_SLUG, attio_record_id)
        if not podcast_record_response or 'data' not in podcast_record_response:
            logger.warning(f"Attio Record with ID {attio_record_id} not found or error in response for reply received event.")
            return {"success": False, "message": f"Attio record {attio_record_id} not found."}

        podcast_data = podcast_record_response['data']
        current_attributes = podcast_data.get('values', {})
        existing_description = current_attributes.get('description', '') # Map to 'description'

        # Append new correspondence
        new_entry_header = f"\n\n--- Reply Received: {timestamp_str} ---"
        new_reply_detail = f"Reply Snippet: {reply_text_snippet}"
        
        # Handle potential list format for description
        if isinstance(existing_description, list):
            existing_description_text = "\n".join(existing_description)
        else:
            existing_description_text = existing_description or ''
            
        new_description = existing_description_text + new_entry_header + new_reply_detail

        # Prepare fields to update
        attributes_to_update = {
            'description': new_description,
            'relationship_stage': 'Responded' # Update relationship stage
        }

        # Update the record in Attio
        updated_record = attio_client_for_webhooks.update_record(
            object_type=ATTIO_PODCAST_OBJECT_SLUG,
            record_id=attio_record_id,
            attributes=attributes_to_update
        )

        if updated_record:
            logger.info(f"Attio Record {attio_record_id} updated successfully with reply.")
            return {"success": True, "message": f"Attio record {attio_record_id} updated with reply."}
        else:
            logger.error(f"Failed to update Attio record {attio_record_id} for reply received event. Check AttioClient logs.")
            return {"success": False, "message": f"Failed to update Attio record {attio_record_id}."}

    except Exception as e:
        logger.exception(f"An error occurred while updating Attio record {attio_record_id} with reply: {str(e)}")
        raise # Re-raise for the webhook router to catch
