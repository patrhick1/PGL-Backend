#!/usr/bin/env python
"""
Migration to add functions for tracking weekly match creation limits.
This ensures we respect the weekly_match_allowance in client_profiles.
"""
import asyncpg
from datetime import datetime

async def migrate_up(conn: asyncpg.Connection):
    """Apply the migration."""
    print("[004] Adding match tracking functions...")
    
    # Create check_and_increment_weekly_matches function
    await conn.execute("""
    CREATE OR REPLACE FUNCTION check_and_increment_weekly_matches(
        p_person_id INTEGER,
        p_increment INTEGER DEFAULT 1
    ) RETURNS TABLE (
        allowed BOOLEAN,
        current_count INTEGER,
        weekly_limit INTEGER,
        message TEXT
    ) AS $$
    DECLARE
        v_current_count INTEGER;
        v_weekly_limit INTEGER;
        v_last_reset TIMESTAMPTZ;
        v_week_start TIMESTAMPTZ;
    BEGIN
        -- Calculate the start of the current week (Monday)
        v_week_start := date_trunc('week', CURRENT_TIMESTAMP);
        
        -- Get current profile data with row lock
        SELECT 
            current_weekly_matches,
            weekly_match_allowance,
            last_weekly_match_reset
        INTO 
            v_current_count,
            v_weekly_limit,
            v_last_reset
        FROM client_profiles
        WHERE person_id = p_person_id
        FOR UPDATE;
        
        -- If no profile found, deny
        IF NOT FOUND THEN
            RETURN QUERY SELECT 
                FALSE::BOOLEAN as allowed,
                0::INTEGER as current_count,
                0::INTEGER as weekly_limit,
                'No client profile found'::TEXT as message;
            RETURN;
        END IF;
        
        -- Check if we need to reset the weekly counter
        IF v_last_reset IS NULL OR v_last_reset < v_week_start THEN
            -- Reset the counter
            UPDATE client_profiles
            SET current_weekly_matches = 0,
                last_weekly_match_reset = CURRENT_TIMESTAMP
            WHERE person_id = p_person_id;
            
            v_current_count := 0;
        END IF;
        
        -- Check if adding matches would exceed limit
        IF v_current_count + p_increment > v_weekly_limit THEN
            RETURN QUERY SELECT 
                FALSE::BOOLEAN as allowed,
                v_current_count::INTEGER as current_count,
                v_weekly_limit::INTEGER as weekly_limit,
                format('Weekly match limit reached. Current: %s, Limit: %s', 
                    v_current_count, v_weekly_limit)::TEXT as message;
            RETURN;
        END IF;
        
        -- Increment the counter
        UPDATE client_profiles
        SET current_weekly_matches = current_weekly_matches + p_increment,
            updated_at = CURRENT_TIMESTAMP
        WHERE person_id = p_person_id;
        
        RETURN QUERY SELECT 
            TRUE::BOOLEAN as allowed,
            (v_current_count + p_increment)::INTEGER as current_count,
            v_weekly_limit::INTEGER as weekly_limit,
            'Match count updated successfully'::TEXT as message;
    END;
    $$ LANGUAGE plpgsql;
    """)
    print("  [OK] Created check_and_increment_weekly_matches function")
    
    # Create reset_weekly_matches function
    await conn.execute("""
    CREATE OR REPLACE FUNCTION reset_weekly_matches() RETURNS INTEGER AS $$
    DECLARE
        v_count INTEGER;
        v_week_start TIMESTAMPTZ;
    BEGIN
        -- Calculate the start of the current week (Monday)
        v_week_start := date_trunc('week', CURRENT_TIMESTAMP);
        
        -- Reset counters for profiles that haven't been reset this week
        WITH updated AS (
            UPDATE client_profiles
            SET current_weekly_matches = 0,
                last_weekly_match_reset = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE last_weekly_match_reset IS NULL 
               OR last_weekly_match_reset < v_week_start
            RETURNING 1
        )
        SELECT COUNT(*) INTO v_count FROM updated;
        
        RETURN v_count;
    END;
    $$ LANGUAGE plpgsql;
    """)
    print("  [OK] Created reset_weekly_matches function")
    
    # Create get_match_allowance_status function
    await conn.execute("""
    CREATE OR REPLACE FUNCTION get_match_allowance_status(p_person_id INTEGER)
    RETURNS TABLE (
        current_weekly_matches INTEGER,
        weekly_match_allowance INTEGER,
        remaining_matches INTEGER,
        last_reset TIMESTAMPTZ,
        needs_reset BOOLEAN
    ) AS $$
    DECLARE
        v_week_start TIMESTAMPTZ;
    BEGIN
        v_week_start := date_trunc('week', CURRENT_TIMESTAMP);
        
        RETURN QUERY
        SELECT 
            cp.current_weekly_matches,
            cp.weekly_match_allowance,
            (cp.weekly_match_allowance - cp.current_weekly_matches)::INTEGER as remaining_matches,
            cp.last_weekly_match_reset,
            (cp.last_weekly_match_reset IS NULL OR cp.last_weekly_match_reset < v_week_start) as needs_reset
        FROM client_profiles cp
        WHERE cp.person_id = p_person_id;
    END;
    $$ LANGUAGE plpgsql;
    """)
    print("  [OK] Created get_match_allowance_status function")
    
    # Create helper function
    await conn.execute("""
    CREATE OR REPLACE FUNCTION get_person_id_from_campaign(p_campaign_id UUID)
    RETURNS INTEGER AS $$
    BEGIN
        RETURN (SELECT person_id FROM campaigns WHERE campaign_id = p_campaign_id);
    END;
    $$ LANGUAGE plpgsql;
    """)
    print("  [OK] Created get_person_id_from_campaign function")
    
    # Fix existing data
    await conn.execute("""
    -- Update current_weekly_matches based on actual matches created this week
    WITH weekly_counts AS (
        SELECT 
            c.person_id,
            COUNT(ms.match_id) as match_count
        FROM match_suggestions ms
        JOIN campaigns c ON ms.campaign_id = c.campaign_id
        WHERE ms.created_at >= date_trunc('week', CURRENT_TIMESTAMP)
        GROUP BY c.person_id
    )
    UPDATE client_profiles cp
    SET 
        current_weekly_matches = COALESCE(wc.match_count, 0),
        last_weekly_match_reset = date_trunc('week', CURRENT_TIMESTAMP),
        updated_at = CURRENT_TIMESTAMP
    FROM weekly_counts wc
    WHERE cp.person_id = wc.person_id;
    """)
    
    # Get count of affected rows
    result = await conn.fetchval("""
        SELECT COUNT(*) FROM client_profiles WHERE current_weekly_matches > 0
    """)
    print(f"  [OK] Updated weekly match counts for {result} profiles")
    
    print("[004] Match tracking functions migration completed successfully!")

async def migrate_down(conn: asyncpg.Connection):
    """Rollback the migration."""
    print("[004] Rolling back match tracking functions...")
    
    # Drop functions in reverse order
    await conn.execute("DROP FUNCTION IF EXISTS get_person_id_from_campaign(UUID);")
    await conn.execute("DROP FUNCTION IF EXISTS get_match_allowance_status(INTEGER);")
    await conn.execute("DROP FUNCTION IF EXISTS reset_weekly_matches();")
    await conn.execute("DROP FUNCTION IF EXISTS check_and_increment_weekly_matches(INTEGER, INTEGER);")
    
    # Reset the counter columns
    await conn.execute("""
        UPDATE client_profiles 
        SET current_weekly_matches = 0,
            last_weekly_match_reset = NULL
        WHERE current_weekly_matches > 0;
    """)
    
    print("[004] Match tracking functions rolled back successfully!")