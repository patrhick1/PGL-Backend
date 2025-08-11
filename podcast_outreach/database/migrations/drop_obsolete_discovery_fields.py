"""
Migration: Drop Obsolete Discovery Fields from client_profiles
================================================================
This migration removes the old discovery tracking fields that have been
replaced by the new match tracking system.

Prerequisites:
- Code has been updated to use new match fields (current_weekly_matches)
- Any remaining data has been migrated to new fields

Fields to drop:
- daily_discovery_allowance (OLD - replaced by match allowance)
- weekly_discovery_allowance (OLD - replaced by weekly_match_allowance)
- current_daily_discoveries (OLD - daily tracking deprecated)
- current_weekly_discoveries (OLD - replaced by current_weekly_matches)
- last_daily_reset (OLD - daily tracking deprecated)
- last_weekly_reset (OLD - replaced by last_weekly_match_reset)

Run: python -m podcast_outreach.database.migrations.drop_obsolete_discovery_fields
"""

import asyncio
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIGRATION_UP = """
-- First, migrate any remaining data from old to new fields
WITH data_migration AS (
    UPDATE client_profiles
    SET 
        -- Ensure new match count has at least the old discovery count
        current_weekly_matches = GREATEST(
            COALESCE(current_weekly_matches, 0),
            COALESCE(current_weekly_discoveries, 0)
        ),
        -- Set weekly match allowance if not already set
        weekly_match_allowance = CASE 
            WHEN weekly_match_allowance IS NULL AND plan_type = 'free' THEN 50
            WHEN weekly_match_allowance IS NULL AND plan_type != 'free' THEN 200
            ELSE weekly_match_allowance
        END,
        updated_at = NOW()
    WHERE current_weekly_discoveries > 0 
       OR weekly_match_allowance IS NULL
    RETURNING person_id, current_weekly_matches, current_weekly_discoveries
)
SELECT COUNT(*) as migrated_rows FROM data_migration;

-- Log the fields we're about to drop for audit purposes
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM client_profiles
    WHERE current_daily_discoveries > 0 
       OR current_weekly_discoveries > 0;
    
    IF v_count > 0 THEN
        RAISE NOTICE 'Found % profiles with non-zero discovery counts that were migrated', v_count;
    END IF;
END $$;

-- Now drop the obsolete columns
ALTER TABLE client_profiles
DROP COLUMN IF EXISTS daily_discovery_allowance CASCADE,
DROP COLUMN IF EXISTS weekly_discovery_allowance CASCADE,
DROP COLUMN IF EXISTS current_daily_discoveries CASCADE,
DROP COLUMN IF EXISTS current_weekly_discoveries CASCADE,
DROP COLUMN IF EXISTS last_daily_reset CASCADE,
DROP COLUMN IF EXISTS last_weekly_reset CASCADE;

-- Add comment to document the change
COMMENT ON TABLE client_profiles IS 
'Client profile tracking match limits and subscription status. Old discovery fields removed in favor of match-based tracking.';

-- Verify the new structure
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'client_profiles'
ORDER BY ordinal_position;
"""

MIGRATION_DOWN = """
-- Re-add the old columns (for rollback purposes)
ALTER TABLE client_profiles
ADD COLUMN IF NOT EXISTS daily_discovery_allowance INTEGER DEFAULT 10,
ADD COLUMN IF NOT EXISTS weekly_discovery_allowance INTEGER DEFAULT 50,
ADD COLUMN IF NOT EXISTS current_daily_discoveries INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS current_weekly_discoveries INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_daily_reset DATE DEFAULT CURRENT_DATE,
ADD COLUMN IF NOT EXISTS last_weekly_reset DATE DEFAULT date_trunc('week', CURRENT_DATE)::date;

-- Restore some data from the new fields (approximate)
UPDATE client_profiles
SET 
    current_weekly_discoveries = COALESCE(current_weekly_matches, 0),
    weekly_discovery_allowance = CASE 
        WHEN plan_type = 'free' THEN 50
        ELSE 200
    END,
    daily_discovery_allowance = CASE 
        WHEN plan_type = 'free' THEN 10
        ELSE 50
    END;

COMMENT ON TABLE client_profiles IS NULL;
"""

