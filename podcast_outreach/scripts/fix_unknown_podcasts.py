#!/usr/bin/env python
"""
Script to fix existing podcasts with 'Unknown' or empty names.
This will attempt to discover the actual podcast names using RSS feeds or re-enrichment.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from podcast_outreach.database.connection import get_db_pool, close_db_pool
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.services.enrichment.enrichment_agent import EnrichmentAgent
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService
from podcast_outreach.services.enrichment.data_merger import DataMergerService
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)


async def find_unknown_podcasts() -> List[Dict[str, Any]]:
    """Find all podcasts with unknown or empty names."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        query = """
        SELECT media_id, name, title, rss_url, api_id, source_api
        FROM media 
        WHERE (name IS NULL OR name = '' OR name = 'Unknown' OR name = 'Unknown Podcast'
               OR title IS NULL OR title = '' OR title = 'Unknown' OR title = 'Unknown Podcast')
        AND media_id > 0
        AND rss_url IS NOT NULL
        ORDER BY media_id DESC
        LIMIT 50;
        """
        rows = await conn.fetch(query)
        return [dict(row) for row in rows]


async def fix_podcast_name(media_data: Dict[str, Any], enrichment_agent: EnrichmentAgent) -> bool:
    """Attempt to fix a single podcast's name."""
    media_id = media_data['media_id']
    logger.info(f"Attempting to fix podcast name for media_id: {media_id}")
    
    try:
        # First try RSS discovery if we have an RSS URL
        if media_data.get('rss_url'):
            discovered_name = await enrichment_agent._discover_podcast_name_from_rss(media_data['rss_url'])
            if discovered_name and discovered_name != 'Unknown Podcast':
                logger.info(f"Discovered name from RSS for media {media_id}: {discovered_name}")
                
                # Update the database
                update_data = {
                    'name': discovered_name,
                    'title': discovered_name
                }
                await media_queries.update_media_with_confidence_check(media_id, update_data, source="manual", confidence=1.0)
                return True
        
        # If RSS didn't work, try Gemini enrichment
        logger.info(f"Attempting Gemini enrichment for media {media_id}")
        enrichment_result = await enrichment_agent._discover_initial_info_with_gemini_and_tavily(media_data)
        
        if enrichment_result and enrichment_result.podcast_name:
            logger.info(f"Discovered name from Gemini for media {media_id}: {enrichment_result.podcast_name}")
            
            # Update the database
            update_data = {
                'name': enrichment_result.podcast_name,
                'title': enrichment_result.podcast_name
            }
            await media_queries.update_media_with_confidence_check(media_id, update_data, source="llm", confidence=0.9)
            return True
            
    except Exception as e:
        logger.error(f"Error fixing podcast {media_id}: {e}")
        return False
    
    logger.warning(f"Could not discover name for media {media_id}")
    return False


async def main():
    """Main function to fix unknown podcasts."""
    logger.info("Starting fix for unknown podcasts...")
    
    # Initialize services
    gemini_service = GeminiService()
    social_discovery = SocialDiscoveryService()
    data_merger = DataMergerService()
    enrichment_agent = EnrichmentAgent(gemini_service, social_discovery, data_merger)
    
    # Find unknown podcasts
    unknown_podcasts = await find_unknown_podcasts()
    logger.info(f"Found {len(unknown_podcasts)} podcasts with unknown names")
    
    if not unknown_podcasts:
        logger.info("No unknown podcasts found!")
        return
    
    # Fix them
    fixed_count = 0
    for podcast in unknown_podcasts:
        success = await fix_podcast_name(podcast, enrichment_agent)
        if success:
            fixed_count += 1
        
        # Add a small delay to avoid overwhelming APIs
        await asyncio.sleep(2)
    
    logger.info(f"Fixed {fixed_count} out of {len(unknown_podcasts)} unknown podcasts")
    
    # Close database pool
    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())