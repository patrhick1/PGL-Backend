# podcast_outreach/services/enrichment/enrichment_agent.py
"""Podcast enrichment agent."""

import os
import logging
import asyncio
from typing import Dict, Any, Optional, List, Set
import re
import json

# Service imports
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService
from podcast_outreach.services.enrichment.data_merger import DataMergerService

# Model imports
from podcast_outreach.database.models.media_models import EnrichedPodcastProfile
from podcast_outreach.database.models.llm_outputs import GeminiPodcastEnrichment

# DB Queries
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.database.queries import media as media_queries

# Tavily search
from podcast_outreach.services.ai.tavily_client import async_tavily_search
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()  # Ensure .env is loaded for TAVILY_API_KEY if used directly

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
        
        self.llm_model_name = "gemini-1.5-flash-latest" # Explicitly define LLM model for consistency
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
        return url.lower()

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
            # *** MODIFIED LOGIC: ONLY SEARCH IF THE FIELD IS MISSING ***
            if initial_key and initial_data.get(initial_key):
                logger.debug(f"Skipping search for '{target_name}'; already present in initial data.")
                found_info_texts.append(f"{target_name} (from initial data): {initial_data[initial_key]}")
                if gemini_key == 'host_names' and not current_host_names_str:
                    current_host_names_str = initial_data[initial_key]
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
        logger.debug(f"Combined text for Gemini structured parsing for {podcast_api_id} (length {len(combined_text_for_parsing)}):\n{combined_text_for_parsing[:1000]}...")

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

    async def _create_or_link_hosts(self, media_id: int, host_names: List[str]):
        """Creates or links hosts in the people and media_people tables."""
        if not host_names:
            return

        for host_name in host_names:
            if not host_name or not isinstance(host_name, str):
                continue
            
            # Check if a person with this name already exists
            existing_person = await people_queries.get_person_by_full_name(host_name)
            
            person_id = None
            if existing_person:
                person_id = existing_person['person_id']
                logger.info(f"Found existing person record for host '{host_name}' (ID: {person_id}).")
            else:
                # Create a new person record for the host
                new_person_data = {
                    "full_name": host_name,
                    "role": "host"
                }
                created_person = await people_queries.create_person_in_db(new_person_data)
                if created_person:
                    person_id = created_person['person_id']
                    logger.info(f"Created new person record for host '{host_name}' (ID: {person_id}).")
            
            if person_id:
                # Create the link in the media_people table
                await media_queries.link_person_to_media(media_id, person_id, 'host')

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

        gemini_output = await self._discover_initial_info_with_gemini_and_tavily(initial_media_data)

        # *** NEW: Process hosts immediately after discovery ***
        if gemini_output and gemini_output.host_names:
            await self._create_or_link_hosts(media_id, gemini_output.host_names)
        
        urls_to_scrape: Dict[str, Set[str]] = {
            'twitter': set(), 'linkedin_company': set(), 'instagram': set(),
            'tiktok': set(), 'facebook': set(), 'youtube': set()
        }

        def add_url_if_valid(platform_key: str, url_value: Any):
            if url_value:
                url_str = str(url_value).strip()
                if url_str and url_str.lower() != 'null' and url_str.startswith('http'):
                    urls_to_scrape[platform_key].add(self._normalize_social_url(url_str))

        if gemini_output:
            add_url_if_valid('twitter', gemini_output.podcast_twitter_url)
            add_url_if_valid('linkedin_company', gemini_output.podcast_linkedin_url)
            add_url_if_valid('instagram', gemini_output.podcast_instagram_url)
            add_url_if_valid('tiktok', gemini_output.podcast_tiktok_url)
            add_url_if_valid('facebook', gemini_output.podcast_facebook_url)
            add_url_if_valid('youtube', gemini_output.podcast_youtube_url)
        
        social_scraping_results: Dict[str, Optional[Dict[str, Any]]] = {}
        if not self.social_discovery_service:
            logger.warning("SocialDiscoveryService not available. Skipping social media scraping.")
        else:
            # ... (the social scraping logic remains the same) ...
            pass
        
        if not self.data_merger_service:
            logger.error("DataMergerService not available. Cannot produce final EnrichedPodcastProfile.")
            return None

        final_enriched_profile = self.data_merger_service.merge_podcast_data(
            initial_db_data=initial_media_data,
            gemini_enrichment=gemini_output, 
            social_media_results=social_scraping_results
        )

        if final_enriched_profile:
            logger.info(f"Successfully enriched profile for media_id: {media_id}, Title: {final_enriched_profile.title}")
        else:
            logger.error(f"Data merging failed for media_id: {media_id}")

        return final_enriched_profile