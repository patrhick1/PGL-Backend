# podcast_outreach/database/queries/pitches_nylas.py

"""
Database queries for Nylas-specific pitch operations.
These extend the existing pitch queries with Nylas-specific functionality.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging
from podcast_outreach.database.connection import get_db_pool

logger = logging.getLogger(__name__)


async def get_pitch_by_nylas_message_id(nylas_message_id: str) -> Optional[Dict[str, Any]]:
    """Get pitch record by Nylas message ID."""
    pool = await get_db_pool()
    query = """
        SELECT * FROM pitches 
        WHERE nylas_message_id = $1
        LIMIT 1
    """
    
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, nylas_message_id)
        return dict(row) if row else None


async def get_pitch_by_nylas_thread_id(nylas_thread_id: str) -> Optional[Dict[str, Any]]:
    """Get most recent pitch in a Nylas thread."""
    pool = await get_db_pool()
    query = """
        SELECT * FROM pitches 
        WHERE nylas_thread_id = $1
        ORDER BY send_ts DESC
        LIMIT 1
    """
    
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, nylas_thread_id)
        return dict(row) if row else None


async def get_recent_pitches_by_recipient_email(
    recipient_email: str, 
    days_back: int = 30
) -> List[Dict[str, Any]]:
    """Get recent pitches sent to a specific email address."""
    pool = await get_db_pool()
    query = """
        SELECT p.* 
        FROM pitches p
        JOIN media m ON p.media_id = m.media_id
        WHERE LOWER(m.contact_email) LIKE '%' || LOWER($1) || '%'
        AND p.send_ts > CURRENT_TIMESTAMP - INTERVAL '%s days'
        AND p.email_provider = 'nylas'
        ORDER BY p.send_ts DESC
    """
    
    async with pool.acquire() as connection:
        rows = await connection.fetch(query % days_back, recipient_email)
        return [dict(row) for row in rows]


async def update_pitch_nylas_fields(
    pitch_id: int,
    nylas_message_id: Optional[str] = None,
    nylas_thread_id: Optional[str] = None,
    nylas_draft_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Update Nylas-specific fields for a pitch."""
    pool = await get_db_pool()
    
    set_clauses = []
    params = []
    param_count = 1
    
    if nylas_message_id is not None:
        set_clauses.append(f"nylas_message_id = ${param_count}")
        params.append(nylas_message_id)
        param_count += 1
    
    if nylas_thread_id is not None:
        set_clauses.append(f"nylas_thread_id = ${param_count}")
        params.append(nylas_thread_id)
        param_count += 1
    
    if nylas_draft_id is not None:
        set_clauses.append(f"nylas_draft_id = ${param_count}")
        params.append(nylas_draft_id)
        param_count += 1
    
    if not set_clauses:
        return None
    
    params.append(pitch_id)
    query = f"""
        UPDATE pitches
        SET {', '.join(set_clauses)}
        WHERE pitch_id = ${param_count}
        RETURNING *
    """
    
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, *params)
        return dict(row) if row else None


