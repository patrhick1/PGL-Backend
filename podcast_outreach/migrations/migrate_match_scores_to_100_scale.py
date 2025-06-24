#!/usr/bin/env python3
"""
Migration script to convert match_scores from 0-10 scale to 0-100 scale.
This complements the vetting_score migration.
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


async def migrate_match_scores():
    """Migrate match scores from 0-10 to 0-100 scale."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                logger.info("Starting match score migration...")
                
                # Step 1: Create backup table for match_score
                logger.info("Creating backup table...")
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS match_suggestions_backup_match_score AS 
                    SELECT match_id, match_score 
                    FROM match_suggestions 
                    WHERE match_score IS NOT NULL;
                """)
                
                # Step 2: Count records before update
                count_before = await conn.fetchval("""
                    SELECT COUNT(*) FROM match_suggestions 
                    WHERE match_score IS NOT NULL;
                """)
                logger.info(f"Found {count_before} records with match scores to update")
                
                # Step 3: Update match scores (multiply by 10)
                logger.info("Updating match_suggestions match scores...")
                await conn.execute("""
                    UPDATE match_suggestions 
                    SET match_score = ROUND(match_score * 10)
                    WHERE match_score IS NOT NULL 
                    AND match_score <= 10;
                """)
                
                # Step 4: Alter column type to INTEGER
                logger.info("Altering column type...")
                await conn.execute("""
                    ALTER TABLE match_suggestions 
                    ALTER COLUMN match_score TYPE INTEGER 
                    USING ROUND(match_score)::INTEGER;
                """)
                
                # Step 5: Add check constraint
                logger.info("Adding check constraint...")
                await conn.execute("""
                    ALTER TABLE match_suggestions 
                    ADD CONSTRAINT match_score_range 
                    CHECK (match_score >= 0 AND match_score <= 100);
                """)
                
                # Step 6: Verify migration
                logger.info("Verifying migration...")
                
                stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total,
                        MIN(match_score) as min_score,
                        MAX(match_score) as max_score,
                        AVG(match_score) as avg_score
                    FROM match_suggestions
                    WHERE match_score IS NOT NULL;
                """)
                logger.info(f"Match score stats after migration: {dict(stats)}")
                
                # Verify correlation with vetting scores
                correlation = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total,
                        AVG(ABS(match_score - vetting_score)) as avg_difference
                    FROM match_suggestions
                    WHERE match_score IS NOT NULL 
                    AND vetting_score IS NOT NULL;
                """)
                logger.info(f"Score correlation: {dict(correlation)}")
                
                logger.info("Migration completed successfully!")
                logger.info("Backup table created: match_suggestions_backup_match_score")
                
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                raise


async def rollback_migration():
    """Rollback the match score migration if needed."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                logger.info("Rolling back match score migration...")
                
                # Remove constraint
                await conn.execute("ALTER TABLE match_suggestions DROP CONSTRAINT IF EXISTS match_score_range;")
                
                # Change column back to NUMERIC
                await conn.execute("""
                    ALTER TABLE match_suggestions 
                    ALTER COLUMN match_score TYPE NUMERIC;
                """)
                
                # Restore original values
                await conn.execute("""
                    UPDATE match_suggestions ms
                    SET match_score = backup.match_score
                    FROM match_suggestions_backup_match_score backup
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
        asyncio.run(migrate_match_scores())