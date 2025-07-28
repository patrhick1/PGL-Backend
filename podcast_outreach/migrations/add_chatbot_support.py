#!/usr/bin/env python
"""
Migration script to add chatbot support tables to the database.
This follows the same pattern as the existing schema.py file.
"""
import psycopg2
from psycopg2 import sql
import os
from dotenv import load_dotenv

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
        # Handle both string and Composed SQL objects
        if hasattr(sql_statement, 'as_string'):
            # It's a Composed SQL object
            print(f"[OK] Successfully executed: {sql_statement.as_string(conn)[:50]}...")
        else:
            # It's a regular string
            print(f"[OK] Successfully executed: {str(sql_statement)[:50]}...")
    except psycopg2.Error as e:
        print(f"[ERROR] Error executing SQL: {e}")
        if conn:
            conn.rollback()
        raise

def create_chatbot_conversations_table(conn):
    """Creates the chatbot_conversations table."""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS chatbot_conversations (
        conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        campaign_id UUID REFERENCES campaigns(campaign_id) ON DELETE CASCADE,
        person_id INTEGER REFERENCES people(person_id) ON DELETE CASCADE,
        status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'abandoned')),
        conversation_phase VARCHAR(50) DEFAULT 'introduction',
        messages JSONB DEFAULT '[]'::jsonb,
        extracted_data JSONB DEFAULT '{}'::jsonb,
        conversation_metadata JSONB DEFAULT '{}'::jsonb,
        progress INTEGER DEFAULT 0,
        started_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        last_activity_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """
    execute_sql(conn, sql_statement)
    print("Table CHATBOT_CONVERSATIONS created/ensured.")
    
    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_chatbot_conversations_campaign_id ON chatbot_conversations(campaign_id);",
        "CREATE INDEX IF NOT EXISTS idx_chatbot_conversations_person_id ON chatbot_conversations(person_id);",
        "CREATE INDEX IF NOT EXISTS idx_chatbot_conversations_status ON chatbot_conversations(status);",
        "CREATE INDEX IF NOT EXISTS idx_chatbot_conversations_last_activity ON chatbot_conversations(last_activity_at);"
    ]
    
    for index_sql in indexes:
        execute_sql(conn, index_sql)

def create_conversation_insights_table(conn):
    """Creates the conversation_insights table."""
    sql_statement = """
    CREATE TABLE IF NOT EXISTS conversation_insights (
        insight_id SERIAL PRIMARY KEY,
        conversation_id UUID REFERENCES chatbot_conversations(conversation_id) ON DELETE CASCADE,
        insight_type VARCHAR(100), -- 'keyword', 'story', 'angle', 'achievement'
        content JSONB NOT NULL,
        confidence_score NUMERIC(3,2),
        extracted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """
    execute_sql(conn, sql_statement)
    print("Table CONVERSATION_INSIGHTS created/ensured.")
    
    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_conversation_insights_conversation_id ON conversation_insights(conversation_id);",
        "CREATE INDEX IF NOT EXISTS idx_conversation_insights_type ON conversation_insights(insight_type);",
        "CREATE INDEX IF NOT EXISTS idx_conversation_insights_confidence ON conversation_insights(confidence_score);"
    ]
    
    for index_sql in indexes:
        execute_sql(conn, index_sql)

def apply_timestamp_update_trigger(conn, table_name):
    """Applies the timestamp update trigger to the specified table."""
    trigger_name = f"trigger_update_{table_name}_updated_at"
    apply_trigger_sql = sql.SQL("""
    DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};
    CREATE TRIGGER {trigger_name}
    BEFORE UPDATE ON {table_name}
    FOR EACH ROW
    EXECUTE FUNCTION update_modified_column();
    """).format(
        trigger_name=sql.Identifier(trigger_name),
        table_name=sql.Identifier(table_name)
    )
    try:
        execute_sql(conn, apply_trigger_sql)
        print(f"Timestamp update trigger applied to table '{table_name}'.")
    except psycopg2.Error as e:
        print(f"Error applying trigger to {table_name}: {e}")

def run_migration():
    """Main function to run all migrations."""
    print("Starting chatbot support migration...")
    
    conn = get_db_connection()
    if not conn:
        print("Database connection failed. Aborting migration.")
        return
    
    try:
        # Create tables
        create_chatbot_conversations_table(conn)
        create_conversation_insights_table(conn)
        
        # Apply triggers
        apply_timestamp_update_trigger(conn, "chatbot_conversations")
        
        print("\n[SUCCESS] Migration completed successfully!")
        
    except psycopg2.Error as e:
        print(f"\n[FAILED] Migration failed: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")

if __name__ == "__main__":
    run_migration()