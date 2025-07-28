#!/usr/bin/env python
"""
Migration script to add email_thread field to placements table.
This field will store the full email conversation history as a JSONB array.
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

def add_email_thread_column(conn):
    """Add email_thread JSONB column to placements table."""
    print("\n" + "="*60)
    print("Adding email_thread column to placements table")
    print("="*60)
    
    # Check if column already exists
    check_sql = """
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'placements' 
    AND column_name = 'email_thread';
    """
    
    with conn.cursor() as cur:
        cur.execute(check_sql)
        if cur.fetchone():
            print("[INFO] email_thread column already exists, skipping...")
            return
    
    # Add the column
    alter_sql = """
    ALTER TABLE placements 
    ADD COLUMN email_thread JSONB DEFAULT '[]'::jsonb;
    """
    
    execute_sql(conn, alter_sql)
    print("[OK] Added email_thread column to placements table")
    
    # Add a comment explaining the structure
    comment_sql = """
    COMMENT ON COLUMN placements.email_thread IS 
    'Stores the full email conversation thread as JSONB array. Each element contains: 
    {
        "timestamp": "ISO 8601 timestamp",
        "direction": "sent" or "received",
        "from": "sender email",
        "to": "recipient email",
        "subject": "email subject",
        "body_text": "plain text body",
        "body_html": "HTML body (optional)",
        "message_id": "email message ID (optional)",
        "instantly_data": {} // Original webhook data
    }';
    """
    
    execute_sql(conn, comment_sql)
    print("[OK] Added column comment")

def add_email_thread_index(conn):
    """Add index for email_thread queries."""
    print("\nAdding index for email_thread...")
    
    # Check if index exists
    check_sql = """
    SELECT indexname 
    FROM pg_indexes 
    WHERE tablename = 'placements' 
    AND indexname = 'idx_placements_email_thread';
    """
    
    with conn.cursor() as cur:
        cur.execute(check_sql)
        if cur.fetchone():
            print("[INFO] Index already exists, skipping...")
            return
    
    # Create GIN index for JSONB queries
    index_sql = """
    CREATE INDEX idx_placements_email_thread 
    ON placements USING gin (email_thread);
    """
    
    execute_sql(conn, index_sql)
    print("[OK] Created GIN index for email_thread")

def update_existing_placements(conn):
    """Initialize email_thread for existing placements with available data."""
    print("\nChecking for existing placements to update...")
    
    # Get placements that have associated pitch data
    query_sql = """
    SELECT 
        pl.placement_id,
        pl.pitch_id,
        p.send_ts,
        p.reply_ts,
        p.subject_line,
        p.body_snippet,
        pg.final_text,
        m.contact_email,
        c.campaign_name
    FROM placements pl
    JOIN pitches p ON pl.pitch_id = p.pitch_id
    JOIN pitch_generations pg ON p.pitch_gen_id = pg.pitch_gen_id
    JOIN media m ON pl.media_id = m.media_id
    JOIN campaigns c ON pl.campaign_id = c.campaign_id
    WHERE pl.email_thread IS NULL OR pl.email_thread = '[]'::jsonb
    LIMIT 100;
    """
    
    with conn.cursor() as cur:
        cur.execute(query_sql)
        placements = cur.fetchall()
        
        if not placements:
            print("[INFO] No existing placements need updating")
            return
        
        print(f"[INFO] Found {len(placements)} placements to initialize")
        
        for placement in placements:
            placement_id = placement[0]
            send_ts = placement[2]
            subject_line = placement[4] or "Podcast Guest Opportunity"
            final_text = placement[6] or placement[5] or ""
            contact_email = placement[7]
            
            # Build initial thread with sent email
            thread = []
            
            if send_ts and final_text:
                thread.append({
                    "timestamp": send_ts.isoformat() if send_ts else datetime.utcnow().isoformat(),
                    "direction": "sent",
                    "from": "aidrian@digitalpodcastguest.com",  # Default sender
                    "to": contact_email,
                    "subject": subject_line,
                    "body_text": final_text,
                    "instantly_data": {
                        "source": "migration",
                        "note": "Reconstructed from existing pitch data"
                    }
                })
            
            # Update the placement
            if thread:
                update_sql = """
                UPDATE placements 
                SET email_thread = %s::jsonb
                WHERE placement_id = %s;
                """
                
                import json
                cur.execute(update_sql, (json.dumps(thread), placement_id))
                
        conn.commit()
        print(f"[OK] Updated {len(placements)} existing placements")

def main():
    """Run the migration."""
    print("Email Thread Migration for Placements Table")
    print("="*60)
    print(f"Started at: {datetime.now()}")
    
    # Connect to database
    conn = get_db_connection()
    if not conn:
        print("[ERROR] Failed to connect to database")
        return
    
    try:
        # Add the column
        add_email_thread_column(conn)
        
        # Add index
        add_email_thread_index(conn)
        
        # Update existing records
        update_existing_placements(conn)
        
        print("\n" + "="*60)
        print("[SUCCESS] Migration completed successfully!")
        print(f"Completed at: {datetime.now()}")
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