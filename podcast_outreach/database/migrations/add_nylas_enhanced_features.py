# podcast_outreach/database/migrations/add_nylas_enhanced_features.py

"""
Enhanced Nylas Migration Script
This migration adds comprehensive Nylas tracking features including:
- Enhanced pitch tracking fields (open count, click count, tracking labels)
- Message events table for complete audit trail
- Contact status management for bounce handling
- Send queue for throttling and scheduled sends
- Additional tracking fields not in the original migration

Run: python add_nylas_enhanced_features.py
Rollback: python add_nylas_enhanced_features.py rollback
"""

import psycopg2
from psycopg2 import sql
import logging
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, parent_dir)

from podcast_outreach.database.schema import get_db_connection, execute_sql

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_existing_fields(conn):
    """Check which fields already exist to avoid conflicts."""
    logger.info("Checking existing database schema...")
    
    cursor = conn.cursor()
    existing_fields = {
        'campaigns': [],
        'pitches': [],
        'people': []
    }
    
    # Check existing columns for each table
    for table in existing_fields.keys():
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = %s
        """, (table,))
        existing_fields[table] = [row[0] for row in cursor.fetchall()]
    
    # Check if tables exist
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    existing_tables = [row[0] for row in cursor.fetchall()]
    
    cursor.close()
    return existing_fields, existing_tables


def add_enhanced_pitch_fields(conn, existing_fields):
    """Add enhanced tracking fields to pitches table."""
    logger.info("Adding enhanced tracking fields to pitches table...")
    
    fields_to_add = []
    
    # Check which fields need to be added
    pitch_fields = existing_fields.get('pitches', [])
    
    if 'tracking_label' not in pitch_fields:
        fields_to_add.append("ADD COLUMN IF NOT EXISTS tracking_label VARCHAR(255)")
    if 'open_count' not in pitch_fields:
        fields_to_add.append("ADD COLUMN IF NOT EXISTS open_count INTEGER DEFAULT 0")
    if 'click_count' not in pitch_fields:
        fields_to_add.append("ADD COLUMN IF NOT EXISTS click_count INTEGER DEFAULT 0")
    if 'scheduled_send_at' not in pitch_fields:
        fields_to_add.append("ADD COLUMN IF NOT EXISTS scheduled_send_at TIMESTAMPTZ")
    if 'send_status' not in pitch_fields:
        fields_to_add.append("ADD COLUMN IF NOT EXISTS send_status VARCHAR(50) DEFAULT 'pending'")
    
    if fields_to_add:
        alter_sql = f"ALTER TABLE pitches {', '.join(fields_to_add)};"
        try:
            execute_sql(conn, alter_sql)
            logger.info(f"Successfully added {len(fields_to_add)} new fields to pitches table")
        except psycopg2.Error as e:
            logger.error(f"Error adding enhanced fields to pitches: {e}")
            raise
    else:
        logger.info("All enhanced pitch fields already exist")


def create_message_events_table(conn, existing_tables):
    """Create message_events table for comprehensive event tracking."""
    if 'message_events' in existing_tables:
        logger.info("Table message_events already exists, skipping...")
        return
    
    logger.info("Creating message_events table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS message_events (
        event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        message_id VARCHAR(255) NOT NULL,
        pitch_id INTEGER REFERENCES pitches(pitch_id),
        event_type VARCHAR(50) NOT NULL, -- opened, clicked, bounced, replied, send_success, send_failed
        timestamp TIMESTAMPTZ NOT NULL,
        payload_json JSONB,
        ip_address INET,
        user_agent TEXT,
        link_url TEXT,
        is_duplicate BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS idx_message_events_message_id 
        ON message_events(message_id);
    CREATE INDEX IF NOT EXISTS idx_message_events_pitch_id 
        ON message_events(pitch_id);
    CREATE INDEX IF NOT EXISTS idx_message_events_type_timestamp 
        ON message_events(event_type, timestamp);
    CREATE INDEX IF NOT EXISTS idx_message_events_created_at 
        ON message_events(created_at);
    
    -- Add comment for documentation
    COMMENT ON TABLE message_events IS 
    'Comprehensive tracking of all email events from Nylas webhooks. 
    Includes deduplication support and full event payload storage for audit trail.';
    """
    
    try:
        execute_sql(conn, create_sql)
        logger.info("Successfully created message_events table")
    except psycopg2.Error as e:
        logger.error(f"Error creating message_events table: {e}")
        raise


