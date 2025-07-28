# podcast_outreach/services/chatbot/linkedin_analyzer.py

import json
import asyncio
from typing import Dict, Optional, List
from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

class LinkedInAnalyzer:
    def __init__(self):
        self.social_scraper = SocialDiscoveryService()
        self.gemini_service = GeminiService()
        
    async def analyze_profile(self, linkedin_url: str) -> Dict:
        """Analyze LinkedIn profile and extract relevant data for chatbot"""
        try:
            # Scrape LinkedIn profile
            scrape_results = await self.social_scraper.get_linkedin_data_for_urls([linkedin_url])
            profile_data = scrape_results.get(linkedin_url)
            
            if not profile_data:
                logger.warning(f"No LinkedIn data scraped for {linkedin_url}")
                return {}
            
            # Analyze with Gemini for deeper insights
            analysis_prompt = self._create_analysis_prompt(profile_data)
            gemini_response = await self.gemini_service.create_message(
                prompt=analysis_prompt,
                model="gemini-2.0-flash",
                workflow="chatbot_linkedin_analysis"
            )
            
            # Parse Gemini response
            try:
                # Clean up the response
                gemini_response = gemini_response.strip()
                if gemini_response.startswith("```json"):
                    gemini_response = gemini_response[7:]
                if gemini_response.endswith("```"):
                    gemini_response = gemini_response[:-3]
                gemini_response = gemini_response.strip()
                
                gemini_analysis = json.loads(gemini_response)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse Gemini response as JSON: {e}")
                logger.error(f"Response was: {gemini_response[:500]}...")
                gemini_analysis = {}
            
            # Structure the results
            return self._structure_results(profile_data, gemini_analysis)
            
        except Exception as e:
            logger.error(f"Error analyzing LinkedIn profile: {e}")
            return {}
    
    def _create_analysis_prompt(self, profile_data: Dict) -> str:
        """Create a detailed prompt for Gemini to analyze LinkedIn data"""
        return f"""
        Analyze this LinkedIn profile data to extract information for a podcast guest media kit.
        
        Profile Data:
        Headline: {profile_data.get('headline', 'Not provided')}
        Summary: {profile_data.get('summary', 'Not provided')}
        
        Extract and infer the following information. Return ONLY valid JSON:
        {{
            "professional_bio": "A 2-3 sentence bio suitable for podcast introductions",
            "expertise_keywords": ["keyword1", "keyword2", ...], // 5-10 technical skills or areas
            "years_experience": number or null,
            "success_stories": [
                {{
                    "title": "Brief title",
                    "description": "What happened",
                    "impact": "Results or metrics"
                }}
            ],
            "podcast_topics": ["topic1", "topic2", ...], // 3-5 topics they could discuss
            "unique_perspective": "What makes them unique",
            "target_audience": "Who would benefit from their insights",
            "speaking_style": "professional/casual/academic/storyteller",
            "key_achievements": ["achievement1", "achievement2", ...]
        }}
        
        Focus on:
        1. Extracting concrete examples and metrics
        2. Identifying unique expertise areas
        3. Suggesting podcast-friendly topics
        4. Finding compelling stories or case studies
        5. Creating a professional bio that's concise and engaging
        
        IMPORTANT: Return ONLY the JSON object, no explanations or additional text.
        """
    
    def _structure_results(self, scraped_data: Dict, gemini_analysis: Dict) -> Dict:
        """Structure the combined results for the chatbot"""
        return {
            # Direct data from LinkedIn
            "headline": scraped_data.get("headline"),
            "summary": scraped_data.get("summary"),
            "followers_count": scraped_data.get("followers_count"),
            
            # AI-enhanced data
            "professional_bio": gemini_analysis.get("professional_bio"),
            "expertise_keywords": gemini_analysis.get("expertise_keywords", []),
            "years_experience": gemini_analysis.get("years_experience"),
            "success_stories": gemini_analysis.get("success_stories", []),
            "podcast_topics": gemini_analysis.get("podcast_topics", []),
            "unique_perspective": gemini_analysis.get("unique_perspective"),
            "target_audience": gemini_analysis.get("target_audience"),
            "key_achievements": gemini_analysis.get("key_achievements", []),
            "speaking_style": gemini_analysis.get("speaking_style"),
            
            # Metadata
            "analysis_complete": True,
            "has_professional_summary": bool(scraped_data.get("summary") or gemini_analysis.get("professional_bio")),
            "has_expertise": len(gemini_analysis.get("expertise_keywords", [])) > 0,
            "has_stories": len(gemini_analysis.get("success_stories", [])) > 0
        }