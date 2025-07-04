#!/usr/bin/env python
"""
Migration to add functions for tracking weekly match creation limits.
This ensures we respect the weekly_match_allowance in client_profiles.
"""
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get("PGDATABASE"),
            user=os.environ.get("PGUSER"),
            password=os.environ.get("PGPASSWORD"),
            host=os.environ.get("PGHOST"),
            port=os.environ.get("PGPORT")
        )
        return conn
    except psycopg2.OperationalError as e:
        print(f"Error connecting to the database: {e}")
        return None

def execute_sql(conn, sql_statement, params=None):
    """Executes a given SQL statement."""
    try:
        with conn.cursor() as cur:
            cur.execute(sql_statement, params)
        conn.commit()
        print(f"[OK] Successfully executed: {str(sql_statement)[:100]}...")
    except psycopg2.Error as e:
        print(f"[ERROR] Error executing SQL: {e}")
        if conn:
            conn.rollback()
        raise

def create_check_and_increment_match_function(conn):
    """Create a function to check match limits and increment counter atomically."""
    print("\nCreating check_and_increment_weekly_matches function...")
    
    function_sql = """
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
    """
    
    execute_sql(conn, function_sql)
    print("[OK] Created check_and_increment_weekly_matches function")

def create_reset_weekly_matches_function(conn):
    """Create a function to reset weekly match counts."""
    print("\nCreating reset_weekly_matches function...")
    
    function_sql = """
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
    """
    
    execute_sql(conn, function_sql)
    print("[OK] Created reset_weekly_matches function")

def create_get_match_allowance_status_function(conn):
    """Create a function to get current match allowance status."""
    print("\nCreating get_match_allowance_status function...")
    
    function_sql = """
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
    """
    
    execute_sql(conn, function_sql)
    print("[OK] Created get_match_allowance_status function")

def add_campaign_person_id_function(conn):
    """Create a helper function to get person_id from campaign_id."""
    print("\nCreating get_person_id_from_campaign function...")
    
    function_sql = """
    CREATE OR REPLACE FUNCTION get_person_id_from_campaign(p_campaign_id UUID)
    RETURNS INTEGER AS $$
    BEGIN
        RETURN (SELECT person_id FROM campaigns WHERE campaign_id = p_campaign_id);
    END;
    $$ LANGUAGE plpgsql;
    """
    
    execute_sql(conn, function_sql)
    print("[OK] Created get_person_id_from_campaign function")

def fix_existing_data(conn):
    """Fix existing data by counting current week's matches."""
    print("\nFixing existing weekly match counts...")
    
    fix_sql = """
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
    """
    
    execute_sql(conn, fix_sql)
    
    # Get count of affected rows
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM client_profiles WHERE current_weekly_matches > 0")
        count = cur.fetchone()[0]
        print(f"[OK] Updated weekly match counts for {count} profiles")

def main():
    """Run the migration."""
    print("Match Tracking Functions Migration")
    print("="*60)
    print(f"Started at: {datetime.now()}")
    
    # Connect to database
    conn = get_db_connection()
    if not conn:
        print("[ERROR] Failed to connect to database")
        return
    
    try:
        # Create functions
        create_check_and_increment_match_function(conn)
        create_reset_weekly_matches_function(conn)
        create_get_match_allowance_status_function(conn)
        add_campaign_person_id_function(conn)
        
        # Fix existing data
        fix_existing_data(conn)
        
        print("\n" + "="*60)
        print("[SUCCESS] Migration completed successfully!")
        print("\nUsage examples:")
        print("-- Check and increment match count:")
        print("SELECT * FROM check_and_increment_weekly_matches(person_id, 1);")
        print("\n-- Get current status:")
        print("SELECT * FROM get_match_allowance_status(person_id);")
        print("\n-- Reset all weekly counts (run weekly):")
        print("SELECT reset_weekly_matches();")
        print("="*60)
        
    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()