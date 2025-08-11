"""
Migration to add match notification tracking
- Adds notification preferences to client_profiles
- Creates a minimal notification log table for tracking sent notifications
"""

import asyncio
import logging
import sys
import os

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, parent_dir)

# Now we can import from podcast_outreach
from podcast_outreach.database.connection import get_db_pool

logger = logging.getLogger(__name__)

async def up():
    """Add notification tracking fields and table"""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        try:
            # Add notification preferences to client_profiles
            alter_client_profiles = """
            ALTER TABLE client_profiles 
            ADD COLUMN IF NOT EXISTS match_notification_enabled BOOLEAN DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS match_notification_threshold INTEGER DEFAULT 30,
            ADD COLUMN IF NOT EXISTS last_match_notification_sent TIMESTAMPTZ;
            """
            await conn.execute(alter_client_profiles)
            logger.info("Added notification fields to client_profiles")
            
            # Create a minimal notification log table
            # We need this because:
            # 1. Track notifications per campaign (a client can have multiple campaigns)
            # 2. Maintain history of all notifications sent
            # 3. Prevent duplicate notifications
            create_log_table = """
            CREATE TABLE IF NOT EXISTS match_notification_log (
                id SERIAL PRIMARY KEY,
                campaign_id UUID NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
                person_id INTEGER NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
                match_count INTEGER NOT NULL,
                sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            
            -- Index for checking when we last sent notification for a campaign
            CREATE INDEX IF NOT EXISTS idx_notification_log_campaign_sent 
                ON match_notification_log(campaign_id, sent_at DESC);
            """
            await conn.execute(create_log_table)
            logger.info("Created match_notification_log table")
            
            logger.info("Migration completed successfully")
            
        except Exception as e:
            logger.error(f"Error in migration: {e}")
            raise

async def down():
    """Remove notification tracking fields and table"""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        try:
            # Drop the notification log table
            await conn.execute("DROP TABLE IF EXISTS match_notification_log CASCADE;")
            logger.info("Dropped match_notification_log table")
            
            # Remove fields from client_profiles
            alter_query = """
            ALTER TABLE client_profiles 
            DROP COLUMN IF EXISTS match_notification_enabled,
            DROP COLUMN IF EXISTS match_notification_threshold,
            DROP COLUMN IF EXISTS last_match_notification_sent;
            """
            await conn.execute(alter_query)
            logger.info("Removed notification fields from client_profiles")
            
        except Exception as e:
            logger.error(f"Error in rollback: {e}")
            raise

async def main():
    """Run the migration"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "down":
        print("Rolling back migration...")
        await down()
        print("Rollback completed")
    else:
        print("Running migration...")
        await up()
        print("Migration completed")

if __name__ == "__main__":
    asyncio.run(main())