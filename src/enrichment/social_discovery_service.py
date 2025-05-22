import os
import logging
import asyncio
import re
import json
from urllib.parse import urlparse
from typing import Optional, Dict, Any, List 

from apify_client import ApifyClient
from dotenv import load_dotenv
from pydantic import HttpUrl, ValidationError # For URL validation if used within methods

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

class SocialDiscoveryService:
    """Discovers and analyzes social media profiles using Apify."""

    def __init__(self, api_key: Optional[str] = None):
        """Initializes the Apify client.
        Args:
            api_key: The Apify API key. If None, loads from APIFY_API_KEY env var.
        """
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = os.getenv("APIFY_API_KEY")
        
        if not self.api_key:
            logger.error("APIFY_API_KEY not found. Social discovery service will not function.")
            # Raise an error or handle gracefully depending on how critical this service is at startup
            raise ValueError("APIFY_API_KEY must be set for SocialDiscoveryService.")
        
        try:
            self.client = ApifyClient(self.api_key)
            logger.info("SocialDiscoveryService: ApifyClient initialized successfully.")
        except Exception as e:
            logger.error(f"SocialDiscoveryService: Failed to initialize ApifyClient: {e}", exc_info=True)
            raise

    async def _run_actor_async(self, actor_id: str, run_input: Dict[str, Any], timeout_secs: int = 120) -> Optional[List[Dict[str, Any]]]:
        """Runs a specific Apify actor asynchronously and retrieves its dataset items."""
        logger.info(f"Running Apify actor: {actor_id} with input (keys): {list(run_input.keys())}")
        try:
            # Run the actor asynchronously
            actor_call = await asyncio.to_thread(
                self.client.actor(actor_id).call, 
                run_input=run_input,
                timeout_secs=timeout_secs # Add timeout to actor call
            )
            
            if not actor_call or not actor_call.get("defaultDatasetId"):
                logger.warning(f"Invalid response or missing dataset ID from actor {actor_id}. Run details: {actor_call}")
                return None

            logger.info(f"Actor {actor_id} run completed. Run ID: {actor_call.get('id')}, Dataset ID: {actor_call.get('defaultDatasetId')}. Fetching items...")
            dataset = self.client.dataset(actor_call["defaultDatasetId"])
            # dataset.list_items() is sync, run in thread
            # Consider potential for large datasets and pagination if actors return many items.
            # For profile scrapers, usually it's one item per profile, or a few related items.
            dataset_page = await asyncio.to_thread(dataset.list_items) # Default limit is 1000 items
            
            dataset_items = dataset_page.items if dataset_page else []
            
            logger.debug(
                f"Raw dataset items retrieved from actor {actor_id} (count={len(dataset_items)}). First item if any: {str(dataset_items[0])[:300] if dataset_items else 'N/A'}"
            )
            
            logger.info(f"Retrieved {len(dataset_items)} items from dataset for actor {actor_id}.")
            return dataset_items
        except Exception as e:
            logger.error(f"Apify actor {actor_id} async run failed: {e}", exc_info=True)
            return None

    def _normalize_url(self, url: Optional[str]) -> Optional[str]:
        """Normalizes a URL: HTTPS, removes www (unless critical), query params, fragments, trailing slashes, lowercase."""
        if not url or not isinstance(url, str):
            return None

        url = url.strip()
        if not url:
            return None
        
        if '://' not in url:
            url = "https://" + url
        elif url.startswith("http://"):
            url = "https://" + url[len("http://"):]

        try:
            parsed_url = urlparse(url)
            hostname = parsed_url.hostname
            if hostname and hostname.startswith("www."):
                # Keep www for LinkedIn, remove for most others for canonical form
                if "linkedin.com" not in hostname.lower():
                    new_hostname = hostname[4:]
                    url = url.replace(hostname, new_hostname, 1)
            
            # Re-parse after potential hostname change for accurate path/query stripping
            parsed_url = urlparse(url)
            # Keep path, remove query and fragment
            url = parsed_url._replace(query='', fragment='').geturl()
            
            if url.endswith("/") and url.count("/") > 2:
                url = url.rstrip("/")
            
            return url.lower()
        except Exception as e:
            logger.warning(f"Could not fully normalize URL '{url}': {e}. Returning as is after basic https forcing.")
            # Fallback to a simpler normalization if parsing complex URLs fails
            if not url.startswith("https://"):
                 if url.startswith("http://"):
                      url = "https://" + url[len("http://"):]
                 else:
                      url = "https://" + url # Default if no scheme
            return url.split("?")[0].split("#")[0].rstrip("/").lower()

    def _extract_username_from_url(self, url: Optional[str], platform_pattern: re.Pattern) -> Optional[str]:
        """General username extractor given a platform-specific regex pattern."""
        if not url: return None
        normalized_url = self._normalize_url(url)
        if not normalized_url: return None
        
        match = platform_pattern.search(normalized_url)
        if match:
            username = match.group(1)
            # Avoid capturing common path segments like 'p', 'reels', 'videos' as usernames
            if username.lower() in ['p', 'reels', 'videos', 'channel', 'user', 'explore', 'stories', 'post', 'posts']:
                logger.debug(f"Extracted segment '{username}' from '{normalized_url}' resembles a path, not a username.")
                return None
            # Basic check for valid username characters (alphanumeric + underscore + dot for some platforms)
            if re.match(r'^[a-zA-Z0-9_.-]+$', username):
                return username
            logger.debug(f"Extracted segment '{username}' from '{normalized_url}' contains invalid characters.")
        return None

    # Platform-specific regex patterns (adjust as needed for robustness)
    _twitter_username_pattern = re.compile(r"twitter\.com/([a-zA-Z0-9_]{1,15})")
    _linkedin_public_profile_pattern = re.compile(r"linkedin\.com/in/([a-zA-Z0-9_-]+)") # Public profiles
    _linkedin_company_pattern = re.compile(r"linkedin\.com/company/([a-zA-Z0-9_-]+)") # Company pages
    _instagram_username_pattern = re.compile(r"instagram\.com/([a-zA-Z0-9_.]+)")
    _tiktok_username_pattern = re.compile(r"tiktok\.com/@([a-zA-Z0-9_.]+)")
    _facebook_username_pattern = re.compile(r"facebook\.com/(?:people/)?([a-zA-Z0-9_.-]+)(?:/)?")
    _youtube_channel_pattern = re.compile(r"youtube\.com/(?:channel/|c/|@)?([a-zA-Z0-9_.-]+)")

    def _get_username_extractor(self, platform: str) -> Optional[Any]: # re.Pattern not available for type hint here
        if platform == 'twitter': return self._twitter_username_pattern
        if platform == 'linkedin_profile': return self._linkedin_public_profile_pattern
        if platform == 'linkedin_company': return self._linkedin_company_pattern
        if platform == 'instagram': return self._instagram_username_pattern
        if platform == 'tiktok': return self._tiktok_username_pattern
        if platform == 'facebook': return self._facebook_username_pattern
        if platform == 'youtube': return self._youtube_channel_pattern
        return None

    async def _fetch_social_data_batch(self, urls: List[str], actor_id: str, input_url_field: str, result_mapper_func, actor_input_modifier_func=None) -> Dict[str, Optional[Dict[str, Any]]]:
        """Generic helper to fetch data for a list of URLs using a specific Apify actor."""
        results_by_norm_url: Dict[str, Optional[Dict[str, Any]]] = {}
        if not urls:
            return results_by_norm_url

        # Normalize all input URLs first and create a mapping back to original
        original_to_norm_map: Dict[str, str] = {url: self._normalize_url(url) for url in urls if url}
        norm_to_original_map: Dict[str, str] = {v: k for k, v in original_to_norm_map.items() if v} # Filter out None normalized URLs
        unique_norm_urls = sorted(list(norm_to_original_map.keys()))

        if not unique_norm_urls:
            logger.info(f"No valid, unique, normalized URLs to process for actor {actor_id}.")
            return {orig_url: None for orig_url in urls} # Return None for all original inputs

        actor_input_params = {input_url_field: unique_norm_urls}
        if actor_input_modifier_func:
            actor_input_params = actor_input_modifier_func(actor_input_params, unique_norm_urls)

        actor_results = await self._run_actor_async(actor_id, actor_input_params)

        if actor_results and isinstance(actor_results, list):
            for item in actor_results:
                if not isinstance(item, dict):
                    logger.warning(f"Skipping non-dict item from actor {actor_id}: {item}")
                    continue
                
                # Map result back to one of the normalized input URLs
                # This requires the actor result to contain a field that matches or can be normalized to our input URLs
                # This logic might need to be customized per actor if their output URL field differs.
                actor_item_url_field = item.get('url') or item.get('profileUrl') or item.get('inputUrl') # Common actor output fields for URL
                
                normalized_actor_item_url = self._normalize_url(actor_item_url_field)
                
                if normalized_actor_item_url and normalized_actor_item_url in unique_norm_urls:
                    if results_by_norm_url.get(normalized_actor_item_url) is None: # Process each normalized URL once
                        mapped_data = result_mapper_func(item)
                        results_by_norm_url[normalized_actor_item_url] = mapped_data
                        logger.debug(f"Mapped Apify result for {normalized_actor_item_url} from actor {actor_id}. Data: {str(mapped_data)[:100]}...")
                    else:
                         logger.debug(f"Already mapped data for {normalized_actor_item_url} from actor {actor_id}. Skipping duplicate item.")
                else:
                    logger.warning(f"Could not map item from actor {actor_id} back to an input URL. Item URL: '{actor_item_url_field}', Normalized: '{normalized_actor_item_url}'. Item keys: {list(item.keys())}")
        
        # Final map from original input URL to result
        final_results: Dict[str, Optional[Dict[str, Any]]] = {}
        for original_url in urls:
            norm_url = original_to_norm_map.get(original_url)
            if norm_url:
                final_results[original_url] = results_by_norm_url.get(norm_url)
            else:
                final_results[original_url] = None # If original URL couldn't be normalized
        
        return final_results

    def _map_linkedin_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'profile_url': self._normalize_url(item.get('inputUrl') or item.get('profileUrl')),
            'name': item.get('fullName') or item.get('name'),
            'headline': item.get('headline') or item.get('occupation'),
            'summary': item.get('summary'),
            'followers_count': item.get('followersCount'), # Typically for company/influencer pages
            'connections_count': item.get('connectionsCount'), # For personal profiles
            'location': item.get('location'),
            'company': item.get('company') # From company scraper part if used
        }

    def _twitter_input_modifier(self, current_input, urls_for_run):
        # Specific modifications for apidojo/twitter-user-scraper
        current_input["getFollowers"] = True # Example: always get followers
        current_input["getFollowing"] = True
        current_input["maxItems"] = len(urls_for_run)
        # Padding for twitter actor if needed (from original example)
        # This is a simplified version; original logic was more complex
        MIN_URLS_FOR_ACTOR = 5 
        if len(urls_for_run) < MIN_URLS_FOR_ACTOR:
            padding_needed = MIN_URLS_FOR_ACTOR - len(urls_for_run)
            # Add some generic, well-known Twitter profiles for padding if needed
            # Ensure these are normalized
            padding_profiles = [self._normalize_url(url) for url in [
                "https://twitter.com/nasa", "https://twitter.com/apify",
                "https://twitter.com/google", "https://twitter.com/github", "https://twitter.com/who"
            ] if self._normalize_url(url)]
            
            additional_padding = []
            for pad_url in padding_profiles:
                if len(additional_padding) >= padding_needed: break
                if pad_url not in urls_for_run: additional_padding.append(pad_url)
            
            current_input[current_input.get("input_url_field", "startUrls")].extend(additional_padding)
            logger.info(f"Padded Twitter URLs to {len(current_input[current_input.get("input_url_field", "startUrls")])} for actor requirements.")
        return current_input
        
    def _map_twitter_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        # Map fields from apidojo/twitter-user-scraper
        return {
            'profile_url': self._normalize_url(item.get('url') or item.get('profile_url') or item.get('twitterUrl')),
            'username': item.get('username') or item.get('screenName') or item.get('userName'),
            'name': item.get('name'),
            'description': item.get('description') or item.get('rawDescription'),
            'followers_count': self._safe_int_cast(item.get('followers_count') or item.get('followers')),
            'following_count': self._safe_int_cast(item.get('following_count') or item.get('following')),
            'is_verified': item.get('isVerified') or item.get('verified') or item.get('isBlueVerified'),
            'location': item.get('location'),
            'profile_picture_url': self._normalize_url(item.get('profile_image_url_https') or item.get('profilePicture')),
            'tweets_count': self._safe_int_cast(item.get('statuses_count') or item.get('tweetCount'))
        }

    def _instagram_input_modifier(self, current_input, urls_for_run):
        # apify/instagram-profile-scraper expects usernames, not full URLs
        usernames = []
        for url_in in urls_for_run:
            username = self._extract_username_from_url(url_in, self._instagram_username_pattern)
            if username: usernames.append(username)
            else: logger.warning(f"Could not extract Instagram username from {url_in} for actor input.")
        current_input["usernames"] = list(set(usernames)) # Use unique usernames
        current_input.pop(current_input.get("input_url_field", "directUrls"), None) # Remove the URL field as actor uses usernames
        return current_input

    def _map_instagram_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        # Map fields from apify/instagram-profile-scraper
        username = item.get('username')
        profile_url = f"https://www.instagram.com/{username}/" if username else None
        return {
            'profile_url': self._normalize_url(profile_url or item.get('profileUrl')),
            'username': username,
            'name': item.get('fullName'),
            'description': item.get('biography'),
            'followers_count': self._safe_int_cast(item.get('followersCount')),
            'following_count': self._safe_int_cast(item.get('followingCount')),
            'is_verified': item.get('isVerified'),
            'profile_picture_url': self._normalize_url(item.get('profilePicUrlHD') or item.get('profilePicUrl')),
            'posts_count': self._safe_int_cast(item.get('postsCount'))
        }

    def _tiktok_input_modifier(self, current_input, urls_for_run):
        # apidojo/tiktok-scraper takes startUrls but seems to work best one by one for profiles for stable data.
        # This service will call it one by one if this modifier isn't robust enough for batching profiles.
        # For now, let's assume batching works if the actor supports it; if not, this needs a loop in the calling function.
        current_input["maxItemsPerQuery"] = 1 # Try to get one main profile data per URL
        current_input["shouldDownloadCovers"] = False
        current_input["shouldDownloadSlideshowImages"] = False
        current_input["shouldDownloadVideos"] = False
        return current_input
        
    def _map_tiktok_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        # Extracts profile info from apidojo/tiktok-scraper results (which are often video-centric)
        # The `authorMeta` or `channel` (if present) sub-object usually has profile details.
        author_meta = item.get('authorMeta') or item.get('author') or item.get('channel') or {}
        username = author_meta.get('name') or author_meta.get('nickName') or author_meta.get('uniqueId')
        profile_url = f"https://www.tiktok.com/@{username}" if username else self._normalize_url(author_meta.get('webUrl') or item.get('webVideoUrl'))
        
        # Fallback if username is still not found from authorMeta (e.g. if item is a direct profile item)
        if not username and item.get('uniqueId'): # From a direct profile item structure
            username = item.get('uniqueId')
            profile_url = f"https://www.tiktok.com/@{username}"

        return {
            'profile_url': profile_url,
            'username': username,
            'name': author_meta.get('nickName', item.get('nickname')), # `item.get('nickname')` if direct profile structure
            'description': author_meta.get('signature', item.get('signature')), # `item.get('signature')` if direct profile structure
            'followers_count': self._safe_int_cast(author_meta.get('fans', item.get('followerCount'))), # fans or followerCount
            'following_count': self._safe_int_cast(author_meta.get('following', item.get('followingCount'))),
            'likes_count': self._safe_int_cast(author_meta.get('heart', item.get('heartCount'))), # total hearts/likes
            'is_verified': author_meta.get('verified', item.get('verified')),
            'profile_picture_url': self._normalize_url(author_meta.get('avatar') or item.get('avatarLarger') or item.get('avatarThumb')),
            'videos_count': self._safe_int_cast(author_meta.get('video', item.get('videoCount')))
        }

    async def get_linkedin_data_for_urls(self, profile_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Extracts LinkedIn profile info for a batch of URLs."""
        # supreme_coder/linkedin-profile-scraper ; input field "urls"
        return await self._fetch_social_data_batch(profile_urls, 'kamilracek/linkedin-profile-scraper', 'startUrls', self._map_linkedin_result) # Changed actor

    async def get_twitter_data_for_urls(self, twitter_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Fetches Twitter user data for a list of Twitter URLs."""
        # apidojo/twitter-user-scraper ; input field "startUrls"
        return await self._fetch_social_data_batch(twitter_urls, 'apidojo/twitter-user-scraper', 'startUrls', self._map_twitter_result, self._twitter_input_modifier)

    async def get_instagram_data_for_urls(self, instagram_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Fetches Instagram profile data for a list of Instagram URLs."""
        # apify/instagram-profile-scraper ; input field "usernames"
        return await self._fetch_social_data_batch(instagram_urls, 'apify/instagram-profile-scraper', 'directUrls', self._map_instagram_result, self._instagram_input_modifier)

    async def get_tiktok_data_for_urls(self, tiktok_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Fetches TikTok profile data for a list of TikTok profile URLs."""
        # Uses apidojo/tiktok-scraper. Input: "startUrls". May require one URL at a time for profiles.
        # This generic batcher might not be ideal if actor needs single URL runs for profiles.
        # If issues, revert to a loop calling _run_actor_async for each URL individually for TikTok.
        logger.info("Fetching TikTok data. Note: apidojo/tiktok-scraper results are often video-centric; profile data is extracted from authorMeta.")
        return await self._fetch_social_data_batch(tiktok_urls, 'tensfer/tiktok-profile-scraper', 'profileURLs', self._map_tiktok_result) # Changed actor

    # Placeholder for Facebook - Apify actors for Facebook are complex due to login requirements
    async def get_facebook_data_for_urls(self, facebook_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        logger.warning("Facebook scraping is not reliably implemented due to Apify actor complexities and login requirements. Returning empty results.")
        return {url: None for url in facebook_urls}

    # Placeholder for YouTube - Actor would be something like 'apify/youtube-scraper'
    async def get_youtube_data_for_urls(self, youtube_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        # Example actor: 'kAirAমাকেটের/youtube-channel-scraper' (fictional or find a real one)
        # Input field might be 'channels' or 'channelUrls'
        # The mapper would extract subscriber_count, video_count, channel_name, etc.
        logger.warning("YouTube scraping using a generic actor is not fully implemented. Returning empty results.")
        # Real implementation would call _fetch_social_data_batch with correct actor and mapper
        return {url: None for url in youtube_urls}

    def _safe_int_cast(self, value: Any) -> Optional[int]:
        """Safely casts a value to an integer, returning None on failure."""
        if value is None: return None
        try: return int(value)
        except (ValueError, TypeError): return None

# Example Usage
if __name__ == "__main__":
    async def main_test():
        # Ensure APIFY_API_KEY is in your .env file
        if not os.getenv("APIFY_API_KEY"):
            print("Error: APIFY_API_KEY not found. Please set it in .env")
            return
        try:
            sds = SocialDiscoveryService()
            
            test_linkedin_urls = ["https://www.linkedin.com/in/williamhgates/", "https://www.linkedin.com/company/microsoft/"]
            print(f"\n--- Testing LinkedIn URLs: {test_linkedin_urls} ---")
            linkedin_results = await sds.get_linkedin_data_for_urls(test_linkedin_urls)
            print(json.dumps(linkedin_results, indent=2))

            test_twitter_urls = ["https://twitter.com/BillGates", "https://x.com/elonmusk/", "https://twitter.com/nonexistentuser123xyzabc"]
            print(f"\n--- Testing Twitter URLs: {test_twitter_urls} ---")
            twitter_results = await sds.get_twitter_data_for_urls(test_twitter_urls)
            print(json.dumps(twitter_results, indent=2))

            test_instagram_urls = ["https://www.instagram.com/nasa/", "https://www.instagram.com/cristiano/"]
            print(f"\n--- Testing Instagram URLs: {test_instagram_urls} ---")
            instagram_results = await sds.get_instagram_data_for_urls(test_instagram_urls)
            print(json.dumps(instagram_results, indent=2))
            
            test_tiktok_urls = ["https://www.tiktok.com/@zachking", "https://www.tiktok.com/@therock"]
            print(f"\n--- Testing TikTok URLs: {test_tiktok_urls} ---")
            tiktok_results = await sds.get_tiktok_data_for_urls(test_tiktok_urls)
            print(json.dumps(tiktok_results, indent=2))

        except ValueError as ve:
            print(f"Setup Error: {ve}")
        except Exception as e:
            print(f"An error occurred: {e}", exc_info=True)

    asyncio.run(main_test()) 