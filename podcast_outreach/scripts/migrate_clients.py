import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor
import os
import uuid
from dotenv import load_dotenv

# Load environment variables from .env file
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
        print("Please ensure PostgreSQL is running and connection details are correct.")
        print("Ensure environment variables are set: PGDATABASE, PGUSER, PGPASSWORD, PGHOST, PGPORT")
        return None

# Data extracted from the second image, with emails from the first image
# Each dictionary represents one campaign with its specific ID
campaign_data_with_ids = [
    {"client_name": "Michael Greenberg", "client_email": "michael@clickdown.xyz", "campaign_name": "MGG Targeted", "campaign_id": "afe3a4d7-5ed7-4fd4-9f8f-cf4e2ddc843d"},
    {"client_name": "Cody Schneider", "client_email": "cody@schneidermedia.co", "campaign_name": "Cody - Business", "campaign_id": "d52f85c0-8341-42d8-9e07-99c6b758fa0b"},
    {"client_name": "Kevin Bibelhausen", "client_email": "kevin@bibelhausen.com", "campaign_name": "Kevin Targeted", "campaign_id": "7b4a5386-8fa1-4059-8ded-398c0f48972b"},
    {"client_name": "Brandon C. White", "client_email": "brandon@3rdbrain.co", "campaign_name": "Brandon - Targeted", "campaign_id": "186fcab7-7c86-4086-9278-99238c453470"},
    {"client_name": "William Christensen", "client_email": "will@equityhammer.com", "campaign_name": "William - Targeted", "campaign_id": "ae1c1042-d10e-4cfc-ba4c-743a42550c85"},
    {"client_name": "Erick Vargas", "client_email": "evargas@followupcrm.com", "campaign_name": "Erick - Targeted (Construction)", "campaign_id": "ccbd7662-bbed-46ee-bd8f-1bc374646472"},
    {"client_name": "Erick Vargas", "client_email": "evargas@followupcrm.com", "campaign_name": "Erick - Targeted (Christian)", "campaign_id": "ad2c89bc-686d-401e-9f06-c6ff9d9b7430"},
    {"client_name": "Anna Sitkoff", "client_email": "reishiandroses@gmail.com", "campaign_name": "Anna - Targeted", "campaign_id": "3816b624-2a1f-408e-91a9-b9f730d03e2b"},
    {"client_name": "Daniel Borba", "client_email": "daniel@sparkportal.com", "campaign_name": "Daniel - Targeted", "campaign_id": "60346de6-915c-43fa-9dfa-b77983570359"},
    {"client_name": "Ashwin Ramesh", "client_email": "ashwin@synup.com", "campaign_name": "Ashwin - Targeted", "campaign_id": "5b1053b5-8143-4814-a9dc-15408971eac8"},
    {"client_name": "Jake Guso", "client_email": "jguso@therighthut.com", "campaign_name": "Jake - Targeted", "campaign_id": "02b1d9ff-0afe-4b64-ac15-a886f43bdbce"},
    {"client_name": "Akash Raju", "client_email": "akash@tryglimpse.com", "campaign_name": "Akash - Targeted", "campaign_id": "0725cdd8-b090-4da4-90af-6ca93ac3c267"},
    {"client_name": "Tom Elliott", "client_email": "tom@ocuroot.com", "campaign_name": "Tom - Targeted", "campaign_id": "640a6822-c1a7-48c7-8385-63b0d4c283fc"},
    {"client_name": "Michael Greenberg", "client_email": "michael@clickdown.xyz", "campaign_name": "Michael Greenberg", "campaign_id": "540b0539-f1c2-4612-94d8-df6fab42c2a7"},
    {"client_name": "Phillip Swan", "client_email": "phillip@theaisolutiongroup.ai", "campaign_name": "Phillip - Targeted", "campaign_id": "b55c61b6-262c-4390-b6e0-63dfca1620c2"},
]