async def up():
    """Apply the migration to drop obsolete fields."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # First check current state
            current_columns = await conn.fetch("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'client_profiles'
                ORDER BY ordinal_position
            """)
            
            column_names = [col['column_name'] for col in current_columns]
            obsolete_fields = [
                'daily_discovery_allowance',
                'weekly_discovery_allowance', 
                'current_daily_discoveries',
                'current_weekly_discoveries',
                'last_daily_reset',
                'last_weekly_reset'
            ]
            
            fields_to_drop = [f for f in obsolete_fields if f in column_names]
            
            if not fields_to_drop:
                logger.info("No obsolete fields found - migration may have already been applied")
                return
            
            logger.info(f"Found {len(fields_to_drop)} obsolete fields to drop: {fields_to_drop}")
            
            # Check for any active data in old fields
            data_check = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_profiles,
                    COUNT(CASE WHEN current_daily_discoveries > 0 THEN 1 END) as with_daily_data,
                    COUNT(CASE WHEN current_weekly_discoveries > 0 THEN 1 END) as with_weekly_data,
                    MAX(current_daily_discoveries) as max_daily,
                    MAX(current_weekly_discoveries) as max_weekly
                FROM client_profiles
            """)
            
            if data_check['with_daily_data'] > 0 or data_check['with_weekly_data'] > 0:
                logger.warning(f"Found active data in old fields:")
                logger.warning(f"  - {data_check['with_daily_data']} profiles with daily discovery data (max: {data_check['max_daily']})")
                logger.warning(f"  - {data_check['with_weekly_data']} profiles with weekly discovery data (max: {data_check['max_weekly']})")
                logger.info("This data will be migrated to new match fields before dropping")
            
            # Apply migration
            await conn.execute(MIGRATION_UP)
            
            # Verify new structure
            new_columns = await conn.fetch("""
                SELECT column_name, data_type
                FROM information_schema.columns 
                WHERE table_name = 'client_profiles'
                ORDER BY ordinal_position
            """)
            
            logger.info("="*60)
            logger.info("MIGRATION COMPLETED SUCCESSFULLY")
            logger.info("="*60)
            logger.info(f"Dropped {len(fields_to_drop)} obsolete fields")
            logger.info(f"Table now has {len(new_columns)} columns:")
            
            # List remaining columns
            essential_columns = [
                'client_profile_id', 'person_id', 'plan_type',
                'weekly_match_allowance', 'current_weekly_matches', 
                'last_weekly_match_reset', 'auto_discovery_matches_this_week'
            ]
            
            for col in new_columns:
                name = col['column_name']
                dtype = col['data_type']
                marker = "✓" if name in essential_columns else " "
                logger.info(f"  {marker} {name:35} ({dtype})")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise

async def down():
    """Revert the migration by re-adding obsolete fields."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(MIGRATION_DOWN)
            
            # Verify rollback
            columns = await conn.fetch("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'client_profiles'
                AND column_name IN (
                    'daily_discovery_allowance',
                    'weekly_discovery_allowance',
                    'current_daily_discoveries', 
                    'current_weekly_discoveries',
                    'last_daily_reset',
                    'last_weekly_reset'
                )
            """)
            
            if len(columns) == 6:
                logger.info("Migration reverted successfully - old fields restored")
            else:
                logger.warning(f"Rollback may be incomplete - only {len(columns)}/6 fields restored")
                
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            raise

async def status():
    """Check the current state of client_profiles table."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Get all columns
        columns = await conn.fetch("""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_name = 'client_profiles'
            ORDER BY ordinal_position
        """)
        
        # Check for obsolete fields
        obsolete_fields = [
            'daily_discovery_allowance',
            'weekly_discovery_allowance',
            'current_daily_discoveries',
            'current_weekly_discoveries', 
            'last_daily_reset',
            'last_weekly_reset'
        ]
        
        current_fields = [col['column_name'] for col in columns]
        found_obsolete = [f for f in obsolete_fields if f in current_fields]
        
        # Get usage statistics
        stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_profiles,
                COUNT(CASE WHEN plan_type = 'free' THEN 1 END) as free_users,
                COUNT(CASE WHEN plan_type != 'free' THEN 1 END) as paid_users,
                COUNT(CASE WHEN current_weekly_matches > 0 THEN 1 END) as with_matches,
                MAX(current_weekly_matches) as max_matches
            FROM client_profiles
        """)
        
        logger.info("="*60)
        logger.info("CLIENT_PROFILES TABLE STATUS")
        logger.info("="*60)
        logger.info(f"Total columns: {len(columns)}")
        logger.info(f"Obsolete fields still present: {len(found_obsolete)}")
        
        if found_obsolete:
            logger.warning("⚠️  Found obsolete fields that should be dropped:")
            for field in found_obsolete:
                logger.warning(f"  - {field}")
        else:
            logger.info("✓ No obsolete fields found - table is clean!")
        
        logger.info("\nCurrent fields:")
        for col in columns:
            obsolete_marker = "⚠️ " if col['column_name'] in obsolete_fields else "  "
            logger.info(f"{obsolete_marker}{col['column_name']:35} {col['data_type']:20}")
        
        logger.info(f"\nProfile statistics:")
        logger.info(f"  Total profiles: {stats['total_profiles']}")
        logger.info(f"  Free users: {stats['free_users']}")
        logger.info(f"  Paid users: {stats['paid_users']}")
        logger.info(f"  Users with matches: {stats['with_matches']}")
        logger.info(f"  Max weekly matches: {stats['max_matches']}")

async def main():
    """Run the migration."""
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "down":
            logger.info("Reverting migration...")
            await down()
        elif command == "status":
            await status()
        elif command == "up":
            logger.info("Applying migration...")
            await up()
        else:
            logger.info(f"Unknown command: {sys.argv[1]}")
            logger.info("Usage: python -m <module> [up|down|status]")
    else:
        # Default to status to be safe
        await status()
        logger.info("\nTo apply migration, run with 'up' argument")
        logger.info("To revert migration, run with 'down' argument")

if __name__ == "__main__":
    asyncio.run(main())