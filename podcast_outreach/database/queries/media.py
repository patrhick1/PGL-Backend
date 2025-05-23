# podcast_outreach/database/queries/media.py

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, date
import uuid # For UUID types if needed for related entities

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool

logger = get_logger(__name__)

async def create_media_in_db(media_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    query = """
    INSERT INTO media (
        name, title, rss_url, rss_feed_url, website, description, ai_description,
        contact_email, language, category, image_url, company_id, avg_downloads,
        audience_size, total_episodes, itunes_id, podcast_spotify_id, listen_score,
        listen_score_global_rank, itunes_rating_average, itunes_rating_count,
        spotify_rating_average, spotify_rating_count, fetched_episodes, source_api,
        api_id, last_posted_at, podcast_twitter_url, podcast_linkedin_url,
        podcast_instagram_url, podcast_facebook_url, podcast_youtube_url,
        podcast_tiktok_url, podcast_other_social_url, host_names, rss_owner_name,
        rss_owner_email, rss_explicit, rss_categories, twitter_followers,
        twitter_following, is_twitter_verified, linkedin_connections,
        instagram_followers, tiktok_followers, facebook_likes, youtube_subscribers,
        publishing_frequency_days, last_enriched_timestamp, quality_score, first_episode_date,
        latest_episode_date
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
        $21, $22, $23, $24, $25, $26, $27, $28, $29, $30, $31, $32, $33, $34, $35, $36, $37, $38,
        $39, $40, $41, $42, $43, $44, $45, $46, $47, $48, $49, $50, $51
    ) RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                media_data.get('name'), media_data.get('title'), media_data.get('rss_url'),
                media_data.get('rss_feed_url'), media_data.get('website'), media_data.get('description'),
                media_data.get('ai_description'), media_data.get('contact_email'), media_data.get('language'),
                media_data.get('category'), media_data.get('image_url'), media_data.get('company_id'),
                media_data.get('avg_downloads'), media_data.get('audience_size'), media_data.get('total_episodes'),
                media_data.get('itunes_id'), media_data.get('podcast_spotify_id'), media_data.get('listen_score'),
                media_data.get('listen_score_global_rank'), media_data.get('itunes_rating_average'),
                media_data.get('itunes_rating_count'), media_data.get('spotify_rating_average'),
                media_data.get('spotify_rating_count'), media_data.get('fetched_episodes', False),
                media_data.get('source_api'), media_data.get('api_id'), media_data.get('last_posted_at'),
                media_data.get('podcast_twitter_url'), media_data.get('podcast_linkedin_url'),
                media_data.get('podcast_instagram_url'), media_data.get('podcast_facebook_url'),
                media_data.get('podcast_youtube_url'), media_data.get('podcast_tiktok_url'),
                media_data.get('podcast_other_social_url'), media_data.get('host_names'),
                media_data.get('rss_owner_name'), media_data.get('rss_owner_email'),
                media_data.get('rss_explicit'), media_data.get('rss_categories'),
                media_data.get('twitter_followers'), media_data.get('twitter_following'),
                media_data.get('is_twitter_verified'), media_data.get('linkedin_connections'),
                media_data.get('instagram_followers'), media_data.get('tiktok_followers'),
                media_data.get('facebook_likes'), media_data.get('youtube_subscribers'),
                media_data.get('publishing_frequency_days'), media_data.get('last_enriched_timestamp'),
                media_data.get('quality_score'), media_data.get('first_episode_date'),
                media_data.get('latest_episode_date')
            )
            logger.info(f"Media created: {media_data.get('name')}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error creating media {media_data.get('name')} in DB: {e}")
            raise

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

async def update_media_in_db(media_id: int, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not update_fields:
        logger.warning(f"No update data for media {media_id}. Fetching current.")
        return await get_media_by_id_from_db(media_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_fields.items():
        if key == "media_id": continue # Don't update the ID
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses: # No valid fields to update
        return await get_media_by_id_from_db(media_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE media SET {set_clause_str} WHERE media_id = ${idx} RETURNING *;"
    values.append(media_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Media updated: {media_id} with fields: {list(update_fields.keys())}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error updating media {media_id}: {e}")
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
    """Create or update a media record based on rss_url or api_id."""
    rss_url = media_data.get("rss_url")
    api_id = media_data.get("api_id")
    
    existing = None
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if rss_url:
            query = "SELECT * FROM media WHERE rss_url = $1;"
            existing = await conn.fetchrow(query, rss_url)
        elif api_id: # Fallback to api_id if no RSS or RSS didn't find a match
            query = "SELECT * FROM media WHERE api_id = $1;"
            existing = await conn.fetchrow(query, api_id)
        
        existing = dict(existing) if existing else None

        if existing:
            set_clauses = []
            values = []
            idx = 1
            for k, v in media_data.items():
                # Skip primary keys and immutable identifiers for update
                if k in ["media_id", "rss_url", "api_id", "created_at"]:
                    continue
                set_clauses.append(f"{k} = ${idx}")
                values.append(v)
                idx += 1
            
            # Always update updated_at timestamp
            set_clauses.append(f"updated_at = NOW()")

            if not set_clauses:
                return existing # No fields to update, return existing record

            # Use existing media_id for update
            update_query = f"UPDATE media SET {', '.join(set_clauses)} WHERE media_id = ${idx} RETURNING *;"
            values.append(existing['media_id'])
            row = await conn.fetchrow(update_query, *values)
            logger.info(f"Media updated: {existing.get('name')} (ID: {existing['media_id']})")
            return dict(row) if row else None
        else:
            # Insert new record
            columns = []
            placeholders = []
            values = []
            idx = 1
            for k, v in media_data.items():
                # Skip media_id if it's auto-generated
                if k == "media_id": continue
                columns.append(k)
                placeholders.append(f"${idx}")
                values.append(v)
                idx += 1
            
            insert_query = f"""
            INSERT INTO media ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING *;
            """
            row = await conn.fetchrow(insert_query, *values)
            logger.info(f"Media created: {media_data.get('name')} (ID: {row.get('media_id') if row else 'N/A'})")
            return dict(row) if row else None

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
