#!/usr/bin/env python3
"""
Cleanup script to remove backup tables created during vetting score migration.
Only run this after confirming the migration is stable and no rollback is needed.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def cleanup_backup_tables():
    """Remove backup tables created during vetting score migrations."""
    pool = await get_db_pool()
    
    backup_tables = [
        'campaign_media_discoveries_backup_vetting',
        'match_suggestions_backup_vetting',
        'match_suggestions_backup_match_score'
    ]
    
    async with pool.acquire() as conn:
        try:
            logger.info("Starting cleanup of backup tables...")
            
            # Check which backup tables exist
            existing_tables = []
            for table in backup_tables:
                exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = $1
                    );
                """, table)
                
                if exists:
                    existing_tables.append(table)
                    logger.info(f"Found backup table: {table}")
                else:
                    logger.info(f"Backup table not found (already removed?): {table}")
            
            if not existing_tables:
                logger.info("No backup tables found to clean up.")
                return
            
            # Confirm before deletion
            logger.warning(f"\n⚠️  About to DELETE the following backup tables:")
            for table in existing_tables:
                logger.warning(f"  - {table}")
            
            if '--force' not in sys.argv:
                response = input("\nAre you sure you want to delete these backup tables? (yes/no): ")
                if response.lower() != 'yes':
                    logger.info("Cleanup cancelled.")
                    return
            
            # Drop each backup table
            async with conn.transaction():
                for table in existing_tables:
                    logger.info(f"Dropping table: {table}")
                    await conn.execute(f"DROP TABLE IF EXISTS {table};")
                    logger.info(f"✓ Dropped {table}")
            
            logger.info("\n✅ Cleanup completed successfully!")
            logger.info(f"Removed {len(existing_tables)} backup tables.")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
            raise


async def verify_current_scores():
    """Verify current vetting and match scores are in correct range."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        logger.info("\nVerifying current score ranges...")
        
        # Check campaign_media_discoveries
        cmd_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total,
                MIN(vetting_score) as min_score,
                MAX(vetting_score) as max_score
            FROM campaign_media_discoveries
            WHERE vetting_score IS NOT NULL;
        """)
        logger.info(f"campaign_media_discoveries: {dict(cmd_stats)}")
        
        # Check match_suggestions
        ms_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total,
                MIN(vetting_score) as min_v_score,
                MAX(vetting_score) as max_v_score,
                MIN(match_score) as min_m_score,
                MAX(match_score) as max_m_score
            FROM match_suggestions
            WHERE vetting_score IS NOT NULL OR match_score IS NOT NULL;
        """)
        logger.info(f"match_suggestions: {dict(ms_stats)}")


if __name__ == "__main__":
    logger.info("Vetting Score Backup Tables Cleanup")
    logger.info("=" * 50)
    
    # First verify current scores
    asyncio.run(verify_current_scores())
    
    # Then cleanup
    asyncio.run(cleanup_backup_tables())