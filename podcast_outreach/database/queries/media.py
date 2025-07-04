# podcast_outreach/database/queries/media.py

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, date
import uuid # For UUID types if needed for related entities

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool, get_background_task_pool
import asyncpg

logger = get_logger(__name__)

async def get_media_by_id_from_db(media_id: int, pool: Optional[asyncpg.Pool] = None) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM media WHERE media_id = $1;"
    if pool is None:
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

async def get_media_by_rss_url_from_db(rss_url: str, pool: Optional[asyncpg.Pool] = None) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM media WHERE rss_url = $1;"
    if pool is None:
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

async def upsert_media_in_db(media_data: Dict[str, Any], pool: Optional[asyncpg.Pool] = None) -> Optional[Dict[str, Any]]:
    """
    Atomically creates a new media record or updates an existing one based on the `api_id`.
    This version uses a standard, non-dynamic ON CONFLICT statement for robustness.
    A UNIQUE index on `api_id` is required in the `media` table.
    """
    # Clean the data before processing
    cleaned_data = media_data.copy()
    
    # URL fields that should contain valid URLs
    url_fields = [
        'podcast_twitter_url', 'podcast_linkedin_url', 'podcast_instagram_url',
        'podcast_facebook_url', 'podcast_youtube_url', 'podcast_tiktok_url',
        'podcast_other_social_url', 'website', 'image_url', 'rss_url'
    ]
    
    # Clean URL fields - move emails to contact_email if needed
    for field in url_fields:
        if field in cleaned_data and cleaned_data[field]:
            value = str(cleaned_data[field]).strip()
            # Check if it's an email (contains @ but not a valid URL)
            if '@' in value and not value.startswith(('http://', 'https://')):
                logger.warning(f"Found email '{value}' in URL field '{field}', moving to contact_email")
                # Move email to contact_email field if it's not already set
                if not cleaned_data.get('contact_email'):
                    cleaned_data['contact_email'] = value
                # Clear the URL field
                cleaned_data[field] = None
    
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
    values = [cleaned_data.get(c) for c in cols]

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
    
    if pool is None:
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
    WHERE last_fetched_at IS NULL OR last_fetched_at < NOW() - make_interval(hours => $1)
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

async def get_media_for_enrichment(batch_size: int = 10, enriched_before_hours: int = 24 * 7, only_new: bool = False) -> List[Dict[str, Any]]:
    """
    Fetches media items that need enrichment or re-enrichment.
    
    Args:
        batch_size: Number of records to return
        enriched_before_hours: Consider re-enrichment if older than this (default: 1 week)
        only_new: If True, only return media that have NEVER been enriched (core enrichment)
    """
    if only_new:
        # Core enrichment: only media that have never been enriched
        query = """
        SELECT *
        FROM media
        WHERE last_enriched_timestamp IS NULL
        ORDER BY created_at ASC
        LIMIT $1;
        """
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(query, batch_size)
                return [dict(row) for row in rows]
            except Exception as e:
                logger.exception(f"Error fetching new media for core enrichment: {e}")
                raise
    else:
        # Regular enrichment: includes re-enrichment of old data
        query = """
        SELECT *
        FROM media
        WHERE last_enriched_timestamp IS NULL OR last_enriched_timestamp < NOW() - INTERVAL '%d hours'
        ORDER BY last_enriched_timestamp ASC NULLS FIRST
        LIMIT $1;
        """ % enriched_before_hours
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(query, batch_size)
                return [dict(row) for row in rows]
            except Exception as e:
                logger.exception(f"Error fetching media for enrichment: {e}")
                raise

