import logging
import asyncio
from typing import Dict, Any, Optional, List, Set

# Service imports (adjust paths if your structure differs)
from ..services.gemini_service import GeminiService
from .social_discovery_service import SocialDiscoveryService # Corrected path
from .data_merger_service import DataMergerService # Corrected path

# Model imports
from ..models.podcast_profile_models import EnrichedPodcastProfile
from ..models.llm_output_models import GeminiPodcastEnrichment

logger = logging.getLogger(__name__)

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

    async def _discover_initial_info_with_gemini(
        self, 
        podcast_title: Optional[str],
        podcast_description: Optional[str]
    ) -> Optional[GeminiPodcastEnrichment]:
        """Uses Gemini to find initial host names and social URLs for a podcast."""
        if not self.gemini_service:
            logger.warning("GeminiService not available for initial discovery.")
            return None
        if not podcast_title:
            logger.warning("Cannot run Gemini discovery without a podcast title.")
            return None

        # More targeted prompt for specific podcast entity social media
        prompt = f"""For the podcast titled '{podcast_title}' (Description: {podcast_description if podcast_description else 'N/A'}), identify the following:
1. Official host name(s) as a list of strings.
2. The official Twitter/X URL for the podcast itself.
3. The official Instagram URL for the podcast itself.
4. The official YouTube channel URL for the podcast itself.
5. The official TikTok profile URL for the podcast itself.
6. The official LinkedIn Company Page URL for the podcast/production company (not personal profiles of hosts).

If specific information is not found, use null for that field. Adhere to the JSON schema for GeminiPodcastEnrichment.
"""
        logger.info(f"Querying Gemini for initial discovery: {podcast_title}")
        structured_output = await self.gemini_service.get_structured_data(
            prompt=prompt,
            output_model=GeminiPodcastEnrichment,
            temperature=0.2 # Slightly higher temp for better discovery if needed
        )
        if structured_output:
            logger.info(f"Gemini discovery for '{podcast_title}' yielded: Hosts: {structured_output.host_names}, Twitter: {structured_output.podcast_twitter_url}")
        else:
            logger.warning(f"Gemini discovery did not return structured data for '{podcast_title}'.")
        return structured_output

    async def enrich_podcast_profile(
        self, 
        initial_media_data: Dict[str, Any] # Data from media table
    ) -> Optional[EnrichedPodcastProfile]:
        """Enriches a single podcast profile.

        Args:
            initial_media_data: A dictionary representing the podcast's current data from the DB.

        Returns:
            An EnrichedPodcastProfile object, or None if enrichment fails.
        """
        if not initial_media_data or not initial_media_data.get('media_id'):
            logger.error("EnrichmentAgent: Missing initial_media_data or media_id.")
            return None
        
        media_id = initial_media_data.get('media_id')
        podcast_title = initial_media_data.get('title') or initial_media_data.get('name')
        logger.info(f"Starting enrichment for media_id: {media_id}, Title: {podcast_title}")

        gemini_discovered_info = await self._discover_initial_info_with_gemini(
            podcast_title=podcast_title,
            podcast_description=initial_media_data.get('description')
        )

        urls_to_scrape: Dict[str, Set[str]] = {
            'twitter': set(), 'linkedin_company': set(), 'instagram': set(),
            'tiktok': set(), 'facebook': set(), 'youtube': set()
        }

        def add_url_if_valid(platform_key: str, url: Any):
            # Ensure url is a string before calling strip()
            if url and isinstance(url, str) and url.strip().startswith('http'):
                # Normalization will happen in SocialDiscoveryService or here before adding
                # For now, SocialDiscoveryService handles normalization.
                urls_to_scrape[platform_key].add(url.strip())
            elif url and hasattr(url, '__str__'): # Handle Pydantic HttpUrl objects from Gemini
                url_str = str(url)
                if url_str.strip().startswith('http'):
                     urls_to_scrape[platform_key].add(url_str.strip())

        # Prioritize URLs from DB, then augment with Gemini if DB field was empty
        # Podcast-specific social media URLs
        db_twitter = initial_media_data.get('podcast_twitter_url')
        db_linkedin = initial_media_data.get('podcast_linkedin_url') # Assumed to be company/show page
        db_instagram = initial_media_data.get('podcast_instagram_url')
        db_tiktok = initial_media_data.get('podcast_tiktok_url')
        db_facebook = initial_media_data.get('podcast_facebook_url')
        db_youtube = initial_media_data.get('podcast_youtube_url')

        add_url_if_valid('twitter', db_twitter)
        add_url_if_valid('linkedin_company', db_linkedin)
        add_url_if_valid('instagram', db_instagram)
        add_url_if_valid('tiktok', db_tiktok)
        add_url_if_valid('facebook', db_facebook)
        add_url_if_valid('youtube', db_youtube)

        if gemini_discovered_info:
            if not db_twitter: add_url_if_valid('twitter', gemini_discovered_info.podcast_twitter_url)
            if not db_linkedin: add_url_if_valid('linkedin_company', gemini_discovered_info.podcast_linkedin_url)
            if not db_instagram: add_url_if_valid('instagram', gemini_discovered_info.podcast_instagram_url)
            if not db_tiktok: add_url_if_valid('tiktok', gemini_discovered_info.podcast_tiktok_url)
            if not db_facebook: add_url_if_valid('facebook', gemini_discovered_info.podcast_facebook_url)
            if not db_youtube: add_url_if_valid('youtube', gemini_discovered_info.podcast_youtube_url)
        
        social_scraping_results: Dict[str, Optional[Dict[str, Any]]] = {}
        if not self.social_discovery_service:
            logger.warning("SocialDiscoveryService not available. Skipping social media scraping.")
        else:
            scraping_tasks = []
            # Twitter for podcast
            if urls_to_scrape['twitter']:
                scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_twitter_data_for_urls(list(urls_to_scrape['twitter'])), name="twitter_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="twitter_placeholder"))
            
            # Instagram for podcast
            if urls_to_scrape['instagram']:
                scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_instagram_data_for_urls(list(urls_to_scrape['instagram'])), name="instagram_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="instagram_placeholder"))

            # TikTok for podcast
            if urls_to_scrape['tiktok']:
                scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_tiktok_data_for_urls(list(urls_to_scrape['tiktok'])), name="tiktok_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="tiktok_placeholder"))
            
            # LinkedIn Company Page for podcast
            if urls_to_scrape['linkedin_company']:
                scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_linkedin_data_for_urls(list(urls_to_scrape['linkedin_company'])), name="linkedin_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="linkedin_placeholder"))
            
            # Facebook & YouTube (placeholders, as actors might be less reliable or need more setup)
            if urls_to_scrape['facebook']:
                scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_facebook_data_for_urls(list(urls_to_scrape['facebook'])), name="facebook_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="facebook_placeholder"))

            if urls_to_scrape['youtube']:
                scraping_tasks.append(asyncio.create_task(self.social_discovery_service.get_youtube_data_for_urls(list(urls_to_scrape['youtube'])), name="youtube_scrape"))
            else: scraping_tasks.append(asyncio.create_task(asyncio.sleep(0, result={}), name="youtube_placeholder"))

            logger.info(f"Dispatching {len(scraping_tasks)} social scraping tasks for media_id: {media_id}.")
            try:
                results = await asyncio.gather(*scraping_tasks, return_exceptions=True) # Catch individual task errors
                
                # Process results carefully, checking for exceptions
                def get_first_valid_result(batch_result: Any) -> Optional[Dict[str, Any]]:
                    if isinstance(batch_result, Exception) or not batch_result or not isinstance(batch_result, dict):
                        if isinstance(batch_result, Exception): logger.error(f"Scraping task failed: {batch_result}")
                        return None
                    return next((data for data in batch_result.values() if data and isinstance(data, dict)), None)

                twitter_scraped_data = get_first_valid_result(results[0])
                instagram_scraped_data = get_first_valid_result(results[1])
                tiktok_scraped_data = get_first_valid_result(results[2])
                linkedin_scraped_data = get_first_valid_result(results[3])
                facebook_scraped_data = get_first_valid_result(results[4])
                youtube_scraped_data = get_first_valid_result(results[5])
                
                if twitter_scraped_data: social_scraping_results['podcast_twitter'] = twitter_scraped_data
                if instagram_scraped_data: social_scraping_results['podcast_instagram'] = instagram_scraped_data
                if tiktok_scraped_data: social_scraping_results['podcast_tiktok'] = tiktok_scraped_data
                if linkedin_scraped_data: social_scraping_results['podcast_linkedin'] = linkedin_scraped_data # For company page
                if facebook_scraped_data: social_scraping_results['podcast_facebook'] = facebook_scraped_data
                if youtube_scraped_data: social_scraping_results['podcast_youtube'] = youtube_scraped_data

                logger.info(f"Social scraping aggregated for media_id: {media_id}. Valid data for: {[k for k,v in social_scraping_results.items() if v]}")
            except Exception as e_gather:
                logger.error(f"Error during asyncio.gather for social scraping tasks (media_id {media_id}): {e_gather}", exc_info=True)
        
        if not self.data_merger_service:
            logger.error("DataMergerService not available. Cannot produce final EnrichedPodcastProfile.")
            return None

        final_enriched_profile = self.data_merger_service.merge_podcast_data(
            initial_db_data=initial_media_data,
            gemini_enrichment=gemini_discovered_info, # This is Optional[GeminiPodcastEnrichment]
            social_media_results=social_scraping_results # This is Dict[str, Optional[Dict[str, Any]]]
        )

        if final_enriched_profile:
            logger.info(f"Successfully enriched profile for media_id: {media_id}, Title: {final_enriched_profile.title}")
            # Handle host information: (Deferred for now as per plan)
            # If gemini_discovered_info and gemini_discovered_info.host_names:
            #   final_enriched_profile.host_names = gemini_discovered_info.host_names (DataMerger handles this)
            #   Logic to find/create People records & link to MediaPeople would go here or in Orchestrator
        else:
            logger.error(f"Data merging failed for media_id: {media_id}")

        return final_enriched_profile

