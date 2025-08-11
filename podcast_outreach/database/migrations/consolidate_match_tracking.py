"""
Migration: Consolidate Match Tracking for All Users
====================================================
This migration simplifies the match tracking system to use a single field
(current_weekly_matches) for both free and paid users.

Changes:
1. Update weekly_match_allowance: 50 for free, 200 for paid users
2. Create/update trigger to increment current_weekly_matches for ALL quality matches
3. Create reset_all_weekly_counts function for weekly resets
4. Deprecate auto_discovery_matches_this_week field (keep for now, stop using)

Run: python -m podcast_outreach.database.migrations.consolidate_match_tracking
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
-- Step 1: Update weekly_match_allowance for all users
UPDATE client_profiles
SET 
    weekly_match_allowance = CASE 
        WHEN plan_type = 'free' THEN 50
        ELSE 200  -- Paid users get 200
    END,
    updated_at = NOW()
WHERE weekly_match_allowance IS NULL 
   OR (plan_type = 'free' AND weekly_match_allowance != 50)
   OR (plan_type != 'free' AND weekly_match_allowance != 200);

-- Step 2: Migrate any auto_discovery_matches to current_weekly_matches for paid users
UPDATE client_profiles
SET 
    current_weekly_matches = GREATEST(
        COALESCE(current_weekly_matches, 0),
        COALESCE(auto_discovery_matches_this_week, 0)
    ),
    updated_at = NOW()
WHERE plan_type != 'free' 
  AND auto_discovery_matches_this_week > 0;

-- Step 3: Drop and recreate the trigger to increment for ALL users (not just free)
DROP TRIGGER IF EXISTS quality_match_counter ON match_suggestions;
DROP FUNCTION IF EXISTS increment_quality_match_counter();

CREATE OR REPLACE FUNCTION increment_quality_match_counter()
RETURNS TRIGGER AS $$
DECLARE
    v_person_id INTEGER;
    v_plan_type TEXT;
    v_current_matches INTEGER;
    v_weekly_limit INTEGER;
BEGIN
    -- Only count quality matches (score >= 50)
    IF NEW.vetting_score < 50 THEN
        RETURN NEW;
    END IF;
    
    -- Get user details
    SELECT c.person_id, cp.plan_type, cp.current_weekly_matches, cp.weekly_match_allowance
    INTO v_person_id, v_plan_type, v_current_matches, v_weekly_limit
    FROM campaigns c
    LEFT JOIN client_profiles cp ON c.person_id = cp.person_id
    WHERE c.campaign_id = NEW.campaign_id;
    
    IF v_person_id IS NULL THEN
        RETURN NEW;
    END IF;
    
    -- Check if limit would be exceeded
    IF v_weekly_limit IS NOT NULL AND v_current_matches >= v_weekly_limit THEN
        RAISE NOTICE 'User % has reached weekly match limit of %', v_person_id, v_weekly_limit;
        -- Still allow the match to be created, but log the limit breach
    END IF;
    
    -- Increment counter for BOTH free and paid users
    UPDATE client_profiles
    SET current_weekly_matches = COALESCE(current_weekly_matches, 0) + 1,
        updated_at = NOW()
    WHERE person_id = v_person_id;
    
    RAISE NOTICE 'User % (%) now has current_weekly_matches incremented', v_person_id, v_plan_type;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Recreate trigger
CREATE TRIGGER quality_match_counter
AFTER INSERT ON match_suggestions
FOR EACH ROW
EXECUTE FUNCTION increment_quality_match_counter();

-- Step 4: Create the weekly reset function (drop existing first)
DROP FUNCTION IF EXISTS reset_all_weekly_counts();
CREATE OR REPLACE FUNCTION reset_all_weekly_counts()
RETURNS TABLE(
    person_id INTEGER,
    plan_type VARCHAR,
    prev_weekly_matches INTEGER,
    prev_auto_discovery INTEGER,
    weekly_limit INTEGER
) AS $$
BEGIN
    RETURN QUERY
    UPDATE client_profiles cp
    SET 
        current_weekly_matches = 0,
        auto_discovery_matches_this_week = 0,  -- Reset this too for cleanup
        last_weekly_match_reset = NOW(),
        last_auto_discovery_reset = NOW(),
        updated_at = NOW()
    WHERE 
        -- Reset if it's been more than 6 days since last reset
        -- This handles both the Monday reset and any missed resets
        (last_weekly_match_reset IS NULL 
         OR last_weekly_match_reset < NOW() - INTERVAL '6 days')
    RETURNING 
        cp.person_id,
        cp.plan_type,
        current_weekly_matches as prev_weekly_matches,
        auto_discovery_matches_this_week as prev_auto_discovery,
        cp.weekly_match_allowance as weekly_limit;
END;
$$ LANGUAGE plpgsql;

-- Step 5: Create helper function to check if user can create matches
CREATE OR REPLACE FUNCTION can_create_quality_matches(
    p_person_id INTEGER,
    p_matches_to_create INTEGER DEFAULT 1
) RETURNS BOOLEAN AS $$
DECLARE
    v_current_matches INTEGER;
    v_weekly_limit INTEGER;
    v_plan_type VARCHAR;
BEGIN
    SELECT current_weekly_matches, weekly_match_allowance, plan_type
    INTO v_current_matches, v_weekly_limit, v_plan_type
    FROM client_profiles
    WHERE person_id = p_person_id;
    
    -- No profile = no limits (admin users)
    IF NOT FOUND THEN
        RETURN TRUE;
    END IF;
    
    -- Check against limit
    IF v_weekly_limit IS NULL THEN
        RETURN TRUE;  -- No limit set
    END IF;
    
    RETURN (v_current_matches + p_matches_to_create) <= v_weekly_limit;
END;
$$ LANGUAGE plpgsql;

-- Step 6: Update column comments for clarity
COMMENT ON COLUMN client_profiles.current_weekly_matches IS 
'Count of quality matches (vetting_score >= 50) created this week. Used for both free (limit: 50) and paid (limit: 200) users.';

COMMENT ON COLUMN client_profiles.weekly_match_allowance IS 
'Weekly limit for quality matches. 50 for free users, 200 for paid users.';

COMMENT ON COLUMN client_profiles.auto_discovery_matches_this_week IS 
'DEPRECATED: Now using current_weekly_matches for all users. Kept for backward compatibility.';

-- Step 7: Fix any existing data inconsistencies
WITH weekly_quality_matches AS (
    SELECT 
        c.person_id,
        COUNT(ms.match_id) as actual_match_count
    FROM campaigns c
    JOIN match_suggestions ms ON c.campaign_id = ms.campaign_id
    WHERE ms.created_at >= date_trunc('week', CURRENT_DATE)
    AND ms.vetting_score >= 50
    GROUP BY c.person_id
)
UPDATE client_profiles cp
SET 
    current_weekly_matches = GREATEST(
        COALESCE(cp.current_weekly_matches, 0),
        COALESCE(wqm.actual_match_count, 0)
    ),
    updated_at = NOW()
FROM weekly_quality_matches wqm
WHERE cp.person_id = wqm.person_id
  AND cp.current_weekly_matches != wqm.actual_match_count;

-- Log the migration completion
DO $$
DECLARE
    v_free_count INTEGER;
    v_paid_count INTEGER;
    v_total_matches INTEGER;
BEGIN
    SELECT 
        COUNT(CASE WHEN plan_type = 'free' THEN 1 END),
        COUNT(CASE WHEN plan_type != 'free' THEN 1 END),
        SUM(current_weekly_matches)
    INTO v_free_count, v_paid_count, v_total_matches
    FROM client_profiles;
    
    RAISE NOTICE 'Migration completed: % free users, % paid users, % total weekly matches tracked',
        v_free_count, v_paid_count, v_total_matches;
END $$;
"""