async def get_media_for_social_refresh(batch_size: int = 20, stale_hours: int = 24 * 7) -> List[Dict[str, Any]]:
    """
    Fetches media items that need social stats refresh (weekly updates).
    Only returns media that have social URLs and need stats refreshing.
    """
    query = """
    SELECT media_id, podcast_twitter_url, podcast_instagram_url, podcast_tiktok_url, 
           podcast_linkedin_url, podcast_facebook_url, podcast_youtube_url,
           social_stats_last_fetched_at
    FROM media
    WHERE (
        social_stats_last_fetched_at IS NULL OR 
        social_stats_last_fetched_at < NOW() - INTERVAL '%d hours'
    )
    AND (
        podcast_twitter_url IS NOT NULL OR 
        podcast_instagram_url IS NOT NULL OR 
        podcast_tiktok_url IS NOT NULL OR 
        podcast_linkedin_url IS NOT NULL OR
        podcast_facebook_url IS NOT NULL OR
        podcast_youtube_url IS NOT NULL
    )
    AND last_enriched_timestamp IS NOT NULL  -- Only refresh stats for already enriched media
    ORDER BY social_stats_last_fetched_at ASC NULLS FIRST
    LIMIT $1;
    """ % stale_hours
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, batch_size)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching media for social refresh: {e}")
            raise

async def get_media_for_quality_score_update(batch_size: int = 20, stale_hours: int = 24 * 7) -> List[Dict[str, Any]]:
    """
    Fetches media items that need quality score updates.
    Only returns enriched media with sufficient episodes for scoring.
    """
    query = """
    SELECT m.*
    FROM media m
    WHERE m.last_enriched_timestamp IS NOT NULL  -- Must be enriched first
    AND (
        m.quality_score IS NULL OR 
        m.updated_at < NOW() - INTERVAL '%d hours'
    )
    AND EXISTS (
        SELECT 1 FROM episodes e 
        WHERE e.media_id = m.media_id 
        AND (e.transcript IS NOT NULL OR e.ai_episode_summary IS NOT NULL)
        LIMIT 3  -- Need at least 3 episodes with content
    )
    ORDER BY m.updated_at ASC NULLS FIRST
    LIMIT $1;
    """ % stale_hours
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, batch_size)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching media for quality score update: {e}")
            raise

