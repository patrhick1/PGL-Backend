#!/usr/bin/env python3
"""
Database migration: Add email inbox management tables
Supports BookingAssistant integration for intelligent email processing
"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()


def run_migration():
    """Add email inbox management tables"""
    
    conn = psycopg2.connect(
        dbname=os.getenv('PGDATABASE'),
        user=os.getenv('PGUSER'),
        password=os.getenv('PGPASSWORD'),
        host=os.getenv('PGHOST'),
        port=os.getenv('PGPORT')
    )
    
    cur = conn.cursor()
    
    try:
        print("[INFO] Creating email inbox management tables...")
        
        # 1. Email classifications table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_classifications (
                classification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                message_id VARCHAR(255) UNIQUE NOT NULL,
                thread_id VARCHAR(255),
                sender_email VARCHAR(255),
                sender_name VARCHAR(255),
                subject TEXT,
                classification VARCHAR(50), -- booking, followup, rejection, spam, other
                confidence_score FLOAT,
                processed_at TIMESTAMPTZ DEFAULT NOW(),
                draft_generated BOOLEAN DEFAULT FALSE,
                draft_id UUID,
                booking_assistant_session_id VARCHAR(255),
                raw_response JSONB
            );
        """)
        
        # Create indexes separately
        cur.execute("CREATE INDEX IF NOT EXISTS idx_thread_classification ON email_classifications(thread_id, classification);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_sender_classification ON email_classifications(sender_email, classification);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_processed_at ON email_classifications(processed_at DESC);")
        print("  [OK] email_classifications table created")
        
        # 2. AI-generated drafts table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_drafts (
                draft_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                thread_id VARCHAR(255) NOT NULL,
                message_id VARCHAR(255),
                draft_content TEXT NOT NULL,
                draft_html TEXT,
                context_used TEXT,
                relevant_threads JSONB,
                approval_status VARCHAR(50) DEFAULT 'pending', -- pending, approved, rejected, sent, edited
                created_at TIMESTAMPTZ DEFAULT NOW(),
                approved_at TIMESTAMPTZ,
                sent_at TIMESTAMPTZ,
                edited_content TEXT,
                edited_by VARCHAR(255),
                nylas_draft_id VARCHAR(255),
                campaign_id UUID REFERENCES campaigns(campaign_id),
                pitch_id INTEGER REFERENCES pitches(pitch_id)
            );
        """)
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_thread_drafts ON email_drafts(thread_id, created_at DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_approval_status ON email_drafts(approval_status, created_at DESC);")
        print("  [OK] email_drafts table created")
        
        # 3. Inbox messages cache
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inbox_messages (
                message_id VARCHAR(255) PRIMARY KEY,
                grant_id VARCHAR(255) NOT NULL,
                thread_id VARCHAR(255),
                folder_id VARCHAR(255),
                subject TEXT,
                snippet TEXT,
                body_html TEXT,
                body_plain TEXT,
                from_email VARCHAR(255),
                from_name VARCHAR(255),
                to_json JSONB,
                cc_json JSONB,
                bcc_json JSONB,
                reply_to_json JSONB,
                date TIMESTAMPTZ,
                unread BOOLEAN DEFAULT true,
                starred BOOLEAN DEFAULT false,
                has_attachments BOOLEAN DEFAULT false,
                attachments_json JSONB,
                labels JSONB,
                headers JSONB,
                synced_at TIMESTAMPTZ DEFAULT NOW(),
                classification_id UUID REFERENCES email_classifications(classification_id),
                related_pitch_id INTEGER REFERENCES pitches(pitch_id),
                related_campaign_id UUID REFERENCES campaigns(campaign_id)
            );
        """)
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_inbox_grant_thread ON inbox_messages(grant_id, thread_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_inbox_date ON inbox_messages(grant_id, date DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_inbox_unread ON inbox_messages(grant_id, unread, date DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_inbox_from ON inbox_messages(from_email, date DESC);")
        print("  [OK] inbox_messages table created")
        
        # 4. Thread aggregation table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inbox_threads (
                thread_id VARCHAR(255) PRIMARY KEY,
                grant_id VARCHAR(255) NOT NULL,
                subject TEXT,
                snippet TEXT,
                participants JSONB,
                message_count INTEGER DEFAULT 1,
                unread_count INTEGER DEFAULT 0,
                has_drafts BOOLEAN DEFAULT false,
                last_message_date TIMESTAMPTZ,
                first_message_date TIMESTAMPTZ,
                has_attachments BOOLEAN DEFAULT false,
                latest_classification VARCHAR(50),
                campaign_id UUID REFERENCES campaigns(campaign_id),
                pitch_id INTEGER REFERENCES pitches(pitch_id),
                is_reply_to_pitch BOOLEAN DEFAULT false,
                folder_id VARCHAR(255),
                labels JSONB,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_threads_grant_date ON inbox_threads(grant_id, last_message_date DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_threads_campaign ON inbox_threads(campaign_id, last_message_date DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_threads_unread ON inbox_threads(grant_id, unread_count, last_message_date DESC);")
        print("  [OK] inbox_threads table created")
        
        # 5. Email templates table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS email_templates (
                template_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES people(person_id),
                name VARCHAR(255) NOT NULL,
                subject VARCHAR(255),
                body_html TEXT,
                body_plain TEXT,
                variables JSONB,
                category VARCHAR(50), -- booking_confirm, followup, rejection_response, etc.
                usage_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_templates_user ON email_templates(user_id, is_active);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_templates_category ON email_templates(category, is_active);")
        print("  [OK] email_templates table created")
        
        # 6. Auto-reply rules table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS auto_reply_rules (
                rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id INTEGER REFERENCES people(person_id),
                name VARCHAR(255) NOT NULL,
                is_active BOOLEAN DEFAULT true,
                priority INTEGER DEFAULT 10,
                conditions JSONB NOT NULL, -- {classification: 'booking', from_domain: 'podcast.com'}
                actions JSONB NOT NULL, -- {use_template: 'uuid', add_label: 'important'}
                template_id UUID REFERENCES email_templates(template_id),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                last_triggered_at TIMESTAMPTZ,
                trigger_count INTEGER DEFAULT 0
            );
        """)
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rules_active ON auto_reply_rules(is_active, priority DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_rules_user ON auto_reply_rules(user_id, is_active);")
        print("  [OK] auto_reply_rules table created")
        
        # 7. Create helper functions
        cur.execute("""
            -- Function to update thread aggregation
            CREATE OR REPLACE FUNCTION update_inbox_thread()
            RETURNS TRIGGER AS $$
            BEGIN
                -- Update or insert thread aggregation
                INSERT INTO inbox_threads (
                    thread_id, grant_id, subject, snippet,
                    message_count, unread_count, last_message_date,
                    first_message_date, has_attachments
                )
                VALUES (
                    NEW.thread_id, NEW.grant_id, NEW.subject, NEW.snippet,
                    1, CASE WHEN NEW.unread THEN 1 ELSE 0 END,
                    NEW.date, NEW.date, NEW.has_attachments
                )
                ON CONFLICT (thread_id) DO UPDATE SET
                    message_count = inbox_threads.message_count + 1,
                    unread_count = inbox_threads.unread_count + 
                        CASE WHEN NEW.unread THEN 1 ELSE 0 END,
                    last_message_date = GREATEST(inbox_threads.last_message_date, NEW.date),
                    has_attachments = inbox_threads.has_attachments OR NEW.has_attachments,
                    updated_at = NOW();
                
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        
        cur.execute("""
            -- Trigger to maintain thread aggregation
            CREATE TRIGGER inbox_message_thread_update
            AFTER INSERT OR UPDATE ON inbox_messages
            FOR EACH ROW
            EXECUTE FUNCTION update_inbox_thread();
        """)
        print("  [OK] Helper functions and triggers created")
        
        # 8. Add indexes for common queries
        cur.execute("""
            -- Index for finding emails related to campaigns
            CREATE INDEX IF NOT EXISTS idx_inbox_campaign_lookup 
            ON inbox_messages(related_campaign_id, date DESC) 
            WHERE related_campaign_id IS NOT NULL;
            
            -- Index for finding drafts needing approval
            CREATE INDEX IF NOT EXISTS idx_drafts_pending_approval
            ON email_drafts(approval_status, created_at DESC)
            WHERE approval_status = 'pending';
            
            -- Index for classification performance tracking
            CREATE INDEX IF NOT EXISTS idx_classification_performance
            ON email_classifications(classification, confidence_score, processed_at DESC);
        """)
        print("  [OK] Performance indexes created")
        
        conn.commit()
        print("[SUCCESS] Email inbox management tables created successfully!")
        
        # Show summary
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN (
                'email_classifications', 'email_drafts', 'inbox_messages',
                'inbox_threads', 'email_templates', 'auto_reply_rules'
            )
            ORDER BY table_name;
        """)
        
        tables = cur.fetchall()
        print("\n[SUMMARY] Created tables:")
        for table in tables:
            print(f"  - {table[0]}")
        
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Migration failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def rollback_migration():
    """Rollback the migration if needed"""
    
    conn = psycopg2.connect(
        dbname=os.getenv('PGDATABASE'),
        user=os.getenv('PGUSER'),
        password=os.getenv('PGPASSWORD'),
        host=os.getenv('PGHOST'),
        port=os.getenv('PGPORT')
    )
    
    cur = conn.cursor()
    
    try:
        print("[INFO] Rolling back email inbox management tables...")
        
        # Drop triggers first
        cur.execute("DROP TRIGGER IF EXISTS inbox_message_thread_update ON inbox_messages;")
        cur.execute("DROP FUNCTION IF EXISTS update_inbox_thread();")
        
        # Drop tables in reverse order of dependencies
        tables_to_drop = [
            'auto_reply_rules',
            'email_templates',
            'inbox_threads',
            'inbox_messages',
            'email_drafts',
            'email_classifications'
        ]
        
        for table in tables_to_drop:
            cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
            print(f"  [OK] Dropped {table}")
        
        conn.commit()
        print("[SUCCESS] Rollback completed!")
        
    except Exception as e:
        conn.rollback()
        print(f"[ERROR] Rollback failed: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "rollback":
        rollback_migration()
    else:
        run_migration()