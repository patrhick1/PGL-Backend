"""
db_service_pg.py

A simple async PostgreSQL service using asyncpg. 
Provides helper methods for reading and updating campaign data 
relevant to the Bio/Angles generation.

Adjust column names/table structure to match your actual schema.
"""

import os
import asyncpg
import logging

logger = logging.getLogger(__name__)

async def get_db_connection():
    """Establish a connection to PostgreSQL via asyncpg."""
    try:
        conn = await asyncpg.connect(
            host=os.getenv("PGHOST"),
            port=os.getenv("PGPORT"),
            user=os.getenv("PGUSER"),
            password=os.getenv("PGPASSWORD"),
            database=os.getenv("PGDATABASE"),
        )
        return conn
    except Exception as e:
        logger.error(f"Error connecting to Postgres: {e}")
        raise

async def get_campaign_by_id(campaign_id: str):
    """
    Fetch a campaign record from Postgres by ID.
    Adjust the SELECT statement and columns to match your schema.
    """
    query = """
    SELECT 
        campaign_id,
        person_id,
        campaign_name,
        campaign_bio,
        campaign_angles,
        bio_v1_url,
        angles_v1_url,
        keywords_v1,
        bio_v2_url,
        angles_v2_url,
        keywords_v2,
        transcription_with_client,
        angles_bio_button,       -- boolean or something that indicates readiness
        mock_interview_email_send
    FROM campaigns
    WHERE campaign_id = $1
    """
    conn = await get_db_connection()
    try:
        row = await conn.fetchrow(query, campaign_id)
        return dict(row) if row else None
    finally:
        await conn.close()

async def update_campaign(campaign_id: str, update_fields: dict):
    """
    Update a campaign record in Postgres with the provided fields.
    The `update_fields` dict keys should match columns in your `campaigns` table.
    """
    # Dynamically build the SET clause
    # Example: UPDATE campaigns SET bio_v1_url = $2, angles_v1_url = $3, ...
    set_clauses = []
    values = []
    
    idx = 1
    for key, val in update_fields.items():
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE campaigns SET {set_clause_str} WHERE campaign_id = ${idx}"
    
    values.append(campaign_id)

    conn = await get_db_connection()
    try:
        await conn.execute(query, *values)
        return True
    finally:
        await conn.close()

