#!/usr/bin/env python
"""
Fast script to fix existing podcasts with 'Unknown' or empty names.
This version prioritizes RSS discovery (fast) over Gemini enrichment (slow).
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import aiohttp
from bs4 import BeautifulSoup

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from podcast_outreach.database.connection import get_db_pool, close_db_pool
from podcast_outreach.database.queries import media as media_queries
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
        ORDER BY 
            CASE WHEN rss_url IS NOT NULL THEN 0 ELSE 1 END,  -- Prioritize those with RSS
            media_id DESC
        LIMIT 100;
        """
        rows = await conn.fetch(query)
        return [dict(row) for row in rows]


async def discover_name_from_rss(rss_url: str) -> Optional[str]:
    """Fast RSS-based name discovery."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(rss_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status != 200:
                    return None
                
                content = await response.text()
                soup = BeautifulSoup(content, 'xml')
                
                # Try various title fields in RSS
                title_fields = ['title', 'itunes:title']
                for field in title_fields:
                    title_elem = soup.find(field)
                    if title_elem and title_elem.get_text():
                        title = title_elem.get_text().strip()
                        if title and title.lower() not in ['', 'none', 'null', 'unknown', 'unknown podcast']:
                            return title
                
                return None
                
    except Exception as e:
        logger.debug(f"Error discovering podcast name from RSS {rss_url}: {e}")
        return None


async def batch_fix_with_rss(podcasts: List[Dict[str, Any]]) -> int:
    """Fix podcasts using RSS discovery only (fast)."""
    fixed_count = 0
    
    for podcast in podcasts:
        media_id = podcast['media_id']
        rss_url = podcast.get('rss_url')
        
        if not rss_url:
            continue
            
        try:
            discovered_name = await discover_name_from_rss(rss_url)
            if discovered_name:
                logger.info(f"Discovered name from RSS for media {media_id}: {discovered_name}")
                
                # Update the database
                update_data = {
                    'name': discovered_name,
                    'title': discovered_name
                }
                await media_queries.update_media_with_confidence_check(
                    media_id, update_data, source="rss", confidence=0.95
                )
                fixed_count += 1
                
        except Exception as e:
            logger.error(f"Error fixing podcast {media_id}: {e}")
        
        # Small delay to avoid overwhelming
        await asyncio.sleep(0.1)
    
    return fixed_count


async def main():
    """Main function to fix unknown podcasts."""
    logger.info("Starting fast fix for unknown podcasts...")
    
    # Find unknown podcasts
    unknown_podcasts = await find_unknown_podcasts()
    total_count = len(unknown_podcasts)
    logger.info(f"Found {total_count} podcasts with unknown names")
    
    if not unknown_podcasts:
        logger.info("No unknown podcasts found!")
        return
    
    # Separate podcasts with and without RSS
    with_rss = [p for p in unknown_podcasts if p.get('rss_url')]
    without_rss = [p for p in unknown_podcasts if not p.get('rss_url')]
    
    logger.info(f"Podcasts with RSS URLs: {len(with_rss)}")
    logger.info(f"Podcasts without RSS URLs: {len(without_rss)}")
    
    # Phase 1: Fast RSS-based fixes
    logger.info("Phase 1: Attempting RSS-based name discovery...")
    rss_fixed = await batch_fix_with_rss(with_rss)
    logger.info(f"Fixed {rss_fixed} podcasts using RSS discovery")
    
    # Summary
    logger.info(f"\n=== Summary ===")
    logger.info(f"Total unknown podcasts: {total_count}")
    logger.info(f"Fixed via RSS: {rss_fixed}")
    logger.info(f"Remaining unknown: {total_count - rss_fixed}")
    logger.info(f"Without RSS (need Gemini): {len(without_rss)}")
    
    # Close database pool
    await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())