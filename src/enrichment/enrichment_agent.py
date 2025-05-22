import logging
import asyncio
from typing import Dict, Any, Optional, List, Set

# Service imports (adjust paths if your structure differs)
from ..services.gemini_service import GeminiService
from ..services.social_discovery_service import SocialDiscoveryService # Corrected path
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
        if not podcast_title:
            logger.warning("Cannot run Gemini discovery without a podcast title.")
            return None

        prompt = f"""For the podcast titled '{podcast_title}' (Description: {podcast_description if podcast_description else 'N/A'}), please identify the following information if available through public web search:

1.  Primary host name(s) (Return as a list of strings).
2.  The official Twitter/X URL of the podcast.
3.  The official Instagram URL of the podcast.
4.  The official YouTube channel URL for the podcast.
5.  The official TikTok profile URL for the podcast.
6.  The official LinkedIn page URL for the podcast (if it's a company/show page).
7.  The primary LinkedIn profile URL of one key host.
8.  The primary Twitter/X profile URL of one key host.

If any piece of information is not found or not applicable, use null for that field. 
Return the information as a JSON object matching the schema for GeminiPodcastEnrichment.
"""
        # schema_prompt = json.dumps(GeminiPodcastEnrichment.model_json_schema(), indent=2) # Already in GeminiService
        # full_prompt_with_schema = f"{prompt}\n\nJSON Schema:\n```json\n{schema_prompt}\n```\nResponse JSON:"

        logger.info(f"Querying Gemini for initial discovery: {podcast_title}")
        structured_output = await self.gemini_service.get_structured_data(
            prompt=prompt, # Pass the direct prompt now
            output_model=GeminiPodcastEnrichment,
            use_google_search=True
        )
        if structured_output:
            logger.info(f"Gemini discovery successful for '{podcast_title}'. Found hosts: {structured_output.host_names}")
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

        # 1. Initial Gemini Discovery for hosts and potential social URLs
        gemini_discovered_info: Optional[GeminiPodcastEnrichment] = None
        if self.gemini_service: # Check if service is available
            gemini_discovered_info = await self._discover_initial_info_with_gemini(
                podcast_title=podcast_title,
                podcast_description=initial_media_data.get('description')
            )
        else:
            logger.warning("GeminiService not available. Skipping initial Gemini discovery.")

        # 2. Compile all known social URLs for scraping
        urls_to_scrape: Dict[str, Set[str]] = {
            'twitter': set(),
            'linkedin': set(), # For podcast's own LinkedIn page or host's
            'instagram': set(),
            'tiktok': set(),
            'facebook': set(),
            'youtube': set()
        }

        def add_url_if_valid(platform_key: str, url: Optional[str]):
            if url and isinstance(url, str) and url.strip().startswith('http'):
                # Normalization will happen in SocialDiscoveryService
                urls_to_scrape[platform_key].add(url.strip())

        # From initial DB data
        add_url_if_valid('twitter', initial_media_data.get('podcast_twitter_url'))
        add_url_if_valid('linkedin', initial_media_data.get('podcast_linkedin_url')) # Podcast's page
        add_url_if_valid('instagram', initial_media_data.get('podcast_instagram_url'))
        add_url_if_valid('tiktok', initial_media_data.get('podcast_tiktok_url'))
        add_url_if_valid('facebook', initial_media_data.get('podcast_facebook_url'))
        add_url_if_valid('youtube', initial_media_data.get('podcast_youtube_url'))

        # From Gemini discovery
        if gemini_discovered_info:
            add_url_if_valid('twitter', str(gemini_discovered_info.podcast_twitter_url) if gemini_discovered_info.podcast_twitter_url else None)
            add_url_if_valid('linkedin', str(gemini_discovered_info.podcast_linkedin_url) if gemini_discovered_info.podcast_linkedin_url else None)
            add_url_if_valid('instagram', str(gemini_discovered_info.podcast_instagram_url) if gemini_discovered_info.podcast_instagram_url else None)
            add_url_if_valid('tiktok', str(gemini_discovered_info.podcast_tiktok_url) if gemini_discovered_info.podcast_tiktok_url else None)
            add_url_if_valid('facebook', str(gemini_discovered_info.podcast_facebook_url) if gemini_discovered_info.podcast_facebook_url else None)
            add_url_if_valid('youtube', str(gemini_discovered_info.podcast_youtube_url) if gemini_discovered_info.podcast_youtube_url else None)
            
            # Add host URLs for potential scraping if we were to process them here.
            # For now, host social URLs from Gemini are just for context or future use in People table linking.
            # add_url_if_valid('linkedin', str(gemini_discovered_info.host_linkedin_url) if gemini_discovered_info.host_linkedin_url else None)
            # add_url_if_valid('twitter', str(gemini_discovered_info.host_twitter_url) if gemini_discovered_info.host_twitter_url else None)

        # 3. Social Media Scraping using SocialDiscoveryService
        social_scraping_results: Dict[str, Optional[Dict[str, Any]]] = {}
        if self.social_discovery_service:
            # We will scrape URLs associated with the *podcast entity* itself.
            # Host-specific scraping would typically be linked to a People entity process.
            
            # Prepare tasks for concurrent scraping
            scraping_tasks = []
            if urls_to_scrape['twitter']:
                scraping_tasks.append(self.social_discovery_service.get_twitter_data_for_urls(list(urls_to_scrape['twitter'])))
            else: scraping_tasks.append(asyncio.sleep(0, result={})) # Placeholder for gather
            
            if urls_to_scrape['instagram']:
                scraping_tasks.append(self.social_discovery_service.get_instagram_data_for_urls(list(urls_to_scrape['instagram'])))
            else: scraping_tasks.append(asyncio.sleep(0, result={}))

            if urls_to_scrape['tiktok']:
                scraping_tasks.append(self.social_discovery_service.get_tiktok_data_for_urls(list(urls_to_scrape['tiktok'])))
            else: scraping_tasks.append(asyncio.sleep(0, result={}))

            # Add LinkedIn, Facebook, YouTube if actors and mappers are robust
            # For now, focusing on Twitter, Instagram, TikTok for podcast pages
            if urls_to_scrape['linkedin']:
                 # Assuming these are for the podcast's COMPANY page on LinkedIn
                 scraping_tasks.append(self.social_discovery_service.get_linkedin_data_for_urls(list(urls_to_scrape['linkedin'])))
            else: scraping_tasks.append(asyncio.sleep(0, result={}))

            # ... add placeholders for Facebook and YouTube if needed ...
            scraping_tasks.append(asyncio.sleep(0, result={})) # FB placeholder
            scraping_tasks.append(asyncio.sleep(0, result={})) # YT placeholder

            try:
                results = await asyncio.gather(*scraping_tasks)
                twitter_scraped = results[0]
                instagram_scraped = results[1]
                tiktok_scraped = results[2]
                linkedin_scraped = results[3] # For podcast company pages
                # facebook_scraped = results[4]
                # youtube_scraped = results[5]

                # The SocialDiscoveryService returns a Dict[str_original_url, Optional[Dict[str, Any]]]
                # We need to aggregate these results slightly for the DataMergerService.
                # DataMergerService expects something like: {"podcast_twitter": aggregate_twitter_data, ...}
                # For now, we'll take the first good result for each platform type if multiple URLs were scraped.
                
                if twitter_scraped: social_scraping_results['podcast_twitter'] = next((data for data in twitter_scraped.values() if data), None)
                if instagram_scraped: social_scraping_results['podcast_instagram'] = next((data for data in instagram_scraped.values() if data), None)
                if tiktok_scraped: social_scraping_results['podcast_tiktok'] = next((data for data in tiktok_scraped.values() if data), None)
                if linkedin_scraped: social_scraping_results['podcast_linkedin'] = next((data for data in linkedin_scraped.values() if data), None)

                logger.info(f"Social scraping complete for media_id: {media_id}. Found data for keys: {list(social_scraping_results.keys())}")
            except Exception as e_scrape:
                logger.error(f"Error during batch social scraping for media_id {media_id}: {e_scrape}", exc_info=True)
        else:
            logger.warning("SocialDiscoveryService not available. Skipping social media scraping.")

        # 4. Merge all data
        if not self.data_merger_service:
            logger.error("DataMergerService not available. Cannot produce final EnrichedPodcastProfile.")
            return None

        final_enriched_profile = self.data_merger_service.merge_podcast_data(
            initial_db_data=initial_media_data,
            gemini_enrichment=gemini_discovered_info,
            social_media_results=social_scraping_results
        )

        if final_enriched_profile:
            logger.info(f"Successfully enriched profile for media_id: {media_id}, Title: {final_enriched_profile.title}")
        else:
            logger.error(f"Data merging failed for media_id: {media_id}")

        return final_enriched_profile

