# podcast_outreach/integrations/instantly.py

import os
import logging
import requests
from typing import Dict, Any, Optional, List

# Assuming base_client.py and exceptions.py are in the same directory (src) (UPDATED IMPORTS)
# from podcast_outreach.integrations.base_client import PodcastAPIClient # Not inheriting from PodcastAPIClient
from podcast_outreach.utils.exceptions import APIClientError

logger = logging.getLogger(__name__)

INSTANTLY_API_KEY = os.getenv('INSTANTLY_API_KEY')
INSTANTLY_BASE_URL = "https://api.instantly.ai/api/v2"

class InstantlyAPIClient: # Renamed from InstantlyAPI to InstantlyAPIClient for consistency
    def __init__(self):
        self.base_url = INSTANTLY_BASE_URL
        self.api_key = INSTANTLY_API_KEY
        self.session = requests.Session() # Use requests.Session for Instantly
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
        else:
            logger.error("INSTANTLY_API_KEY not set. InstantlyAPI calls will likely fail.")
            raise ValueError("INSTANTLY_API_KEY environment variable not set.") # Raise error if key is missing

    def _request_instantly(self, method: str, endpoint_suffix: str, **kwargs) -> requests.Response:
        """Internal request method for Instantly, using its own session and error handling."""
        url = f"{self.base_url}/{endpoint_suffix.lstrip('/')}"
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status() # Will raise HTTPError for 4xx/5xx
            return response
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"InstantlyAPIClient HTTP error: {http_err} for URL {url} - Response: {http_err.response.text}")
            raise APIClientError(f"InstantlyAPIClient HTTP error: {http_err}", status_code=http_err.response.status_code) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(f"InstantlyAPIClient Request error: {req_err} for URL {url}")
            raise APIClientError(f"InstantlyAPIClient Request error: {req_err}") from req_err

    def add_lead_v2(self, data: Dict[str, Any]) -> Dict[str, Any]:
        # The data here is the JSON payload itself for POST
        response = self._request_instantly("POST", "leads", json=data)
        return response.json()

    def list_campaigns(self) -> Optional[Dict[str, Any]]:
        try:
            response = self._request_instantly("GET", "campaigns", params={"limit": "1"})
            return response.json()
        except APIClientError as e:
            # For list_campaigns, often used as a health/auth check, so non-fatal logging
            logger.warning(f"InstantlyAPIClient list_campaigns failed (maybe auth issue?): {e}")
            return None # Return None if it fails, allows caller to check

    def list_emails(self, limit: int = 100, starting_after: Optional[str] = None) -> Optional[Dict[str, Any]]:
        params = {"limit": limit}
        if starting_after: params["starting_after"] = starting_after
        try:
            response = self._request_instantly("GET", "emails", params=params)
            return response.json()
        except APIClientError as e:
            logger.error(f"InstantlyAPIClient list_emails failed: {e}")
            return None

    def list_leads_from_campaign(self, campaign_id: str, search: Optional[str] = None, limit_per_page: int = 100) -> List[Dict[str, Any]]:
        if not campaign_id: return []
        all_leads = []
        starting_after = None
        while True:
            payload = {"campaign": campaign_id, "limit": limit_per_page}
            if starting_after: payload["starting_after"] = starting_after
            if search: payload["search"] = search
            try:
                response = self._request_instantly("POST", "leads/list", json=payload)
                data = response.json()
            except APIClientError as e:
                logger.error(f"InstantlyAPIClient list_leads_from_campaign page fetch failed: {e}")
                break # Stop pagination on error
            except ValueError:
                 logger.error(f"InstantlyAPIClient list_leads_from_campaign JSON decode error. Response: {response.text if 'response' in locals() else 'N/A'}")
                 break

            leads_this_page = data.get("items", [])
            all_leads.extend(leads_this_page)
            next_starting_after = data.get("next_starting_after")
            if not next_starting_after or len(leads_this_page) < limit_per_page:
                break
            starting_after = next_starting_after
        return all_leads
