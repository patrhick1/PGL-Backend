# app/external_api_service.py

import os
import logging
import html
import requests
from typing import Dict, Any, Optional, List
import asyncio # Not strictly needed here unless base_client becomes async
import time # For potential delays if ever needed

# Assuming base_client.py and exceptions.py are in the same directory (src)
# If they are in the parent directory, adjust to: from ..base_client import PodcastAPIClient etc.
from .base_client import PodcastAPIClient 
from .exceptions import APIClientError, AuthenticationError, NotFoundError, RateLimitError

logger = logging.getLogger(__name__)

# --- Podscan.fm API Client ---
PODSCAN_API_KEY = os.getenv("PODSCANAPI") 
PODSCAN_BASE_URL = "https://podscan.fm/api/v1"

class PodscanAPIClient(PodcastAPIClient):
    """API Client for Podscan.fm, inheriting from PodcastAPIClient."""

    def __init__(self):
        if not PODSCAN_API_KEY:
            logger.error("PODSCAN_API_KEY environment variable not set.")
            raise AuthenticationError("Podscan API key not configured")
        super().__init__(api_key=PODSCAN_API_KEY, base_url=PODSCAN_BASE_URL)
        logger.info("PodscanAPIClient initialized.")

    def _set_auth_header(self):
        """Sets the Authorization Bearer token header for Podscan authentication."""
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
            logger.debug("Podscan API authentication header set.")

    def search_podcasts(self, query: str, **kwargs) -> Dict[str, Any]:
        endpoint = "podcasts/search"
        params = {
            'query': query,
            'per_page': kwargs.get('per_page', 20),
            'language': kwargs.get('language', 'en'),
            **{k: v for k, v in kwargs.items() if k in ['page', 'category_ids']}
        }
        if 'category_id' in params: # Legacy mapping from single id
            params['category_ids'] = params.pop('category_id')

        logger.info(f"Searching Podscan for query: '{query}' with params: {params}")
        try:
            return self._request("GET", endpoint, params=params)
        except APIClientError as e:
            logger.error(f"Podscan API search failed: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in Podscan search: {e}")
            raise APIClientError(f"Unexpected error in Podscan search: {e}")

    def get_categories(self) -> List[Dict[str, Any]]:
        endpoint = 'categories'
        logger.info("Fetching categories from Podscan.")
        try:
            response_data = self._request("GET", endpoint)
            categories = response_data.get("categories", [])
            if not isinstance(categories, list):
                 logger.warning(f"Podscan get_categories returned non-list: {type(categories)}")
                 return []
            return [
                {
                    "category_id": cat.get("category_id"),
                    "category_name": cat.get("category_name"),
                    "category_display_name": cat.get("category_display_name")
                } for cat in categories
            ]
        except APIClientError as e:
            logger.error(f"Podscan get_categories failed: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in Podscan get_categories: {e}")
            raise APIClientError(f"Unexpected error in Podscan get_categories: {e}")

    def get_podcast_episodes(self, podcast_id: str, **kwargs) -> List[Dict[str, Any]]:
        endpoint = f'podcasts/{podcast_id}/episodes'
        params = {
            'order_by': kwargs.get('order_by', 'posted_at'),
            'order_dir': kwargs.get('order_dir', 'desc'),
            'per_page': kwargs.get('per_page', 10)
        }
        logger.info(f"Fetching Podscan episodes for {podcast_id} with params: {params}")
        try:
            response_data = self._request("GET", endpoint, params=params)
            episodes = response_data.get("episodes", [])
            if not isinstance(episodes, list):
                 logger.warning(f"Podscan get_podcast_episodes returned non-list: {type(episodes)}")
                 return []
            return [
                {
                    "episode_id": ep.get("episode_id"), "episode_url": ep.get("episode_url"),
                    "episode_title": ep.get("episode_title"), "episode_audio_url": ep.get("episode_audio_url"),
                    "posted_at": ep.get("posted_at"), "episode_transcript": ep.get("episode_transcript"),
                    'episode_description': ep.get('episode_description')
                } for ep in episodes
            ]
        except APIClientError as e:
            logger.error(f"Podscan get_podcast_episodes for {podcast_id} failed: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in Podscan get_podcast_episodes: {e}")
            raise APIClientError(f"Unexpected error in Podscan get_podcast_episodes: {e}")

    def search_podcast_by_rss(self, rss_feed_url: str) -> Optional[Dict[str, Any]]:
        endpoint = 'podcasts/search/by/RSS'
        params = {'rss_feed': rss_feed_url}
        logger.info(f"Searching Podscan by RSS: {rss_feed_url}")
        try:
            response_data = self._request("GET", endpoint, params=params)
            podcast_list = []
            if isinstance(response_data, dict) and 'podcasts' in response_data and isinstance(response_data['podcasts'], list):
                podcast_list = response_data['podcasts']
            elif isinstance(response_data, list):
                podcast_list = response_data
            else:
                logger.warning(f"Unexpected Podscan RSS search format for {rss_feed_url}. Got {type(response_data)}")
                return None

            if len(podcast_list) == 1:
                podcast_data = podcast_list[0]
                if isinstance(podcast_data, dict) and podcast_data.get('podcast_id'):
                     return podcast_data
                logger.warning(f"Podscan RSS search for {rss_feed_url} found single item, but invalid format: {podcast_data}")
                return None
            elif len(podcast_list) > 1:
                logger.warning(f"Podscan RSS search for {rss_feed_url} returned {len(podcast_list)} results. Returning None.")
            return None # Handles 0 results or >1 results after warning
        except NotFoundError:
            logger.info(f"Podscan RSS {rss_feed_url} not found (404).")
            return None
        except APIClientError as e:
            logger.error(f"Podscan search_by_rss for {rss_feed_url} failed: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in Podscan search_by_rss for {rss_feed_url}: {e}")
            return None 

    def search_podcast_by_itunes_id(self, itunes_id: int) -> Optional[Dict[str, Any]]:
        if not itunes_id: return None
        endpoint = 'podcasts/search/by/itunesid'
        params = {'itunes_id': str(itunes_id)} # API expects string for itunes_id
        logger.info(f"Searching Podscan by iTunes ID: {itunes_id}")
        try:
            response_data = self._request("GET", endpoint, params=params)
            if isinstance(response_data, dict) and 'podcast' in response_data:
                podcast_data = response_data.get('podcast')
                if isinstance(podcast_data, dict) and podcast_data.get('podcast_id'):
                    if str(podcast_data.get('podcast_itunes_id')) == str(itunes_id):
                        return podcast_data
                    logger.warning(f"Podscan iTunes ID search for {itunes_id} returned mismatch: {podcast_data.get('podcast_itunes_id')}")
                    return None
                logger.warning(f"Podscan iTunes ID search for {itunes_id} 'podcast' value invalid: {podcast_data}")
                return None
            logger.warning(f"Unexpected Podscan iTunes ID search format for {itunes_id}. Got {type(response_data)}")
            return None
        except NotFoundError:
            logger.info(f"Podscan iTunes ID {itunes_id} not found (404).")
            return None
        except APIClientError as e:
            logger.error(f"Podscan search_by_itunes_id for {itunes_id} failed: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in Podscan search_by_itunes_id for {itunes_id}: {e}")
            return None
            
    def get_related_podcasts(self, podcast_id: str) -> Optional[List[Dict[str, Any]]]:
        if not podcast_id: return None
        endpoint = f"podcasts/{podcast_id}/related_podcasts"
        logger.info(f"Fetching related podcasts for Podscan ID: {podcast_id}")
        try:
            response_data = self._request("GET", endpoint)
            related_podcasts_list = []
            if isinstance(response_data, dict) and 'related_podcasts' in response_data:
                 related_podcasts_list = response_data.get('related_podcasts', [])
                 if not isinstance(related_podcasts_list, list):
                     logger.warning(f"Podscan get_related_podcasts for {podcast_id} 'related_podcasts' not a list.")
                     return None
            elif isinstance(response_data, list):
                 related_podcasts_list = response_data
            else:
                 logger.warning(f"Podscan get_related_podcasts for {podcast_id} returned unexpected format: {type(response_data)}")
                 return None
            valid_results = [p for p in related_podcasts_list if isinstance(p, dict) and p.get('podcast_id')]
            if len(valid_results) != len(related_podcasts_list):
                logger.warning(f"Some items in related podcasts response for {podcast_id} were invalid.")
            return valid_results
        except APIClientError as e:
            logger.error(f"Podscan get_related_podcasts for {podcast_id} failed: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error in Podscan get_related_podcasts for {podcast_id}: {e}")
            return None 