# Example Usage (Conceptual - requires setup of services)
if __name__ == '__main__':
    # This is a conceptual example. To run, you would need to:
    # 1. Have .env file with API keys (GEMINI_API_KEY, APIFY_API_KEY)
    # 2. Initialize GeminiService, SocialDiscoveryService, DataMergerService
    # 3. Have some mock initial_media_data
    
    async def test_enrichment_agent():
        logging.basicConfig(level=logging.DEBUG) # More verbose for testing
        logger.info("--- Testing EnrichmentAgent --- ")
        
        # Mock services (in a real scenario, these would be properly initialized)
        try:
            gemini_service = GeminiService() # Needs GEMINI_API_KEY
            social_discovery_service = SocialDiscoveryService() # Needs APIFY_API_KEY
            data_merger_service = DataMergerService()
        except ValueError as e:
            logger.error(f"Failed to initialize services for test: {e}")
            return

        agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger_service)

        # Example: Fetch a real podcast from DB or use mock data
        mock_podcast_from_db = {
            "media_id": "test_media_123",
            "api_id": "some_api_id_listennotes",
            "name": "The Daily", # Title for Gemini
            "title": "The Daily by The New York Times",
            "description": "This is what the news should sound like. The biggest stories of our time, told by the best journalists in the world. Hosted by Michael Barbaro and Sabrina Tavernise. Twenty minutes a day, five days a week, ready by 6 a.m.",
            "podcast_twitter_url": None, # Let Gemini try to find it
            "contact_email": "thedaily@nytimes.com"
            # Add other fields as they exist in your 'media' table
        }

        enriched_profile = await agent.enrich_podcast_profile(mock_podcast_from_db)

        if enriched_profile:
            print("\n--- Final Enriched Profile --- ")
            print(enriched_profile.model_dump_json(indent=2, exclude_none=True))
        else:
            print("\nEnrichment failed for the test podcast.")

    asyncio.run(test_enrichment_agent()) 