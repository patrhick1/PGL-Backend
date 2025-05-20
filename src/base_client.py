import abc
import requests
import time
import logging
from typing import Dict, Any, Optional

from .exceptions import (
    APIClientError, AuthenticationError, RateLimitError, APIRequestError, APIParsingError
)

logger = logging.getLogger(__name__)

class PodcastAPIClient(abc.ABC):
    """Abstract base class for podcast API clients."""

    DEFAULT_TIMEOUT = 10 # Default request timeout in seconds
    MAX_RETRIES = 3
    INITIAL_BACKOFF = 1 # Initial backoff delay in seconds

    def __init__(self, api_key: Optional[str] = None, base_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        if self.api_key:
            self._set_auth_header()

    @abc.abstractmethod
    def _set_auth_header(self):
        """Sets the necessary authentication headers for the specific API."""
        pass

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None, json: Optional[Dict] = None) -> Dict[str, Any]:
        """Makes an HTTP request with retries and error handling."""
        url = self.base_url.rstrip('/') + '/' + endpoint.lstrip('/')
        retries = 0
        backoff = self.INITIAL_BACKOFF

        while retries <= self.MAX_RETRIES:
            try:
                logger.debug(f"Making {method} request to {url} with params: {params}, data: {data}, json: {json}")
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json,
                    timeout=self.DEFAULT_TIMEOUT
                )

                # Handle specific HTTP errors
                if response.status_code == 401:
                    raise AuthenticationError(f"Authentication failed for {url}", status_code=401)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", backoff))
                    raise RateLimitError(f"Rate limit exceeded for {url}", status_code=429, retry_after=retry_after)
                if 400 <= response.status_code < 500:
                    raise APIRequestError(f"Client error {response.status_code} for {url}: {response.text}", status_code=response.status_code)
                if response.status_code >= 500:
                    # Retry on server errors
                    logger.warning(f"Server error {response.status_code} for {url}. Retrying in {backoff}s...")
                    time.sleep(backoff)
                    retries += 1
                    backoff *= 2 # Exponential backoff
                    continue

                # If status is OK (2xx)
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

                try:
                    json_response = response.json()
                    logger.debug(f"Request successful. Response from {url}: {json_response}")
                    return json_response
                except ValueError:
                     logger.error(f"Failed to parse JSON response from {url}. Response text: {response.text[:500]}...")
                     raise APIParsingError(f"Invalid JSON received from {url}")

            except requests.exceptions.Timeout:
                logger.warning(f"Request timed out for {url}. Retrying in {backoff}s...")
                time.sleep(backoff)
                retries += 1
                backoff *= 2
            except RateLimitError as e:
                logger.warning(f"Rate limit hit. Retrying after {e.retry_after} seconds...")
                time.sleep(e.retry_after)
                retries += 1 # Consuming a retry attempt after waiting
                # Reset backoff? Or keep increasing? Keep increasing for now.
                backoff *= 2
            except requests.exceptions.RequestException as e:
                # Catch other requests errors (ConnectionError, etc.)
                logger.error(f"Request failed for {url}: {e}. Retrying in {backoff}s...")
                time.sleep(backoff)
                retries += 1
                backoff *= 2
            except APIClientError: # Catch our custom errors that shouldn't be retried (Auth, Client errors)
                raise
            except Exception as e:
                # Catch unexpected errors
                logger.exception(f"An unexpected error occurred during request to {url}: {e}")
                raise APIClientError(f"Unexpected error during request: {e}")

        # If max retries exceeded
        logger.error(f"Max retries exceeded for request to {url}.")
        raise APIRequestError(f"Max retries exceeded for {url}")

    @abc.abstractmethod
    def search_podcasts(self, query: str, **kwargs) -> Dict[str, Any]:
        """Searches for podcasts based on a query string."""
        pass

    # Add other common methods if applicable (e.g., get_podcast_details) 