#!/usr/bin/env python3
"""
Migration to add recipient_email column to pitches table.
This allows storing and overriding the email address used for each pitch,
providing better flexibility and audit trail.
"""

import asyncio
import logging
from datetime import datetime
import asyncpg
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from podcast_outreach.database.connection import get_db_pool, init_db_pool, close_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def add_recipient_email_column():
    """Add recipient_email column to pitches table."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        try:
            # Check if column already exists
            check_query = """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'pitches' 
            AND column_name = 'recipient_email';
            """
            
            existing = await conn.fetchval(check_query)
            
            if existing:
                logger.info("Column 'recipient_email' already exists in pitches table")
                return False
            
            # Add the new column
            logger.info("Adding recipient_email column to pitches table...")
            await conn.execute("""
                ALTER TABLE pitches 
                ADD COLUMN recipient_email TEXT;
            """)
            
            logger.info("Column added successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error adding recipient_email column: {e}")
            raise


async def backfill_recipient_emails():
    """
    Backfill recipient_email for existing pitches using contact_email from media table.
    This ensures existing pitches have the email that would have been used.
    """
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        try:
            # Count pitches that need backfilling
            count_query = """
            SELECT COUNT(*) 
            FROM pitches p
            WHERE p.recipient_email IS NULL
            """
            
            count = await conn.fetchval(count_query)
            logger.info(f"Found {count} pitches that need recipient_email backfilled")
            
            if count == 0:
                return 0
            
            # Backfill recipient_email from media.contact_email
            update_query = """
            UPDATE pitches p
            SET recipient_email = m.contact_email
            FROM media m
            WHERE p.media_id = m.media_id
            AND p.recipient_email IS NULL
            AND m.contact_email IS NOT NULL;
            """
            
            result = await conn.execute(update_query)
            rows_updated = int(result.split()[-1])
            
            logger.info(f"Backfilled recipient_email for {rows_updated} pitches")
            
            # Check if any pitches still don't have recipient_email
            remaining_query = """
            SELECT COUNT(*) 
            FROM pitches p
            LEFT JOIN media m ON p.media_id = m.media_id
            WHERE p.recipient_email IS NULL
            AND (m.contact_email IS NULL OR m.contact_email = '');
            """
            
            remaining = await conn.fetchval(remaining_query)
            if remaining > 0:
                logger.warning(f"{remaining} pitches have no recipient_email because their media has no contact_email")
            
            return rows_updated
            
        except Exception as e:
            logger.error(f"Error backfilling recipient_emails: {e}")
            raise


async def add_index_if_needed():
    """
    Add index on recipient_email for better query performance.
    This is useful if we need to search pitches by email address.
    """
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        try:
            # Check if index already exists
            check_query = """
            SELECT indexname 
            FROM pg_indexes 
            WHERE tablename = 'pitches' 
            AND indexname = 'idx_pitches_recipient_email';
            """
            
            existing = await conn.fetchval(check_query)
            
            if existing:
                logger.info("Index 'idx_pitches_recipient_email' already exists")
                return False
            
            # Create index for recipient_email
            logger.info("Creating index on recipient_email column...")
            await conn.execute("""
                CREATE INDEX idx_pitches_recipient_email 
                ON pitches(recipient_email) 
                WHERE recipient_email IS NOT NULL;
            """)
            
            logger.info("Index created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error creating index: {e}")
            raise


async def verify_migration():
    """Verify the migration was successful."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        try:
            # Check column exists
            check_column = """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'pitches' 
            AND column_name = 'recipient_email';
            """
            
            column_info = await conn.fetchrow(check_column)
            if not column_info:
                logger.error("Column 'recipient_email' not found after migration!")
                return False
            
            logger.info(f"Column info: {dict(column_info)}")
            
            # Check some statistics
            stats_query = """
            SELECT 
                COUNT(*) as total_pitches,
                COUNT(recipient_email) as pitches_with_email,
                COUNT(*) - COUNT(recipient_email) as pitches_without_email
            FROM pitches;
            """
            
            stats = await conn.fetchrow(stats_query)
            logger.info(f"Pitch statistics after migration:")
            logger.info(f"  Total pitches: {stats['total_pitches']}")
            logger.info(f"  Pitches with recipient_email: {stats['pitches_with_email']}")
            logger.info(f"  Pitches without recipient_email: {stats['pitches_without_email']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error verifying migration: {e}")
            return False


async def main():
    """Run the complete migration."""
    try:
        logger.info("=" * 60)
        logger.info("Starting recipient_email migration for pitches table")
        logger.info("=" * 60)
        
        # Initialize database connection
        await init_db_pool()
        
        # Step 1: Add the column
        column_added = await add_recipient_email_column()
        
        # Step 2: Backfill existing data
        if column_added:
            await backfill_recipient_emails()
        
        # Step 3: Add index for performance
        await add_index_if_needed()
        
        # Step 4: Verify the migration
        success = await verify_migration()
        
        if success:
            logger.info("=" * 60)
            logger.info("Migration completed successfully!")
            logger.info("=" * 60)
        else:
            logger.error("Migration verification failed")
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())