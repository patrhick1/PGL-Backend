import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor, Json
import os
from dotenv import load_dotenv
import json # For handling potential JSON string conversion if needed, though psycopg2 handles dicts for JSONB well.

# Load environment variables from .env file at the start
load_dotenv()

# --- Database Connection ---
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
        print("Please ensure PostgreSQL is running and connection details are correct.")
        print("Ensure environment variables are set: PGDATABASE, PGUSER, PGPASSWORD, PGHOST, PGPORT")
        return None

# --- Table Creation ---
def create_clientsinstantlyleads_table():
    """Creates the clientsinstantlyleads table in the database if it doesn't exist."""
    conn = get_db_connection()
    if not conn:
        return

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS clientsinstantlyleads (
        lead_id UUID PRIMARY KEY,
        timestamp_created TIMESTAMPTZ,
        timestamp_updated TIMESTAMPTZ,
        organization_id UUID,
        lead_status INTEGER,
        email_open_count INTEGER,
        email_reply_count INTEGER,
        email_click_count INTEGER,
        company_domain TEXT,
        status_summary JSONB,
        campaign_id UUID,
        email TEXT,
        personalization TEXT,
        website TEXT,
        last_name TEXT,
        first_name TEXT,
        company_name TEXT,
        phone TEXT,
        payload JSONB,
        status_summary_subseq JSONB,
        last_step_from TEXT,
        last_step_id UUID,
        last_step_timestamp_executed TIMESTAMPTZ,
        email_opened_step INTEGER,
        email_opened_variant INTEGER,
        email_replied_step INTEGER,
        email_replied_variant INTEGER,
        email_clicked_step INTEGER,
        email_clicked_variant INTEGER,
        lt_interest_status INTEGER,
        subsequence_id UUID,
        verification_status INTEGER,
        pl_value_lead TEXT,
        timestamp_added_subsequence TIMESTAMPTZ,
        timestamp_last_contact TIMESTAMPTZ,
        timestamp_last_open TIMESTAMPTZ,
        timestamp_last_reply TIMESTAMPTZ,
        timestamp_last_interest_change TIMESTAMPTZ,
        timestamp_last_click TIMESTAMPTZ,
        enrichment_status INTEGER,
        list_id UUID,
        last_contacted_from TEXT,
        uploaded_by_user UUID,
        upload_method TEXT,
        assigned_to UUID,
        is_website_visitor BOOLEAN,
        timestamp_last_touch TIMESTAMPTZ,
        esp_code INTEGER,
        backup_creation_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
    );
    """
    # Comments for ENUM-like fields:
    # lead_status: 1:Active, 2:Paused, 3:Completed, -1:Bounced, -2:Unsubscribed, -3:Skipped
    # lt_interest_status: 0:OutOfOffice, 1:Interested, 2:MeetingBooked, 3:MeetingCompleted, 4:Closed, -1:NotInterested, -2:WrongPerson, -3:Lost
    # verification_status: 1:Verified, 11:Pending, 12:PendingVerificationJob, -1:Invalid, -2:Risky, -3:CatchAll, -4:JobChange
    # enrichment_status: 1:Enriched, 11:Pending, -1:NotAvailable, -2:Error
    # upload_method: 'manual', 'api', 'website-visitor'
    # esp_code: e.g., 0:InQueue, 1:Google, 2:Microsoft, 1000:NotFound

    create_email_index_sql = "CREATE INDEX IF NOT EXISTS idx_clientsinstantlyleads_email ON clientsinstantlyleads (email);"
    create_campaign_index_sql = "CREATE INDEX IF NOT EXISTS idx_clientsinstantlyleads_campaign_id ON clientsinstantlyleads (campaign_id);"
    create_ts_created_index_sql = "CREATE INDEX IF NOT EXISTS idx_clientsinstantlyleads_timestamp_created ON clientsinstantlyleads (timestamp_created);"
    create_payload_gin_index_sql = "CREATE INDEX IF NOT EXISTS idx_clientsinstantlyleads_payload_gin ON clientsinstantlyleads USING GIN (payload);"

    try:
        with conn.cursor() as cur:
            cur.execute(create_table_sql)
            cur.execute(create_email_index_sql)
            cur.execute(create_campaign_index_sql)
            cur.execute(create_ts_created_index_sql)
            cur.execute(create_payload_gin_index_sql)
            conn.commit()
            print("clientsinstantlyleads table checked/created successfully with indexes.")
    except psycopg2.Error as e:
        print(f"Error creating clientsinstantlyleads table or indexes: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# --- CRUD Operations ---

def add_instantly_lead_record(lead_api_data):
    """Adds a new lead record from Instantly API to the clientsinstantlyleads table.
    lead_api_data should be a dictionary from the Instantly API response for a single lead.
    Returns the lead_id of the newly inserted record, or None on failure.
    """
    conn = get_db_connection()
    if not conn:
        return None

    # Map API data to table columns
    # Note: API keys are often camelCase or similar, table columns are snake_case
    # Ensure all required fields are present or handle missing data appropriately (e.g. default to None)
    
    # It's crucial that lead_api_data['id'] exists and is a valid UUID string for the PRIMARY KEY.
    if not lead_api_data.get('id'):
        print("Error: Lead data is missing 'id' field.")
        return None

    insert_data = {
        "lead_id": lead_api_data.get("id"),
        "timestamp_created": lead_api_data.get("timestamp_created"),
        "timestamp_updated": lead_api_data.get("timestamp_updated"),
        "organization_id": lead_api_data.get("organization"),
        "lead_status": lead_api_data.get("status"),
        "email_open_count": lead_api_data.get("email_open_count"),
        "email_reply_count": lead_api_data.get("email_reply_count"),
        "email_click_count": lead_api_data.get("email_click_count"),
        "company_domain": lead_api_data.get("company_domain"),
        "status_summary": lead_api_data.get("status_summary"), # psycopg2 handles dict -> JSONB
        "campaign_id": lead_api_data.get("campaign"),
        "email": lead_api_data.get("email"),
        "personalization": lead_api_data.get("personalization"),
        "website": lead_api_data.get("website"),
        "last_name": lead_api_data.get("last_name"),
        "first_name": lead_api_data.get("first_name"),
        "company_name": lead_api_data.get("company_name"),
        "phone": lead_api_data.get("phone"),
        "payload": lead_api_data.get("payload"), # psycopg2 handles dict -> JSONB
        "status_summary_subseq": lead_api_data.get("status_summary_subseq"), # psycopg2 handles dict -> JSONB
        "last_step_from": lead_api_data.get("last_step_from"),
        "last_step_id": lead_api_data.get("last_step_id"),
        "last_step_timestamp_executed": lead_api_data.get("last_step_timestamp_executed"),
        "email_opened_step": lead_api_data.get("email_opened_step"),
        "email_opened_variant": lead_api_data.get("email_opened_variant"),
        "email_replied_step": lead_api_data.get("email_replied_step"),
        "email_replied_variant": lead_api_data.get("email_replied_variant"),
        "email_clicked_step": lead_api_data.get("email_clicked_step"),
        "email_clicked_variant": lead_api_data.get("email_clicked_variant"),
        "lt_interest_status": lead_api_data.get("lt_interest_status"),
        "subsequence_id": lead_api_data.get("subsequence_id"),
        "verification_status": lead_api_data.get("verification_status"),
        "pl_value_lead": lead_api_data.get("pl_value_lead"),
        "timestamp_added_subsequence": lead_api_data.get("timestamp_added_subsequence"),
        "timestamp_last_contact": lead_api_data.get("timestamp_last_contact"),
        "timestamp_last_open": lead_api_data.get("timestamp_last_open"),
        "timestamp_last_reply": lead_api_data.get("timestamp_last_reply"),
        "timestamp_last_interest_change": lead_api_data.get("timestamp_last_interest_change"),
        "timestamp_last_click": lead_api_data.get("timestamp_last_click"),
        "enrichment_status": lead_api_data.get("enrichment_status"),
        "list_id": lead_api_data.get("list_id"),
        "last_contacted_from": lead_api_data.get("last_contacted_from"),
        "uploaded_by_user": lead_api_data.get("uploaded_by_user"),
        "upload_method": lead_api_data.get("upload_method"),
        "assigned_to": lead_api_data.get("assigned_to"),
        "is_website_visitor": lead_api_data.get("is_website_visitor"),
        "timestamp_last_touch": lead_api_data.get("timestamp_last_touch"),
        "esp_code": lead_api_data.get("esp_code")
        # backup_creation_timestamp has a DEFAULT
    }

    # Filter out None values to avoid inserting NULL for columns that might not exist in lead_api_data
    # or if you want to rely on table defaults for some fields (though most here don't have defaults other than backup_creation_timestamp)
    # However, for a backup, explicit NULLs for missing data from API might be desired.
    # The .get(key) method already returns None if key is not found, which psycopg2 handles as NULL.

    columns = insert_data.keys()
    # sql.Placeholder(col) creates named placeholders like %(col_name)s
    # So the second argument to execute should be a dictionary.
    values_placeholders = [sql.Placeholder(col) for col in columns] 
    
    insert_query = sql.SQL("INSERT INTO clientsinstantlyleads ({}) VALUES ({}) RETURNING lead_id").format(
        sql.SQL(', ').join(map(sql.Identifier, columns)),
        sql.SQL(', ').join(values_placeholders)
    )
    
    # Prepare the dictionary for execute, wrapping dicts for JSONB columns with Json()
    execute_dict = {}
    for col, value in insert_data.items():
        if col in ["status_summary", "payload", "status_summary_subseq"] and isinstance(value, dict):
            execute_dict[col] = Json(value)
        else:
            execute_dict[col] = value

    try:
        with conn.cursor() as cur:
            cur.execute(insert_query, execute_dict) # Pass the dictionary directly
            inserted_lead_id = cur.fetchone()[0]
            conn.commit()
            # print(f"Lead record {inserted_lead_id} added to clientsinstantlyleads successfully.")
            return inserted_lead_id
    except psycopg2.IntegrityError as e:
        print(f"Integrity error adding lead {lead_api_data.get('id')}: {e}")
        print("This might be due to a duplicate lead_id if not using ON CONFLICT.")
        if conn:
            conn.rollback()
        return None
    except psycopg2.Error as e:
        print(f"Error adding lead {lead_api_data.get('id')} to backup: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if conn:
            conn.close()

def update_instantly_lead_record(lead_id: str, update_data: dict):
    """Updates an existing lead record in the clientsinstantlyleads table.
    
    Args:
        lead_id (str): The UUID string of the lead to update.
        update_data (dict): A dictionary where keys are column names (snake_case)
                              and values are their new values.
                              
    Returns:
        bool: True if the update was successful and at least one row was affected, False otherwise.
    """
    conn = get_db_connection()
    if not conn:
        return False
    if not update_data:
        print("No update data provided.")
        return False

    # Prepare the SET clause dynamically
    set_clauses = []
    processed_update_data = {}

    for key, value in update_data.items():
        # Ensure the key is a valid column name to prevent SQL injection if keys come from untrusted source
        # For now, assuming keys are controlled and map to actual column names.
        set_clauses.append(sql.SQL("{} = {}").format(sql.Identifier(key), sql.Placeholder(key)))
        if key in ["status_summary", "payload", "status_summary_subseq"] and isinstance(value, dict):
            processed_update_data[key] = Json(value)
        else:
            processed_update_data[key] = value
    
    if not set_clauses:
        print("No valid fields to update.")
        return False

    # Add the lead_id to the dictionary for the WHERE clause placeholder
    processed_update_data['lead_id_where'] = lead_id

    update_query = sql.SQL("UPDATE clientsinstantlyleads SET {} WHERE lead_id = {} ").format(
        sql.SQL(', ').join(set_clauses),
        sql.Placeholder('lead_id_where')
    )

    try:
        with conn.cursor() as cur:
            cur.execute(update_query, processed_update_data)
            updated_rows = cur.rowcount # Number of rows affected
            conn.commit()
            if updated_rows > 0:
                print(f"Lead record {lead_id} updated successfully. {updated_rows} row(s) affected.")
                return True
            else:
                print(f"Lead record {lead_id} not found or no data changed. {updated_rows} row(s) affected.")
                return False # Could be True if no change is also success, but False if not found.
    except psycopg2.Error as e:
        print(f"Error updating lead {lead_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_instantly_lead_by_id(lead_id: str):
    """Fetches a single lead record from clientsinstantlyleads by its lead_id."""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT * FROM clientsinstantlyleads WHERE lead_id = %s;", (lead_id,))
            record = cur.fetchone()
            return dict(record) if record else None
    except psycopg2.Error as e:
        print(f"Error fetching lead by ID {lead_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_all_instantly_leads_for_campaign(campaign_id: str, limit: int = None, offset: int = 0):
    """Fetches all lead records for a specific campaign_id, with optional pagination."""
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            query = "SELECT * FROM clientsinstantlyleads WHERE campaign_id = %s ORDER BY timestamp_created DESC"
            params = [campaign_id]
            if limit is not None:
                query += " LIMIT %s OFFSET %s"
                params.extend([limit, offset])
            query += ";"
            cur.execute(query, tuple(params))
            records = [dict(row) for row in cur.fetchall()]
            return records
    except psycopg2.Error as e:
        print(f"Error fetching leads for campaign {campaign_id}: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_all_instantly_leads(limit: int = None, offset: int = 0):
    """Fetches all lead records from clientsinstantlyleads, with optional pagination."""
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            query = "SELECT * FROM clientsinstantlyleads ORDER BY timestamp_created DESC"
            params = []
            if limit is not None:
                query += " LIMIT %s OFFSET %s"
                params.extend([limit, offset])
            query += ";"
            cur.execute(query, tuple(params) if params else None)
            records = [dict(row) for row in cur.fetchall()]
            return records
    except psycopg2.Error as e:
        print(f"Error fetching all leads: {e}")
        return []
    finally:
        if conn:
            conn.close()

def delete_instantly_lead_record(lead_id: str):
    """Deletes a lead record from clientsinstantlyleads by its lead_id."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM clientsinstantlyleads WHERE lead_id = %s;", (lead_id,))
            deleted_rows = cur.rowcount
            conn.commit()
            if deleted_rows > 0:
                print(f"Lead record {lead_id} deleted successfully.")
                return True
            else:
                print(f"Lead record {lead_id} not found for deletion.")
                return False
    except psycopg2.Error as e:
        print(f"Error deleting lead {lead_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()
