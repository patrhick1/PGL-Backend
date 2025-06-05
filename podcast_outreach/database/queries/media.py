# podcast_outreach/database/queries/media.py

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, date
import uuid # For UUID types if needed for related entities

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool

logger = get_logger(__name__)

async def get_media_by_id_from_db(media_id: int) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM media WHERE media_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, media_id)
            if not row:
                logger.debug(f"Media not found: {media_id}")
                return None
            return dict(row)
        except Exception as e:
            logger.exception(f"Error fetching media {media_id}: {e}")
            raise

async def get_media_by_rss_url_from_db(rss_url: str) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM media WHERE rss_url = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, rss_url)
            if not row:
                logger.debug(f"Media not found by RSS URL: {rss_url}")
                return None
            return dict(row)
        except Exception as e:
            logger.exception(f"Error fetching media by RSS URL {rss_url}: {e}")
            raise

async def get_all_media_from_db(skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    query = "SELECT * FROM media ORDER BY created_at DESC OFFSET $1 LIMIT $2;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, skip, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching all media: {e}")
            raise

async def delete_media_from_db(media_id: int) -> bool:
    query = "DELETE FROM media WHERE media_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, media_id)
            deleted_count = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
            if deleted_count > 0:
                logger.info(f"Media deleted: {media_id}")
                return True
            logger.warning(f"Media not found for deletion or delete failed: {media_id}")
            return False
        except Exception as e:
            logger.exception(f"Error deleting media {media_id} from DB: {e}")
            raise

async def upsert_media_in_db(media_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Atomically creates a new media record or updates an existing one based on the `api_id`.
    This version uses a standard, non-dynamic ON CONFLICT statement for robustness.
    A UNIQUE index on `api_id` is required in the `media` table.
    """
    # Define the full list of columns that can be inserted or updated.
    # This order MUST match the order of values provided in the query.
    cols = [
        'api_id', 'source_api', 'name', 'title', 'rss_url', 'website', 'description', 
        'contact_email', 'language', 'category', 'image_url', 'total_episodes', 
        'itunes_id', 'podcast_spotify_id', 'listen_score', 'listen_score_global_rank', 
        'itunes_rating_average', 'itunes_rating_count', 'audience_size', 'last_posted_at',
        'podcast_twitter_url', 'podcast_linkedin_url', 'podcast_instagram_url',
        'podcast_facebook_url', 'podcast_youtube_url', 'podcast_tiktok_url', 
        'podcast_other_social_url', 'host_names', 'last_enriched_timestamp'
        # Add any other columns from your schema that you want to manage through this upsert
    ]

    # Prepare values tuple, using .get(col, None) to prevent KeyErrors
    values = [media_data.get(c) for c in cols]

    # Build the SET clause for the UPDATE part of the query
    # This will update every column (except api_id) with the new value if it's not NULL,
    # otherwise it keeps the existing value.
    update_set_parts = [f"{col} = COALESCE(EXCLUDED.{col}, media.{col})" for col in cols if col != 'api_id']
    update_set_parts.append("updated_at = NOW()") # Always update the timestamp
    update_set_clause = ", ".join(update_set_parts)

    # Build the placeholders for the INSERT values, e.g., $1, $2, $3...
    placeholders = ", ".join([f"${i+1}" for i in range(len(cols))])

    query = f"""
    INSERT INTO media ({', '.join(cols)})
    VALUES ({placeholders})
    ON CONFLICT (api_id) DO UPDATE 
    SET {update_set_clause}
    RETURNING *;
    """
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Important: Ensure the number of values in the `values` list
            # matches the number of placeholders in the query string.
            row = await conn.fetchrow(query, *values)
            if row:
                logger.info(f"Media upserted successfully: '{row['name']}' (ID: {row['media_id']})")
                return dict(row)
            else:
                logger.error(f"Upsert for '{media_data.get('name')}' returned no row.")
                return None
        except Exception as e:
            logger.exception(f"Error during robust upsert for media '{media_data.get('name')}': {e}")
            raise # Re-raise the exception to be handled by the caller

async def update_media_after_sync(media_id: int) -> Optional[Dict[str, Any]]:
    """Updates last_fetched_at for a media item after episode sync."""
    query = """
    UPDATE media
    SET last_fetched_at = NOW(),
        fetched_episodes = TRUE
    WHERE media_id = $1
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, media_id)
            if row:
                logger.info(f"Media {media_id} last_fetched_at updated.")
                return dict(row)
            logger.warning(f"Media {media_id} not found for last_fetched_at update.")
            return None
        except Exception as e:
            logger.exception(f"Error updating media {media_id} last_fetched_at: {e}")
            raise

