#!/usr/bin/env python3
"""
Check vetting status for discovery 21
"""

import asyncio
import logging
from podcast_outreach.database.connection import init_db_pool, close_db_pool, get_db_pool

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


async def check_vetting_status():
    """Check vetting status"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Check discovery 21
        query1 = """
        SELECT cmd.*, m.ai_description IS NOT NULL as has_ai_desc,
               c.ideal_podcast_description IS NOT NULL as has_ideal_desc
        FROM campaign_media_discoveries cmd
        JOIN media m ON cmd.media_id = m.media_id
        JOIN campaigns c ON cmd.campaign_id = c.campaign_id
        WHERE cmd.id = 21
        """
        
        row = await conn.fetchrow(query1)
        if row:
            logger.info("Discovery 21 status:")
            logger.info(f"  ID: {row['id']}")
            logger.info(f"  Enrichment status: {row['enrichment_status']}")
            logger.info(f"  Vetting status: {row['vetting_status']}")
            logger.info(f"  Vetting error: {row.get('vetting_error')}")
            logger.info(f"  Has AI description: {row['has_ai_desc']}")
            logger.info(f"  Has ideal description: {row['has_ideal_desc']}")
            logger.info(f"  Updated at: {row['updated_at']}")
        
        # Check what vetting pipeline is looking for
        query2 = """
        SELECT cmd.id, cmd.enrichment_status, cmd.vetting_status, 
               cmd.vetting_error, m.name
        FROM campaign_media_discoveries cmd
        JOIN media m ON cmd.media_id = m.media_id
        JOIN campaigns c ON cmd.campaign_id = c.campaign_id
        WHERE cmd.enrichment_status = 'completed'
        AND cmd.vetting_status = 'pending'
        AND m.ai_description IS NOT NULL
        AND c.ideal_podcast_description IS NOT NULL
        AND (cmd.vetting_error IS NULL OR cmd.vetting_error NOT LIKE 'PROCESSING:%')
        ORDER BY cmd.enrichment_completed_at ASC
        LIMIT 10;
        """
        
        rows = await conn.fetch(query2)
        logger.info(f"\nDiscoveries ready for vetting: {len(rows)}")
        for row in rows:
            logger.info(f"  - ID: {row['id']}, Media: {row['name']}, Status: {row['vetting_status']}")


async def main():
    """Main function"""
    await init_db_pool()
    
    try:
        await check_vetting_status()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())