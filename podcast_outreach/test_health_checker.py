#!/usr/bin/env python3
"""
Test the health checker to see why it's not fixing discovery 21
"""

import asyncio
import logging
from podcast_outreach.database.connection import init_db_pool, close_db_pool, get_db_pool
from podcast_outreach.services.tasks.health_checker import WorkflowHealthChecker

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


async def check_discovery_21_status():
    """Check current status of discovery 21"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        query = """
        SELECT 
            cmd.*,
            m.last_enriched_timestamp,
            m.quality_score,
            m.ai_description IS NOT NULL as has_ai_description,
            m.episode_summaries_compiled IS NOT NULL as has_episode_summaries
        FROM campaign_media_discoveries cmd
        JOIN media m ON cmd.media_id = m.media_id
        WHERE cmd.id = 21
        """
        row = await conn.fetchrow(query)
        if row:
            logger.info("Discovery 21 current status:")
            logger.info(f"  Enrichment status: {row['enrichment_status']}")
            logger.info(f"  Vetting status: {row['vetting_status']}")
            logger.info(f"  Media enriched: {row['last_enriched_timestamp'] is not None}")
            logger.info(f"  Has quality score: {row['quality_score'] is not None}")
            logger.info(f"  Has AI description: {row['has_ai_description']}")
            logger.info(f"  Has episode summaries: {row['has_episode_summaries']}")
            logger.info(f"  Updated at: {row['updated_at']}")
            return dict(row)
        return None


async def manually_run_health_check():
    """Run health checker manually"""
    logger.info("\nRunning health checker manually...")
    checker = WorkflowHealthChecker()
    results = await checker.run_health_check()
    
    logger.info(f"\nHealth check results:")
    logger.info(f"  Issues found: {results['issues_found']}")
    logger.info(f"  Issues fixed: {results['issues_fixed']}")
    
    for detail in results['details']:
        if detail['found'] > 0:
            logger.info(f"\n  {detail['check']}:")
            logger.info(f"    Found: {detail['found']}")
            logger.info(f"    Fixed: {detail['fixed']}")
            if 'details' in detail and detail['details']:
                for item in detail['details'][:3]:  # Show first 3
                    logger.info(f"    - {item}")
    
    return results


async def force_fix_discovery_21():
    """Force fix discovery 21 specifically"""
    logger.info("\nForce fixing discovery 21...")
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Check if media is actually enriched
        check_query = """
        SELECT 
            m.media_id,
            m.last_enriched_timestamp IS NOT NULL as is_enriched,
            m.quality_score IS NOT NULL as has_quality_score,
            m.ai_description IS NOT NULL as has_ai_description,
            m.episode_summaries_compiled IS NOT NULL as has_episode_summaries
        FROM campaign_media_discoveries cmd
        JOIN media m ON cmd.media_id = m.media_id
        WHERE cmd.id = 21
        """
        
        media_check = await conn.fetchrow(check_query)
        if media_check:
            logger.info(f"Media checks:")
            logger.info(f"  Is enriched: {media_check['is_enriched']}")
            logger.info(f"  Has quality score: {media_check['has_quality_score']}")
            logger.info(f"  Has AI description: {media_check['has_ai_description']}")
            logger.info(f"  Has episode summaries: {media_check['has_episode_summaries']}")
            
            # If all checks pass, update the discovery
            if all([media_check['is_enriched'], media_check['has_quality_score'], 
                    media_check['has_ai_description'], media_check['has_episode_summaries']]):
                
                update_query = """
                UPDATE campaign_media_discoveries
                SET enrichment_status = 'completed',
                    vetting_status = 'pending',
                    vetting_error = NULL,
                    updated_at = NOW()
                WHERE id = 21
                RETURNING *
                """
                
                result = await conn.fetchrow(update_query)
                if result:
                    logger.info("✓ Successfully updated discovery 21")
                    logger.info(f"  New enrichment status: {result['enrichment_status']}")
                    logger.info(f"  New vetting status: {result['vetting_status']}")
            else:
                logger.warning("Media 11 is not fully enriched yet!")


async def main():
    """Main function"""
    await init_db_pool()
    
    try:
        # Check current status
        await check_discovery_21_status()
        
        # Run health check
        await manually_run_health_check()
        
        # Check status again
        logger.info("\n--- After health check ---")
        status = await check_discovery_21_status()
        
        # If still not fixed, force fix it
        if status and status['enrichment_status'] != 'completed':
            await force_fix_discovery_21()
            
            # Final check
            logger.info("\n--- After force fix ---")
            await check_discovery_21_status()
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())