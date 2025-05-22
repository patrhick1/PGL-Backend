import os
import logging
import asyncio
from typing import Dict, Any, Optional, List, Set
import re
import json

# Service imports (adjust paths if your structure differs)
from ..services.gemini_service import GeminiService
from .social_discovery_service import SocialDiscoveryService
from .data_merger_service import DataMergerService

# Model imports
from ..models.podcast_profile_models import EnrichedPodcastProfile
from ..models.llm_output_models import GeminiPodcastEnrichment

# For async_tavily_search if included directly
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv() # Ensure .env is loaded for TAVILY_API_KEY if used directly

# --- Tavily Search Service (Directly included as per user script) ---
async def async_tavily_search(query: str, max_results: int = 5, search_depth: str = "basic", include_answer: bool = False) -> Dict[str, Any]:
    """
    Performs an asynchronous Tavily search.
    Requires TAVILY_API_KEY environment variable.
    """
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        logger.error("TAVILY_API_KEY environment variable not set. Cannot perform Tavily search.")
        return {"error": "TAVILY_API_KEY not set"}

    headers = {
        "Content-Type": "application/json"
    }
    data = {
        "query": query,
        "api_key": tavily_api_key,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": include_answer,
        "include_raw_content": False,
        "include_images": False
    }
    
    try:
        import aiohttp
    except ImportError:
        logger.error("aiohttp not installed. Please install with `pip install aiohttp` to use Tavily search.")
        return {"error": "aiohttp not installed"}

    url = "https://api.tavily.com/search"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                response.raise_for_status()  # Raise an exception for HTTP errors
                result = await response.json()
                return result
    except aiohttp.ClientError as e:
        logger.error(f"Tavily search HTTP client error: {e}")
        return {"error": f"Tavily search HTTP client error: {e}"}
    except Exception as e:
        logger.error(f"An unexpected error occurred during Tavily search: {e}")
        return {"error": f"Unexpected error during Tavily search: {e}"}

