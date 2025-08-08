# podcast_outreach/database/migrations/add_campaign_email_accounts.py

"""
Database migration to support multiple email accounts per campaign.
This allows campaigns to use multiple email addresses for outreach.
"""

import psycopg2
from psycopg2 import sql
import logging
from podcast_outreach.database.schema import get_db_connection, execute_sql

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_campaign_email_accounts_table(conn):
    """Create table to manage multiple email accounts per campaign."""
    logger.info("Creating campaign_email_accounts table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS campaign_email_accounts (
        id SERIAL PRIMARY KEY,
        campaign_id UUID NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        email_address VARCHAR(255) NOT NULL,
        display_name VARCHAR(255),
        email_provider VARCHAR(50) NOT NULL DEFAULT 'nylas',
        
        -- Nylas-specific fields
        nylas_grant_id VARCHAR(255),
        
        -- Instantly-specific fields (if using multiple Instantly accounts)
        instantly_campaign_id VARCHAR(255),
        
        -- Account settings
        is_active BOOLEAN DEFAULT TRUE,
        is_primary BOOLEAN DEFAULT FALSE,  -- Primary account for the campaign
        daily_send_limit INTEGER DEFAULT 50,
        current_daily_sends INTEGER DEFAULT 0,
        last_daily_reset DATE DEFAULT CURRENT_DATE,
        
        -- Rotation settings
        use_for_outreach BOOLEAN DEFAULT TRUE,
        rotation_weight INTEGER DEFAULT 1,  -- Higher weight = more emails sent from this account
        last_used_at TIMESTAMPTZ,
        total_sent INTEGER DEFAULT 0,
        
        -- Performance metrics
        total_opens INTEGER DEFAULT 0,
        total_replies INTEGER DEFAULT 0,
        total_bounces INTEGER DEFAULT 0,
        
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        
        CONSTRAINT unique_campaign_email UNIQUE(campaign_id, email_address)
    );
    
    -- Indexes for performance
    CREATE INDEX IF NOT EXISTS idx_campaign_email_accounts_campaign_id 
        ON campaign_email_accounts(campaign_id);
    
    CREATE INDEX IF NOT EXISTS idx_campaign_email_accounts_active 
        ON campaign_email_accounts(is_active) WHERE is_active = TRUE;
    
    CREATE INDEX IF NOT EXISTS idx_campaign_email_accounts_provider 
        ON campaign_email_accounts(email_provider);
    
    CREATE INDEX IF NOT EXISTS idx_campaign_email_accounts_nylas_grant 
        ON campaign_email_accounts(nylas_grant_id) WHERE nylas_grant_id IS NOT NULL;
    """
    
    try:
        execute_sql(conn, create_sql)
        logger.info("Successfully created campaign_email_accounts table")
    except psycopg2.Error as e:
        logger.error(f"Error creating campaign_email_accounts table: {e}")
        raise


def create_email_account_rotation_log(conn):
    """Create table to log email account usage for analysis."""
    logger.info("Creating email_account_rotation_log table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS email_account_rotation_log (
        log_id SERIAL PRIMARY KEY,
        campaign_id UUID NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        email_account_id INTEGER REFERENCES campaign_email_accounts(id) ON DELETE SET NULL,
        email_address VARCHAR(255),
        pitch_id INTEGER REFERENCES pitches(pitch_id) ON DELETE CASCADE,
        selected_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        selection_reason VARCHAR(100),  -- 'rotation', 'primary', 'manual', 'retry'
        rotation_score NUMERIC(5,2)  -- Score used for selection
    );
    
    CREATE INDEX IF NOT EXISTS idx_rotation_log_campaign ON email_account_rotation_log(campaign_id);
    CREATE INDEX IF NOT EXISTS idx_rotation_log_selected_at ON email_account_rotation_log(selected_at);
    """
    
    try:
        execute_sql(conn, create_sql)
        logger.info("Successfully created email_account_rotation_log table")
    except psycopg2.Error as e:
        logger.error(f"Error creating email_account_rotation_log table: {e}")
        raise


def add_email_account_fields_to_pitches(conn):
    """Add fields to track which email account sent each pitch."""
    logger.info("Adding email account fields to pitches table...")
    
    alter_sql = """
    ALTER TABLE pitches
    ADD COLUMN IF NOT EXISTS sending_email_address VARCHAR(255),
    ADD COLUMN IF NOT EXISTS email_account_id INTEGER REFERENCES campaign_email_accounts(id);
    
    CREATE INDEX IF NOT EXISTS idx_pitches_sending_email 
        ON pitches(sending_email_address);
    """
    
    try:
        execute_sql(conn, alter_sql)
        logger.info("Successfully added email account fields to pitches table")
    except psycopg2.Error as e:
        logger.error(f"Error adding fields to pitches table: {e}")
        raise