MIGRATION_DOWN = """
-- Revert trigger to only increment for free users
DROP TRIGGER IF EXISTS quality_match_counter ON match_suggestions;
DROP FUNCTION IF EXISTS increment_quality_match_counter();

CREATE OR REPLACE FUNCTION increment_quality_match_counter()
RETURNS TRIGGER AS $$
DECLARE
    v_person_id INTEGER;
    v_plan_type TEXT;
BEGIN
    IF NEW.vetting_score < 50 THEN
        RETURN NEW;
    END IF;
    
    SELECT c.person_id, cp.plan_type 
    INTO v_person_id, v_plan_type
    FROM campaigns c
    LEFT JOIN client_profiles cp ON c.person_id = cp.person_id
    WHERE c.campaign_id = NEW.campaign_id;
    
    IF v_person_id IS NULL THEN
        RETURN NEW;
    END IF;
    
    IF v_plan_type = 'free' THEN
        UPDATE client_profiles
        SET current_weekly_matches = COALESCE(current_weekly_matches, 0) + 1,
            updated_at = NOW()
        WHERE person_id = v_person_id;
    ELSE
        UPDATE client_profiles
        SET auto_discovery_matches_this_week = COALESCE(auto_discovery_matches_this_week, 0) + 1,
            updated_at = NOW()
        WHERE person_id = v_person_id
        AND EXISTS (
            SELECT 1 FROM campaigns 
            WHERE campaign_id = NEW.campaign_id 
            AND auto_discovery_status = 'running'
        );
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER quality_match_counter
AFTER INSERT ON match_suggestions
FOR EACH ROW
EXECUTE FUNCTION increment_quality_match_counter();

-- Remove helper functions
DROP FUNCTION IF EXISTS reset_all_weekly_counts();
DROP FUNCTION IF EXISTS can_create_quality_matches(INTEGER, INTEGER);

-- Remove comments
COMMENT ON COLUMN client_profiles.current_weekly_matches IS NULL;
COMMENT ON COLUMN client_profiles.weekly_match_allowance IS NULL;
COMMENT ON COLUMN client_profiles.auto_discovery_matches_this_week IS NULL;
"""

