import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor
import os
from dotenv import load_dotenv
import uuid # For UUID validation and generation if needed

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

def create_clients_table():
    """Creates the Clients table in the database if it doesn't exist."""
    conn = get_db_connection()
    if not conn:
        return

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS Clients (
        campaign_id UUID PRIMARY KEY,
        client_name TEXT NOT NULL,
        linkedin_profile_url TEXT,
        twitter_profile_url TEXT,
        instagram_profile_url TEXT,
        tiktok_profile_url TEXT,
        dashboard_username TEXT,
        dashboard_password_hash TEXT, -- Store hashed passwords only
        media_kit_url TEXT,
        timestamp_created TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
        timestamp_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
    );
    """
    # Trigger to automatically update timestamp_updated on row update
    create_trigger_sql = """
    CREATE OR REPLACE FUNCTION update_timestamp_column()
    RETURNS TRIGGER AS $$
    BEGIN
       NEW.timestamp_updated = NOW(); 
       RETURN NEW;
    END;
    $$ language 'plpgsql';

    DROP TRIGGER IF EXISTS update_clients_timestamp_trigger ON Clients;
    CREATE TRIGGER update_clients_timestamp_trigger
    BEFORE UPDATE ON Clients
    FOR EACH ROW
    EXECUTE FUNCTION update_timestamp_column();
    """

    try:
        with conn.cursor() as cur:
            cur.execute(create_table_sql)
            cur.execute(create_trigger_sql)
            conn.commit()
            print("Clients table checked/created successfully with update trigger.")
    except psycopg2.Error as e:
        print(f"Error creating Clients table or trigger: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def ensure_all_campaign_ids_in_clients():
    """
    Ensures that all campaign_ids from clientsinstantlyleads exist in the Clients table.
    If a campaign_id is missing in Clients, it's inserted with a placeholder name.
    """
    conn = get_db_connection()
    if not conn:
        return

    print("Ensuring all campaign_ids from clientsinstantlyleads are in Clients table...")
    try:
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("SELECT DISTINCT campaign_id FROM clientsinstantlyleads WHERE campaign_id IS NOT NULL;")
            lead_campaign_ids = [row['campaign_id'] for row in cur.fetchall()]

            if not lead_campaign_ids:
                print("No campaign_ids found in clientsinstantlyleads to check.")
                return

            placeholders = ','.join(['%s'] * len(lead_campaign_ids))
            cur.execute(f"SELECT campaign_id FROM Clients WHERE campaign_id IN ({placeholders});", tuple(lead_campaign_ids))
            client_campaign_ids = {row['campaign_id'] for row in cur.fetchall()}

            missing_ids_count = 0
            for camp_id in lead_campaign_ids:
                if camp_id not in client_campaign_ids:
                    placeholder_name = f"Unknown Client - {str(camp_id)}"
                    print(f"Found campaign_id {camp_id} in leads but not in Clients. Adding with placeholder name: {placeholder_name}")
                    cur.execute(
                        sql.SQL("INSERT INTO Clients (campaign_id, client_name) VALUES (%s, %s) ON CONFLICT (campaign_id) DO NOTHING;"),
                        (camp_id, placeholder_name)
                    )
                    missing_ids_count +=1
            
            conn.commit()
            if missing_ids_count > 0:
                 print(f"Added {missing_ids_count} missing campaign_ids to Clients table with placeholder names.")
            else:
                print("All campaign_ids from leads are already present or accounted for in Clients table.")

    except psycopg2.Error as e:
        print(f"Error ensuring campaign_ids in Clients table: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

def upsert_client_data(clients_data_list):
    """
    Inserts or updates client data into the Clients table.
    clients_data_list is a list of tuples: (client_name, campaign_id_str)
    """
    conn = get_db_connection()
    if not conn:
        return

    print(f"Upserting {len(clients_data_list)} client records...")
    upsert_count = 0
    for client_name, campaign_id_str in clients_data_list:
        try:
            # Validate UUID
            campaign_uuid = uuid.UUID(campaign_id_str)
        except ValueError:
            print(f"Invalid UUID format for campaign_id: {campaign_id_str}. Skipping record for client: {client_name}")
            continue

        upsert_sql = """
        INSERT INTO Clients (campaign_id, client_name, timestamp_updated)
        VALUES (%s, %s, NOW())
        ON CONFLICT (campaign_id) DO UPDATE SET
            client_name = EXCLUDED.client_name,
            timestamp_updated = NOW();
        """
        try:
            with conn.cursor() as cur:
                # Try passing the UUID as a string, PostgreSQL will handle the cast
                cur.execute(upsert_sql, (str(campaign_uuid), client_name))
                upsert_count += cur.rowcount # Should be 1 if inserted or updated
            conn.commit()
        except psycopg2.ProgrammingError as prog_e:
            # ProgrammingError is usually an issue with the SQL or data types, not the connection itself.
            print(f"Programming error upserting client {client_name} (Campaign ID: {campaign_id_str}): {prog_e}")
            if conn: conn.rollback()
            # We might not want to continue if there's a programming error, as it might affect all subsequent operations.
            # For now, we'll log and continue to see if it's specific to some data.
        except psycopg2.OperationalError as op_e: # Specifically handle connection-related errors
            print(f"Operational error upserting client {client_name} (Campaign ID: {campaign_id_str}): {op_e}")
            if conn: conn.rollback()
            if op_e.pgconn is None or op_e.pgconn.closed:
                print("Attempting to re-establish DB connection...")
                conn = get_db_connection()
                if not conn:
                    print("Failed to re-establish DB connection. Aborting further upserts.")
                    break 
        except psycopg2.Error as e: # Catch other psycopg2 errors
            print(f"General psycopg2 error upserting client {client_name} (Campaign ID: {campaign_id_str}): {e}")
            if conn: conn.rollback()
            # Decide if to break or continue based on error type
    
    print(f"Finished upserting client data. {upsert_count} records affected/processed.")
    if conn:
        conn.close()


def add_foreign_key_to_leads_table():
    """Adds a foreign key constraint from clientsinstantlyleads.campaign_id to Clients.campaign_id."""
    conn = get_db_connection()
    if not conn:
        return

    new_constraint_name = "fk_clientsinstantlyleads_campaign_id_clients"
    target_table = "clientsinstantlyleads"

    check_constraint_sql = sql.SQL("""
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = %s::regclass
      AND confrelid = 'clients'::regclass
      AND conname = %s;
    """)

    add_fk_sql = sql.SQL("""
    ALTER TABLE {}
    ADD CONSTRAINT {}
    FOREIGN KEY (campaign_id)
    REFERENCES Clients (campaign_id)
    ON DELETE RESTRICT;
    """).format(sql.Identifier(target_table), sql.Identifier(new_constraint_name))
    
    try:
        with conn.cursor() as cur:
            cur.execute(check_constraint_sql, (target_table, new_constraint_name))
            exists = cur.fetchone()
            if exists:
                print(f"Foreign key '{new_constraint_name}' already exists on table '{target_table}'.")
            else:
                print(f"Adding foreign key constraint '{new_constraint_name}' from '{target_table}' to Clients...")
                cur.execute(add_fk_sql)
                conn.commit()
                print("Foreign key constraint added successfully.")
    except psycopg2.Error as e:
        print(f"Error adding foreign key constraint: {e}")
        print(f"This might be due to campaign_ids in {target_table} that do not exist in the Clients table.")
        if conn: conn.rollback()
    finally:
        if conn:
            conn.close()

def drop_foreign_key_if_exists(table_name: str, constraint_name: str):
    """Drops a foreign key constraint if it exists on the specified table."""
    conn = get_db_connection()
    if not conn:
        print(f"Cannot connect to DB to drop FK {constraint_name}")
        return

    check_sql = sql.SQL("""
    SELECT 1 FROM pg_constraint 
    WHERE conrelid = %s::regclass AND conname = %s;
    """)

    drop_sql = sql.SQL("ALTER TABLE {} DROP CONSTRAINT IF EXISTS {};").format(
        sql.Identifier(table_name),
        sql.Identifier(constraint_name)
    )
    
    try:
        with conn.cursor() as cur:
            cur.execute(check_sql, (table_name, constraint_name))
            exists = cur.fetchone()
            if exists:
                print(f"Constraint '{constraint_name}' found on table '{table_name}'. Attempting to drop...")
                cur.execute(drop_sql)
                conn.commit()
                print(f"Foreign key constraint '{constraint_name}' dropped successfully from table '{table_name}'.")
            else:
                print(f"Foreign key constraint '{constraint_name}' not found on table '{table_name}'. No action taken.")
    except psycopg2.Error as e:
        print(f"Error dropping foreign key constraint '{constraint_name}' from table '{table_name}': {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    print("Client Data Management Script - FULL RUN")
    print("----------------------------------------")

    create_clients_table()
    ensure_all_campaign_ids_in_clients()

    client_data_to_load = [
        ("Michael Greenberg", "afe3a4d7-5ed7-4fd4-9f8f-cf4e2ddc843d"),
        ("Cody Schneider", "d52f85c0-8341-42d8-9e07-99c6b758fa0b"),
        ("Kevin Bibelhausen", "7b4a5386-8fa1-4059-8ded-398c0f4897cb"),
        ("Brandon C. White", "186fcab7-7c86-4086-9278-99238c453470"),
        ("William Christensen", "ae1c1042-d10e-4cfc-ba4c-743a42550c85"),
        ("Erick Vargas (Construction)", "ccbd7662-bbed-46ee-bd8f-1bc374646472"),
        ("Erick Vargas (Christian)", "ad2c89bc-686d-401e-9f06-c6ff9d9b7430"),
        ("Anna Sitkoff", "3816b624-2a1f-408e-91a9-b9f730d03e2b"),
        ("Daniel Borba", "60346de6-915c-43fa-9dfa-b77983570359"),
        ("Ashwin Ramesh", "5b1053b5-8143-4814-a9dc-15408971eac8"),
        ("Jake Guso", "02b1d9ff-0afe-4b64-ac15-a886f43bdbce"),
        ("Akash Raju", "0725cdd8-b090-4da4-90af-6ca93ac3c267"),
        ("Tom Elliott", "640a6822-c1a7-48c7-8385-63b0d4c283fc"),
        ("Michael Greenberg, Michael", "540b0539-f1c2-4612-94d8-df6fab42c2a7"),
        ("Phillip Swan", "b55c61b6-262c-4390-b6e0-63dfca1620c2")
    ]
    upsert_client_data(client_data_to_load)
    add_foreign_key_to_leads_table()

    print("\nClient data management script finished.") 