def migrate_clients_to_db():
    conn = get_db_connection()
    if not conn:
        print("Database connection failed. Aborting migration.")
        return

    all_successful = True
    email_to_person_id = {} # To store emails and their corresponding person_ids

    try:
        with conn.cursor() as cur:
            for campaign_entry in campaign_data_with_ids:
                client_name = campaign_entry["client_name"]
                client_email = campaign_entry["client_email"]
                campaign_name = campaign_entry["campaign_name"]
                campaign_id = campaign_entry["campaign_id"]
                
                person_id = email_to_person_id.get(client_email)

                if not person_id:
                    try:
                        cur.execute(
                            """
                            INSERT INTO PEOPLE (full_name, email, role)
                            VALUES (%s, %s, %s)
                            RETURNING person_id;
                            """,
                            (client_name, client_email, 'client')
                        )
                        person_id = cur.fetchone()[0]
                        email_to_person_id[client_email] = person_id
                        print(f"Inserted new person: {client_name} (ID: {person_id}) with email {client_email}")
                    except psycopg2.errors.UniqueViolation:
                        conn.rollback() # Rollback the failed INSERT attempt
                        # Try to fetch the existing person_id after rollback
                        try:
                            cur.execute("SELECT person_id FROM PEOPLE WHERE email = %s;", (client_email,))
                            result = cur.fetchone()
                            if result:
                                person_id = result[0]
                                email_to_person_id[client_email] = person_id
                                print(f"Person with email {client_email} (Name: {client_name}) already exists (ID: {person_id}). Associating campaign.")
                            else:
                                # This should ideally not happen if the unique constraint was on email
                                print(f"Error: UniqueViolation for email {client_email}, but could not find existing person. Skipping campaign: {campaign_name}")
                                all_successful = False
                                continue # Skip to the next campaign_entry in the outer loop
                        except Exception as fetch_e:
                            print(f"Error fetching existing person {client_email} after UniqueViolation: {fetch_e}")
                            all_successful = False
                            continue # Skip to the next campaign_entry
                    except Exception as e:
                        conn.rollback() # Rollback on other person insertion errors
                        print(f"Error processing person {client_name} ({client_email}): {e}. Skipping campaign: {campaign_name}")
                        all_successful = False
                        continue # Skip to the next campaign_entry

                # If person_id was obtained (either new or existing)
                if person_id:
                    try:
                        cur.execute(
                            """
                            INSERT INTO CAMPAIGNS (campaign_id, person_id, campaign_name)
                            VALUES (%s, %s, %s);
                            """,
                            (campaign_id, person_id, campaign_name)
                        )
                        print(f"  Inserted campaign: '{campaign_name}' (ID: {campaign_id}) for person_id {person_id}")
                    except psycopg2.errors.UniqueViolation:
                        conn.rollback() # Rollback this specific failed campaign insert
                        print(f"  Campaign with ID {campaign_id} ('{campaign_name}') already exists. Skipping this campaign.")
                        # Depending on requirements, a duplicate campaign ID might be a true error
                        # all_successful = False 
                    except Exception as e:
                        conn.rollback() # Rollback this specific failed campaign insert
                        print(f"  Error inserting campaign '{campaign_name}' (ID: {campaign_id}) for {client_name}: {e}")
                        all_successful = False
            
            if all_successful:
                conn.commit()
                print("\nClient and campaign data migration completed successfully.")
            else:
                conn.rollback()
                print("\nClient and campaign data migration encountered errors. Changes have been rolled back.")

    except Exception as e:
        if conn and not conn.closed:
            conn.rollback()
        print(f"An unexpected error occurred during migration: {e}")
        all_successful = False # Ensure flag reflects the outer exception
    finally:
        if conn:
            conn.close()
            print("Database connection closed.")
    
    # Final status message based on all_successful flag
    if all_successful:
        # Message already printed if commit was successful
        # This ensures a clear final status if no other message was printed due to early successful exit.
        # (Though with the current loop structure, it's less likely to hit this without prior message)
        if conn is None or (hasattr(conn, 'closed') and conn.closed):
             print("Client and campaign data migration process finished.")
    else:
        print("Migration process finished with errors.")

if __name__ == "__main__":
    print("Starting client and campaign data migration process...")
    migrate_clients_to_db()
    # The final message is now primarily handled within migrate_clients_to_db

# The final message is now handled within migrate_clients_to_db based on success 