async def up():
    """Apply the migration."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Check current state
            current_state = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_users,
                    COUNT(CASE WHEN plan_type = 'free' THEN 1 END) as free_users,
                    COUNT(CASE WHEN plan_type != 'free' THEN 1 END) as paid_users,
                    SUM(current_weekly_matches) as total_weekly_matches,
                    SUM(auto_discovery_matches_this_week) as total_auto_discovery
                FROM client_profiles
            """)
            
            logger.info("="*60)
            logger.info("BEFORE MIGRATION:")
            logger.info(f"Total users: {current_state['total_users']}")
            logger.info(f"Free users: {current_state['free_users']}")
            logger.info(f"Paid users: {current_state['paid_users']}")
            logger.info(f"Total weekly matches: {current_state['total_weekly_matches']}")
            logger.info(f"Total auto-discovery matches: {current_state['total_auto_discovery']}")
            
            # Apply migration
            await conn.execute(MIGRATION_UP)
            
            # Check new state
            new_state = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_users,
                    COUNT(CASE WHEN weekly_match_allowance = 50 THEN 1 END) as free_users_with_limit,
                    COUNT(CASE WHEN weekly_match_allowance = 200 THEN 1 END) as paid_users_with_limit,
                    SUM(current_weekly_matches) as total_weekly_matches,
                    MAX(current_weekly_matches) as max_weekly_matches
                FROM client_profiles
            """)
            
            # Verify functions were created
            functions_check = await conn.fetch("""
                SELECT proname 
                FROM pg_proc 
                WHERE proname IN ('reset_all_weekly_counts', 'can_create_quality_matches', 'increment_quality_match_counter')
            """)
            
            logger.info("="*60)
            logger.info("MIGRATION COMPLETED SUCCESSFULLY")
            logger.info("="*60)
            logger.info(f"Free users with 50 limit: {new_state['free_users_with_limit']}")
            logger.info(f"Paid users with 200 limit: {new_state['paid_users_with_limit']}")
            logger.info(f"Total weekly matches tracked: {new_state['total_weekly_matches']}")
            logger.info(f"Max weekly matches for any user: {new_state['max_weekly_matches']}")
            logger.info(f"Functions created: {[f['proname'] for f in functions_check]}")
            logger.info("\nKey changes:")
            logger.info("✓ All users now tracked in current_weekly_matches")
            logger.info("✓ Free users: 50 match limit")
            logger.info("✓ Paid users: 200 match limit")
            logger.info("✓ Weekly reset function created")
            logger.info("✓ Trigger updated to increment for all users")
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise

async def down():
    """Revert the migration."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(MIGRATION_DOWN)
            logger.info("Migration reverted successfully")
        except Exception as e:
            logger.error(f"Revert failed: {e}")
            raise

async def status():
    """Check current status of match tracking."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Check if functions exist
        functions = await conn.fetch("""
            SELECT proname 
            FROM pg_proc 
            WHERE proname IN ('reset_all_weekly_counts', 'can_create_quality_matches', 'increment_quality_match_counter')
        """)
        
        # Get user statistics
        stats = await conn.fetch("""
            SELECT 
                plan_type,
                weekly_match_allowance,
                COUNT(*) as user_count,
                AVG(current_weekly_matches)::numeric(5,1) as avg_matches,
                MAX(current_weekly_matches) as max_matches,
                COUNT(CASE WHEN current_weekly_matches >= weekly_match_allowance THEN 1 END) as at_limit
            FROM client_profiles
            GROUP BY plan_type, weekly_match_allowance
            ORDER BY plan_type
        """)
        
        # Check for users near limits
        near_limit = await conn.fetch("""
            SELECT 
                cp.person_id,
                p.email,
                cp.plan_type,
                cp.current_weekly_matches,
                cp.weekly_match_allowance,
                cp.weekly_match_allowance - cp.current_weekly_matches as remaining
            FROM client_profiles cp
            JOIN people p ON cp.person_id = p.person_id
            WHERE cp.current_weekly_matches >= (cp.weekly_match_allowance * 0.8)
            ORDER BY remaining
            LIMIT 10
        """)
        
        logger.info("="*60)
        logger.info("MATCH TRACKING STATUS")
        logger.info("="*60)
        
        logger.info(f"\nFunctions installed: {[f['proname'] for f in functions]}")
        
        logger.info("\nUser statistics by plan:")
        for stat in stats:
            logger.info(f"\n{stat['plan_type'].upper()} USERS:")
            logger.info(f"  Count: {stat['user_count']}")
            logger.info(f"  Weekly limit: {stat['weekly_match_allowance']}")
            logger.info(f"  Avg matches this week: {stat['avg_matches']}")
            logger.info(f"  Max matches this week: {stat['max_matches']}")
            logger.info(f"  Users at limit: {stat['at_limit']}")
        
        if near_limit:
            logger.info("\nUsers near or at limit:")
            for user in near_limit:
                status = "AT LIMIT" if user['remaining'] <= 0 else f"{user['remaining']} remaining"
                logger.info(f"  {user['email'][:30]:30} ({user['plan_type']:4}): {user['current_weekly_matches']}/{user['weekly_match_allowance']} - {status}")

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