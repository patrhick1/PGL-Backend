# podcast_outreach/database/migrations/add_nylas_fields.py

"""
Database migration to add Nylas-specific fields to support email integration.
This migration adds fields for Nylas message IDs, thread IDs, and grant IDs.
"""

import psycopg2
from psycopg2 import sql
import logging
from podcast_outreach.database.schema import get_db_connection, execute_sql

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def add_nylas_fields_to_campaigns(conn):
    """Add Nylas grant ID to campaigns table for account association."""
    logger.info("Adding Nylas fields to campaigns table...")
    
    # Add nylas_grant_id to campaigns
    alter_sql = """
    ALTER TABLE campaigns 
    ADD COLUMN IF NOT EXISTS nylas_grant_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS email_account VARCHAR(255),
    ADD COLUMN IF NOT EXISTS email_provider VARCHAR(50) DEFAULT 'instantly';
    """
    
    try:
        execute_sql(conn, alter_sql)
        logger.info("Successfully added Nylas fields to campaigns table")
    except psycopg2.Error as e:
        logger.error(f"Error adding Nylas fields to campaigns: {e}")
        raise


def add_nylas_fields_to_pitches(conn):
    """Add Nylas-specific tracking fields to pitches table."""
    logger.info("Adding Nylas fields to pitches table...")
    
    alter_sql = """
    ALTER TABLE pitches
    ADD COLUMN IF NOT EXISTS nylas_message_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS nylas_thread_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS nylas_draft_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS email_provider VARCHAR(50) DEFAULT 'instantly',
    ADD COLUMN IF NOT EXISTS opened_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS clicked_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS bounce_type VARCHAR(50),
    ADD COLUMN IF NOT EXISTS bounce_reason TEXT,
    ADD COLUMN IF NOT EXISTS bounced_ts TIMESTAMPTZ;
    """
    
    try:
        execute_sql(conn, alter_sql)
        
        # Add indexes for Nylas fields
        index_sql = """
        CREATE INDEX IF NOT EXISTS idx_pitches_nylas_message_id 
            ON pitches(nylas_message_id) 
            WHERE nylas_message_id IS NOT NULL;
        
        CREATE INDEX IF NOT EXISTS idx_pitches_nylas_thread_id 
            ON pitches(nylas_thread_id) 
            WHERE nylas_thread_id IS NOT NULL;
        
        CREATE INDEX IF NOT EXISTS idx_pitches_email_provider 
            ON pitches(email_provider);
        """
        execute_sql(conn, index_sql)
        
        logger.info("Successfully added Nylas fields to pitches table")
    except psycopg2.Error as e:
        logger.error(f"Error adding Nylas fields to pitches: {e}")
        raise


def add_nylas_fields_to_people(conn):
    """Add Nylas grant ID to people table for individual email accounts."""
    logger.info("Adding Nylas fields to people table...")
    
    alter_sql = """
    ALTER TABLE people
    ADD COLUMN IF NOT EXISTS nylas_grant_id VARCHAR(255),
    ADD COLUMN IF NOT EXISTS nylas_email_account VARCHAR(255);
    """
    
    try:
        execute_sql(conn, alter_sql)
        logger.info("Successfully added Nylas fields to people table")
    except psycopg2.Error as e:
        logger.error(f"Error adding Nylas fields to people: {e}")
        raise


