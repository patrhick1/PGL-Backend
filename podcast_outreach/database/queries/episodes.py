# podcast_outreach/database/queries/episodes.py
import logging
from typing import Any, Dict, Optional, List, Set, Tuple
from datetime import datetime, date
 
from podcast_outreach.database.connection import get_db_pool
 
logger = logging.getLogger(__name__)
 
async def insert_episode(episode_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Insert a single episode record and return it."""
    query = """
    INSERT INTO episodes (
        media_id, title, publish_date, duration_sec, episode_summary,
        episode_url, transcript, transcribe, downloaded, guest_names,
        host_names, source_api, api_episode_id, ai_episode_summary, embedding,
        episode_themes, episode_keywords, ai_analysis_done
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                episode_data["media_id"],
                episode_data["title"],
                episode_data["publish_date"],
                episode_data.get("duration_sec"),
                episode_data.get("episode_summary"),
                episode_data.get("episode_url"),
                episode_data.get("transcript"),
                episode_data.get("transcribe", False),
                episode_data.get("downloaded", False),
                episode_data.get("guest_names"),
                episode_data.get("host_names"),
                episode_data.get("source_api"),
                episode_data.get("api_episode_id"),
                episode_data.get("ai_episode_summary"),
                episode_data.get("embedding"),
                episode_data.get("episode_themes"),
                episode_data.get("episode_keywords"),
                episode_data.get("ai_analysis_done", False),
            )
            return dict(row) if row else None
        except Exception as e:
            logger.exception("Error inserting episode for media_id %s: %s", episode_data.get("media_id"), e)
            return None

async def insert_episodes_batch(episodes_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Inserts multiple episode records in a single batch operation."""
    if not episodes_data:
        return []

    # Column list for clarity and easier modification
    columns = [
        "media_id", "title", "publish_date", "duration_sec", "episode_summary",
        "episode_url", "transcript", "transcribe", "downloaded", "guest_names",
        "host_names", "source_api", "api_episode_id", "ai_episode_summary", "embedding",
        "episode_themes", "episode_keywords", "ai_analysis_done"
    ]
    
    # Generate placeholders like $1, $2, ..., $N
    placeholders = ", ".join([f"${i+1}" for i in range(len(columns))])
    
    query = f"""
    INSERT INTO episodes ({', '.join(columns)}) 
    VALUES ({placeholders})
    RETURNING *;
    """
    
    records = []
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                for episode_data in episodes_data:
                    # Prepare values in the correct order corresponding to columns list
                    values_tuple = tuple(episode_data.get(col) for col in columns)
                    # Special handling for boolean defaults if not present in episode_data
                    # This is a bit verbose; ideally, episode_data would always have these keys or DB defaults handle them.
                    # For this specific function, let's ensure defaults are applied if keys are missing.
                    current_values = list(values_tuple)
                    if episode_data.get("transcribe") is None:
                        current_values[columns.index("transcribe")] = False
                    if episode_data.get("downloaded") is None:
                        current_values[columns.index("downloaded")] = False
                    if episode_data.get("ai_analysis_done") is None:
                        current_values[columns.index("ai_analysis_done")] = False
                    
                    row = await conn.fetchrow(query, *current_values)
                    if row:
                        records.append(dict(row))
                logger.info(f"Successfully inserted {len(records)} episodes in batch.")
                return records
            except Exception as e:
                logger.exception("Error inserting episodes batch: %s", e)
                raise # Re-raise to trigger transaction rollback
 
async def delete_oldest_episodes(media_id: int, keep_count: int = 10) -> int:
    """Delete episodes beyond the most recent `keep_count` for a media."""
    query = """
    DELETE FROM episodes
    WHERE media_id = $1 AND episode_id NOT IN (
        SELECT episode_id FROM episodes
        WHERE media_id = $1
        ORDER BY publish_date DESC, episode_id DESC
        LIMIT $2
    )
    RETURNING episode_id;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, media_id, keep_count)
            deleted = len(rows)
            logger.info("Deleted %s old episodes for media_id %s", deleted, media_id)
            return deleted
        except Exception as e:
            logger.exception("Error deleting old episodes for media_id %s: %s", media_id, e)
            return 0
 
async def flag_recent_episodes_for_transcription(media_id: int, count: int = 4) -> int:
    """Flag the most recent episodes for transcription."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                candidate_rows = await conn.fetch(
                    """
                    SELECT episode_id FROM episodes
                    WHERE media_id = $1 AND downloaded = FALSE
                          AND (transcript IS NULL OR transcript = '')
                    ORDER BY COALESCE(publish_date, '1970-01-01') DESC, episode_id DESC
                    LIMIT $2;
                    """,
                    media_id,
                    count,
                )
                candidate_ids = [row["episode_id"] for row in candidate_rows]
 
                if candidate_ids:
                    # Set existing 'transcribe = TRUE' episodes to FALSE if they are not in the new candidate list
                    await conn.execute(
                        f"""
                        UPDATE episodes
                        SET transcribe = FALSE, updated_at = NOW()
                        WHERE media_id = $1 AND transcribe = TRUE AND downloaded = FALSE
                              AND episode_id NOT IN ({','.join(map(str, candidate_ids))});
                        """,
                        media_id,
                    )
                    # Set new candidates to TRUE
                    flagged = await conn.fetch(
                        f"""
                        UPDATE episodes
                        SET transcribe = TRUE, updated_at = NOW()
                        WHERE episode_id IN ({','.join(map(str, candidate_ids))})
                        RETURNING episode_id;
                        """
                    )
                    logger.info("Flagged %s episodes for transcription for media_id %s", len(flagged), media_id)
                    return len(flagged)
                else:
                    # If no candidates, ensure all existing 'transcribe = TRUE' episodes are set to FALSE
                    await conn.execute(
                        "UPDATE episodes SET transcribe = FALSE, updated_at = NOW() "
                        "WHERE media_id = $1 AND transcribe = TRUE AND downloaded = FALSE;",
                        media_id,
                    )
                    return 0
            except Exception as e:
                logger.exception("Error flagging episodes for transcription for media_id %s: %s", media_id, e)
                raise
 
async def fetch_episodes_for_transcription(limit: int = 20) -> list[Dict[str, Any]]:
    """Return episodes that need transcription."""
    query = """
    SELECT episode_id, media_id, episode_url, title
    FROM episodes
    WHERE transcribe = TRUE AND (transcript IS NULL OR transcript = '')
    ORDER BY created_at ASC
    LIMIT $1;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception("Error fetching episodes for transcription: %s", e)
            return []
 
async def update_episode_transcription(
    episode_id: int,
    transcript: str,
    summary: str | None = None,
    embedding: list[float] | None = None,
) -> Optional[Dict[str, Any]]:
    """Update an episode with its transcript and optional summary/embedding."""
    set_clauses = ["transcript = $1", "downloaded = TRUE", "updated_at = NOW()"]
    values = [transcript]
    idx = 2
    if summary is not None:
        set_clauses.append(f"ai_episode_summary = ${idx}")
        values.append(summary)
        idx += 1
    if embedding is not None:
        set_clauses.append(f"embedding = ${idx}")
        values.append(embedding)
        idx += 1
    query = f"""
    UPDATE episodes
    SET {', '.join(set_clauses)}
    WHERE episode_id = ${idx}
    RETURNING *;
    """
    values.append(episode_id)
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            return dict(row) if row else None
        except Exception as e:
            logger.exception("Error updating transcription for episode %s: %s", episode_id, e)
            return None
 
async def get_episodes_for_media_with_content(media_id: int) -> List[Dict[str, Any]]:
    """
    Fetches episodes for a given media_id that have either an AI summary or a transcript,
    and their embeddings if available.
    """
    query = """
    SELECT episode_id, title, publish_date, episode_summary, ai_episode_summary, transcript, embedding
    FROM episodes
    WHERE media_id = $1 AND (ai_episode_summary IS NOT NULL OR transcript IS NOT NULL)
    ORDER BY publish_date DESC;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, media_id)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching episodes with content for media_id {media_id}: {e}")
            return []

async def get_existing_episode_identifiers(media_id: int) -> Set[Tuple[str, datetime.date]]:
    """
    Fetches a set of (title, publish_date) tuples for existing episodes of a given media.
    Used to prevent duplicate insertions.
    """
    query = """
    SELECT title, publish_date FROM episodes WHERE media_id = $1;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, media_id)
            return {(r['title'], r['publish_date']) for r in rows}
        except Exception as e:
            logger.exception(f"Error fetching existing episode identifiers for media_id {media_id}: {e}")
            return set()

