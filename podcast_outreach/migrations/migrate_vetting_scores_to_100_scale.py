#!/usr/bin/env python3
"""
Migration script to convert vetting scores from 0-10 scale to 0-100 scale.
This updates both the data and the column types.
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


async def migrate_vetting_scores():
    """Migrate vetting scores from 0-10 to 0-100 scale."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                logger.info("Starting vetting score migration...")
                
                # Step 1: Create backup tables
                logger.info("Creating backup tables...")
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS campaign_media_discoveries_backup_vetting AS 
                    SELECT id, vetting_score, vetting_status, vetted_at 
                    FROM campaign_media_discoveries 
                    WHERE vetting_score IS NOT NULL;
                """)
                
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS match_suggestions_backup_vetting AS 
                    SELECT match_id, vetting_score, last_vetted_at 
                    FROM match_suggestions 
                    WHERE vetting_score IS NOT NULL;
                """)
                
                # Step 2: Update vetting scores in campaign_media_discoveries
                logger.info("Updating campaign_media_discoveries vetting scores...")
                await conn.execute("""
                    UPDATE campaign_media_discoveries 
                    SET vetting_score = ROUND(vetting_score * 10)
                    WHERE vetting_score IS NOT NULL 
                    AND vetting_score <= 10;
                """)
                updated_cmd = await conn.fetchval("""
                    SELECT COUNT(*) FROM campaign_media_discoveries 
                    WHERE vetting_score IS NOT NULL;
                """)
                logger.info(f"Updated {updated_cmd} records in campaign_media_discoveries")
                
                # Step 3: Update vetting scores in match_suggestions
                logger.info("Updating match_suggestions vetting scores...")
                await conn.execute("""
                    UPDATE match_suggestions 
                    SET vetting_score = ROUND(vetting_score * 10)
                    WHERE vetting_score IS NOT NULL 
                    AND vetting_score <= 10;
                """)
                updated_ms = await conn.fetchval("""
                    SELECT COUNT(*) FROM match_suggestions 
                    WHERE vetting_score IS NOT NULL;
                """)
                logger.info(f"Updated {updated_ms} records in match_suggestions")
                
                # Step 4: Alter column types to INTEGER
                logger.info("Altering column types...")
                
                # First, alter campaign_media_discoveries
                await conn.execute("""
                    ALTER TABLE campaign_media_discoveries 
                    ALTER COLUMN vetting_score TYPE INTEGER 
                    USING ROUND(vetting_score)::INTEGER;
                """)
                
                # Then, alter match_suggestions
                await conn.execute("""
                    ALTER TABLE match_suggestions 
                    ALTER COLUMN vetting_score TYPE INTEGER 
                    USING ROUND(vetting_score)::INTEGER;
                """)
                
                # Step 5: Add check constraints to ensure valid range
                logger.info("Adding check constraints...")
                await conn.execute("""
                    ALTER TABLE campaign_media_discoveries 
                    ADD CONSTRAINT vetting_score_range 
                    CHECK (vetting_score >= 0 AND vetting_score <= 100);
                """)
                
                await conn.execute("""
                    ALTER TABLE match_suggestions 
                    ADD CONSTRAINT vetting_score_range 
                    CHECK (vetting_score >= 0 AND vetting_score <= 100);
                """)
                
                # Step 6: Verify migration
                logger.info("Verifying migration...")
                
                # Check campaign_media_discoveries
                cmd_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total,
                        MIN(vetting_score) as min_score,
                        MAX(vetting_score) as max_score,
                        AVG(vetting_score) as avg_score
                    FROM campaign_media_discoveries
                    WHERE vetting_score IS NOT NULL;
                """)
                logger.info(f"campaign_media_discoveries stats: {dict(cmd_stats)}")
                
                # Check match_suggestions
                ms_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total,
                        MIN(vetting_score) as min_score,
                        MAX(vetting_score) as max_score,
                        AVG(vetting_score) as avg_score
                    FROM match_suggestions
                    WHERE vetting_score IS NOT NULL;
                """)
                logger.info(f"match_suggestions stats: {dict(ms_stats)}")
                
                logger.info("Migration completed successfully!")
                logger.info("Backup tables created: campaign_media_discoveries_backup_vetting, match_suggestions_backup_vetting")
                
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                raise


async def rollback_migration():
    """Rollback the migration if needed."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                logger.info("Rolling back vetting score migration...")
                
                # Remove constraints
                await conn.execute("ALTER TABLE campaign_media_discoveries DROP CONSTRAINT IF EXISTS vetting_score_range;")
                await conn.execute("ALTER TABLE match_suggestions DROP CONSTRAINT IF EXISTS vetting_score_range;")
                
                # Change columns back to NUMERIC
                await conn.execute("""
                    ALTER TABLE campaign_media_discoveries 
                    ALTER COLUMN vetting_score TYPE NUMERIC(4,2);
                """)
                
                await conn.execute("""
                    ALTER TABLE match_suggestions 
                    ALTER COLUMN vetting_score TYPE NUMERIC;
                """)
                
                # Restore original values
                await conn.execute("""
                    UPDATE campaign_media_discoveries cmd
                    SET vetting_score = backup.vetting_score
                    FROM campaign_media_discoveries_backup_vetting backup
                    WHERE cmd.id = backup.id;
                """)
                
                await conn.execute("""
                    UPDATE match_suggestions ms
                    SET vetting_score = backup.vetting_score
                    FROM match_suggestions_backup_vetting backup
                    WHERE ms.match_id = backup.match_id;
                """)
                
                logger.info("Rollback completed successfully!")
                
            except Exception as e:
                logger.error(f"Rollback failed: {e}")
                raise


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        asyncio.run(rollback_migration())
    else:
        asyncio.run(migrate_vetting_scores())