async def record_email_processed(
    message_id: str,
    thread_id: Optional[str] = None,
    grant_id: Optional[str] = None,
    processing_type: str = "unknown",
    pitch_id: Optional[int] = None,
    placement_id: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """Record that an email message has been processed."""
    pool = await get_db_pool()
    
    query = """
        INSERT INTO processed_emails 
        (message_id, thread_id, grant_id, processing_type, pitch_id, placement_id, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (message_id) DO UPDATE
        SET processed_at = CURRENT_TIMESTAMP,
            processing_type = EXCLUDED.processing_type,
            metadata = EXCLUDED.metadata
        RETURNING id
    """
    
    try:
        async with pool.acquire() as connection:
            result = await connection.fetchval(
                query,
                message_id,
                thread_id,
                grant_id,
                processing_type,
                pitch_id,
                placement_id,
                metadata or {}
            )
            return result is not None
    except Exception as e:
        logger.error(f"Error recording processed email: {e}")
        return False


async def is_email_processed(message_id: str) -> bool:
    """Check if an email message has already been processed."""
    pool = await get_db_pool()
    query = """
        SELECT EXISTS(
            SELECT 1 FROM processed_emails 
            WHERE message_id = $1
        )
    """
    
    async with pool.acquire() as connection:
        return await connection.fetchval(query, message_id)


async def update_email_sync_status(
    grant_id: str,
    last_sync_timestamp: Optional[datetime] = None,
    last_message_timestamp: Optional[datetime] = None,
    sync_cursor: Optional[str] = None,
    messages_processed: Optional[int] = None,
    sync_status: Optional[str] = None,
    error_info: Optional[Dict[str, Any]] = None
) -> bool:
    """Update email sync status for a grant."""
    pool = await get_db_pool()
    
    # Build update query dynamically
    set_clauses = ["updated_at = CURRENT_TIMESTAMP"]
    params = []
    param_count = 1
    
    if last_sync_timestamp is not None:
        set_clauses.append(f"last_sync_timestamp = ${param_count}")
        params.append(last_sync_timestamp)
        param_count += 1
    
    if last_message_timestamp is not None:
        set_clauses.append(f"last_message_timestamp = ${param_count}")
        params.append(last_message_timestamp)
        param_count += 1
    
    if sync_cursor is not None:
        set_clauses.append(f"sync_cursor = ${param_count}")
        params.append(sync_cursor)
        param_count += 1
    
    if messages_processed is not None:
        set_clauses.append(f"messages_processed = messages_processed + ${param_count}")
        params.append(messages_processed)
        param_count += 1
    
    if sync_status is not None:
        set_clauses.append(f"sync_status = ${param_count}")
        params.append(sync_status)
        param_count += 1
    
    if error_info:
        set_clauses.append(f"error_count = error_count + 1")
        set_clauses.append(f"last_error = ${param_count}")
        params.append(error_info.get("error", "Unknown error"))
        param_count += 1
    
    params.append(grant_id)
    
    query = f"""
        INSERT INTO email_sync_status (grant_id, last_sync_timestamp, sync_status)
        VALUES (${param_count}, CURRENT_TIMESTAMP, 'active')
        ON CONFLICT (grant_id) DO UPDATE
        SET {', '.join(set_clauses)}
        RETURNING sync_id
    """
    
    try:
        async with pool.acquire() as connection:
            result = await connection.fetchval(query, *params)
            return result is not None
    except Exception as e:
        logger.error(f"Error updating email sync status: {e}")
        return False


async def get_email_sync_status(grant_id: str) -> Optional[Dict[str, Any]]:
    """Get email sync status for a grant."""
    pool = await get_db_pool()
    query = """
        SELECT * FROM email_sync_status
        WHERE grant_id = $1
    """
    
    async with pool.acquire() as connection:
        row = await connection.fetchrow(query, grant_id)
        return dict(row) if row else None


async def get_pitches_for_email_provider(
    provider: str,
    status: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get pitches for a specific email provider."""
    pool = await get_db_pool()
    
    query = """
        SELECT p.*, c.campaign_name, m.name as media_name
        FROM pitches p
        JOIN campaigns c ON p.campaign_id = c.campaign_id
        JOIN media m ON p.media_id = m.media_id
        WHERE p.email_provider = $1
    """
    
    params = [provider]
    param_count = 2
    
    if status:
        query += f" AND p.pitch_state = ${param_count}"
        params.append(status)
        param_count += 1
    
    query += f" ORDER BY p.created_at DESC LIMIT ${param_count}"
    params.append(limit)
    
    async with pool.acquire() as connection:
        rows = await connection.fetch(query, *params)
        return [dict(row) for row in rows]


async def migrate_pitch_to_nylas(
    pitch_id: int,
    nylas_message_id: str,
    nylas_thread_id: Optional[str] = None
) -> bool:
    """Migrate an existing pitch from Instantly to Nylas."""
    pool = await get_db_pool()
    
    query = """
        UPDATE pitches
        SET email_provider = 'nylas',
            nylas_message_id = $2,
            nylas_thread_id = $3,
            instantly_lead_id = NULL
        WHERE pitch_id = $1
        AND email_provider = 'instantly'
        RETURNING pitch_id
    """
    
    try:
        async with pool.acquire() as connection:
            result = await connection.fetchval(
                query,
                pitch_id,
                nylas_message_id,
                nylas_thread_id
            )
            return result is not None
    except Exception as e:
        logger.error(f"Error migrating pitch to Nylas: {e}")
        return False