def create_email_account_management_functions(conn):
    """Create database functions for email account management."""
    logger.info("Creating email account management functions...")
    
    functions_sql = """
    -- Function to select next email account for sending (round-robin with weights)
    CREATE OR REPLACE FUNCTION select_next_email_account(p_campaign_id UUID)
    RETURNS campaign_email_accounts AS $$
    DECLARE
        selected_account campaign_email_accounts;
    BEGIN
        -- Reset daily limits if needed
        UPDATE campaign_email_accounts
        SET current_daily_sends = 0,
            last_daily_reset = CURRENT_DATE
        WHERE campaign_id = p_campaign_id
        AND last_daily_reset < CURRENT_DATE;
        
        -- Select account based on rotation weight and availability
        SELECT * INTO selected_account
        FROM campaign_email_accounts
        WHERE campaign_id = p_campaign_id
        AND is_active = TRUE
        AND use_for_outreach = TRUE
        AND current_daily_sends < daily_send_limit
        ORDER BY 
            -- Prioritize accounts that haven't been used recently
            COALESCE(last_used_at, '1970-01-01'::timestamptz) ASC,
            -- Then by rotation weight (higher weight = higher priority)
            rotation_weight DESC,
            -- Finally by least used
            total_sent ASC
        LIMIT 1;
        
        -- Update last used timestamp
        IF selected_account.id IS NOT NULL THEN
            UPDATE campaign_email_accounts
            SET last_used_at = CURRENT_TIMESTAMP,
                current_daily_sends = current_daily_sends + 1,
                total_sent = total_sent + 1
            WHERE id = selected_account.id;
        END IF;
        
        RETURN selected_account;
    END;
    $$ LANGUAGE plpgsql;
    
    -- Function to get email account statistics
    CREATE OR REPLACE FUNCTION get_email_account_stats(p_campaign_id UUID)
    RETURNS TABLE(
        email_address VARCHAR,
        total_sent INTEGER,
        total_opens INTEGER,
        total_replies INTEGER,
        total_bounces INTEGER,
        open_rate NUMERIC,
        reply_rate NUMERIC,
        bounce_rate NUMERIC
    ) AS $$
    BEGIN
        RETURN QUERY
        SELECT 
            cea.email_address,
            cea.total_sent,
            cea.total_opens,
            cea.total_replies,
            cea.total_bounces,
            CASE WHEN cea.total_sent > 0 
                THEN ROUND((cea.total_opens::numeric / cea.total_sent) * 100, 2)
                ELSE 0 
            END as open_rate,
            CASE WHEN cea.total_sent > 0 
                THEN ROUND((cea.total_replies::numeric / cea.total_sent) * 100, 2)
                ELSE 0 
            END as reply_rate,
            CASE WHEN cea.total_sent > 0 
                THEN ROUND((cea.total_bounces::numeric / cea.total_sent) * 100, 2)
                ELSE 0 
            END as bounce_rate
        FROM campaign_email_accounts cea
        WHERE cea.campaign_id = p_campaign_id
        ORDER BY cea.total_sent DESC;
    END;
    $$ LANGUAGE plpgsql;
    """
    
    try:
        execute_sql(conn, functions_sql)
        logger.info("Successfully created email account management functions")
    except psycopg2.Error as e:
        logger.error(f"Error creating functions: {e}")
        raise


def migrate_existing_campaigns(conn):
    """Migrate existing campaign email settings to new structure."""
    logger.info("Migrating existing campaigns to email accounts table...")
    
    migration_sql = """
    -- Migrate Nylas campaigns
    INSERT INTO campaign_email_accounts (
        campaign_id, 
        email_address, 
        email_provider, 
        nylas_grant_id, 
        is_primary,
        is_active
    )
    SELECT 
        c.campaign_id,
        COALESCE(c.email_account, p.email, 'default@digitalpodcastguest.com'),
        'nylas',
        c.nylas_grant_id,
        TRUE,
        TRUE
    FROM campaigns c
    LEFT JOIN people p ON c.person_id = p.person_id
    WHERE c.nylas_grant_id IS NOT NULL
    ON CONFLICT (campaign_id, email_address) DO NOTHING;
    
    -- Migrate Instantly campaigns
    INSERT INTO campaign_email_accounts (
        campaign_id, 
        email_address, 
        email_provider, 
        instantly_campaign_id, 
        is_primary,
        is_active
    )
    SELECT 
        c.campaign_id,
        COALESCE(c.email_account, 'aidrian@digitalpodcastguest.com'),
        'instantly',
        c.instantly_campaign_id,
        TRUE,
        TRUE
    FROM campaigns c
    WHERE c.instantly_campaign_id IS NOT NULL
    AND NOT EXISTS (
        SELECT 1 FROM campaign_email_accounts 
        WHERE campaign_id = c.campaign_id
    )
    ON CONFLICT (campaign_id, email_address) DO NOTHING;
    """
    
    try:
        execute_sql(conn, migration_sql)
        logger.info("Successfully migrated existing campaigns")
    except psycopg2.Error as e:
        logger.error(f"Error migrating campaigns: {e}")
        # Don't raise - migration errors shouldn't break the whole process


def run_migration():
    """Run the complete migration."""
    logger.info("Starting campaign email accounts migration...")
    
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        raise Exception("Database connection failed")
    
    try:
        create_campaign_email_accounts_table(conn)
        create_email_account_rotation_log(conn)
        add_email_account_fields_to_pitches(conn)
        create_email_account_management_functions(conn)
        migrate_existing_campaigns(conn)
        
        conn.commit()
        logger.info("Campaign email accounts migration completed successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed, rolling back: {e}")
        raise
    finally:
        conn.close()


def rollback_migration():
    """Rollback the migration."""
    logger.info("Rolling back campaign email accounts migration...")
    
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        raise Exception("Database connection failed")
    
    try:
        # Drop new tables and functions
        rollback_sql = """
        DROP FUNCTION IF EXISTS get_email_account_stats(UUID);
        DROP FUNCTION IF EXISTS select_next_email_account(UUID);
        DROP TABLE IF EXISTS email_account_rotation_log CASCADE;
        DROP TABLE IF EXISTS campaign_email_accounts CASCADE;
        
        ALTER TABLE pitches 
        DROP COLUMN IF EXISTS sending_email_address,
        DROP COLUMN IF EXISTS email_account_id;
        """
        
        execute_sql(conn, rollback_sql)
        conn.commit()
        logger.info("Rollback completed successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Rollback failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback_migration()
    else:
        run_migration()