# Example Usage (Conceptual)
if __name__ == '__main__':
    async def test_enrichment_agent():
        logging.basicConfig(level=logging.DEBUG)
        logger.info("--- Testing EnrichmentAgent --- ")
        
        # Mock services (replace with actual initialization if running standalone tests with API keys)
        class MockGeminiService:
            async def get_structured_data(self, prompt: str, output_model, use_google_search: bool = True, temperature: Optional[float]=0.1):
                logger.debug(f"MockGeminiService.get_structured_data called for {output_model.__name__}")
                if output_model == GeminiPodcastEnrichment:
                    return GeminiPodcastEnrichment(
                        host_names=["Mock Host A", "Mock Host B"],
                        podcast_twitter_url="https://twitter.com/mockpodcast",
                        podcast_instagram_url="https://instagram.com/mockpodcast"
                    )
                return None

        class MockSocialDiscoveryService:
            async def get_twitter_data_for_urls(self, urls: List[str]): 
                logger.debug(f"MockSocialDiscovery.get_twitter_data_for_urls: {urls}")
                return {url: {"followers_count": 1000, "profile_url": url} for url in urls} if urls else {}
            async def get_instagram_data_for_urls(self, urls: List[str]): 
                logger.debug(f"MockSocialDiscovery.get_instagram_data_for_urls: {urls}")
                return {url: {"followers_count": 2000, "profile_url": url} for url in urls} if urls else {}
            async def get_tiktok_data_for_urls(self, urls: List[str]): return {}
            async def get_linkedin_data_for_urls(self, urls: List[str]): return {}
            async def get_facebook_data_for_urls(self, urls: List[str]): return {}
            async def get_youtube_data_for_urls(self, urls: List[str]): return {}

        gemini_service = MockGeminiService()
        social_discovery_service = MockSocialDiscoveryService()
        data_merger_service = DataMergerService() # Assuming it can be initialized simply

        agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger_service)

        mock_podcast_from_db = {
            "media_id": "mock_media_001", "api_id": "api_001", "name": "Mockcast Fun",
            "description": "A fun podcast about mocks.",
            "podcast_twitter_url": "https://twitter.com/db_mock" # DB has one URL
        }

        enriched_profile = await agent.enrich_podcast_profile(mock_podcast_from_db)

        if enriched_profile:
            print("\n--- Final Enriched Profile (Mock Test) --- ")
            print(enriched_profile.model_dump_json(indent=2, exclude_none=False))
        else:
            print("\nEnrichment failed for the mock test podcast.")

    asyncio.run(test_enrichment_agent()) 