# --- ListenNotes API Client ---
LISTENNOTES_API_KEY = os.getenv("LISTEN_NOTES_API_KEY")
LISTENNOTES_BASE_URL = "https://listen-api.listennotes.com/api/v2"

class ListenNotesAPIClient(PodcastAPIClient):
    """API Client for Listen Notes, inheriting from PodcastAPIClient."""

    def __init__(self):
        if not LISTENNOTES_API_KEY:
            logger.error("LISTENNOTES_API_KEY environment variable not set.")
            raise AuthenticationError("Listen Notes API key not configured")
        super().__init__(api_key=LISTENNOTES_API_KEY, base_url=LISTENNOTES_BASE_URL)
        logger.info("ListenNotesAPIClient initialized.")

    def _set_auth_header(self):
        """Sets the X-ListenAPI-Key header for Listen Notes authentication."""
        if self.api_key:
            self.session.headers.update({"X-ListenAPI-Key": self.api_key})
            logger.debug("Listen Notes API authentication header set.")

    def _fetch_podcasts_batch(self, 
                             ids: Optional[List[str]] = None,
                             rsses: Optional[List[str]] = None,
                             itunes_ids: Optional[List[int]] = None,
                             # spotify_ids: Optional[List[str]] = None, # ListenNotes POST /podcasts doesn't support spotify_ids
                             show_latest_episodes: int = 0,
                             next_episode_pub_date: Optional[int] = None) -> Optional[Dict[str, Any]]:
        endpoint = "podcasts"
        data = {}
        if ids: data['ids'] = ",".join(ids)
        if rsses: data['rsses'] = ",".join(rsses)
        if itunes_ids: data['itunes_ids'] = ",".join(map(str, itunes_ids))
        # if spotify_ids: data['spotify_ids'] = ",".join(spotify_ids) # Not supported by this LN endpoint
        if show_latest_episodes in [0, 1]: data['show_latest_episodes'] = str(show_latest_episodes)
        if next_episode_pub_date: data['next_episode_pub_date'] = str(next_episode_pub_date)

        if not data or (not ids and not rsses and not itunes_ids):
            logger.warning("No valid identifiers provided to ListenNotes _fetch_podcasts_batch.")
            return None

        logger.info(f"Fetching ListenNotes podcast batch data with params: {list(data.keys())}")
        try:
            return self._request("POST", endpoint, data=data)
        except APIClientError as e:
            logger.error(f"Listen Notes POST /podcasts failed: {e}")
            return None # Return None on API errors for batch lookups
        except Exception as e:
            logger.exception(f"Unexpected error in Listen Notes POST /podcasts: {e}")
            # Do not raise APIClientError for general exceptions here to avoid breaking loops unnecessarily
            return None 

    def search_podcasts(self, query: str, **kwargs) -> Dict[str, Any]:
        endpoint = "search"
        params = {
            "q": query,
            "sort_by_date": kwargs.get("sort_by_date", 1),
            "type": kwargs.get("type", "podcast"),
            "offset": kwargs.get("offset", 0),
            "language": kwargs.get("language", "English"),
            "episode_count_min": kwargs.get("episode_count_min", 10), # From original script
            "region": kwargs.get("region", "us"), # Changed from US to us (lowercase)
            **{k: v for k, v in kwargs.items() if k in [
                'genre_ids', 'published_after', 'ocid', 'safe_mode', 'page_size' # Added page_size
            ]}
        }
        if kwargs.get('interviews_only') == 1: # From original script
             params['only_in'] = 'title,description'
        if 'page_size' not in params: # Ensure default page_size if not provided
            params['page_size'] = 10

        logger.info(f"Searching Listen Notes for query: '{query}' with params: {params}")
        try:
            return self._request("GET", endpoint, params=params)
        except APIClientError as e:
            logger.error(f"Listen Notes API search failed: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error in Listen Notes search: {e}")
            raise APIClientError(f"Unexpected error in Listen Notes search: {e}")

    def lookup_podcast_by_rss(self, rss_feed_url: str) -> Optional[Dict[str, Any]]:
        if not rss_feed_url: return None
        logger.info(f"Looking up ListenNotes by RSS (POST /podcasts): {rss_feed_url}")
        response_data = self._fetch_podcasts_batch(rsses=[rss_feed_url])
        if response_data and isinstance(response_data.get('podcasts'), list) and len(response_data['podcasts']) == 1:
            return response_data['podcasts'][0]
        logger.info(f"ListenNotes lookup_by_rss for {rss_feed_url} returned no unique result. Response: {response_data}")
        return None

    def lookup_podcast_by_itunes_id(self, itunes_id: int) -> Optional[Dict[str, Any]]:
        if not itunes_id: return None
        logger.info(f"Looking up ListenNotes by iTunes ID (POST /podcasts): {itunes_id}")
        response_data = self._fetch_podcasts_batch(itunes_ids=[itunes_id])
        if response_data and isinstance(response_data.get('podcasts'), list) and len(response_data['podcasts']) == 1:
            podcast_data = response_data['podcasts'][0]
            try:
                if int(podcast_data.get('itunes_id', -1)) == int(itunes_id):
                    return podcast_data
                logger.warning(f"ListenNotes lookup_by_itunes_id for {itunes_id} returned ID mismatch: {podcast_data.get('itunes_id')}")
            except (TypeError, ValueError):
                 logger.warning(f"Could not compare iTunes IDs for query {itunes_id}. Found: {podcast_data.get('itunes_id')}")
            return None
        logger.info(f"ListenNotes lookup_by_itunes_id for {itunes_id} returned no unique result. Response: {response_data}")
        return None

    def get_recommendations(self, podcast_id: str, safe_mode: int = 0) -> Optional[List[Dict[str, Any]]]:
        if not podcast_id: return None
        endpoint = f"podcasts/{podcast_id}/recommendations"
        params = {"safe_mode": str(safe_mode)} # API expects string for safe_mode
        logger.info(f"Fetching ListenNotes recommendations for {podcast_id} with safe_mode={safe_mode}")
        try:
            response_data = self._request("GET", endpoint, params=params)
            recommendations = response_data.get('recommendations')
            if isinstance(recommendations, list):
                return recommendations
            logger.warning(f"ListenNotes get_recommendations for {podcast_id} non-list/missing key. Response: {response_data}")
            return None
        except APIClientError as e:
            logger.error(f"ListenNotes get_recommendations for {podcast_id} failed: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error in ListenNotes get_recommendations for {podcast_id}: {e}")
            return None