class EnrichmentAgent:
    """Agent responsible for enriching a single podcast profile using various services."""

    def __init__(self,
                 gemini_service: GeminiService,
                 social_discovery_service: SocialDiscoveryService,
                 data_merger_service: DataMergerService):
        self.gemini_service = gemini_service
        self.social_discovery_service = social_discovery_service
        self.data_merger_service = data_merger_service
        logger.info("EnrichmentAgent initialized with Gemini, SocialDiscovery, and DataMerger services.")
        
        self._url_pattern = re.compile(r'https?://[\w\-./?=&%#:]+')
        self._twitter_pattern = re.compile(r'https?://(?:mobile\.|m\.)?(?:twitter\.com|x\.com)/', re.IGNORECASE)
        self._linkedin_pattern = re.compile(r'https?://(?:[a-z]{2,3}\.)?linkedin\.com/', re.IGNORECASE)
        self._instagram_pattern = re.compile(r'https?://(?:www\.)?instagram\.com/', re.IGNORECASE)
        self._facebook_pattern = re.compile(r'https?://(?:www\.)?facebook\.com/', re.IGNORECASE)
        self._youtube_pattern = re.compile(r'https?://(?:www\.)?(?:youtube\.com|youtu\.be)/', re.IGNORECASE)
        self._tiktok_pattern = re.compile(r'https?://(?:www\.)?tiktok\.com/', re.IGNORECASE)

    def _normalize_social_url(self, url: str) -> str:
        if not url: return url
        url = url.strip()
        if url.startswith("http://"): url = "https://" + url[len("http://"):]
        if not url.startswith("https://") and not url.startswith("http://"): url = "https://" + url # Ensure schema
        
        url = self._twitter_pattern.sub("https://twitter.com/", url)
        url = self._linkedin_pattern.sub("https://www.linkedin.com/", url) # LinkedIn often uses www
        url = self._instagram_pattern.sub("https://www.instagram.com/", url)
        url = self._facebook_pattern.sub("https://www.facebook.com/", url)
        url = self._youtube_pattern.sub("https://www.youtube.com/", url)
        url = self._tiktok_pattern.sub("https://www.tiktok.com/", url)

        url = url.split("?")[0].split("#")[0]
        if url.endswith("/") and url.count("/") > 2: url = url.rstrip("/")
        return url

    def _extract_url(self, text: Optional[str]) -> Optional[str]:
        if not text: return None
        match = self._url_pattern.search(text)
        if match:
            url = match.group(0).strip('.,;)\'')
            return self._normalize_social_url(url) # Normalize after extraction
        return None

    def _extract_host_names(self, text: Optional[str]) -> Optional[List[str]]:
        if not text: return None
        text = re.sub(r'^(?:The host(?:s)? (?:is|are)|Hosted by)\s*:?\s*', '', text, flags=re.IGNORECASE).strip()
        text = text.split('.')[0].strip('.,;)\'')
        names = []
        if ' and '.lower() in text.lower(): names = [name.strip() for name in re.split(r'\s+and\s+', text, flags=re.IGNORECASE)]
        elif ',' in text: names = [name.strip() for name in text.split(',')]
        else: names = [text]
        cleaned_names = [name for name in names if name and len(name) > 1] # Basic filter for very short/empty names
        return cleaned_names if cleaned_names else None

    async def _discover_initial_info_with_gemini_and_tavily(
        self, 
        initial_data: Dict[str, Any] 
    ) -> Optional[GeminiPodcastEnrichment]:
        podcast_name = initial_data.get('title', initial_data.get('name', 'Unknown Podcast'))
        podcast_description = initial_data.get('description', '')
        podcast_api_id = initial_data.get('api_id', initial_data.get('media_id', 'Unknown ID'))
        logger.info(f"Starting Gemini+Tavily discovery for {podcast_api_id} ({podcast_name})")

        discovery_targets = [
            ("Host Names", 'host_names', 'host_names', False),
            ("Podcast Twitter URL", 'podcast_twitter_url', 'podcast_twitter_url', False),
            ("Podcast LinkedIn URL", 'podcast_linkedin_url', 'podcast_linkedin_url', False),
            ("Podcast Instagram URL", 'podcast_instagram_url', 'podcast_instagram_url', False),
            ("Podcast Facebook URL", 'podcast_facebook_url', 'podcast_facebook_url', False),
            ("Podcast YouTube URL", 'podcast_youtube_url', 'podcast_youtube_url', False),
            ("Podcast TikTok URL", 'podcast_tiktok_url', 'podcast_tiktok_url', False),
            ("Primary Host LinkedIn URL", 'host_linkedin_url', 'host_linkedin_url', True),
            ("Primary Host Twitter URL", 'host_twitter_url', 'host_twitter_url', True)
        ]

        found_info_texts = [f"Original Podcast Name: {podcast_name}"]
        if podcast_description: found_info_texts.append(f"Original Podcast Description: {podcast_description[:500]}...")

        current_host_names_str = None
        if initial_data.get('host_names'):
            host_data = initial_data['host_names']
            if isinstance(host_data, list): current_host_names_str = ", ".join(host_data)
            elif isinstance(host_data, str): current_host_names_str = host_data
            if current_host_names_str: found_info_texts.append(f"Host Names (from initial data): {current_host_names_str}")

        for target_name, initial_key, gemini_key, needs_host_context in discovery_targets:
            if initial_key and isinstance(initial_data.get(initial_key), str) and initial_data.get(initial_key):
                found_info_texts.append(f"{target_name} (from initial data): {initial_data[initial_key]}")
                if gemini_key == 'host_names' and not current_host_names_str: # Update if found from initial_key
                    current_host_names_str = initial_data[initial_key]
                continue
            elif gemini_key == 'host_names' and current_host_names_str: # Already have hosts, skip search for host names
                continue
            
            query_subject_name = current_host_names_str if needs_host_context and current_host_names_str else podcast_name
            query_for_target = f"the host of '{query_subject_name}'" if needs_host_context and current_host_names_str else f"the podcast '{query_subject_name}'"
            if target_name == "Host Names" and not current_host_names_str: query_for_target = f"the podcast '{podcast_name}'"
            
            search_query = f"{target_name} for {query_for_target}"
            logger.debug(f"Tavily search for '{target_name}' for {podcast_api_id}. Query: '{search_query}'")
            
            tavily_response = await async_tavily_search(search_query, max_results=2, search_depth="advanced", include_answer=True)
            await asyncio.sleep(0.25)

            search_output_for_gemini = f"Search Query for {target_name}: {search_query}\n"
            if tavily_response and not tavily_response.get("error"):
                if tavily_response.get("answer"): search_output_for_gemini += f"Tavily Answer: {tavily_response['answer']}\n"
                elif tavily_response.get("results"): 
                    snippets = "\n".join([f"- {res.get('title', '')}: {res.get('content', '')[:200]}... (URL: {res.get('url')})" for res in tavily_response["results"]])
                    search_output_for_gemini += f"Tavily Snippets:\n{snippets}\n"
                else: search_output_for_gemini += "Tavily: No specific answer or results found.\n"
            else: search_output_for_gemini += f"Tavily: Search failed or error: {tavily_response.get('error', 'Unknown error')}\n"
            found_info_texts.append(search_output_for_gemini)

            if gemini_key == 'host_names' and not current_host_names_str and tavily_response and not tavily_response.get("error"):
                text_to_parse_hosts = tavily_response.get("answer") or ""
                if not text_to_parse_hosts and tavily_response.get("results"): 
                    text_to_parse_hosts = " ".join([res.get("content","") for res in tavily_response["results"]])
                parsed_hosts_from_search = self._extract_host_names(text_to_parse_hosts)
                if parsed_hosts_from_search:
                    current_host_names_str = ", ".join(parsed_hosts_from_search)
                    logger.info(f"Tentatively identified hosts for {podcast_name} via Tavily: {current_host_names_str}")

        combined_text_for_parsing = "\n\n---\n\n".join(found_info_texts)
        logger.debug(f"Combined text for Gemini structured parsing for {podcast_api_id} (length {len(combined_text_for_parsing)}):
{combined_text_for_parsing[:1000]}...")

        if not self.gemini_service: return None

        final_parser_prompt = f"""You are an expert data extraction assistant.
Based *only* on the information within the 'Provided Text' section below, extract the required information and structure it according to the 'JSON Schema'.

Key Instructions:
1. If specific information for a field is not explicitly found in the 'Provided Text', use null for that field. Do not guess or infer. If multiple distinct URLs are found for the *same* field, pick the one that seems most official or appears most frequently. If unsure, pick the first one encountered.
2. Prioritize information that is clearly labeled or directly answers a search query.
3. For social media URLs, look for full, valid HTTP/HTTPS links. Ensure the extracted URL corresponds to the type requested (e.g., a LinkedIn Company Page URL for 'podcast_linkedin_url', not a personal profile).
4. If the text for a specific URL search explicitly states "unable to find", "no official page", or similar, then the value for that URL field in the JSON output should be null.
5. Host names should be a list of strings. If multiple hosts are mentioned (e.g., "Host A and Host B"), list them as ["Host A", "Host B"]. If a search for host names yields no clear names, use null for the host_names field.

Provided Text:
---
{combined_text_for_parsing}
---

JSON Schema:
```json
{GeminiPodcastEnrichment.model_json_schema(indent=2)}
```
"""
        structured_output = await self.gemini_service.get_structured_data(
            prompt=final_parser_prompt,
            output_model=GeminiPodcastEnrichment,
            temperature=0.1 
        )
        if structured_output:
            logger.info(f"Gemini structured parsing for '{podcast_name}' successful.")
        else:
            logger.warning(f"Gemini structured parsing did not return data for '{podcast_name}'.")
        return structured_output

    async def enrich_podcast_profile(
        self, 
        initial_media_data: Dict[str, Any]
    ) -> Optional[EnrichedPodcastProfile]:
        if not initial_media_data or not initial_media_data.get('media_id'):
            logger.error("EnrichmentAgent: Missing initial_media_data or media_id.")
            return None
        
        media_id = initial_media_data.get('media_id')
        podcast_title = initial_media_data.get('title') or initial_media_data.get('name')
        logger.info(f"Starting enrichment for media_id: {media_id}, Title: {podcast_title}")

        gemini_output_after_web_search = await self._discover_initial_info_with_gemini_and_tavily(initial_media_data)

        urls_to_scrape: Dict[str, Set[str]] = {
            'twitter': set(), 'linkedin_company': set(), 'instagram': set(),
            'tiktok': set(), 'facebook': set(), 'youtube': set()
        }

        def add_url_if_valid(platform_key: str, url_value: Any):
            if url_value:
                url_str = str(url_value).strip()
                if url_str and url_str.lower() != 'null' and url_str.startswith('http'):
                    urls_to_scrape[platform_key].add(self._normalize_social_url(url_str))

        if gemini_output_after_web_search:
            add_url_if_valid('twitter', gemini_output_after_web_search.podcast_twitter_url)
            add_url_if_valid('linkedin_company', gemini_output_after_web_search.podcast_linkedin_url)
            add_url_if_valid('instagram', gemini_output_after_web_search.podcast_instagram_url)
            add_url_if_valid('tiktok', gemini_output_after_web_search.podcast_tiktok_url)
            add_url_if_valid('facebook', gemini_output_after_web_search.podcast_facebook_url)
            add_url_if_valid('youtube', gemini_output_after_web_search.podcast_youtube_url)
        
        social_scraping_results: Dict[str, Optional[Dict[str, Any]]] = {}
        if not self.social_discovery_service:
            logger.warning("SocialDiscoveryService not available. Skipping social media scraping.")
        else:
            scraping_tasks = []
            # Create tasks ensuring lists are not empty before calling service methods
            if urls_to_scrape['twitter']: scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_twitter_data_for_urls(list(urls_to_scrape['twitter'])), name="twitter_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="twitter_placeholder"))
            
            if urls_to_scrape['instagram']: scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_instagram_data_for_urls(list(urls_to_scrape['instagram'])), name="instagram_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="instagram_placeholder"))

            if urls_to_scrape['tiktok']: scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_tiktok_data_for_urls(list(urls_to_scrape['tiktok'])), name="tiktok_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="tiktok_placeholder"))
            
            # Use get_linkedin_data_for_urls for company pages
            if urls_to_scrape['linkedin_company']: scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_linkedin_data_for_urls(list(urls_to_scrape['linkedin_company'])), name="linkedin_company_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="linkedin_placeholder"))
            
            if urls_to_scrape['facebook']: scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_facebook_data_for_urls(list(urls_to_scrape['facebook'])), name="facebook_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="facebook_placeholder"))

            if urls_to_scrape['youtube']: scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_youtube_data_for_urls(list(urls_to_scrape['youtube'])), name="youtube_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="youtube_placeholder"))

            logger.info(f"Dispatching social scraping tasks for media_id: {media_id}.")
            try:
                results = await asyncio.gather(*scraping_tasks, return_exceptions=True)
                
                def get_first_valid_data_from_batch_result(batch_result: Any) -> Optional[Dict[str, Any]]:
                    if isinstance(batch_result, Exception) or not batch_result or not isinstance(batch_result, dict):
                        if isinstance(batch_result, Exception): logger.error(f"Scraping task failed: {batch_result}")
                        return None
                    for data in batch_result.values():
                        if data and isinstance(data, dict):
                            return data
                    return None
                
                key_map = ['podcast_twitter', 'podcast_instagram', 'podcast_tiktok', 'podcast_linkedin', 'podcast_facebook', 'podcast_youtube']
                if len(results) == len(key_map):
                    for i, key in enumerate(key_map):
                        social_scraping_results[key] = get_first_valid_data_from_batch_result(results[i])
                else:
                    logger.error(f"Unexpected number of results from asyncio.gather for social scraping: {len(results)}")

                logger.info(f"Social scraping aggregated for media_id: {media_id}. Valid data for: {[k for k,v in social_scraping_results.items() if v]}")
            except Exception as e_gather:
                logger.error(f"Error during asyncio.gather for social scraping tasks (media_id {media_id}): {e_gather}", exc_info=True)
        
        if not self.data_merger_service:
            logger.error("DataMergerService not available. Cannot produce final EnrichedPodcastProfile.")
            return None

        final_enriched_profile = self.data_merger_service.merge_podcast_data(
            initial_db_data=initial_media_data,
            gemini_enrichment=gemini_output_after_web_search, 
            social_media_results=social_scraping_results
        )

        if final_enriched_profile:
            logger.info(f"Successfully enriched profile for media_id: {media_id}, Title: {final_enriched_profile.title}")
        else:
            logger.error(f"Data merging failed for media_id: {media_id}")

        return final_enriched_profile

# Example Usage (Conceptual)
if __name__ == '__main__':
    # This import is only needed if running this script directly with nest_asyncio
    # In a typical FastAPI app, nest_asyncio might be applied at the top level if needed.
    # import nest_asyncio
    # nest_asyncio.apply() 

    async def test_enrichment_agent():
        logging.basicConfig(level=logging.DEBUG)
        logger.info("--- Testing EnrichmentAgent --- ")
        
        # Mock services (replace with actual initialization if running standalone tests with API keys)
        class MockGeminiService(GeminiService): # Inherit to satisfy type hint
            async def get_structured_data(self, prompt: str, output_model, temperature: Optional[float]=0.1):
                logger.debug(f"MockGeminiService.get_structured_data called for {output_model.__name__}")
                if output_model == GeminiPodcastEnrichment:
                    # Simulate some URLs being found, others null
                    return GeminiPodcastEnrichment(
                        host_names=["Mock Host Alpha", "Mock Host Beta"],
                        podcast_twitter_url="https://twitter.com/mockpodcast",
                        podcast_linkedin_url=None, # Simulate not found by Gemini initially
                        podcast_instagram_url="https://instagram.com/mockpodcast",
                        host_linkedin_url="https://linkedin.com/in/mockhostalpha" # Example host specific
                    )
                return None

        class MockSocialDiscoveryService(SocialDiscoveryService):
            def __init__(self):
                super().__init__(api_key="DUMMY_APIFY_KEY_FOR_MOCK") # Call parent init
                logger.info("MockSocialDiscoveryService initialized.")
            async def get_twitter_data_for_urls(self, urls: List[str]): 
                logger.debug(f"MockSocialDiscovery.get_twitter_data_for_urls: {urls}")
                return {url: {"followers_count": 1000, "profile_url": url, "username": url.split('/')[-1]} for url in urls} if urls else {}
            async def get_instagram_data_for_urls(self, urls: List[str]): 
                logger.debug(f"MockSocialDiscovery.get_instagram_data_for_urls: {urls}")
                return {url: {"followers_count": 2000, "profile_url": url, "username": url.split('/')[-1]} for url in urls} if urls else {}
            async def get_linkedin_data_for_urls(self, urls: List[str]): 
                logger.debug(f"MockSocialDiscovery.get_linkedin_data_for_urls (for company pages): {urls}")
                # Simulate finding company data for a URL that might have been discovered
                return {url: {"name": "Mock LinkedIn Company", "followers_count": 500, "profile_url": url} for url in urls} if urls else {}
            async def get_tiktok_data_for_urls(self, urls: List[str]): return {url: None for url in urls}
            async def get_facebook_data_for_urls(self, urls: List[str]): return {url: None for url in urls}
            async def get_youtube_data_for_urls(self, urls: List[str]): return {url: None for url in urls}

        # Ensure TAVILY_API_KEY is set in .env or mock async_tavily_search if needed for offline testing
        if not os.getenv("TAVILY_API_KEY"):
            logger.warning("TAVILY_API_KEY not set, Tavily searches in test will fail or use mock.")
            # You could monkeypatch async_tavily_search here for a fully offline test if desired

        gemini_service = MockGeminiService(model_name="gemini-1.5-flash-latest") # Pass required arg
        social_discovery_service = MockSocialDiscoveryService()
        data_merger_service = DataMergerService()

        agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger_service)

        mock_podcast_from_db = {
            "media_id": "mock_media_001", "api_id": "api_001", "name": "The Mockingbird Lane",
            "title": "The Mockingbird Lane Podcast",
            "description": "Discussions about all things mockingbirds and spooky lanes.",
            # Start with some data potentially missing or different
            "podcast_twitter_url": "https://twitter.com/db_mockbird", 
            "host_names": ["Herman Munster"] 
        }

        enriched_profile = await agent.enrich_podcast_profile(mock_podcast_from_db)

        if enriched_profile:
            print("\n--- Final Enriched Profile (Mock Test) --- ")
            print(enriched_profile.model_dump_json(indent=2, exclude_none=False))
        else:
            print("\nEnrichment failed for the mock test podcast.")

    asyncio.run(test_enrichment_agent()) 