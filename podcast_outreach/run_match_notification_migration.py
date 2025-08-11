#!/usr/bin/env python3
"""
Run the match notification migration
This script should be run from the podcast_outreach directory
"""

import asyncio
import logging
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Get a synchronous database connection using psycopg2"""
    try:
        DATABASE_URL = os.getenv('DATABASE_URL')
        if not DATABASE_URL:
            raise ValueError("DATABASE_URL not found in environment variables")
        
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def run_migration():
    """Run the migration using psycopg2"""
    conn = get_db_connection()
    
    try:
        with conn.cursor() as cur:
            # Add notification preferences to client_profiles
            logger.info("Adding notification fields to client_profiles...")
            
            # Check if columns already exist before adding
            cur.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'client_profiles' 
                AND column_name IN ('match_notification_enabled', 'match_notification_threshold', 'last_match_notification_sent')
            """)
            existing_columns = [row[0] for row in cur.fetchall()]
            
            if 'match_notification_enabled' not in existing_columns:
                cur.execute("""
                    ALTER TABLE client_profiles 
                    ADD COLUMN match_notification_enabled BOOLEAN DEFAULT TRUE
                """)
                logger.info("Added match_notification_enabled column")
            
            if 'match_notification_threshold' not in existing_columns:
                cur.execute("""
                    ALTER TABLE client_profiles 
                    ADD COLUMN match_notification_threshold INTEGER DEFAULT 30
                """)
                logger.info("Added match_notification_threshold column")
            
            if 'last_match_notification_sent' not in existing_columns:
                cur.execute("""
                    ALTER TABLE client_profiles 
                    ADD COLUMN last_match_notification_sent TIMESTAMPTZ
                """)
                logger.info("Added last_match_notification_sent column")
            
            # Create match_notification_log table
            logger.info("Creating match_notification_log table...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS match_notification_log (
                    notification_id SERIAL PRIMARY KEY,
                    campaign_id UUID NOT NULL REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
                    person_id INTEGER NOT NULL REFERENCES people(person_id) ON DELETE CASCADE,
                    match_count INTEGER NOT NULL,
                    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            
            # Create indexes
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_notification_log_campaign_sent 
                ON match_notification_log(campaign_id, sent_at DESC)
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_notification_log_person 
                ON match_notification_log(person_id, sent_at DESC)
            """)
            
            logger.info("Created match_notification_log table and indexes")
            
            # Commit the changes
            conn.commit()
            logger.info("Migration completed successfully!")
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def rollback_migration():
    """Rollback the migration"""
    conn = get_db_connection()
    
    try:
        with conn.cursor() as cur:
            # Drop the notification log table
            cur.execute("DROP TABLE IF EXISTS match_notification_log CASCADE")
            logger.info("Dropped match_notification_log table")
            
            # Remove fields from client_profiles
            cur.execute("""
                ALTER TABLE client_profiles 
                DROP COLUMN IF EXISTS match_notification_enabled,
                DROP COLUMN IF EXISTS match_notification_threshold,
                DROP COLUMN IF EXISTS last_match_notification_sent
            """)
            logger.info("Removed notification fields from client_profiles")
            
            conn.commit()
            logger.info("Rollback completed successfully!")
            
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

def main():
    """Main entry point"""
    import sys
    
    print("Match Notification Migration")
    print("=" * 50)
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        print("Rolling back migration...")
        rollback_migration()
    else:
        print("Running migration...")
        print("\nThis will add:")
        print("- Notification preference fields to client_profiles table")
        print("- New match_notification_log table")
        print()
        
        # Ask for confirmation
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Migration cancelled.")
            return
        
        run_migration()

if __name__ == "__main__":
    main()