# --- InstantlyAPI Client (remains largely the same as original, but can inherit from base_client if desired) ---
# For now, keeping it separate as its auth is different and methods are not podcast lookups.
INSTANTLY_API_KEY = os.getenv('INSTANTLY_API_KEY')
INSTANTLY_BASE_URL = "https://api.instantly.ai/api/v2"

class InstantlyAPI:
    def __init__(self):
        self.base_url = INSTANTLY_BASE_URL
        self.api_key = INSTANTLY_API_KEY
        self.session = requests.Session() # Use requests.Session for Instantly
        if self.api_key:
            self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})
        else:
            logger.error("INSTANTLY_API_KEY not set. InstantlyAPI calls will likely fail.")

    def _request_instantly(self, method: str, endpoint_suffix: str, **kwargs) -> requests.Response:
        """Internal request method for Instantly, using its own session and error handling."""
        url = f"{self.base_url}/{endpoint_suffix.lstrip('/')}"
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            response.raise_for_status() # Will raise HTTPError for 4xx/5xx
            return response
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"InstantlyAPI HTTP error: {http_err} for URL {url} - Response: {http_err.response.text}")
            raise APIClientError(f"InstantlyAPI HTTP error: {http_err}", status_code=http_err.response.status_code) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(f"InstantlyAPI Request error: {req_err} for URL {url}")
            raise APIClientError(f"InstantlyAPI Request error: {req_err}") from req_err

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
            logger.warning(f"InstantlyAPI list_campaigns failed (maybe auth issue?): {e}")
            return None # Return None if it fails, allows caller to check

    def list_emails(self, limit: int = 100, starting_after: Optional[str] = None) -> Optional[Dict[str, Any]]:
        params = {"limit": limit}
        if starting_after: params["starting_after"] = starting_after
        try:
            response = self._request_instantly("GET", "emails", params=params)
            return response.json()
        except APIClientError as e:
            logger.error(f"InstantlyAPI list_emails failed: {e}")
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
                logger.error(f"InstantlyAPI list_leads_from_campaign page fetch failed: {e}")
                break # Stop pagination on error
            except ValueError:
                 logger.error(f"InstantlyAPI list_leads_from_campaign JSON decode error. Response: {response.text if 'response' in locals() else 'N/A'}")
                 break

            leads_this_page = data.get("items", [])
            all_leads.extend(leads_this_page)
            next_starting_after = data.get("next_starting_after")
            if not next_starting_after or len(leads_this_page) < limit_per_page:
                break
            starting_after = next_starting_after
        return all_leads

