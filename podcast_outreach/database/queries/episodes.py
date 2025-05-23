import logging
from typing import Any, Dict, Optional

from db_service_pg import get_db_pool

logger = logging.getLogger(__name__)

async def insert_episode(episode_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Insert a single episode record and return it."""
    query = """
    INSERT INTO episodes (
        media_id, title, publish_date, duration_sec, episode_summary,
        episode_url, transcript, transcribe, downloaded, guest_names,
        source_api, api_episode_id
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
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
                episode_data.get("source_api"),
                episode_data.get("api_episode_id"),
            )
            return dict(row) if row else None
        except Exception as e:
            logger.exception("Error inserting episode for media_id %s: %s", episode_data.get("media_id"), e)
            return None

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
                    await conn.execute(
                        f"""
                        UPDATE episodes
                        SET transcribe = FALSE, updated_at = NOW()
                        WHERE media_id = $1 AND transcribe = TRUE AND downloaded = FALSE
                              AND episode_id NOT IN ({','.join(map(str, candidate_ids))});
                        """,
                        media_id,
                    )
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
                    await conn.execute(
                        "UPDATE episodes SET transcribe = FALSE, updated_at = NOW() "
                        "WHERE media_id = $1 AND transcribe = TRUE AND downloaded = FALSE;",
                        media_id,
                    )
                    return 0
            except Exception as e:
                logger.exception("Error flagging episodes for transcription for media_id %s: %s", media_id, e)
                raise
