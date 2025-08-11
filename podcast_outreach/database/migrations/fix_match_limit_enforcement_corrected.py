"""
Migration: Fix Match Limit Enforcement (CORRECTED)
===================================================
Ensures that current_weekly_matches is properly incremented when quality
match_suggestions (vetting_score >= 50) are created.

This ensures automated discovery stops when limit is reached:
- Free users: 50 quality matches per week
- Paid users: tracked separately via auto_discovery_matches_this_week

The automated discovery service already checks current_weekly_matches < 50
for free users, so we just need to ensure the counter is incremented.

Run: python -m podcast_outreach.database.migrations.fix_match_limit_enforcement_corrected
"""

import asyncio
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file FIRST
load_dotenv()

# Now import database connection after env vars are loaded
from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIGRATION_UP = """
-- Trigger to increment match counter when quality match is created
CREATE OR REPLACE FUNCTION increment_quality_match_counter()
RETURNS TRIGGER AS $$
DECLARE
    v_person_id INTEGER;
    v_plan_type TEXT;
BEGIN
    -- Only count quality matches (score >= 50)
    IF NEW.vetting_score < 50 THEN
        RETURN NEW;
    END IF;
    
    -- Get person_id and plan_type from campaign
    SELECT c.person_id, cp.plan_type 
    INTO v_person_id, v_plan_type
    FROM campaigns c
    LEFT JOIN client_profiles cp ON c.person_id = cp.person_id
    WHERE c.campaign_id = NEW.campaign_id;
    
    IF v_person_id IS NULL THEN
        RETURN NEW;
    END IF;
    
    -- Update the appropriate counter based on plan type
    IF v_plan_type = 'free' THEN
        -- Free users: increment current_weekly_matches
        UPDATE client_profiles
        SET current_weekly_matches = COALESCE(current_weekly_matches, 0) + 1,
            updated_at = NOW()
        WHERE person_id = v_person_id;
        
        RAISE NOTICE 'Free user % now has current_weekly_matches incremented', v_person_id;
    ELSE
        -- Paid users: increment auto_discovery_matches_this_week if it's from auto-discovery
        -- (we'd need to track this in match_suggestions table or check campaign status)
        UPDATE client_profiles
        SET auto_discovery_matches_this_week = COALESCE(auto_discovery_matches_this_week, 0) + 1,
            updated_at = NOW()
        WHERE person_id = v_person_id
        AND EXISTS (
            SELECT 1 FROM campaigns 
            WHERE campaign_id = NEW.campaign_id 
            AND auto_discovery_status = 'running'
        );
        
        RAISE NOTICE 'Paid user % match counted', v_person_id;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger on match_suggestions table
DROP TRIGGER IF EXISTS quality_match_counter ON match_suggestions;
CREATE TRIGGER quality_match_counter
AFTER INSERT ON match_suggestions
FOR EACH ROW
EXECUTE FUNCTION increment_quality_match_counter();

-- Fix existing counts based on quality matches created this week
WITH weekly_quality_matches AS (
    SELECT 
        c.person_id,
        cp.plan_type,
        COUNT(ms.match_id) as match_count
    FROM campaigns c
    JOIN match_suggestions ms ON c.campaign_id = ms.campaign_id
    JOIN client_profiles cp ON c.person_id = cp.person_id
    WHERE ms.created_at >= date_trunc('week', CURRENT_DATE)
    AND ms.vetting_score >= 50  -- Only quality matches
    GROUP BY c.person_id, cp.plan_type
)
UPDATE client_profiles cp
SET 
    current_weekly_matches = CASE 
        WHEN wqm.plan_type = 'free' THEN COALESCE(wqm.match_count, 0)
        ELSE cp.current_weekly_matches  -- Don't change for paid users
    END,
    auto_discovery_matches_this_week = CASE
        WHEN wqm.plan_type != 'free' THEN COALESCE(wqm.match_count, 0)
        ELSE cp.auto_discovery_matches_this_week  -- Don't change for free users
    END,
    last_weekly_match_reset = date_trunc('week', CURRENT_DATE),
    updated_at = NOW()
FROM weekly_quality_matches wqm
WHERE cp.person_id = wqm.person_id;

-- Add function to check if limit would be exceeded BEFORE creating match
CREATE OR REPLACE FUNCTION check_match_limit_before_insert(
    p_campaign_id UUID,
    p_vetting_score NUMERIC
) RETURNS BOOLEAN AS $$
DECLARE
    v_person_id INTEGER;
    v_plan_type TEXT;
    v_current_matches INTEGER;
    v_weekly_limit INTEGER;
BEGIN
    -- Only check for quality matches
    IF p_vetting_score < 50 THEN
        RETURN TRUE; -- Allow low-score matches
    END IF;
    
    -- Get user details
    SELECT c.person_id, cp.plan_type, cp.current_weekly_matches, cp.weekly_match_allowance
    INTO v_person_id, v_plan_type, v_current_matches, v_weekly_limit
    FROM campaigns c
    JOIN client_profiles cp ON c.person_id = cp.person_id
    WHERE c.campaign_id = p_campaign_id;
    
    -- No profile = admin/unlimited
    IF NOT FOUND THEN
        RETURN TRUE;
    END IF;
    
    -- Check limits based on plan type
    IF v_plan_type = 'free' THEN
        IF v_current_matches >= 50 THEN
            RAISE NOTICE 'Free user % has reached 50 match weekly limit', v_person_id;
            RETURN FALSE;
        END IF;
    ELSE
        -- Paid users have a different limit for auto-discovery
        DECLARE
            v_auto_matches INTEGER;
        BEGIN
            SELECT auto_discovery_matches_this_week 
            INTO v_auto_matches
            FROM client_profiles 
            WHERE person_id = v_person_id;
            
            -- Check if this is from auto-discovery and if limit reached
            IF EXISTS (
                SELECT 1 FROM campaigns 
                WHERE campaign_id = p_campaign_id 
                AND auto_discovery_status = 'running'
            ) AND v_auto_matches >= 200 THEN
                RAISE NOTICE 'Paid user % has reached 200 auto-discovery limit', v_person_id;
                RETURN FALSE;
            END IF;
        END;
    END IF;
    
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- Add comments to clarify field usage
COMMENT ON COLUMN client_profiles.current_weekly_matches IS 
'For FREE users: Count of quality matches (vetting_score >= 50) this week. Limit: 50/week. Used by automated discovery.';

COMMENT ON COLUMN client_profiles.auto_discovery_matches_this_week IS 
'For PAID users: Count of matches from automated discovery this week. Limit: 200/week.';

COMMENT ON COLUMN client_profiles.weekly_match_allowance IS 
'Weekly limit for quality matches. 50 for free, higher for paid plans.';
"""