# NEW: Function to fetch a single episode by ID
async def get_episode_by_id(episode_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a single episode record by its ID."""
    query = "SELECT * FROM episodes WHERE episode_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, episode_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching episode {episode_id}: {e}")
            return None

# NEW: Function to update episode analysis data
async def update_episode_analysis_data(
    episode_id: int,
    host_names: Optional[List[str]] = None,
    guest_names: Optional[List[str]] = None,
    episode_themes: Optional[List[str]] = None,
    episode_keywords: Optional[List[str]] = None,
    ai_analysis_done: bool = True
) -> Optional[Dict[str, Any]]:
    """
    Updates an episode record with AI analysis results.
    """
    set_clauses = ["updated_at = NOW()", "ai_analysis_done = $1"]
    values = [ai_analysis_done]
    idx = 2

    if host_names is not None:
        set_clauses.append(f"guest_names = $2") # Reusing guest_names for host/guest list
        values.append(host_names)
        idx += 1
    if guest_names is not None:
        # If you want separate host_names and guest_names columns, you'd need to add them to schema
        # For now, I'll combine them into 'guest_names' or pick one.
        # Let's update the existing 'guest_names' column with a combined list if both are present.
        # Or, if 'guest_names' is specifically for guests, we need a new 'host_names' column.
        # Given the schema, 'guest_names' is TEXT, not TEXT[]. Let's update it to TEXT[] in schema.
        # For now, I'll use it as a combined list of identified people.
        if guest_names is not None:
            set_clauses.append(f"guest_names = ${idx}")
            values.append(guest_names)
            idx += 1

    if episode_themes is not None:
        set_clauses.append(f"episode_themes = ${idx}")
        values.append(episode_themes)
        idx += 1
    if episode_keywords is not None:
        set_clauses.append(f"episode_keywords = ${idx}")
        values.append(episode_keywords)
        idx += 1

    query = f"""
    UPDATE episodes
    SET {', '.join(set_clauses)}
    WHERE episode_id = ${idx}
    RETURNING *;
    """
    values.append(episode_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error updating episode analysis data for episode {episode_id}: {e}")
            return None

# NEW: Function to fetch episodes needing AI analysis
async def fetch_episodes_for_analysis(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Fetches episodes that have a transcript/summary but haven't been analyzed by AI yet.
    """
    query = """
    SELECT episode_id, media_id, title, episode_summary, ai_episode_summary, transcript
    FROM episodes
    WHERE (transcript IS NOT NULL OR ai_episode_summary IS NOT NULL) AND ai_analysis_done = FALSE
    ORDER BY created_at ASC
    LIMIT $1;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching episodes for AI analysis: {e}")
            return []

async def get_episodes_for_media_with_embeddings(media_id: int, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Fetches recent episodes for a given media_id that have embeddings.
    Orders by publish_date descending to get the most recent ones.
    """
    query = """
    SELECT episode_id, title, publish_date, episode_summary, ai_episode_summary, transcript, embedding
    FROM episodes
    WHERE media_id = $1 AND embedding IS NOT NULL
    ORDER BY publish_date DESC, episode_id DESC
    LIMIT $2;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, media_id, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching episodes with embeddings for media_id {media_id}: {e}", exc_info=True)
            return []

async def get_episodes_for_media_paginated(media_id: int, offset: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetches episodes for a given media_id with pagination, ordered by publish_date descending."""
    query = """
    SELECT *
    FROM episodes
    WHERE media_id = $1
    ORDER BY publish_date DESC, episode_id DESC
    LIMIT $2 OFFSET $3;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, media_id, limit, offset)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching paginated episodes for media_id {media_id}: {e}", exc_info=True)
            return []

async def get_episode_by_api_id(api_episode_id: str, media_id: int, source_api: str) -> Optional[Dict[str, Any]]:
    """Fetches a single episode by its API-specific ID, media_id, and source_api."""
    query = """
    SELECT * FROM episodes 
    WHERE api_episode_id = $1 AND media_id = $2 AND source_api = $3;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, api_episode_id, media_id, source_api)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching episode by api_episode_id '{api_episode_id}' for media_id {media_id}: {e}")
            return None