# --- Example Usage (for testing external_api_service.py directly) ---
async def main_test_external_apis():
    logger.info("--- Testing External API Services ---")
    # Podscan Test
    try:
        logger.info("\n--- Testing PodscanAPIClient ---")
        podscan_client = PodscanAPIClient()
        ps_categories = podscan_client.get_categories()
        logger.info(f"Podscan Categories (first 5): {ps_categories[:5]}")
        ps_search = podscan_client.search_podcasts(query="tech startup", per_page=2)
        logger.info(f"Podscan Search ('tech startup', first 2): {ps_search.get('podcasts')}")
        if ps_search.get('podcasts') and len(ps_search['podcasts']) > 0:
            test_ps_id = ps_search['podcasts'][0].get('podcast_id')
            if test_ps_id:
                ps_episodes = podscan_client.get_podcast_episodes(test_ps_id, per_page=1)
                logger.info(f"Podscan Episodes for {test_ps_id} (first 1): {ps_episodes}")
                ps_by_rss = podscan_client.search_podcast_by_rss(ps_search['podcasts'][0].get('rss_url'))
                logger.info(f"Podscan by RSS for {ps_search['podcasts'][0].get('rss_url')}: {ps_by_rss}")
        test_itunes_id = 624693800 # Example iTunes ID
        ps_by_itunes = podscan_client.search_podcast_by_itunes_id(test_itunes_id)
        logger.info(f"Podscan by iTunes ID {test_itunes_id}: {ps_by_itunes}")

    except AuthenticationError as auth_err:
        logger.error(f"Podscan Auth Error: {auth_err}")    
    except APIClientError as api_err:
        logger.error(f"Podscan API Error: {api_err}")
    except Exception as e:
        logger.exception(f"Unexpected error during Podscan test: {e}")

    # ListenNotes Test
    try:
        logger.info("\n--- Testing ListenNotesAPIClient ---")
        listennotes_client = ListenNotesAPIClient()
        ln_search = listennotes_client.search_podcasts(query="python programming", genre_ids="133,100", page_size=2) # Tech & Business
        logger.info(f"ListenNotes Search ('python programming', first 2): {ln_search.get('results')}")
        if ln_search.get('results') and len(ln_search['results']) > 0:
            test_ln_id = ln_search['results'][0].get('id')
            if test_ln_id:
                ln_recommendations = listennotes_client.get_recommendations(test_ln_id)
                logger.info(f"ListenNotes Recommendations for {test_ln_id} (first 3): {ln_recommendations[:3] if ln_recommendations else 'None'}")
                ln_by_rss = listennotes_client.lookup_podcast_by_rss(ln_search['results'][0].get('rss'))
                logger.info(f"ListenNotes by RSS for {ln_search['results'][0].get('rss')}: {ln_by_rss}")
        test_ln_itunes_id = 1532112202 # Example: Lex Fridman Podcast iTunes ID
        ln_by_itunes = listennotes_client.lookup_podcast_by_itunes_id(test_ln_itunes_id)
        logger.info(f"ListenNotes by iTunes ID {test_ln_itunes_id}: {ln_by_itunes}")
        
    except AuthenticationError as auth_err:
        logger.error(f"ListenNotes Auth Error: {auth_err}")    
    except APIClientError as api_err:
        logger.error(f"ListenNotes API Error: {api_err}")
    except Exception as e:
        logger.exception(f"Unexpected error during ListenNotes test: {e}")

    # Instantly Test (remains synchronous for now)
    try:
        logger.info("\n--- Testing InstantlyAPI ---")
        instantly_service = InstantlyAPI()
        if instantly_service.api_key:
            campaigns_resp = instantly_service.list_campaigns()
            if campaigns_resp:
                logger.info(f"Instantly Campaigns (sample): {campaigns_resp.get('data', [])[:1]}")
            else:
                logger.warning("Could not list Instantly campaigns (check API key or service status).")
        else:
            logger.warning("InstantlyAPI key not set, skipping Instantly tests.")
    except APIClientError as api_err:
        logger.error(f"Instantly API Error: {api_err}")
    except Exception as e:
        logger.exception(f"Unexpected error during Instantly test: {e}")

if __name__ == "__main__":
    # If you need to run these tests standalone, ensure env vars are set.
    # Note: main_test_external_apis is now async if base_client becomes async.
    # For now, assuming base_client is synchronous and these tests run with asyncio.run for it.
    # If PodcastAPIClient._request becomes async, these test calls would need `await`.
    # For simplicity, keeping external_api_service tests synchronous for now
    # by not making main_test_external_apis async directly and calling sync methods.
    # This part is for direct testing of external_api_service.py, not used by batch fetcher directly.
    pass # To make main_test_external_apis callable if needed directly, but not run by default.
    # To test: python -m src.external_api_service (if you add a call to asyncio.run(main_test_external_apis()) here)