# podcast_outreach/services/enrichment/social_scraper.py

import os
import logging
import asyncio
from apify_client import ApifyClient
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List, Set
from urllib.parse import urlparse
import re
import json

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class SocialDiscoveryService:
    """Discovers and analyzes social media profiles using Apify."""

    def __init__(self, api_key: Optional[str] = None):
        """Initializes the Apify client."""
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = os.getenv("APIFY_API_KEY")
        
        if not self.api_key:
            logger.error("APIFY_API_KEY not found. Social discovery service will not function.")
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
            actor_call = await asyncio.to_thread(
                self.client.actor(actor_id).call, 
                run_input=run_input,
                timeout_secs=timeout_secs
            )
            
            if not actor_call or not actor_call.get("defaultDatasetId"):
                logger.warning(f"Invalid response or missing dataset ID from actor {actor_id}. Run details: {actor_call}")
                return None

            logger.info(f"Actor {actor_id} run completed. Run ID: {actor_call.get('id')}, Dataset ID: {actor_call.get('defaultDatasetId')}. Fetching items...")
            dataset = self.client.dataset(actor_call["defaultDatasetId"])
            dataset_page = await asyncio.to_thread(dataset.list_items)
            dataset_items = dataset_page.items if dataset_page else []
            
            # Enhanced debug logging for the first raw item
            if dataset_items and logger.isEnabledFor(logging.DEBUG):
                try:
                    first_item_json = json.dumps(dataset_items[0], indent=2, default=str)
                    logger.debug(
                        f"Raw dataset items retrieved from actor {actor_id} (count={len(dataset_items)}). Full structure of first item:\n{first_item_json}"
                    )
                except Exception as e_json:
                    logger.debug(
                        f"Raw dataset items retrieved from actor {actor_id} (count={len(dataset_items)}). First item (non-JSON or serialization error: {e_json}): {str(dataset_items[0])[:500]}"
                    )
            elif logger.isEnabledFor(logging.DEBUG):
                 logger.debug(f"No dataset items retrieved from actor {actor_id}.")
            
            logger.info(f"Retrieved {len(dataset_items)} items from dataset for actor {actor_id}.")
            return dataset_items
        except Exception as e:
            logger.error(f"Apify actor {actor_id} async run failed: {e}", exc_info=True)
            return None

    def _normalize_url(self, url: Optional[str]) -> Optional[str]:
        """Normalizes a URL: forces HTTPS, removes www. (unless critical like www.linkedin.com), removes query params, fragments, and trailing slashes."""
        if not url or not isinstance(url, str):
            return url
        url = url.strip()
        if not url:
            return None
        
        if '://' not in url:
            url = "https://" + url
        elif url.startswith("http://"):
            url = "https://" + url[len("http://"):]

        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if hostname and hostname.startswith("www."):
                if "linkedin.com" not in hostname.lower():
                    new_hostname = hostname[4:]
                    url = url.replace(hostname, new_hostname, 1)
            
            parsed = urlparse(url)
            url = parsed._replace(query='', fragment='').geturl()
            
            if url.endswith("/") and url.count("/") > 2:
                url = url.rstrip("/")
            return url.lower()
        except Exception as e:
            logger.warning(f"Could not fully parse URL '{url}' during normalization: {e}. Applying basic normalization.")
            url = url.split("?")[0].split("#")[0]
            if url.endswith("/") and url.count("/") > 2:
                url = url.rstrip("/")
            return url.lower()

    def _extract_username_from_twitter_url(self, url: str) -> Optional[str]:
        """Extracts the username from a Twitter/X URL, assuming URL might need some normalization first."""
        if not isinstance(url, str): return None
        # Apply a less aggressive normalization for username extraction, mainly ensuring domain consistency
        temp_url = url.strip().lower()
        if '://' not in temp_url:
            temp_url = "https://" + temp_url
        temp_url = re.sub(r"https://(?:www\.)?x\.com/", "https://twitter.com/", temp_url, flags=re.IGNORECASE)
        temp_url = re.sub(r"https://(?:www\.)?twitter\.com/", "https://twitter.com/", temp_url, flags=re.IGNORECASE)
        
        try:
            parsed_url = urlparse(temp_url)
            if parsed_url.netloc == 'twitter.com':
                path_parts = parsed_url.path.strip('/').split('/')
                if path_parts and path_parts[0] and re.match(r'^[A-Za-z0-9_]{1,15}', path_parts[0]):
                    # Avoid known non-username paths if they appear as first part
                    if path_parts[0].lower() not in ['i', 'intent', 'search', 'home', 'explore', 'notifications', 'messages', 'settings', 'compose']:
                        return path_parts[0]
        except Exception as e:
            logger.warning(f"Could not parse username from Twitter URL '{url}' (temp_url: '{temp_url}'): {e}")
        return None

    def _canonicalize_twitter_url(self, url: str) -> str:
        """Returns a canonical https://twitter.com/<username> form."""
        if not isinstance(url, str) or not url: return url 
        username = self._extract_username_from_twitter_url(url)
        if username:
            return f"https://twitter.com/{username}".lower()
        logger.warning(f"Could not derive canonical Twitter URL for: {url}. Returning normalized version.")
        return self._normalize_url(url) or url # Fallback to normalized original if username extraction fails

    def _extract_username_from_linkedin_url(self, url: str) -> Optional[str]:
        if not url: return None
        normalized_url = self._normalize_url(url)
        if not normalized_url: return None
        match = re.search(r"linkedin\.com/in/([a-zA-Z0-9_-]+)", normalized_url)
        return match.group(1) if match else None

    def _extract_vanity_from_linkedin_company_url(self, url: str) -> Optional[str]:
        if not url: return None
        normalized_url = self._normalize_url(url)
        if not normalized_url: return None
        match = re.search(r"linkedin\.com/company/([a-zA-Z0-9_-]+)", normalized_url)
        return match.group(1) if match else None

    def _extract_username_from_instagram_url(self, url: str) -> Optional[str]:
        if not url: return None
        normalized_url = self._normalize_url(url)
        if not normalized_url: return None
        match = re.search(r"instagram\.com/([a-zA-Z0-9_.]+)/?", normalized_url)
        if match:
            username = match.group(1)
            if username.lower() not in ['p', 'reels', 'tv', 'explore', 'accounts', 'stories']:
                return username
        return None

    def _extract_username_from_tiktok_url(self, url: str) -> Optional[str]:
        if not url: return None
        normalized_url = self._normalize_url(url)
        if not normalized_url: return None
        match = re.search(r"tiktok\.com/@([a-zA-Z0-9_.]+)", normalized_url)
        return match.group(1) if match else None

    def _map_linkedin_profile_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Maps fields from supreme_coder/linkedin-profile-scraper results."""
        return {
            'profile_url': self._normalize_url(item.get('inputUrl') or item.get('url')),
            'headline': item.get('headline') or item.get('occupation'),
            'summary': item.get('summary'),
            'followers_count': self._safe_int_cast(item.get('followersCount')), # May not be present for personal profiles
            'connections_count': self._safe_int_cast(item.get('connectionsCount'))
        }

    def _map_twitter_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'profile_url': self._canonicalize_twitter_url(item.get('url') or item.get('profile_url') or item.get('twitterUrl')),
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

    def _map_instagram_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        username = item.get('username')
        profile_url = f"https://www.instagram.com/{username}/" if username else self._normalize_url(item.get('profileUrl'))
        return {
            'profile_url': profile_url,
            'username': username,
            'name': item.get('fullName'),
            'description': item.get('biography'),
            'followers_count': self._safe_int_cast(item.get('followersCount')),
            'following_count': self._safe_int_cast(item.get('followingCount')),
            'is_verified': item.get('isVerified'),
            'profile_picture_url': self._normalize_url(item.get('profilePicUrlHD') or item.get('profilePicUrl')),
            'posts_count': self._safe_int_cast(item.get('postsCount'))
        }

    def _map_tiktok_result(self, item: Dict[str, Any]) -> Dict[str, Any]:
        # Handle apidojo/tiktok-scraper format (flattened with dot notation)
        if 'channel.username' in item:
            username = item.get('channel.username')
            profile_url = item.get('channel.url') or (f"https://www.tiktok.com/@{username}" if username else None)
            name = item.get('channel.name')
            followers_count = self._safe_int_cast(item.get('channel.followers'))
            following_count = self._safe_int_cast(item.get('channel.following'))
            videos_count = self._safe_int_cast(item.get('channel.videos'))
            is_verified = item.get('channel.verified')
            profile_picture_url = self._normalize_url(item.get('channel.avatar'))
            
            return {
                'profile_url': profile_url,
                'username': username,
                'name': name,
                'description': None,  # Not available in this format
                'followers_count': followers_count,
                'following_count': following_count,
                'likes_count': None,  # Not available in channel data
                'is_verified': is_verified,
                'profile_picture_url': profile_picture_url,
                'videos_count': videos_count
            }
        
        # Handle legacy format (nested objects)
        author_meta = item.get('authorMeta') or item.get('author') or item.get('channel') or item.get('user') or {}
        username = author_meta.get('name') or author_meta.get('nickName') or author_meta.get('uniqueId') or item.get('unique_id')
        profile_url = f"https://www.tiktok.com/@{username}" if username else self._normalize_url(author_meta.get('webUrl') or item.get('webVideoUrl') or item.get('url'))
        
        if not username and item.get('uniqueId'): # Fallback if directly a profile item
            username = item.get('uniqueId')
            profile_url = f"https://www.tiktok.com/@{username}"
        elif not username and item.get('author') and isinstance(item.get('author'), dict): # Another common pattern
             username = item['author'].get('uniqueId')
             if username: profile_url = f"https://www.tiktok.com/@{username}"

        return {
            'profile_url': profile_url,
            'username': username,
            'name': author_meta.get('nickName', item.get('nickname', item.get('name'))),
            'description': author_meta.get('signature', item.get('signature')),
            'followers_count': self._safe_int_cast(author_meta.get('fans', item.get('followerCount', item.get('follower_count')))),
            'following_count': self._safe_int_cast(author_meta.get('following', item.get('followingCount', item.get('following_count')))),
            'likes_count': self._safe_int_cast(author_meta.get('heart', item.get('heartCount', item.get('like_count')))),
            'is_verified': author_meta.get('verified', item.get('verified')),
            'profile_picture_url': self._normalize_url(author_meta.get('avatar') or item.get('avatarLarger') or item.get('avatarThumb')),
            'videos_count': self._safe_int_cast(author_meta.get('video', item.get('videoCount', item.get('video_count'))))
        }

    async def _fetch_social_data_batch_generic(
        self, 
        urls: List[str], 
        actor_id: str, 
        input_config: Dict[str, Any], # Actor-specific input structure beyond URLs
        result_mapper_func,
        actor_item_url_key_candidates: List[str] = ['url', 'profileUrl', 'inputUrl'] 
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        results_by_norm_url: Dict[str, Optional[Dict[str, Any]]] = {}
        if not urls: return results_by_norm_url

        # Map original URLs to normalized versions for internal processing and result mapping
        original_to_norm_map: Dict[str, Optional[str]] = {url: self._normalize_url(url) for url in urls if url}
        # Create a reverse map from normalized URL back to the first original URL that produced it
        # This handles cases where multiple original URLs might normalize to the same canonical form.
        norm_to_first_original_map: Dict[str, str] = {}
        unique_norm_urls_for_run = []
        for original_url, norm_url in original_to_norm_map.items():
            if norm_url:
                if norm_url not in norm_to_first_original_map: # Keep track of which normalized URLs we are running
                    norm_to_first_original_map[norm_url] = original_url
                    unique_norm_urls_for_run.append(norm_url)
        
        if not unique_norm_urls_for_run:
            logger.info(f"No valid, unique, normalized URLs to process for actor {actor_id}.")
            return {orig_url: None for orig_url in urls} # Return None for all original inputs

        run_input = input_config.copy() # run_input is the correctly structured input from the calling function

        actor_results_list = await self._run_actor_async(actor_id, run_input)
        
        if actor_results_list and isinstance(actor_results_list, list):
            for item in actor_results_list:
                if not isinstance(item, dict):
                    logger.warning(f"Skipping non-dict item from actor {actor_id}: {item}")
                    continue
                
                actor_item_url_value = None
                for key_candidate in actor_item_url_key_candidates:
                    val = item.get(key_candidate)
                    if isinstance(val, str) and val.strip(): # Ensure it's a non-empty string
                        actor_item_url_value = val
                        break
                
                normalized_actor_item_url = self._normalize_url(actor_item_url_value)

                if normalized_actor_item_url and normalized_actor_item_url in norm_to_first_original_map:
                    # Use the first original URL that mapped to this normalized URL
                    # This is to handle if multiple input URLs normalize to the same thing
                    key_for_results = norm_to_first_original_map[normalized_actor_item_url]
                    if results_by_norm_url.get(key_for_results) is None: 
                        mapped_data = result_mapper_func(item)
                        results_by_norm_url[key_for_results] = mapped_data
        
        final_results: Dict[str, Optional[Dict[str, Any]]] = {}
        for original_url in urls: # Iterate through original URLs provided by the user
            norm_url = original_to_norm_map.get(original_url)
            # Find the first original URL that maps to this norm_url to retrieve the result
            result_key = norm_to_first_original_map.get(norm_url) if norm_url else None
            final_results[original_url] = results_by_norm_url.get(result_key) if result_key else None
        
        return final_results

    async def get_linkedin_data_for_urls(self, profile_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not profile_urls: return {}
        valid_urls = list(set(filter(lambda u: isinstance(u, str) and u.startswith('http'), profile_urls)))
        if not valid_urls: return {url: None for url in profile_urls}
        
        run_input_urls = [{ "url": url } for url in valid_urls] # Actor expects list of dicts
        actor_input = {"urls": run_input_urls, "findContacts": False, "scrapeCompany": False} # Match user-provided script
        
        # Using the actor ID from the user's script
        return await self._fetch_social_data_batch_generic(
            profile_urls, # Pass original urls for final mapping
            'supreme_coder/linkedin-profile-scraper', 
            actor_input, # Pass the fully structured input here
            self._map_linkedin_profile_result,
            actor_item_url_key_candidates=['inputUrl', 'url'] # 'inputUrl' is often in results
        )

    async def get_twitter_data_for_urls(self, twitter_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not self.client: return {url: None for url in twitter_urls}
        if not twitter_urls: return {}

        # Map original URLs to their canonical versions, and canonical back to one original
        original_to_canonical_map: Dict[str, str] = {}
        canonical_to_first_original_map: Dict[str, str] = {}
        urls_for_actor_run_set = set()

        for url in twitter_urls:
            if not url or not isinstance(url, str): continue
            cano_url = self._canonicalize_twitter_url(url)
            if cano_url:
                original_to_canonical_map[url] = cano_url
                if cano_url not in canonical_to_first_original_map:
                    canonical_to_first_original_map[cano_url] = url
                    urls_for_actor_run_set.add(cano_url)
        
        urls_for_actor_run = sorted(list(urls_for_actor_run_set))
        if not urls_for_actor_run: return {orig: None for orig in twitter_urls}

        # Padding logic from user's code
        padding_profiles = [self._canonicalize_twitter_url(url) for url in ["https://twitter.com/nasa", "https://twitter.com/bbcworld", "https://twitter.com/github", "https://twitter.com/teslamotors", "https://twitter.com/apify"]] 
        MIN_URLS = 5
        actor_run_urls_with_padding = list(urls_for_actor_run)
        if len(actor_run_urls_with_padding) < MIN_URLS:
            padding_to_add = [p for p in padding_profiles if p not in actor_run_urls_with_padding][:MIN_URLS - len(actor_run_urls_with_padding)]
            actor_run_urls_with_padding.extend(padding_to_add)
        
        actor_input = {"startUrls": actor_run_urls_with_padding, "getFollowers": True, "getFollowing": False, "maxItems": len(actor_run_urls_with_padding)}
        actor_items = await self._run_actor_async("apidojo/twitter-user-scraper", actor_input)

        results_by_canonical_url: Dict[str, Optional[Dict[str, Any]]] = {}
        if actor_items:
            for item in actor_items:
                item_url_canonical = self._canonicalize_twitter_url(item.get('url') or item.get('profile_url') or item.get('twitterUrl'))
                if item_url_canonical in canonical_to_first_original_map: # Only process if it was one of our original canonical URLs
                    if results_by_canonical_url.get(item_url_canonical) is None:
                         results_by_canonical_url[item_url_canonical] = self._map_twitter_result(item)
        
        final_results = {}
        for original_url, canonical_url in original_to_canonical_map.items():
            final_results[original_url] = results_by_canonical_url.get(canonical_url)
        return final_results

    async def get_instagram_data_for_urls(self, instagram_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        if not instagram_urls: return {}
        unique_normalized_urls = {self._normalize_url(url):url for url in instagram_urls if url and isinstance(url, str)}
        if not unique_normalized_urls: return {orig:None for orig in instagram_urls}
        
        usernames_to_fetch = []
        norm_url_to_username_map: Dict[str, str] = {}
        for norm_url, original_url in unique_normalized_urls.items():
            if not norm_url: continue
            username = self._extract_username_from_instagram_url(norm_url)
            if username:
                if username not in usernames_to_fetch: # Keep list of unique usernames for actor
                    usernames_to_fetch.append(username)
                norm_url_to_username_map[norm_url] = username # map norm_url to username for result lookup
            else: logger.warning(f"Could not extract Instagram username from {original_url} (normalized: {norm_url})")

        if not usernames_to_fetch: return {orig_url: None for orig_url in instagram_urls}
        
        actor_input = {"usernames": sorted(list(set(usernames_to_fetch)))}
        actor_items = await self._run_actor_async("apify/instagram-profile-scraper", actor_input)
        
        results_by_username: Dict[str, Dict[str, Any]] = {}
        if actor_items:
            for item in actor_items:
                item_username = item.get('username')
                if item_username:
                    results_by_username[item_username] = self._map_instagram_result(item)

        final_results: Dict[str, Optional[Dict[str, Any]]] = {}
        for original_url in instagram_urls:
            norm_url = self._normalize_url(original_url)
            username = norm_url_to_username_map.get(norm_url)
            final_results[original_url] = results_by_username.get(username) if username else None
        return final_results

    async def get_tiktok_data_for_urls(self, tiktok_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        # Actor: 'apidojo/tiktok-scraper', Input: 'startUrls' (list of strings)
        # Note: This scraper processes one URL at a time, so we need to run them individually
        results = {}
        
        for url in tiktok_urls:
            try:
                single_result = await self._fetch_social_data_batch_generic(
                    [url], 
                    'apidojo/tiktok-scraper', 
                    {"startUrls": [url], "maxItems": 1}, # Single URL input for this actor
                    self._map_tiktok_result,
                    actor_item_url_key_candidates=['channel.url', 'postPage']
                )
                results.update(single_result)
            except Exception as e:
                logger.error(f"Error scraping TikTok URL {url}: {e}")
                results[url] = None
        
        return results

    async def get_facebook_data_for_urls(self, facebook_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        logger.warning("Facebook scraping is not reliably implemented. Returning empty results.")
        return {url: None for url in facebook_urls}

    async def get_youtube_data_for_urls(self, youtube_urls: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        logger.warning("YouTube scraping is not fully implemented. Returning empty results.")
        return {url: None for url in youtube_urls}

    def _safe_int_cast(self, value: Any) -> Optional[int]:
        if value is None: return None
        try: return int(value)
        except (ValueError, TypeError): 
            logger.debug(f"Could not cast value '{value}' (type: {type(value)}) to int.")
            return None