async def update_media_enrichment_data(media_id: int, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates a media record with enriched data."""
    if not update_fields:
        logger.warning(f"No enrichment update data for media {media_id}.")
        return await get_media_by_id_from_db(media_id)

    # Clean the update fields before processing
    cleaned_fields = update_fields.copy()
    
    # URL fields that should contain valid URLs
    url_fields = [
        'podcast_twitter_url', 'podcast_linkedin_url', 'podcast_instagram_url',
        'podcast_facebook_url', 'podcast_youtube_url', 'podcast_tiktok_url',
        'podcast_other_social_url', 'website', 'image_url', 'rss_url'
    ]
    
    # Clean URL fields - move emails to contact_email if needed
    for field in url_fields:
        if field in cleaned_fields and cleaned_fields[field]:
            value = str(cleaned_fields[field]).strip()
            # Check if it's an email (contains @ but not a valid URL)
            if '@' in value and not value.startswith(('http://', 'https://')):
                logger.warning(f"Found email '{value}' in URL field '{field}', moving to contact_email")
                # Move email to contact_email field if it's not already set
                if not cleaned_fields.get('contact_email'):
                    cleaned_fields['contact_email'] = value
                # Clear the URL field
                cleaned_fields[field] = None

    # Known JSONB fields in the media table that need JSON serialization
    jsonb_fields = {
        'host_names_discovery_sources', 
        'host_names_discovery_confidence',
        'notification_settings',
        'privacy_settings',
        'social_media_stats',
        'enrichment_metadata'
    }
    
    set_clauses = []
    values = []
    idx = 1
    for key, val in cleaned_fields.items():
        if key in ["media_id", "created_at", "updated_at", "last_enriched_timestamp"]: continue
        
        # For JSONB fields, asyncpg needs JSON strings, not Python objects
        if key in jsonb_fields and val is not None:
            if isinstance(val, (list, dict)):
                import json
                val = json.dumps(val)
            # If it's already a string (pre-serialized JSON), leave it as is
        
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
            if row:
                logger.info(f"Media {media_id} enrichment data updated.")
                
                # Update all pending discovery statuses for this media to 'completed'
                # since core enrichment is now complete (last_enriched_timestamp set)
                discovery_update_query = """
                UPDATE campaign_media_discoveries 
                SET enrichment_status = 'completed',
                    enrichment_completed_at = NOW(),
                    updated_at = NOW()
                WHERE media_id = $1 AND enrichment_status = 'pending'
                RETURNING id;
                """
                updated_discoveries = await conn.fetch(discovery_update_query, media_id)
                if updated_discoveries:
                    discovery_count = len(updated_discoveries)
                    logger.info(f"Updated {discovery_count} discovery statuses to 'completed' for media {media_id}")
                
            return dict(row) if row else None
        except Exception as e:
            # Enhanced error logging to debug data type issues
            if "expected str, got list" in str(e) or "invalid input for query argument" in str(e):
                logger.error(f"Data type error updating media {media_id}. Query: {query}")
                logger.error(f"Values passed: {[f'${i+1}: {v} (type: {type(v).__name__})' for i, v in enumerate(values)]}")
                logger.error(f"Update fields: {list(cleaned_fields.keys())}")
            logger.exception(f"Error updating media {media_id} enrichment data: {e}")
            raise

async def update_media_with_confidence_check(media_id: int, update_fields: Dict[str, Any], source: str = "api", confidence: float = 0.8) -> Optional[Dict[str, Any]]:
    """
    Updates media data while respecting manual overrides and confidence levels.
    
    Args:
        media_id: ID of media to update
        update_fields: Fields to update
        source: Source of the data ('api', 'llm', 'manual')
        confidence: Confidence level (0.0-1.0, where 1.0 = manual/certain)
    
    Rules:
        - Manual data (confidence 1.0) is never overridden
        - Higher confidence data can override lower confidence
        - Always respect last_manual_update_ts
    """
    if not update_fields:
        return await get_media_by_id_from_db(media_id)
    
    # Clean the update fields before processing
    cleaned_update_fields = update_fields.copy()
    
    # URL fields that should contain valid URLs
    url_fields = [
        'podcast_twitter_url', 'podcast_linkedin_url', 'podcast_instagram_url',
        'podcast_facebook_url', 'podcast_youtube_url', 'podcast_tiktok_url',
        'podcast_other_social_url', 'website', 'image_url', 'rss_url'
    ]
    
    # Clean URL fields - move emails to contact_email if needed
    for field in url_fields:
        if field in cleaned_update_fields and cleaned_update_fields[field]:
            value = str(cleaned_update_fields[field]).strip()
            # Check if it's an email (contains @ but not a valid URL)
            if '@' in value and not value.startswith(('http://', 'https://')):
                logger.warning(f"Found email '{value}' in URL field '{field}', moving to contact_email")
                # Move email to contact_email field if it's not already set
                if not cleaned_update_fields.get('contact_email'):
                    cleaned_update_fields['contact_email'] = value
                # Clear the URL field
                cleaned_update_fields[field] = None
    
    # Get current media data to check existing confidence levels
    current_media = await get_media_by_id_from_db(media_id)
    if not current_media:
        logger.warning(f"Media {media_id} not found for confidence-based update")
        return None
    
    # Fields that have confidence tracking
    confidence_fields = {
        'website': ('website_source', 'website_confidence'),
        'contact_email': ('contact_email_source', 'contact_email_confidence'),
        'host_names': ('host_names_source', 'host_names_confidence'),
    }
    
    filtered_updates = {}
    confidence_updates = {}
    
    for field, value in cleaned_update_fields.items():
        if field in confidence_fields:
            source_field, confidence_field = confidence_fields[field]
            current_confidence = current_media.get(confidence_field, 0.0) or 0.0
            current_source = current_media.get(source_field)
            
            # Check if we should override based on confidence
            should_update = False
            
            if source == "manual":
                # Manual updates always win
                should_update = True
                confidence = 1.0
            elif current_source == "manual":
                # Never override manual data with API/LLM data
                logger.info(f"Skipping update to {field} for media {media_id} - manual data takes precedence")
                continue
            elif confidence > current_confidence:
                # Higher confidence can override lower confidence
                should_update = True
            elif confidence == current_confidence and current_media.get(field) is None:
                # Same confidence but no existing data
                should_update = True
            
            if should_update:
                filtered_updates[field] = value
                confidence_updates[source_field] = source
                confidence_updates[confidence_field] = confidence
        else:
            # Fields without confidence tracking - update normally
            filtered_updates[field] = value
    
    # Add confidence tracking updates
    filtered_updates.update(confidence_updates)
    
    # Add manual update timestamp if this is a manual update
    if source == "manual":
        filtered_updates["last_manual_update_ts"] = "NOW()"
    
    if not filtered_updates:
        logger.info(f"No updates applied to media {media_id} after confidence checks")
        return current_media
    
    # Use existing update function
    return await update_media_enrichment_data(media_id, filtered_updates)

async def update_media_manual_override(media_id: int, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Updates media data with manual overrides. These always have the highest confidence (1.0)
    and will not be overridden by API or LLM data.
    """
    return await update_media_with_confidence_check(
        media_id, update_fields, source="manual", confidence=1.0
    )

async def update_media_quality_score(media_id: int, quality_score: float) -> bool:
    """Updates the quality_score for a media item and compiles episode summaries."""
    # First, compile episode summaries
    compile_query = """
    WITH episode_summaries AS (
        SELECT 
            media_id,
            string_agg(
                COALESCE(ai_episode_summary, episode_summary, ''), 
                E'\n\n---\n\n'
                ORDER BY publish_date DESC
            ) as compiled_summaries
        FROM episodes
        WHERE media_id = $1
        AND (ai_episode_summary IS NOT NULL OR episode_summary IS NOT NULL)
        GROUP BY media_id
    )
    UPDATE media m
    SET quality_score = $2,
        episode_summaries_compiled = es.compiled_summaries,
        updated_at = NOW()
    FROM episode_summaries es
    WHERE m.media_id = $1 AND m.media_id = es.media_id
    RETURNING m.media_id;
    """
    
    # Fallback query if no episodes have summaries
    fallback_query = """
    UPDATE media
    SET quality_score = $1,
        updated_at = NOW()
    WHERE media_id = $2
    RETURNING media_id;
    """
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Try to update with episode summaries compilation
            row = await conn.fetchrow(compile_query, media_id, quality_score)
            
            # If no row returned (no episodes with summaries), use fallback
            if not row:
                row = await conn.fetchrow(fallback_query, quality_score, media_id)
            
            if row:
                logger.info(f"Media {media_id} quality score updated to {quality_score} and episode summaries compiled.")
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
        
async def link_person_to_media(media_id: int, person_id: int, role: str) -> bool:
    """
    Creates a link in the media_people table between a media and a person (e.g., a host).
    Uses ON CONFLICT DO NOTHING to avoid errors if the link already exists.
    """
    query = """
    INSERT INTO media_people (media_id, person_id, show_role)
    VALUES ($1, $2, $3)
    ON CONFLICT (media_id, person_id) DO NOTHING;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, media_id, person_id, role)
            logger.info(f"Ensured link between media_id {media_id} and person_id {person_id} with role '{role}'.")
            return True
        except Exception as e:
            logger.error(f"Error linking person {person_id} to media {media_id}: {e}", exc_info=True)
            return False

async def check_campaign_media_discovery_exists(campaign_id: uuid.UUID, media_id: int, pool: Optional[asyncpg.Pool] = None) -> bool:
    """
    Check if a campaign-media discovery record already exists.
    """
    query = """
    SELECT EXISTS(
        SELECT 1 FROM campaign_media_discoveries 
        WHERE campaign_id = $1 AND media_id = $2
    );
    """
    if pool is None:
        pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.fetchval(query, campaign_id, media_id)
            return result
        except Exception as e:
            logger.debug(f"Could not check campaign media discovery (table may not exist): {e}")
            return False

async def track_campaign_media_discovery(campaign_id: uuid.UUID, media_id: int, keyword: str, pool: Optional[asyncpg.Pool] = None) -> bool:
    """
    Track that a media was discovered for a campaign during discovery phase.
    This will be used later to create match suggestions after enrichment.
    Returns True if a NEW record was created, False if it already existed or on error.
    """
    query = """
    INSERT INTO campaign_media_discoveries (campaign_id, media_id, discovery_keyword, discovered_at)
    VALUES ($1, $2, $3, NOW())
    ON CONFLICT (campaign_id, media_id) 
    DO UPDATE SET 
        discovery_keyword = EXCLUDED.discovery_keyword,
        discovered_at = NOW()
    RETURNING (xmax = 0) AS inserted;
    """
    if pool is None:
        pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.fetchrow(query, campaign_id, media_id, keyword)
            is_new = result['inserted'] if result else False
            logger.debug(f"{'Created new' if is_new else 'Updated existing'} discovery for media {media_id}, campaign {campaign_id}")
            return is_new
        except Exception as e:
            # Table might not exist yet - this is expected during transition
            logger.debug(f"Could not track campaign media discovery (table may not exist): {e}")
            return False

async def get_enriched_media_for_campaigns() -> List[Dict[str, Any]]:
    """
    Get media that have been discovered for campaigns and are ready for match creation.
    Returns media that are enriched and have episodes analyzed.
    """
    query = """
    SELECT DISTINCT cmd.campaign_id, cmd.media_id, cmd.discovery_keyword, m.name as media_name
    FROM campaign_media_discoveries cmd
    JOIN media m ON cmd.media_id = m.media_id
    LEFT JOIN match_suggestions ms ON cmd.campaign_id = ms.campaign_id AND cmd.media_id = ms.media_id
    WHERE ms.match_id IS NULL  -- No match suggestion created yet
    AND m.last_enriched_timestamp IS NOT NULL  -- Has been enriched
    AND m.quality_score IS NOT NULL  -- Quality score calculated
    AND EXISTS (
        SELECT 1 FROM episodes e 
        WHERE e.media_id = m.media_id 
        AND e.ai_analysis_done = TRUE
        LIMIT 3  -- At least 3 episodes analyzed
    )
    ORDER BY cmd.discovered_at ASC
    LIMIT 100;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
        except Exception as e:
            # Table might not exist yet - this is expected during transition
            logger.debug(f"Could not fetch enriched media for campaigns (table may not exist): {e}")
            return []

async def update_media_ai_description(media_id: int, ai_description: str) -> bool:
    """Updates the AI-generated description for a media item."""
    query = """
    UPDATE media
    SET ai_description = $1, updated_at = NOW()
    WHERE media_id = $2
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, ai_description, media_id)
            logger.info(f"Updated AI description for media {media_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating AI description for media {media_id}: {e}")
            return False

async def update_media_embedding(media_id: int, embedding: list) -> bool:
    """Updates the embedding vector for a media item."""
    query = """
    UPDATE media
    SET embedding = $1, updated_at = NOW()
    WHERE media_id = $2
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Convert embedding to proper vector format
            if isinstance(embedding, list):
                embedding_str = '[' + ','.join(map(str, embedding)) + ']'
            else:
                embedding_str = str(embedding)
            
            await conn.execute(query, embedding_str, media_id)
            logger.info(f"Updated embedding for media {media_id}")
            return True
        except Exception as e:
            logger.error(f"Error updating embedding for media {media_id}: {e}")
            return False