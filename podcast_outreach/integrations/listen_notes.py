# podcast_outreach/integrations/listen_notes.py

import os
import logging
import html
import requests
from typing import Dict, Any, Optional, List
import asyncio # Not strictly needed here unless base_client becomes async
import time # For potential delays if ever needed

# Assuming base_client.py and exceptions.py are in the same directory (src) (UPDATED IMPORTS)
from podcast_outreach.integrations.base_client import PodcastAPIClient 
from podcast_outreach.utils.exceptions import APIClientError, AuthenticationError, NotFoundError, RateLimitError

logger = logging.getLogger(__name__)

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
            "episode_count_min": kwargs.get("episode_count_min", 10), # Minimum episodes for quality podcasts
            "interviews_only": kwargs.get("interviews_only", 1), # Only podcasts with guest interviews
            "region": kwargs.get("region", "us"), # Changed from US to us (lowercase)
            **{k: v for k, v in kwargs.items() if k in [
                'genre_ids', 'published_after', 'ocid', 'safe_mode', 'page_size' # Added page_size
            ]}
        }
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

    def get_podcast_episodes(self, podcast_ln_id: str, sort: str = 'recent_first', next_episode_pub_date: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        """Fetches episodes for a given ListenNotes podcast ID.
        The free plan for ListenNotes GET /podcasts/{id} returns up to 10 latest episodes.
        Paid plans can use next_episode_pub_date for pagination.
        """
        if not podcast_ln_id:
            logger.warning("ListenNotes get_podcast_episodes: podcast_ln_id not provided.")
            return None
        
        endpoint = f"podcasts/{podcast_ln_id}"
        params = {"sort": sort}
        if next_episode_pub_date: # For pagination if ever needed beyond the default 10
            params["next_episode_pub_date"] = next_episode_pub_date

        logger.info(f"Fetching ListenNotes episodes for podcast ID: {podcast_ln_id} with params: {params}")
        try:
            response_data = self._request("GET", endpoint, params=params)
            # The 'episodes' list is directly under the podcast object in the response
            episodes = response_data.get('episodes')
            if isinstance(episodes, list):
                logger.info(f"Successfully fetched {len(episodes)} episodes for ListenNotes podcast {podcast_ln_id}.")
                return episodes
            else:
                logger.warning(f"ListenNotes get_podcast_episodes for {podcast_ln_id} did not return a list of episodes. Response: {response_data}")
                return None # Or an empty list: []
        except NotFoundError:
            logger.warning(f"ListenNotes podcast with ID {podcast_ln_id} not found when fetching episodes.")
            return None
        except APIClientError as e:
            logger.error(f"ListenNotes API error fetching episodes for {podcast_ln_id}: {e}")
            return None # Or raise, depending on desired error handling for individual fetches
        except Exception as e:
            logger.exception(f"Unexpected error fetching ListenNotes episodes for {podcast_ln_id}: {e}")
            return None