MIGRATION_DOWN = """
-- Remove the trigger and functions
DROP TRIGGER IF EXISTS quality_match_counter ON match_suggestions;
DROP FUNCTION IF EXISTS increment_quality_match_counter();
DROP FUNCTION IF EXISTS check_match_limit_before_insert(UUID, NUMERIC);

-- Reset counters
UPDATE client_profiles 
SET current_weekly_matches = 0,
    auto_discovery_matches_this_week = 0;

-- Remove comments
COMMENT ON COLUMN client_profiles.current_weekly_matches IS NULL;
COMMENT ON COLUMN client_profiles.auto_discovery_matches_this_week IS NULL;
COMMENT ON COLUMN client_profiles.weekly_match_allowance IS NULL;
"""

async def up():
    """Apply the migration."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(MIGRATION_UP)
            
            # Get statistics
            stats = await conn.fetchrow("""
                WITH match_counts AS (
                    SELECT 
                        cp.plan_type,
                        COUNT(DISTINCT cp.person_id) as user_count,
                        AVG(cp.current_weekly_matches)::numeric(5,1) as avg_weekly_matches,
                        MAX(cp.current_weekly_matches) as max_weekly_matches,
                        COUNT(DISTINCT CASE 
                            WHEN cp.plan_type = 'free' AND cp.current_weekly_matches >= 50 
                            THEN cp.person_id 
                        END) as free_at_limit,
                        COUNT(DISTINCT CASE 
                            WHEN cp.plan_type != 'free' AND cp.auto_discovery_matches_this_week >= 200 
                            THEN cp.person_id 
                        END) as paid_at_auto_limit
                    FROM client_profiles cp
                    GROUP BY cp.plan_type
                )
                SELECT 
                    SUM(user_count) as total_users,
                    SUM(CASE WHEN plan_type = 'free' THEN user_count ELSE 0 END) as free_users,
                    MAX(CASE WHEN plan_type = 'free' THEN avg_weekly_matches ELSE 0 END) as avg_free_matches,
                    MAX(CASE WHEN plan_type = 'free' THEN max_weekly_matches ELSE 0 END) as max_free_matches,
                    MAX(free_at_limit) as free_at_limit,
                    MAX(paid_at_auto_limit) as paid_at_auto_limit
                FROM match_counts
            """)
            
            logger.info("="*60)
            logger.info("MIGRATION APPLIED SUCCESSFULLY")
            logger.info("="*60)
            logger.info(f"Total users: {stats['total_users']}")
            logger.info(f"Free users: {stats['free_users']}")
            logger.info(f"Average weekly matches (free): {stats['avg_free_matches'] or 0}")
            logger.info(f"Max weekly matches (free): {stats['max_free_matches'] or 0}")
            logger.info(f"Free users at 50-match limit: {stats['free_at_limit'] or 0}")
            logger.info(f"Paid users at 200 auto-discovery limit: {stats['paid_at_auto_limit'] or 0}")
            logger.info("\nKey changes:")
            logger.info("✓ Trigger added to increment current_weekly_matches for quality matches")
            logger.info("✓ Free users: limited to 50 quality matches/week")
            logger.info("✓ Paid users: limited to 200 auto-discovery matches/week")
            logger.info("✓ Automated discovery will now stop when limits are reached")
            
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
    """Check current status of match limits and automated discovery."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Check if trigger exists
        trigger_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM pg_trigger 
                WHERE tgname = 'quality_match_counter'
            )
        """)
        
        # Get users near or at limits
        at_limit_users = await conn.fetch("""
            SELECT 
                cp.person_id,
                p.email,
                cp.plan_type,
                cp.current_weekly_matches,
                cp.weekly_match_allowance,
                cp.auto_discovery_matches_this_week,
                COUNT(c.campaign_id) as active_campaigns
            FROM client_profiles cp
            JOIN people p ON p.person_id = cp.person_id
            LEFT JOIN campaigns c ON c.person_id = cp.person_id 
                AND c.auto_discovery_enabled = TRUE
            WHERE 
                (cp.plan_type = 'free' AND cp.current_weekly_matches >= 45)  -- Near limit
                OR (cp.plan_type != 'free' AND cp.auto_discovery_matches_this_week >= 180)
            GROUP BY cp.person_id, p.email, cp.plan_type, cp.current_weekly_matches, 
                     cp.weekly_match_allowance, cp.auto_discovery_matches_this_week
            ORDER BY cp.current_weekly_matches DESC
            LIMIT 10
        """)
        
        logger.info("="*60)
        logger.info("MATCH LIMIT STATUS")
        logger.info("="*60)
        logger.info(f"Quality match counter trigger installed: {trigger_exists}")
        logger.info("\nUsers near or at weekly limits:")
        
        for user in at_limit_users:
            if user['plan_type'] == 'free':
                status = "AT LIMIT" if user['current_weekly_matches'] >= 50 else "NEAR LIMIT"
                logger.info(
                    f"  FREE: {user['email'][:30]:30} - "
                    f"{user['current_weekly_matches']}/50 matches - {status}"
                    f" ({user['active_campaigns']} active campaigns)"
                )
            else:
                status = "AT AUTO LIMIT" if user['auto_discovery_matches_this_week'] >= 200 else "NEAR LIMIT"
                logger.info(
                    f"  PAID: {user['email'][:30]:30} - "
                    f"{user['auto_discovery_matches_this_week']}/200 auto-discoveries - {status}"
                    f" ({user['active_campaigns']} active campaigns)"
                )
        
        # Check if automated discovery is respecting limits
        blocked_campaigns = await conn.fetch("""
            SELECT 
                c.campaign_id,
                c.campaign_name,
                cp.plan_type,
                cp.current_weekly_matches,
                p.email
            FROM campaigns c
            JOIN client_profiles cp ON c.person_id = cp.person_id
            JOIN people p ON c.person_id = p.person_id
            WHERE c.auto_discovery_enabled = TRUE
            AND cp.plan_type = 'free'
            AND cp.current_weekly_matches >= 50
            LIMIT 5
        """)
        
        if blocked_campaigns:
            logger.info("\nCampaigns that SHOULD be blocked from auto-discovery:")
            for camp in blocked_campaigns:
                logger.info(
                    f"  Campaign '{camp['campaign_name'][:20]}' - "
                    f"Owner: {camp['email'][:20]} - "
                    f"Matches: {camp['current_weekly_matches']}/50"
                )

async def main():
    """Run the migration."""
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "down":
            logger.info("Reverting migration...")
            await down()
        elif sys.argv[1] == "status":
            await status()
        else:
            logger.info(f"Unknown command: {sys.argv[1]}")
            logger.info("Usage: python -m <module> [up|down|status]")
    else:
        logger.info("Applying migration...")
        await up()

if __name__ == "__main__":
    asyncio.run(main())