def create_email_sync_status_table(conn):
    """Create table to track email sync status and processing."""
    logger.info("Creating email_sync_status table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS email_sync_status (
        sync_id SERIAL PRIMARY KEY,
        grant_id VARCHAR(255) NOT NULL,
        last_sync_timestamp TIMESTAMPTZ,
        last_message_timestamp TIMESTAMPTZ,
        sync_cursor VARCHAR(500),
        messages_processed INTEGER DEFAULT 0,
        sync_status VARCHAR(50) DEFAULT 'active',
        error_count INTEGER DEFAULT 0,
        last_error TEXT,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE INDEX IF NOT EXISTS idx_email_sync_grant_id 
        ON email_sync_status(grant_id);
    
    CREATE INDEX IF NOT EXISTS idx_email_sync_status 
        ON email_sync_status(sync_status);
    """
    
    try:
        execute_sql(conn, create_sql)
        logger.info("Successfully created email_sync_status table")
    except psycopg2.Error as e:
        logger.error(f"Error creating email_sync_status table: {e}")
        raise


def create_processed_emails_table(conn):
    """Create table to track processed email messages."""
    logger.info("Creating processed_emails table...")
    
    create_sql = """
    CREATE TABLE IF NOT EXISTS processed_emails (
        id SERIAL PRIMARY KEY,
        message_id VARCHAR(255) UNIQUE NOT NULL,
        thread_id VARCHAR(255),
        grant_id VARCHAR(255),
        processed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        processing_type VARCHAR(50), -- 'reply', 'bounce', 'opened', etc.
        pitch_id INTEGER REFERENCES pitches(pitch_id),
        placement_id INTEGER REFERENCES placements(placement_id),
        metadata JSONB DEFAULT '{}'::jsonb
    );
    
    CREATE INDEX IF NOT EXISTS idx_processed_emails_message_id 
        ON processed_emails(message_id);
    
    CREATE INDEX IF NOT EXISTS idx_processed_emails_thread_id 
        ON processed_emails(thread_id);
    
    CREATE INDEX IF NOT EXISTS idx_processed_emails_grant_id 
        ON processed_emails(grant_id);
    
    CREATE INDEX IF NOT EXISTS idx_processed_emails_processed_at 
        ON processed_emails(processed_at);
    """
    
    try:
        execute_sql(conn, create_sql)
        logger.info("Successfully created processed_emails table")
    except psycopg2.Error as e:
        logger.error(f"Error creating processed_emails table: {e}")
        raise


def add_pitch_query_functions(conn):
    """Add database functions for querying pitches by Nylas IDs."""
    logger.info("Creating pitch query functions...")
    
    functions_sql = """
    -- Function to get pitch by Nylas message ID
    CREATE OR REPLACE FUNCTION get_pitch_by_nylas_message_id(p_message_id VARCHAR)
    RETURNS SETOF pitches AS $$
    BEGIN
        RETURN QUERY
        SELECT * FROM pitches 
        WHERE nylas_message_id = p_message_id
        LIMIT 1;
    END;
    $$ LANGUAGE plpgsql;
    
    -- Function to get pitch by Nylas thread ID
    CREATE OR REPLACE FUNCTION get_pitch_by_nylas_thread_id(p_thread_id VARCHAR)
    RETURNS SETOF pitches AS $$
    BEGIN
        RETURN QUERY
        SELECT * FROM pitches 
        WHERE nylas_thread_id = p_thread_id
        ORDER BY send_ts DESC
        LIMIT 1;
    END;
    $$ LANGUAGE plpgsql;
    
    -- Function to get recent pitches by recipient email
    CREATE OR REPLACE FUNCTION get_recent_pitches_by_recipient(
        p_email VARCHAR,
        p_days_back INTEGER DEFAULT 30
    )
    RETURNS SETOF pitches AS $$
    BEGIN
        RETURN QUERY
        SELECT p.* 
        FROM pitches p
        JOIN media m ON p.media_id = m.media_id
        WHERE LOWER(m.contact_email) LIKE '%' || LOWER(p_email) || '%'
        AND p.send_ts > CURRENT_TIMESTAMP - INTERVAL '1 day' * p_days_back
        ORDER BY p.send_ts DESC;
    END;
    $$ LANGUAGE plpgsql;
    """
    
    try:
        execute_sql(conn, functions_sql)
        logger.info("Successfully created pitch query functions")
    except psycopg2.Error as e:
        logger.error(f"Error creating pitch query functions: {e}")
        raise


def run_migration():
    """Run the complete migration to add Nylas support."""
    logger.info("Starting Nylas fields migration...")
    
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        raise Exception("Database connection failed")
    
    try:
        # Run all migration steps
        add_nylas_fields_to_campaigns(conn)
        add_nylas_fields_to_pitches(conn)
        add_nylas_fields_to_people(conn)
        create_email_sync_status_table(conn)
        create_processed_emails_table(conn)
        add_pitch_query_functions(conn)
        
        # Commit all changes
        conn.commit()
        logger.info("Nylas fields migration completed successfully")
        
    except Exception as e:
        # Rollback on any error
        conn.rollback()
        logger.error(f"Migration failed, rolling back: {e}")
        raise
    finally:
        conn.close()


def rollback_migration():
    """Rollback the Nylas fields migration."""
    logger.info("Rolling back Nylas fields migration...")
    
    conn = get_db_connection()
    if not conn:
        logger.error("Failed to connect to database")
        raise Exception("Database connection failed")
    
    try:
        # Drop new tables
        drop_tables_sql = """
        DROP TABLE IF EXISTS processed_emails CASCADE;
        DROP TABLE IF EXISTS email_sync_status CASCADE;
        """
        execute_sql(conn, drop_tables_sql)
        
        # Drop functions
        drop_functions_sql = """
        DROP FUNCTION IF EXISTS get_pitch_by_nylas_message_id(VARCHAR);
        DROP FUNCTION IF EXISTS get_pitch_by_nylas_thread_id(VARCHAR);
        DROP FUNCTION IF EXISTS get_recent_pitches_by_recipient(VARCHAR, INTEGER);
        """
        execute_sql(conn, drop_functions_sql)
        
        # Remove columns from existing tables
        # Note: Be careful with this in production - you might want to keep the data
        alter_campaigns_sql = """
        ALTER TABLE campaigns 
        DROP COLUMN IF EXISTS nylas_grant_id,
        DROP COLUMN IF EXISTS email_account,
        DROP COLUMN IF EXISTS email_provider;
        """
        execute_sql(conn, alter_campaigns_sql)
        
        alter_pitches_sql = """
        ALTER TABLE pitches
        DROP COLUMN IF EXISTS nylas_message_id,
        DROP COLUMN IF EXISTS nylas_thread_id,
        DROP COLUMN IF EXISTS nylas_draft_id,
        DROP COLUMN IF EXISTS email_provider,
        DROP COLUMN IF EXISTS opened_ts,
        DROP COLUMN IF EXISTS clicked_ts,
        DROP COLUMN IF EXISTS bounce_type,
        DROP COLUMN IF EXISTS bounce_reason,
        DROP COLUMN IF EXISTS bounced_ts;
        """
        execute_sql(conn, alter_pitches_sql)
        
        alter_people_sql = """
        ALTER TABLE people
        DROP COLUMN IF EXISTS nylas_grant_id,
        DROP COLUMN IF EXISTS nylas_email_account;
        """
        execute_sql(conn, alter_people_sql)
        
        conn.commit()
        logger.info("Nylas fields migration rolled back successfully")
        
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