def create_contact_status_table(conn, existing_tables):
    """Create contact_status table for email deliverability management."""
    if 'contact_status' in existing_tables:
        logger.info("Table contact_status already exists, skipping...")
        return
    
    logger.info("Creating contact_status table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS contact_status (
        email VARCHAR(255) PRIMARY KEY,
        status VARCHAR(50) DEFAULT 'active' 
            CHECK (status IN ('active', 'bounced', 'cleaned', 'do_not_contact')),
        last_bounce_reason TEXT,
        bounce_count INTEGER DEFAULT 0,
        hard_bounce_count INTEGER DEFAULT 0,
        soft_bounce_count INTEGER DEFAULT 0,
        do_not_contact BOOLEAN DEFAULT FALSE,
        do_not_contact_reason TEXT,
        last_activity_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS idx_contact_status_status 
        ON contact_status(status);
    CREATE INDEX IF NOT EXISTS idx_contact_status_do_not_contact 
        ON contact_status(do_not_contact);
    CREATE INDEX IF NOT EXISTS idx_contact_status_updated_at 
        ON contact_status(updated_at);
    
    -- Create trigger for updated_at
    CREATE OR REPLACE FUNCTION update_contact_status_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    
    DROP TRIGGER IF EXISTS trigger_update_contact_status_updated_at ON contact_status;
    CREATE TRIGGER trigger_update_contact_status_updated_at
    BEFORE UPDATE ON contact_status
    FOR EACH ROW
    EXECUTE FUNCTION update_contact_status_updated_at();
    
    COMMENT ON TABLE contact_status IS 
    'Manages email deliverability status and compliance. 
    Tracks bounces and do-not-contact preferences for GDPR/CAN-SPAM compliance.';
    """
    
    try:
        execute_sql(conn, create_sql)
        logger.info("Successfully created contact_status table")
    except psycopg2.Error as e:
        logger.error(f"Error creating contact_status table: {e}")
        raise


def create_send_queue_table(conn, existing_tables):
    """Create send_queue table for throttling and scheduled sends."""
    if 'send_queue' in existing_tables:
        logger.info("Table send_queue already exists, skipping...")
        return
    
    logger.info("Creating send_queue table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS send_queue (
        queue_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        pitch_id INTEGER REFERENCES pitches(pitch_id) ON DELETE CASCADE,
        grant_id VARCHAR(255) NOT NULL,
        scheduled_for TIMESTAMPTZ NOT NULL,
        priority INTEGER DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),
        attempts INTEGER DEFAULT 0,
        max_attempts INTEGER DEFAULT 3,
        last_attempt_at TIMESTAMPTZ,
        status VARCHAR(50) DEFAULT 'pending' 
            CHECK (status IN ('pending', 'processing', 'sent', 'failed', 'cancelled')),
        error_message TEXT,
        metadata JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS idx_send_queue_status_scheduled 
        ON send_queue(status, scheduled_for) 
        WHERE status IN ('pending', 'processing');
    CREATE INDEX IF NOT EXISTS idx_send_queue_grant_id 
        ON send_queue(grant_id);
    CREATE INDEX IF NOT EXISTS idx_send_queue_pitch_id 
        ON send_queue(pitch_id);
    CREATE INDEX IF NOT EXISTS idx_send_queue_priority 
        ON send_queue(priority DESC, scheduled_for);
    
    -- Create trigger for updated_at
    CREATE OR REPLACE FUNCTION update_send_queue_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    
    DROP TRIGGER IF EXISTS trigger_update_send_queue_updated_at ON send_queue;
    CREATE TRIGGER trigger_update_send_queue_updated_at
    BEFORE UPDATE ON send_queue
    FOR EACH ROW
    EXECUTE FUNCTION update_send_queue_updated_at();
    
    COMMENT ON TABLE send_queue IS 
    'Manages email send throttling and scheduling. 
    Enforces rate limits (700/day per grant) and handles scheduled sends with retry logic.';
    """
    
    try:
        execute_sql(conn, create_sql)
        logger.info("Successfully created send_queue table")
    except psycopg2.Error as e:
        logger.error(f"Error creating send_queue table: {e}")
        raise


def create_grant_send_limits_table(conn, existing_tables):
    """Create table to track daily/hourly send limits per grant."""
    if 'grant_send_limits' in existing_tables:
        logger.info("Table grant_send_limits already exists, skipping...")
        return
    
    logger.info("Creating grant_send_limits table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS grant_send_limits (
        grant_id VARCHAR(255) PRIMARY KEY,
        daily_limit INTEGER DEFAULT 700,
        hourly_limit INTEGER DEFAULT 50,
        current_daily_count INTEGER DEFAULT 0,
        current_hourly_count INTEGER DEFAULT 0,
        daily_reset_at TIMESTAMPTZ DEFAULT NOW(),
        hourly_reset_at TIMESTAMPTZ DEFAULT NOW(),
        total_sent_all_time INTEGER DEFAULT 0,
        last_send_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS idx_grant_send_limits_reset 
        ON grant_send_limits(daily_reset_at, hourly_reset_at);
    
    -- Create trigger for updated_at
    CREATE OR REPLACE FUNCTION update_grant_send_limits_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    
    DROP TRIGGER IF EXISTS trigger_update_grant_send_limits_updated_at ON grant_send_limits;
    CREATE TRIGGER trigger_update_grant_send_limits_updated_at
    BEFORE UPDATE ON grant_send_limits
    FOR EACH ROW
    EXECUTE FUNCTION update_grant_send_limits_updated_at();
    
    COMMENT ON TABLE grant_send_limits IS 
    'Tracks send limits per Nylas grant to prevent rate limiting. 
    Default: 700/day, 50/hour per grant as recommended by Nylas.';
    """
    
    try:
        execute_sql(conn, create_sql)
        logger.info("Successfully created grant_send_limits table")
    except psycopg2.Error as e:
        logger.error(f"Error creating grant_send_limits table: {e}")
        raise


def create_domain_health_table(conn, existing_tables):
    """Create table to track domain health metrics."""
    if 'domain_health' in existing_tables:
        logger.info("Table domain_health already exists, skipping...")
        return
    
    logger.info("Creating domain_health table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS domain_health (
        domain VARCHAR(255) PRIMARY KEY,
        spf_status VARCHAR(50),
        dkim_status VARCHAR(50),
        dmarc_status VARCHAR(50),
        bounce_rate NUMERIC(5,2),
        complaint_rate NUMERIC(5,2),
        reputation_score NUMERIC(3,2),
        last_checked_at TIMESTAMPTZ,
        total_sent INTEGER DEFAULT 0,
        total_bounced INTEGER DEFAULT 0,
        total_complaints INTEGER DEFAULT 0,
        notes TEXT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS idx_domain_health_reputation 
        ON domain_health(reputation_score);
    CREATE INDEX IF NOT EXISTS idx_domain_health_last_checked 
        ON domain_health(last_checked_at);
    
    -- Create trigger for updated_at
    CREATE OR REPLACE FUNCTION update_domain_health_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    
    DROP TRIGGER IF EXISTS trigger_update_domain_health_updated_at ON domain_health;
    CREATE TRIGGER trigger_update_domain_health_updated_at
    BEFORE UPDATE ON domain_health
    FOR EACH ROW
    EXECUTE FUNCTION update_domain_health_updated_at();
    
    COMMENT ON TABLE domain_health IS 
    'Tracks email domain health metrics including SPF/DKIM/DMARC status 
    and reputation scores for deliverability monitoring.';
    """
    
    try:
        execute_sql(conn, create_sql)
        logger.info("Successfully created domain_health table")
    except psycopg2.Error as e:
        logger.error(f"Error creating domain_health table: {e}")
        raise


def create_automation_rules_table(conn, existing_tables):
    """Create table for automation rules configuration."""
    if 'automation_rules' in existing_tables:
        logger.info("Table automation_rules already exists, skipping...")
        return
    
    logger.info("Creating automation_rules table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS automation_rules (
        rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        rule_name VARCHAR(255) NOT NULL,
        rule_type VARCHAR(50) NOT NULL 
            CHECK (rule_type IN ('bounce', 'reply', 'open', 'click', 'no_engagement')),
        trigger_conditions JSONB NOT NULL,
        actions JSONB NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        priority INTEGER DEFAULT 5,
        campaign_id UUID REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        applies_to_all_campaigns BOOLEAN DEFAULT FALSE,
        execution_count INTEGER DEFAULT 0,
        last_executed_at TIMESTAMPTZ,
        created_by VARCHAR(255),
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    
    CREATE INDEX IF NOT EXISTS idx_automation_rules_active 
        ON automation_rules(is_active, rule_type) 
        WHERE is_active = TRUE;
    CREATE INDEX IF NOT EXISTS idx_automation_rules_campaign 
        ON automation_rules(campaign_id);
    CREATE INDEX IF NOT EXISTS idx_automation_rules_priority 
        ON automation_rules(priority DESC);
    
    -- Create trigger for updated_at
    CREATE OR REPLACE FUNCTION update_automation_rules_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    
    DROP TRIGGER IF EXISTS trigger_update_automation_rules_updated_at ON automation_rules;
    CREATE TRIGGER trigger_update_automation_rules_updated_at
    BEFORE UPDATE ON automation_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_automation_rules_updated_at();
    
    COMMENT ON TABLE automation_rules IS 
    'Configurable automation rules for email events. 
    Defines triggers and actions for bounce handling, follow-ups, and engagement tracking.';
    """
    
    try:
        execute_sql(conn, create_sql)
        logger.info("Successfully created automation_rules table")
    except psycopg2.Error as e:
        logger.error(f"Error creating automation_rules table: {e}")
        raise


def add_helper_functions(conn):
    """Add helper database functions for Nylas operations."""
    logger.info("Creating helper functions...")
    
    functions_sql = """
    -- Function to increment send counts with automatic reset
    CREATE OR REPLACE FUNCTION increment_grant_send_count(p_grant_id VARCHAR)
    RETURNS BOOLEAN AS $$
    DECLARE
        can_send BOOLEAN := FALSE;
    BEGIN
        -- Insert or update grant limits
        INSERT INTO grant_send_limits (grant_id, current_daily_count, current_hourly_count, last_send_at)
        VALUES (p_grant_id, 1, 1, NOW())
        ON CONFLICT (grant_id) DO UPDATE
        SET 
            -- Reset daily count if needed
            current_daily_count = CASE 
                WHEN grant_send_limits.daily_reset_at < NOW() - INTERVAL '24 hours' 
                THEN 1 
                ELSE grant_send_limits.current_daily_count + 1 
            END,
            daily_reset_at = CASE 
                WHEN grant_send_limits.daily_reset_at < NOW() - INTERVAL '24 hours' 
                THEN NOW() 
                ELSE grant_send_limits.daily_reset_at 
            END,
            -- Reset hourly count if needed
            current_hourly_count = CASE 
                WHEN grant_send_limits.hourly_reset_at < NOW() - INTERVAL '1 hour' 
                THEN 1 
                ELSE grant_send_limits.current_hourly_count + 1 
            END,
            hourly_reset_at = CASE 
                WHEN grant_send_limits.hourly_reset_at < NOW() - INTERVAL '1 hour' 
                THEN NOW() 
                ELSE grant_send_limits.hourly_reset_at 
            END,
            total_sent_all_time = grant_send_limits.total_sent_all_time + 1,
            last_send_at = NOW();
        
        -- Check if we can send
        SELECT 
            current_daily_count <= daily_limit AND 
            current_hourly_count <= hourly_limit
        INTO can_send
        FROM grant_send_limits
        WHERE grant_id = p_grant_id;
        
        RETURN can_send;
    END;
    $$ LANGUAGE plpgsql;
    
    -- Function to check if we can send for a grant
    CREATE OR REPLACE FUNCTION can_send_for_grant(p_grant_id VARCHAR)
    RETURNS BOOLEAN AS $$
    DECLARE
        can_send BOOLEAN := TRUE;
        daily_count INTEGER;
        hourly_count INTEGER;
        daily_limit_val INTEGER;
        hourly_limit_val INTEGER;
    BEGIN
        SELECT 
            current_daily_count,
            current_hourly_count,
            daily_limit,
            hourly_limit
        INTO 
            daily_count,
            hourly_count,
            daily_limit_val,
            hourly_limit_val
        FROM grant_send_limits
        WHERE grant_id = p_grant_id;
        
        IF NOT FOUND THEN
            -- No record exists, we can send
            RETURN TRUE;
        END IF;
        
        -- Check limits
        IF daily_count >= daily_limit_val OR hourly_count >= hourly_limit_val THEN
            RETURN FALSE;
        END IF;
        
        RETURN TRUE;
    END;
    $$ LANGUAGE plpgsql;
    
    -- Function to update contact status after bounce
    CREATE OR REPLACE FUNCTION update_contact_bounce_status(
        p_email VARCHAR,
        p_bounce_type VARCHAR,
        p_bounce_reason TEXT
    )
    RETURNS VOID AS $$
    BEGIN
        INSERT INTO contact_status (
            email, 
            status, 
            last_bounce_reason,
            bounce_count,
            hard_bounce_count,
            soft_bounce_count,
            last_activity_at
        )
        VALUES (
            LOWER(p_email),
            CASE WHEN p_bounce_type = 'hard_bounce' THEN 'bounced' ELSE 'active' END,
            p_bounce_reason,
            1,
            CASE WHEN p_bounce_type = 'hard_bounce' THEN 1 ELSE 0 END,
            CASE WHEN p_bounce_type = 'soft_bounce' THEN 1 ELSE 0 END,
            NOW()
        )
        ON CONFLICT (email) DO UPDATE
        SET 
            status = CASE 
                WHEN contact_status.hard_bounce_count >= 1 OR p_bounce_type = 'hard_bounce' 
                THEN 'bounced' 
                WHEN contact_status.soft_bounce_count >= 3 
                THEN 'bounced'
                ELSE contact_status.status 
            END,
            last_bounce_reason = p_bounce_reason,
            bounce_count = contact_status.bounce_count + 1,
            hard_bounce_count = contact_status.hard_bounce_count + 
                CASE WHEN p_bounce_type = 'hard_bounce' THEN 1 ELSE 0 END,
            soft_bounce_count = contact_status.soft_bounce_count + 
                CASE WHEN p_bounce_type = 'soft_bounce' THEN 1 ELSE 0 END,
            last_activity_at = NOW();
    END;
    $$ LANGUAGE plpgsql;
    
    COMMENT ON FUNCTION increment_grant_send_count IS 
    'Increments send count for a grant and returns whether sending is allowed based on limits';
    
    COMMENT ON FUNCTION can_send_for_grant IS 
    'Checks if a grant has capacity to send based on daily/hourly limits';
    
    COMMENT ON FUNCTION update_contact_bounce_status IS 
    'Updates contact status after a bounce event';
    """
    
    try:
        execute_sql(conn, functions_sql)
        logger.info("Successfully created helper functions")
    except psycopg2.Error as e:
        logger.error(f"Error creating helper functions: {e}")
        raise


def run_migration():
    """Run the complete enhanced Nylas migration."""
    logger.info("="*60)
    logger.info("Starting Enhanced Nylas Features Migration")
    logger.info("="*60)
    
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        raise Exception("Database connection failed")
    
    try:
        # Check what already exists
        existing_fields, existing_tables = check_existing_fields(conn)
        
        logger.info(f"Found {len(existing_tables)} existing tables")
        
        # Run migration steps
        logger.info("\n--- Step 1: Adding enhanced pitch fields ---")
        add_enhanced_pitch_fields(conn, existing_fields)
        
        logger.info("\n--- Step 2: Creating message_events table ---")
        create_message_events_table(conn, existing_tables)
        
        logger.info("\n--- Step 3: Creating contact_status table ---")
        create_contact_status_table(conn, existing_tables)
        
        logger.info("\n--- Step 4: Creating send_queue table ---")
        create_send_queue_table(conn, existing_tables)
        
        logger.info("\n--- Step 5: Creating grant_send_limits table ---")
        create_grant_send_limits_table(conn, existing_tables)
        
        logger.info("\n--- Step 6: Creating domain_health table ---")
        create_domain_health_table(conn, existing_tables)
        
        logger.info("\n--- Step 7: Creating automation_rules table ---")
        create_automation_rules_table(conn, existing_tables)
        
        logger.info("\n--- Step 8: Adding helper functions ---")
        add_helper_functions(conn)
        
        # Commit all changes
        conn.commit()
        
        logger.info("\n" + "="*60)
        logger.info("[SUCCESS] Enhanced Nylas migration completed successfully!")
        logger.info("="*60)
        
        # Print summary
        print_migration_summary()
        
    except Exception as e:
        # Rollback on any error
        conn.rollback()
        logger.error(f"[ERROR] Migration failed, rolling back: {e}")
        raise
    finally:
        conn.close()


def rollback_migration():
    """Rollback the enhanced Nylas migration."""
    logger.info("="*60)
    logger.info("Rolling back Enhanced Nylas Features Migration")
    logger.info("="*60)
    
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        raise Exception("Database connection failed")
    
    try:
        # Drop new tables
        logger.info("Dropping new tables...")
        drop_tables_sql = """
        DROP TABLE IF EXISTS automation_rules CASCADE;
        DROP TABLE IF EXISTS domain_health CASCADE;
        DROP TABLE IF EXISTS grant_send_limits CASCADE;
        DROP TABLE IF EXISTS send_queue CASCADE;
        DROP TABLE IF EXISTS contact_status CASCADE;
        DROP TABLE IF EXISTS message_events CASCADE;
        """
        execute_sql(conn, drop_tables_sql)
        
        # Drop functions
        logger.info("Dropping helper functions...")
        drop_functions_sql = """
        DROP FUNCTION IF EXISTS increment_grant_send_count(VARCHAR) CASCADE;
        DROP FUNCTION IF EXISTS can_send_for_grant(VARCHAR) CASCADE;
        DROP FUNCTION IF EXISTS update_contact_bounce_status(VARCHAR, VARCHAR, TEXT) CASCADE;
        DROP FUNCTION IF EXISTS update_contact_status_updated_at() CASCADE;
        DROP FUNCTION IF EXISTS update_send_queue_updated_at() CASCADE;
        DROP FUNCTION IF EXISTS update_grant_send_limits_updated_at() CASCADE;
        DROP FUNCTION IF EXISTS update_domain_health_updated_at() CASCADE;
        DROP FUNCTION IF EXISTS update_automation_rules_updated_at() CASCADE;
        """
        execute_sql(conn, drop_functions_sql)
        
        # Remove enhanced fields from pitches table
        logger.info("Removing enhanced fields from pitches table...")
        alter_pitches_sql = """
        ALTER TABLE pitches
        DROP COLUMN IF EXISTS tracking_label,
        DROP COLUMN IF EXISTS open_count,
        DROP COLUMN IF EXISTS click_count,
        DROP COLUMN IF EXISTS scheduled_send_at,
        DROP COLUMN IF EXISTS send_status;
        """
        execute_sql(conn, alter_pitches_sql)
        
        conn.commit()
        
        logger.info("\n" + "="*60)
        logger.info("[SUCCESS] Enhanced Nylas migration rolled back successfully")
        logger.info("="*60)
        
    except Exception as e:
        conn.rollback()
        logger.error(f"[ERROR] Rollback failed: {e}")
        raise
    finally:
        conn.close()


def print_migration_summary():
    """Print a summary of what was added in the migration."""
    summary = """
    
    MIGRATION SUMMARY
    ===================
    
    New Tables Added:
    ----------------
    1. message_events       - Complete audit trail of all email events
    2. contact_status       - Email deliverability and bounce management
    3. send_queue          - Throttling and scheduled send management
    4. grant_send_limits   - Per-grant rate limiting (700/day, 50/hour)
    5. domain_health       - SPF/DKIM/DMARC and reputation tracking
    6. automation_rules    - Configurable automation for events
    
    Enhanced Fields Added to 'pitches':
    -----------------------------------
    - tracking_label       - Custom tracking labels for campaigns
    - open_count          - Aggregate open tracking
    - click_count         - Aggregate click tracking
    - scheduled_send_at   - Support for scheduled sends
    - send_status         - Detailed send status tracking
    
    Helper Functions Added:
    ----------------------
    - increment_grant_send_count()  - Rate limit enforcement
    - can_send_for_grant()         - Check send capacity
    - update_contact_bounce_status() - Automatic bounce handling
    
    Next Steps:
    ----------
    1. Update your .env file with Nylas webhook secret if not done
    2. Configure webhooks in Nylas dashboard to point to your endpoint
    3. Test the enhanced tracking with a test campaign
    4. Monitor the message_events table for incoming webhooks
    5. Set up automation rules as needed
    
    Rate Limits:
    -----------
    Default limits per grant:
    - Daily: 700 emails
    - Hourly: 50 emails
    
    These can be adjusted in the grant_send_limits table.
    """
    
    print(summary)


def check_migration_status():
    """Check the current status of the migration."""
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        return
    
    try:
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN (
                'message_events', 'contact_status', 'send_queue',
                'grant_send_limits', 'domain_health', 'automation_rules'
            )
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        
        print("\n[STATUS] Migration Status Check")
        print("=" * 40)
        print(f"Enhanced Nylas tables found: {len(tables)}/6")
        
        if tables:
            print("\nExisting tables:")
            for table in tables:
                print(f"  [OK] {table[0]}")
        
        # Check enhanced pitch fields
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'pitches'
            AND column_name IN (
                'tracking_label', 'open_count', 'click_count',
                'scheduled_send_at', 'send_status'
            );
        """)
        fields = cursor.fetchall()
        
        print(f"\nEnhanced pitch fields found: {len(fields)}/5")
        if fields:
            print("Existing fields:")
            for field in fields:
                print(f"  [OK] {field[0]}")
        
        cursor.close()
        
    except Exception as e:
        logger.error(f"Error checking migration status: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "rollback":
            rollback_migration()
        elif sys.argv[1] == "status":
            check_migration_status()
        else:
            print("Usage: python add_nylas_enhanced_features.py [rollback|status]")
    else:
        run_migration()