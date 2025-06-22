# podcast_outreach/integrations/podscan.py

import os
import logging
import requests
from typing import Dict, Any, Optional, List

# Assuming base_client.py and exceptions.py are in the same directory (src) (UPDATED IMPORTS)
from podcast_outreach.integrations.base_client import PodcastAPIClient 
from podcast_outreach.utils.exceptions import APIClientError, AuthenticationError, NotFoundError

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
            'min_episode_count': kwargs.get('min_episode_count', 10), # Minimum episodes for quality podcasts
            'has_guests': kwargs.get('has_guests', True), # Only podcasts with guest interviews
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
                    logger.warning(f"Podscan iTunes ID search for {itunes_id} returned ID mismatch: {podcast_data.get('podcast_itunes_id')}")
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
