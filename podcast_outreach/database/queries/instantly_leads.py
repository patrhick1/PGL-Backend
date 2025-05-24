"""Instantly leads backup queries using the asyncpg connection pool."""

import logging
from typing import Any, Dict, List, Optional

from podcast_outreach.database.queries.connection import get_db_pool

logger = logging.getLogger(__name__)

# No synchronous connections here. All interactions go through the asyncpg pool.

# --- Table Creation ---
async def create_clientsinstantlyleads_table() -> None:
    """Creates the clientsinstantlyleads table if it doesn't exist."""

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

    create_email_index_sql = (
        "CREATE INDEX IF NOT EXISTS idx_clientsinstantlyleads_email ON clientsinstantlyleads (email);"
    )
    create_campaign_index_sql = (
        "CREATE INDEX IF NOT EXISTS idx_clientsinstantlyleads_campaign_id ON clientsinstantlyleads (campaign_id);"
    )
    create_ts_created_index_sql = (
        "CREATE INDEX IF NOT EXISTS idx_clientsinstantlyleads_timestamp_created ON clientsinstantlyleads (timestamp_created);"
    )
    create_payload_gin_index_sql = (
        "CREATE INDEX IF NOT EXISTS idx_clientsinstantlyleads_payload_gin ON clientsinstantlyleads USING GIN (payload);"
    )

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(create_table_sql)
            await conn.execute(create_email_index_sql)
            await conn.execute(create_campaign_index_sql)
            await conn.execute(create_ts_created_index_sql)
            await conn.execute(create_payload_gin_index_sql)
            logger.info("clientsinstantlyleads table checked/created successfully with indexes.")
        except Exception as e:
            logger.error(f"Error creating clientsinstantlyleads table or indexes: {e}")
            raise

# --- CRUD Operations ---

async def add_instantly_lead_record(lead_api_data: Dict[str, Any]) -> Optional[str]:
    """Adds a new lead record from Instantly API to the backup table."""

    if not lead_api_data.get("id"):
        logger.warning("Lead data missing 'id' field.")
        return None

    # Map API data to table columns
    # Note: API keys are often camelCase or similar, table columns are snake_case
    # Ensure all required fields are present or handle missing data appropriately (e.g. default to None)
    


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

    columns = list(insert_data.keys())
    placeholders = [f"${i}" for i in range(1, len(columns) + 1)]
    values = [insert_data[col] for col in columns]
    insert_query = (
        f"INSERT INTO clientsinstantlyleads ({', '.join(columns)}) "
        f"VALUES ({', '.join(placeholders)}) RETURNING lead_id;"
    )

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            lead_id = await conn.fetchval(insert_query, *values)
            return str(lead_id) if lead_id else None
        except Exception as e:
            logger.error(f"Error adding lead {lead_api_data.get('id')} to backup: {e}")
            return None

async def update_instantly_lead_record(lead_id: str, update_data: Dict[str, Any]) -> bool:
    """Updates an existing lead record in the clientsinstantlyleads table."""

    if not update_data:
        logger.warning("No update data provided.")
        return False

    set_clauses: List[str] = []
    values: List[Any] = []
    idx = 1
    for key, value in update_data.items():
        set_clauses.append(f"{key} = ${idx}")
        values.append(value)
        idx += 1

    if not set_clauses:
        return False

    update_query = (
        f"UPDATE clientsinstantlyleads SET {', '.join(set_clauses)} "
        f"WHERE lead_id = ${idx};"
    )
    values.append(lead_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(update_query, *values)
            updated_rows = int(result.split(' ')[1]) if result.startswith('UPDATE ') else 0
            return updated_rows > 0
        except Exception as e:
            logger.error(f"Error updating lead {lead_id}: {e}")
            return False

async def get_instantly_lead_by_id(lead_id: str) -> Optional[Dict[str, Any]]:
    """Fetches a single lead record by its lead_id."""

    query = "SELECT * FROM clientsinstantlyleads WHERE lead_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, lead_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching lead by ID {lead_id}: {e}")
            return None

async def get_all_instantly_leads_for_campaign(campaign_id: str, limit: int | None = None, offset: int = 0) -> List[Dict[str, Any]]:
    """Fetches lead records for a specific campaign."""

    query = "SELECT * FROM clientsinstantlyleads WHERE campaign_id = $1 ORDER BY timestamp_created DESC"
    params: List[Any] = [campaign_id]
    if limit is not None:
        query += " LIMIT $2 OFFSET $3"
        params.extend([limit, offset])

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching leads for campaign {campaign_id}: {e}")
            return []

async def get_all_instantly_leads(limit: int | None = None, offset: int = 0) -> List[Dict[str, Any]]:
    """Fetches all lead records from the backup table."""

    query = "SELECT * FROM clientsinstantlyleads ORDER BY timestamp_created DESC"
    params: List[Any] = []
    if limit is not None:
        query += " LIMIT $1 OFFSET $2"
        params.extend([limit, offset])

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching all leads: {e}")
            return []

async def delete_instantly_lead_record(lead_id: str) -> bool:
    """Deletes a lead record by its lead_id."""

    query = "DELETE FROM clientsinstantlyleads WHERE lead_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, lead_id)
            deleted_rows = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
            return deleted_rows > 0
        except Exception as e:
            logger.error(f"Error deleting lead {lead_id}: {e}")
            return False