async def update_media_latest_episode_date(media_id: int) -> Optional[Dict[str, Any]]:
    """Updates the latest_episode_date for a media item based on its episodes."""
    query = """
    UPDATE media
    SET latest_episode_date = (
        SELECT MAX(publish_date) FROM episodes WHERE media_id = $1
    )
    WHERE media_id = $1
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, media_id)
            if row:
                logger.info(f"Media {media_id} latest_episode_date updated to {row.get('latest_episode_date')}.")
                return dict(row)
            logger.warning(f"Media {media_id} not found for latest_episode_date update.")
            return None
        except Exception as e:
            logger.exception(f"Error updating media {media_id} latest_episode_date: {e}")
            raise

async def get_media_to_sync_episodes(interval_hours: int = 24) -> List[Dict[str, Any]]:
    """
    Fetches media items that need their episodes synced.
    Criteria: last_fetched_at is NULL OR last_fetched_at is older than interval_hours.
    """
    query = """
    SELECT media_id, name, rss_url, api_id, source_api
    FROM media
    WHERE last_fetched_at IS NULL OR last_fetched_at < NOW() - INTERVAL '$1 hours'
    ORDER BY last_fetched_at ASC NULLS FIRST
    LIMIT 50; -- Limit to a reasonable batch size
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, interval_hours)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching media to sync episodes: {e}")
            raise

async def get_media_for_enrichment(batch_size: int = 10, enriched_before_hours: int = 24 * 7) -> List[Dict[str, Any]]:
    """
    Fetches media items that need enrichment or re-enrichment.
    Criteria: last_enriched_timestamp is NULL OR last_enriched_timestamp is older than enriched_before_hours.
    """
    query = """
    SELECT *
    FROM media
    WHERE last_enriched_timestamp IS NULL OR last_enriched_timestamp < NOW() - INTERVAL '$1 hours'
    ORDER BY last_enriched_timestamp ASC NULLS FIRST
    LIMIT $2;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, enriched_before_hours, batch_size)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching media for enrichment: {e}")
            raise

async def update_media_enrichment_data(media_id: int, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates a media record with enriched data."""
    if not update_fields:
        logger.warning(f"No enrichment update data for media {media_id}.")
        return await get_media_by_id_from_db(media_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_fields.items():
        if key in ["media_id", "created_at", "updated_at"]: continue # Don't update these
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    
    # Always update last_enriched_timestamp
    set_clauses.append(f"last_enriched_timestamp = NOW()")

    if not set_clauses:
        return await get_media_by_id_from_db(media_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE media SET {set_clause_str} WHERE media_id = ${idx} RETURNING *;"
    values.append(media_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Media {media_id} enrichment data updated.")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error updating media {media_id} enrichment data: {e}")
            raise

async def update_media_quality_score(media_id: int, quality_score: float) -> bool:
    """Updates the quality_score for a media item."""
    query = """
    UPDATE media
    SET quality_score = $1
    WHERE media_id = $2
    RETURNING media_id;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, quality_score, media_id)
            if row:
                logger.info(f"Media {media_id} quality score updated to {quality_score}.")
                return True
            logger.warning(f"Media {media_id} not found for quality score update.")
            return False
        except Exception as e:
            logger.exception(f"Error updating media {media_id} quality score: {e}")
            raise

async def count_transcribed_episodes_for_media(media_id: int) -> int:
    """Counts the number of episodes for a media item that have a transcript."""
    query = """
    SELECT COUNT(*) FROM episodes
    WHERE media_id = $1 AND (transcript IS NOT NULL AND transcript != '');
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            count = await conn.fetchval(query, media_id)
            return count if count is not None else 0
        except Exception as e:
            logger.exception(f"Error counting transcribed episodes for media {media_id}: {e}")
            return 0

async def get_media_for_recommendation(limit: int = 3, min_quality_score: Optional[float] = None) -> List[Dict[str, Any]]:
    """Fetches media items for recommendation, e.g., by recency or quality score."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            conditions = []
            params = []
            
            if min_quality_score is not None:
                conditions.append(f"quality_score >= ${len(params) + 1}")
                params.append(min_quality_score)
            
            # Add other conditions like "has contact_email", "is not in a 'do not contact' list", etc.
            conditions.append("contact_email IS NOT NULL AND contact_email != ''")


            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            
            # Order by quality_score desc (if available), then by recency of last_posted_at or creation
            query = f"""
                SELECT * FROM media
                {where_clause}
                ORDER BY quality_score DESC NULLS LAST, last_posted_at DESC NULLS LAST, created_at DESC
                LIMIT ${len(params) + 1};
            """
            params.append(limit)
            
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching media for recommendation: {e}")
            return []