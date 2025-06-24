# podcast_outreach/database/queries/episodes.py
import logging
import re
import json
import numpy as np
from typing import Any, Dict, Optional, List, Set, Tuple
from datetime import datetime, date
 
from podcast_outreach.database.connection import get_db_pool, get_background_task_pool
 
logger = logging.getLogger(__name__)
 
async def insert_episode(episode_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Insert a single episode record and return it."""
    query = """
    INSERT INTO episodes (
        media_id, title, publish_date, duration_sec, episode_summary,
        episode_url, direct_audio_url, transcript, transcribe, downloaded, guest_names,
        host_names, source_api, api_episode_id, ai_episode_summary, embedding,
        episode_themes, episode_keywords, ai_analysis_done
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
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
                episode_data.get("direct_audio_url"),
                episode_data.get("transcript"),
                episode_data.get("transcribe", False), # Default to False
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
    ON CONFLICT DO NOTHING -- Added to prevent errors if an episode is somehow processed twice
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
 
async def flag_specific_episodes_for_transcription(media_id: int, episode_ids_to_flag: List[int]) -> int:
    """
    Atomically sets `transcribe` to TRUE for specific episode IDs and FALSE for all others of that media.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                # Step 1: Set all to FALSE first for this media_id
                await conn.execute(
                    "UPDATE episodes SET transcribe = FALSE WHERE media_id = $1",
                    media_id
                )
                
                # Step 2: Set specific episodes to TRUE
                if episode_ids_to_flag:
                    # Use `unnest` for performance with a list of IDs
                    update_query = """
                    UPDATE episodes
                    SET transcribe = TRUE
                    WHERE media_id = $1 AND episode_id = ANY($2::int[])
                    RETURNING episode_id;
                    """
                    flagged_rows = await conn.fetch(update_query, media_id, episode_ids_to_flag)
                    flagged_count = len(flagged_rows)
                    logger.info(f"Specifically flagged {flagged_count} episodes for transcription for media_id {media_id}")
                    return flagged_count
                return 0
            except Exception as e:
                logger.exception(f"Error in flag_specific_episodes_for_transcription for media_id {media_id}: {e}")
                raise

async def fetch_episodes_for_transcription(limit: int = 20, pool: Optional[Any] = None) -> list[Dict[str, Any]]:
    """
    Return episodes that need transcription.
    
    IMPORTANT: When no pool is provided, this function uses get_background_task_pool()
    instead of get_db_pool() because it's primarily called from background transcription
    tasks. Using the frontend pool can cause timeout errors during long-running operations.
    
    See: Database connection issues fix - 2025-06-20
    """
    query = """
    SELECT episode_id, media_id, episode_url, title, direct_audio_url
    FROM episodes
    WHERE transcribe = TRUE AND (transcript IS NULL OR transcript = '')
    ORDER BY created_at ASC
    LIMIT $1;
    """
    # Use background task pool when no specific pool provided (transcription is a background task)
    if pool is None:
        pool_to_use = await get_background_task_pool()
    else:
        pool_to_use = pool
    async with pool_to_use.acquire() as conn:
        try:
            rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception("Error fetching episodes for transcription: %s", e)
            return []

async def fetch_episodes_for_analysis(limit: int = 20, pool: Optional[Any] = None) -> list[Dict[str, Any]]:
    """Return episodes that need AI analysis (have transcript/summary but no analysis done)."""
    query = """
    SELECT episode_id, media_id, title, transcript, ai_episode_summary, episode_summary
    FROM episodes
    WHERE ai_analysis_done = FALSE 
    AND (transcript IS NOT NULL OR ai_episode_summary IS NOT NULL OR episode_summary IS NOT NULL)
    AND (transcript != '' OR ai_episode_summary != '' OR episode_summary != '')
    ORDER BY created_at ASC
    LIMIT $1;
    """
    if pool is None:
        pool_to_use = await get_db_pool()
    else:
        pool_to_use = pool
    async with pool_to_use.acquire() as conn:
        try:
            rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception("Error fetching episodes for analysis: %s", e)
            return []
 
async def update_episode_transcription(
    episode_id: int,
    transcript: str,
    summary: str | None = None,
    embedding: list[float] | None = None,
    max_retries: int = 3,
    pool: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Update an episode with its transcript and optional summary/embedding.
    
    IMPORTANT: When no pool is provided, this function uses get_background_task_pool()
    instead of get_db_pool() because it's called from background transcription tasks.
    This prevents "TimeoutError" and "Control plane request failed" errors that occur
    when using the frontend pool for long-running operations.
    
    See: Database connection issues fix - 2025-06-20
    """
    set_clauses = ["transcript = $1", "downloaded = TRUE", "updated_at = NOW()"]
    values = [transcript]
    idx = 2
    if summary is not None:
        set_clauses.append(f"ai_episode_summary = ${idx}")
        values.append(summary)
        idx += 1
    if embedding is not None:
        set_clauses.append(f"embedding = ${idx}")
        # Convert to proper pgvector format
        import numpy as np
        
        # Debug logging to see what type of embedding we're getting
        logger.debug(f"Embedding type: {type(embedding)}, first 100 chars: {str(embedding)[:100]}")
        
        # Handle different input types
        if isinstance(embedding, (list, tuple)):
            # Convert list/tuple to vector string
            embedding_str = '[' + ','.join(map(str, embedding)) + ']'
            values.append(embedding_str)
        elif isinstance(embedding, np.ndarray):
            # Convert numpy array to vector string
            embedding_str = '[' + ','.join(map(str, embedding.tolist())) + ']'
            values.append(embedding_str)
        elif isinstance(embedding, str):
            # If it's already a string, check if it's a numpy string representation
            if embedding.startswith("np.str_('") and embedding.endswith("')"):
                # Extract the actual vector string from numpy representation
                clean_embedding = embedding[9:-2]  # Remove np.str_(' and ')
                values.append(clean_embedding)
            elif embedding.startswith("np.float") or embedding.startswith("array("):
                # Handle other numpy string representations
                import re
                # Extract numbers from numpy string using regex
                numbers = re.findall(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?', embedding)
                if numbers:
                    embedding_str = '[' + ','.join(numbers) + ']'
                    values.append(embedding_str)
                else:
                    values.append(embedding)
            elif embedding.startswith('[') and embedding.endswith(']'):
                # Already in correct format
                values.append(embedding)
            else:
                # Try to parse as comma-separated values
                try:
                    # Convert to list and back to proper format
                    nums = [float(x.strip()) for x in embedding.split(',')]
                    embedding_str = '[' + ','.join(map(str, nums)) + ']'
                    values.append(embedding_str)
                except:
                    # If all else fails, pass as is
                    values.append(embedding)
        else:
            values.append(str(embedding))
        idx += 1
    query = f"""
    UPDATE episodes
    SET {', '.join(set_clauses)}
    WHERE episode_id = ${idx}
    RETURNING *;
    """
    values.append(episode_id)
    
    for attempt in range(max_retries + 1):
        try:
            # Use background task pool when no specific pool provided (this is called from background tasks)
            if pool is None:
                pool_to_use = await get_background_task_pool()
            else:
                pool_to_use = pool
            async with pool_to_use.acquire() as conn:
                row = await conn.fetchrow(query, *values)
                return dict(row) if row else None
        except Exception as e:
            if attempt < max_retries and "connection is closed" in str(e).lower():
                logger.warning(f"Connection closed during episode update (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                # Force background task pool reset and retry (not frontend pool)
                from podcast_outreach.database.connection import reset_background_task_pool
                try:
                    await reset_background_task_pool()
                except:
                    pass  # If reset fails, continue with retry anyway
                import asyncio
                await asyncio.sleep(0.5)  # Brief delay before retry
                continue
            else:
                logger.exception("Error updating transcription for episode %s: %s", episode_id, e)
                return None
    
    return None

async def update_episode_audio_url(episode_id: int, audio_url: str, pool: Optional[Any] = None) -> bool:
    """Update an episode's audio URL."""
    query = """
    UPDATE episodes 
    SET direct_audio_url = $1, updated_at = NOW()
    WHERE episode_id = $2
    """
    try:
        if pool is None:
            pool_to_use = await get_db_pool()
        else:
            pool_to_use = pool
        async with pool_to_use.acquire() as conn:
            await conn.execute(query, audio_url, episode_id)
            return True
    except Exception as e:
        logger.error(f"Error updating audio URL for episode {episode_id}: {e}")
        return False

async def get_episode_by_id(episode_id: int, pool: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Get episode by ID."""
    query = "SELECT * FROM episodes WHERE episode_id = $1"
    try:
        if pool is None:
            pool_to_use = await get_db_pool()
        else:
            pool_to_use = pool
        async with pool_to_use.acquire() as conn:
            row = await conn.fetchrow(query, episode_id)
            return dict(row) if row else None
    except Exception as e:
        logger.error(f"Error fetching episode {episode_id}: {e}")
        return None
 
async def get_episodes_for_media_with_content(media_id: int, limit: int = None) -> List[Dict[str, Any]]:
    """
    Fetches episodes for a given media_id that have either an AI summary or a transcript,
    and their embeddings if available.
    """
    if limit is not None:
        query = """
        SELECT episode_id, title, publish_date, episode_summary, ai_episode_summary, transcript, embedding
        FROM episodes
        WHERE media_id = $1 AND (ai_episode_summary IS NOT NULL OR transcript IS NOT NULL)
        ORDER BY publish_date DESC
        LIMIT $2;
        """
    else:
        query = """
        SELECT episode_id, title, publish_date, episode_summary, ai_episode_summary, transcript, embedding
        FROM episodes
        WHERE media_id = $1 AND (ai_episode_summary IS NOT NULL OR transcript IS NOT NULL)
        ORDER BY publish_date DESC;
        """
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            if limit is not None:
                rows = await conn.fetch(query, media_id, limit)
            else:
                rows = await conn.fetch(query, media_id)
            
            results = []
            for row in rows:
                episode = dict(row)
                # Convert vector string to numpy array if needed
                if episode.get('embedding') and isinstance(episode['embedding'], str):
                    # PostgreSQL returns vectors as strings like '[0.1, 0.2, ...]'
                    try:
                        episode['embedding'] = np.array(eval(episode['embedding']))
                    except:
                        # If eval fails, try parsing as JSON
                        try:
                            episode['embedding'] = np.array(json.loads(episode['embedding']))
                        except:
                            logger.warning(f"Could not parse embedding for episode {episode['episode_id']}")
                            episode['embedding'] = None
                results.append(episode)
            return results
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
        set_clauses.append(f"host_names = ${idx}")
        values.append(host_names)
        idx += 1
    if guest_names is not None:
        # Converting guest_names list to a comma-separated string since guest_names is TEXT, not TEXT[]
        guest_names_str = ', '.join(guest_names) if isinstance(guest_names, list) else guest_names
        set_clauses.append(f"guest_names = ${idx}")
        values.append(guest_names_str)
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

async def fetch_episodes_for_embedding_generation(limit: int = 20, pool: Optional[Any] = None) -> List[Dict[str, Any]]:
    """
    Return episodes that have content but are missing embeddings.
    
    IMPORTANT: When no pool is provided, this function uses get_background_task_pool()
    instead of get_db_pool() because it's called from background embedding generation
    tasks. Using the frontend pool can cause timeout errors during AI operations.
    
    See: Database connection issues fix - 2025-06-20
    """
    query = """
    SELECT episode_id, media_id, title, transcript, ai_episode_summary, episode_summary
    FROM episodes
    WHERE embedding IS NULL 
    AND (transcript IS NOT NULL OR ai_episode_summary IS NOT NULL OR episode_summary IS NOT NULL)
    AND (transcript != '' OR ai_episode_summary != '' OR episode_summary != '')
    ORDER BY created_at ASC
    LIMIT $1;
    """
    # Use background task pool when no specific pool provided (embedding generation is a background task)
    if pool is None:
        pool_to_use = await get_background_task_pool()
    else:
        pool_to_use = pool
    async with pool_to_use.acquire() as conn:
        try:
            rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception("Error fetching episodes for embedding generation: %s", e)
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
            results = []
            for row in rows:
                episode = dict(row)
                
                if episode.get('embedding') and isinstance(episode['embedding'], str):
                    # PostgreSQL returns vectors as strings like '[0.1, 0.2, ...]'
                    try:
                        episode['embedding'] = np.array(eval(episode['embedding']))
                    except:
                        # If eval fails, try parsing as JSON
                        try:
                            episode['embedding'] = np.array(json.loads(episode['embedding']))
                        except:
                            logger.warning(f"Could not parse embedding for episode {episode['episode_id']}")
                            episode['embedding'] = None
                results.append(episode)
            return results
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

# DEPRECATED: This function is too broad. Use flag_specific_episodes_for_transcription instead.
async def flag_recent_episodes_for_transcription(media_id: int, count: int = 4) -> int:
    """DEPRECATED: Flag the most recent episodes for transcription."""
    logger.warning("flag_recent_episodes_for_transcription is deprecated. Use flag_specific_episodes_for_transcription.")
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

async def get_most_recent_episode_for_media(media_id: int) -> Optional[Dict[str, Any]]:
    """Get the most recent episode for a specific media."""
    query = """
    SELECT episode_id, title, publish_date
    FROM episodes
    WHERE media_id = $1
    ORDER BY publish_date DESC
    LIMIT 1;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, media_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching most recent episode for media {media_id}: {e}")
            return None


async def get_episodes_with_embeddings_for_media(media_id: int) -> List[Dict[str, Any]]:
    """Get all episodes with embeddings for a specific media."""
    query = """
    SELECT episode_id, title, publish_date, embedding
    FROM episodes
    WHERE media_id = $1 
    AND embedding IS NOT NULL
    ORDER BY publish_date DESC;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, media_id)
            results = []
            for row in rows:
                episode = dict(row)
                # Convert vector string to numpy array if needed
                embedding = episode.get('embedding')
                if embedding:
                    if isinstance(embedding, str):
                        # PostgreSQL returns vectors as strings like '[0.1, 0.2, ...]'
                        try:
                            # Safe parsing: remove brackets and split by comma
                            vector_str = embedding.strip('[]')
                            values = [float(x.strip()) for x in vector_str.split(',')]
                            episode['embedding'] = np.array(values)
                        except Exception as e:
                            logger.warning(f"Could not parse embedding for episode {episode['episode_id']}: {e}")
                            episode['embedding'] = None
                    elif isinstance(embedding, (list, np.ndarray)):
                        # Already in proper format
                        episode['embedding'] = np.array(embedding)
                    else:
                        logger.warning(f"Unexpected embedding type for episode {episode['episode_id']}: {type(embedding)}")
                        episode['embedding'] = None
                
                # Only include episodes with valid embeddings
                if episode.get('embedding') is not None:
                    results.append(episode)
            return results
        except Exception as e:
            logger.error(f"Error fetching episodes with embeddings for media {media_id}: {e}")
            return []

