"""
Migration to add comprehensive email thread tracking
Stores full conversation threads between clients and podcast hosts
"""

import logging
from datetime import datetime
import psycopg2
from podcast_outreach.database.schema import get_db_connection, execute_sql

logger = logging.getLogger(__name__)

def upgrade():
    """Add email threads and messages tables for full conversation tracking"""
    conn = get_db_connection()
    
    try:
        # Create email_threads table to track entire conversations
        create_threads_table = """
        CREATE TABLE IF NOT EXISTS email_threads (
            thread_id SERIAL PRIMARY KEY,
            nylas_thread_id VARCHAR(255) UNIQUE NOT NULL,
            pitch_id INTEGER REFERENCES pitches(pitch_id),
            placement_id INTEGER REFERENCES placements(placement_id),
            campaign_id UUID REFERENCES campaigns(campaign_id),
            media_id INTEGER REFERENCES media(media_id),
            
            -- Thread metadata
            subject TEXT,
            participant_emails TEXT[], -- All email addresses in thread
            message_count INTEGER DEFAULT 0,
            last_message_at TIMESTAMPTZ,
            thread_status VARCHAR(50), -- active, completed, stale
            
            -- Tracking
            first_reply_at TIMESTAMPTZ,
            last_reply_at TIMESTAMPTZ,
            client_last_sent_at TIMESTAMPTZ,
            host_last_sent_at TIMESTAMPTZ,
            
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_email_threads_nylas_thread_id 
            ON email_threads(nylas_thread_id);
        CREATE INDEX IF NOT EXISTS idx_email_threads_pitch_id 
            ON email_threads(pitch_id);
        CREATE INDEX IF NOT EXISTS idx_email_threads_placement_id 
            ON email_threads(placement_id);
        CREATE INDEX IF NOT EXISTS idx_email_threads_campaign_id 
            ON email_threads(campaign_id);
        """
        
        execute_sql(conn, create_threads_table)
        logger.info("Created email_threads table")
        
        # Create email_messages table to store individual messages
        create_messages_table = """
        CREATE TABLE IF NOT EXISTS email_messages (
            message_id SERIAL PRIMARY KEY,
            nylas_message_id VARCHAR(255) UNIQUE NOT NULL,
            thread_id INTEGER REFERENCES email_threads(thread_id) ON DELETE CASCADE,
            
            -- Message details
            sender_email TEXT NOT NULL,
            sender_name TEXT,
            recipient_emails TEXT[],
            cc_emails TEXT[],
            bcc_emails TEXT[],
            
            subject TEXT,
            body_text TEXT,
            body_html TEXT,
            snippet TEXT,
            
            -- Metadata
            message_date TIMESTAMPTZ,
            direction VARCHAR(20), -- inbound, outbound
            is_reply BOOLEAN DEFAULT FALSE,
            is_forward BOOLEAN DEFAULT FALSE,
            
            -- Tracking
            opened_at TIMESTAMPTZ,
            clicked_at TIMESTAMPTZ,
            replied_at TIMESTAMPTZ,
            
            -- Raw data
            raw_message JSONB,
            
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        
        CREATE INDEX IF NOT EXISTS idx_email_messages_nylas_message_id 
            ON email_messages(nylas_message_id);
        CREATE INDEX IF NOT EXISTS idx_email_messages_thread_id 
            ON email_messages(thread_id);
        CREATE INDEX IF NOT EXISTS idx_email_messages_sender_email 
            ON email_messages(sender_email);
        CREATE INDEX IF NOT EXISTS idx_email_messages_message_date 
            ON email_messages(message_date DESC);
        """
        
        execute_sql(conn, create_messages_table)
        logger.info("Created email_messages table")
        
        # Create thread_participants table for tracking all participants
        create_participants_table = """
        CREATE TABLE IF NOT EXISTS thread_participants (
            participant_id SERIAL PRIMARY KEY,
            thread_id INTEGER REFERENCES email_threads(thread_id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            name TEXT,
            role VARCHAR(50), -- client, host, cc_participant
            first_message_at TIMESTAMPTZ,
            last_message_at TIMESTAMPTZ,
            message_count INTEGER DEFAULT 0,
            
            UNIQUE(thread_id, email)
        );
        
        CREATE INDEX IF NOT EXISTS idx_thread_participants_thread_id 
            ON thread_participants(thread_id);
        CREATE INDEX IF NOT EXISTS idx_thread_participants_email 
            ON thread_participants(email);
        """
        
        execute_sql(conn, create_participants_table)
        logger.info("Created thread_participants table")
        
        # Note: placements table already has email_thread JSONB column
        logger.info("Placements table already has email_thread column for storing conversations")
        
        conn.commit()
        logger.info("Email threads tracking migration completed successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


def downgrade():
    """Remove email thread tracking tables"""
    conn = get_db_connection()
    
    try:
        # Remove tables in reverse order due to foreign keys
        drop_sql = """
        DROP TABLE IF EXISTS thread_participants CASCADE;
        DROP TABLE IF EXISTS email_messages CASCADE;
        DROP TABLE IF EXISTS email_threads CASCADE;
        """
        
        execute_sql(conn, drop_sql)
        conn.commit()
        logger.info("Email threads tracking migration rolled back successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Rollback failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()