# podcast_outreach/database/queries/campaign_media_discoveries.py

import logging
import json
import uuid
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone

from podcast_outreach.database.connection import get_db_pool, get_background_task_pool

logger = logging.getLogger(__name__)

async def create_or_get_discovery(
    campaign_id: uuid.UUID, 
    media_id: int, 
    discovery_keyword: str
) -> Optional[Dict[str, Any]]:
    """Create a new campaign-media discovery record or return existing one."""
    query = """
    INSERT INTO campaign_media_discoveries (campaign_id, media_id, discovery_keyword)
    VALUES ($1, $2, $3)
    ON CONFLICT (campaign_id, media_id) 
    DO UPDATE SET 
        updated_at = NOW(),
        discovery_keyword = EXCLUDED.discovery_keyword
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id, media_id, discovery_keyword)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error creating/getting discovery for campaign {campaign_id}, media {media_id}: {e}")
            return None

async def get_discoveries_needing_enrichment(limit: int = 50) -> List[Dict[str, Any]]:
    """Get discoveries that need enrichment (media not fully enriched)."""
    query = """
    SELECT cmd.*, m.name as media_name, m.last_enriched_timestamp, m.quality_score
    FROM campaign_media_discoveries cmd
    JOIN media m ON cmd.media_id = m.media_id
    WHERE cmd.enrichment_status = 'pending'
    AND (m.last_enriched_timestamp IS NULL OR m.quality_score IS NULL)
    ORDER BY cmd.discovered_at ASC
    LIMIT $1;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching discoveries needing enrichment: {e}")
            return []

async def update_enrichment_status(
    discovery_id: int, 
    status: str, 
    error: str = None
) -> bool:
    """Update enrichment status for a discovery."""
    query = """
    UPDATE campaign_media_discoveries
    SET enrichment_status = $1,
        enrichment_completed_at = CASE WHEN $1 = 'completed' THEN NOW() ELSE enrichment_completed_at END,
        enrichment_error = $2,
        updated_at = NOW()
    WHERE id = $3
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, status, error, discovery_id)
            logger.info(f"Updated enrichment status for discovery {discovery_id} to {status}")
            return True
        except Exception as e:
            logger.error(f"Error updating enrichment status for discovery {discovery_id}: {e}")
            return False

async def update_vetting_status(
    discovery_id: int, 
    status: str, 
    error: str = None
) -> bool:
    """Update vetting status for a discovery."""
    query = """
    UPDATE campaign_media_discoveries
    SET vetting_status = $1,
        vetting_error = $2,
        updated_at = NOW()
    WHERE id = $3
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, status, error, discovery_id)
            logger.info(f"Updated vetting status for discovery {discovery_id} to {status}")
            return True
        except Exception as e:
            logger.error(f"Error updating vetting status for discovery {discovery_id}: {e}")
            return False

async def get_discoveries_ready_for_vetting(limit: int = 50) -> List[Dict[str, Any]]:
    """Get discoveries ready for vetting (enrichment completed, vetting pending, has confident host names)."""
    query = """
    SELECT cmd.*, m.name as media_name, m.ai_description, c.ideal_podcast_description,
           m.host_names, m.host_names_confidence
    FROM campaign_media_discoveries cmd
    JOIN media m ON cmd.media_id = m.media_id
    JOIN campaigns c ON cmd.campaign_id = c.campaign_id
    WHERE cmd.enrichment_status = 'completed'
    AND cmd.vetting_status = 'pending'
    AND m.ai_description IS NOT NULL
    AND c.ideal_podcast_description IS NOT NULL
    -- Ensure podcast has host names with sufficient confidence
    AND m.host_names IS NOT NULL
    AND array_length(m.host_names, 1) > 0
    AND m.host_names_confidence >= 0.8
    -- Only include podcasts that have at least one episode
    AND EXISTS (
        SELECT 1 FROM episodes e 
        WHERE e.media_id = m.media_id
        LIMIT 1
    )
    ORDER BY cmd.enrichment_completed_at ASC
    LIMIT $1;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching discoveries ready for vetting: {e}")
            return []

async def acquire_vetting_work_batch(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Atomically acquire a batch of discoveries ready for vetting.
    Uses row-level locking to prevent race conditions.
    Requires host names with confidence >= 0.8 for email personalization.
    """
    query = """
    WITH candidates AS (
        SELECT cmd.id
        FROM campaign_media_discoveries cmd
        JOIN media m ON cmd.media_id = m.media_id
        JOIN campaigns c ON cmd.campaign_id = c.campaign_id
        WHERE cmd.enrichment_status = 'completed'
        AND cmd.vetting_status = 'pending'
        AND m.ai_description IS NOT NULL
        AND c.ideal_podcast_description IS NOT NULL
        -- Ensure podcast has host names with sufficient confidence
        AND m.host_names IS NOT NULL
        AND array_length(m.host_names, 1) > 0
        AND m.host_names_confidence >= 0.8
        -- Check if not already being processed (using vetting_error field temporarily for lock)
        AND (cmd.vetting_error IS NULL OR cmd.vetting_error NOT LIKE 'PROCESSING:%')
        -- Only vet podcasts that have at least one episode
        AND EXISTS (
            SELECT 1 FROM episodes e 
            WHERE e.media_id = m.media_id
            LIMIT 1
        )
        ORDER BY cmd.enrichment_completed_at ASC
        LIMIT $1
        FOR UPDATE OF cmd SKIP LOCKED
    )
    UPDATE campaign_media_discoveries
    SET vetting_status = 'in_progress',
        vetting_error = $2,
        updated_at = NOW()
    FROM candidates
    WHERE campaign_media_discoveries.id = candidates.id
    RETURNING campaign_media_discoveries.*,
              (SELECT name FROM media WHERE media_id = campaign_media_discoveries.media_id) as media_name,
              (SELECT ai_description FROM media WHERE media_id = campaign_media_discoveries.media_id) as ai_description,
              (SELECT host_names FROM media WHERE media_id = campaign_media_discoveries.media_id) as host_names,
              (SELECT host_names_confidence FROM media WHERE media_id = campaign_media_discoveries.media_id) as host_names_confidence,
              (SELECT ideal_podcast_description FROM campaigns WHERE campaign_id = campaign_media_discoveries.campaign_id) as ideal_podcast_description,
              (SELECT questionnaire_responses FROM campaigns WHERE campaign_id = campaign_media_discoveries.campaign_id) as questionnaire_responses;
    """
    
    # Create a processing lock identifier
    import uuid
    from datetime import datetime
    lock_id = f"PROCESSING:VETTING:{uuid.uuid4().hex[:8]}:{datetime.now().isoformat()}"
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                rows = await conn.fetch(query, limit, lock_id)
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Error acquiring vetting work batch: {e}")
                return []

async def update_vetting_results(
    discovery_id: int,
    vetting_score: float,
    vetting_reasoning: str,
    vetting_criteria_met: dict,
    status: str = 'completed'
) -> bool:
    """Update vetting results for a discovery."""
    # Validate vetting_criteria_met is a dict, not a JSON string
    if isinstance(vetting_criteria_met, str):
        logger.warning(f"Received JSON string instead of dict for vetting_criteria_met in discovery {discovery_id}")
        try:
            vetting_criteria_met = json.loads(vetting_criteria_met)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse vetting_criteria_met JSON string for discovery {discovery_id}")
            vetting_criteria_met = {}
    
    # Convert dict to JSON string for asyncpg
    if isinstance(vetting_criteria_met, dict):
        vetting_criteria_json = json.dumps(vetting_criteria_met)
    else:
        vetting_criteria_json = vetting_criteria_met
    
    query = """
    UPDATE campaign_media_discoveries
    SET vetting_status = $1,
        vetting_score = $2,
        vetting_reasoning = $3,
        vetting_criteria_met = $4::jsonb,
        vetted_at = NOW(),
        updated_at = NOW()
    WHERE id = $5
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, status, vetting_score, vetting_reasoning, vetting_criteria_json, discovery_id)
            logger.info(f"Updated vetting results for discovery {discovery_id}: score {vetting_score}")
            return True
        except Exception as e:
            logger.error(f"Error updating vetting results for discovery {discovery_id}: {e}")
            return False

async def get_discoveries_ready_for_match_creation(
    min_vetting_score: int = 50, 
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get vetted discoveries ready for match suggestion creation."""
    query = """
    SELECT cmd.*, m.name as media_name
    FROM campaign_media_discoveries cmd
    JOIN media m ON cmd.media_id = m.media_id
    WHERE cmd.vetting_status = 'completed'
    AND cmd.vetting_score >= $1
    AND cmd.match_created = FALSE
    ORDER BY cmd.vetting_score DESC, cmd.vetted_at ASC
    LIMIT $2;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, min_vetting_score, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching discoveries ready for match creation: {e}")
            return []

async def update_media_episode_summaries_compiled(media_id: int) -> bool:
    """Compile all episode summaries for a media and update episode_summaries_compiled field."""
    query = """
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
    SET episode_summaries_compiled = es.compiled_summaries,
        updated_at = NOW()
    FROM episode_summaries es
    WHERE m.media_id = es.media_id
    RETURNING m.media_id;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.fetchrow(query, media_id)
            if result:
                logger.info(f"Updated episode_summaries_compiled for media {media_id}")
                return True
            else:
                logger.warning(f"No episodes found to compile for media {media_id}")
                return False
        except Exception as e:
            logger.error(f"Error updating episode_summaries_compiled for media {media_id}: {e}")
            return False

async def bulk_update_episode_summaries_compiled(media_ids: List[int]) -> int:
    """Bulk update episode_summaries_compiled for multiple media records."""
    query = """
    WITH episode_summaries AS (
        SELECT 
            media_id,
            string_agg(
                COALESCE(ai_episode_summary, episode_summary, ''), 
                E'\n\n---\n\n'
                ORDER BY publish_date DESC
            ) as compiled_summaries
        FROM episodes
        WHERE media_id = ANY($1)
        AND (ai_episode_summary IS NOT NULL OR episode_summary IS NOT NULL)
        GROUP BY media_id
    )
    UPDATE media m
    SET episode_summaries_compiled = es.compiled_summaries,
        updated_at = NOW()
    FROM episode_summaries es
    WHERE m.media_id = es.media_id;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, media_ids)
            count = int(result.split()[-1]) if result else 0
            logger.info(f"Updated episode_summaries_compiled for {count} media records")
            return count
        except Exception as e:
            logger.error(f"Error bulk updating episode_summaries_compiled: {e}")
            return 0

async def mark_match_created(
    discovery_id: int, 
    match_suggestion_id: int
) -> bool:
    """Mark that a match suggestion has been created for this discovery."""
    query = """
    UPDATE campaign_media_discoveries
    SET match_created = TRUE,
        match_suggestion_id = $1,
        match_created_at = NOW(),
        updated_at = NOW()
    WHERE id = $2
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, match_suggestion_id, discovery_id)
            logger.info(f"Marked match created for discovery {discovery_id}, match {match_suggestion_id}")
            return True
        except Exception as e:
            logger.error(f"Error marking match created for discovery {discovery_id}: {e}")
            return False

async def mark_review_task_created(
    discovery_id: int, 
    review_task_id: int
) -> bool:
    """Mark that a review task has been created for this discovery."""
    query = """
    UPDATE campaign_media_discoveries
    SET review_task_created = TRUE,
        review_task_id = $1,
        updated_at = NOW()
    WHERE id = $2
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, review_task_id, discovery_id)
            logger.info(f"Marked review task created for discovery {discovery_id}, task {review_task_id}")
            return True
        except Exception as e:
            logger.error(f"Error marking review task created for discovery {discovery_id}: {e}")
            return False

async def get_discovery_by_campaign_and_media(
    campaign_id: uuid.UUID, 
    media_id: int
) -> Optional[Dict[str, Any]]:
    """Get discovery record by campaign and media IDs."""
    query = """
    SELECT * FROM campaign_media_discoveries
    WHERE campaign_id = $1 AND media_id = $2
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id, media_id)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting discovery for campaign {campaign_id}, media {media_id}: {e}")
            return None

async def get_discoveries_for_campaign(
    campaign_id: uuid.UUID,
    status_filter: str = None,
    limit: int = 100,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """Get all discoveries for a campaign with optional status filtering."""
    base_query = """
    SELECT cmd.*, m.name as media_name, m.image_url, m.description
    FROM campaign_media_discoveries cmd
    JOIN media m ON cmd.media_id = m.media_id
    WHERE cmd.campaign_id = $1
    """
    
    params = [campaign_id]
    param_count = 1
    
    if status_filter:
        if status_filter == 'enrichment':
            base_query += f" AND cmd.enrichment_status != 'completed'"
        elif status_filter == 'vetting':
            base_query += f" AND cmd.enrichment_status = 'completed' AND cmd.vetting_status != 'completed'"
        elif status_filter == 'ready':
            base_query += f" AND cmd.vetting_status = 'completed' AND cmd.vetting_score >= 50"
        elif status_filter == 'approved':
            base_query += f" AND cmd.review_status = 'approved'"
    
    base_query += f" ORDER BY cmd.vetting_score DESC NULLS LAST, cmd.discovered_at DESC LIMIT ${param_count + 1} OFFSET ${param_count + 2}"
    params.extend([limit, offset])
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(base_query, *params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting discoveries for campaign {campaign_id}: {e}")
            return []

async def get_discoveries_needing_ai_description(limit: int = 20) -> List[Dict[str, Any]]:
    """Get discoveries where enrichment is complete but AI description is missing."""
    query = """
    SELECT cmd.*, m.name as media_name, m.description, m.total_episodes,
           c.ideal_podcast_description, c.questionnaire_responses
    FROM campaign_media_discoveries cmd
    JOIN media m ON cmd.media_id = m.media_id
    JOIN campaigns c ON cmd.campaign_id = c.campaign_id
    WHERE cmd.enrichment_status = 'completed'
    AND cmd.vetting_status = 'pending'
    AND (m.ai_description IS NULL OR m.ai_description = '')
    AND m.total_episodes > 0
    ORDER BY cmd.enrichment_completed_at ASC
    LIMIT $1;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error fetching discoveries needing AI description: {e}")
            return []

async def acquire_ai_description_work_batch(
    limit: int = 20,
    lock_duration_minutes: int = 45
) -> List[Dict[str, Any]]:
    """
    Atomically acquire a batch of discoveries needing AI descriptions.
    Uses row-level locking to prevent race conditions.
    """
    query = """
    WITH candidates AS (
        SELECT cmd.id, cmd.media_id, cmd.campaign_id
        FROM campaign_media_discoveries cmd
        JOIN media m ON cmd.media_id = m.media_id
        JOIN campaigns c ON cmd.campaign_id = c.campaign_id
        WHERE cmd.enrichment_status = 'completed'
        AND cmd.vetting_status = 'pending'
        AND (m.ai_description IS NULL OR m.ai_description = '')
        AND m.total_episodes > 0
        -- Check if not already being processed (using enrichment_error field temporarily for lock)
        AND (cmd.enrichment_error IS NULL OR cmd.enrichment_error NOT LIKE 'PROCESSING:%')
        ORDER BY cmd.enrichment_completed_at ASC
        LIMIT $1
        FOR UPDATE OF cmd SKIP LOCKED
    )
    UPDATE campaign_media_discoveries
    SET enrichment_error = $2,
        updated_at = NOW()
    FROM candidates
    WHERE campaign_media_discoveries.id = candidates.id
    RETURNING campaign_media_discoveries.*, 
              (SELECT name FROM media WHERE media_id = candidates.media_id) as media_name,
              (SELECT description FROM media WHERE media_id = candidates.media_id) as description,
              (SELECT total_episodes FROM media WHERE media_id = candidates.media_id) as total_episodes,
              (SELECT ideal_podcast_description FROM campaigns WHERE campaign_id = candidates.campaign_id) as ideal_podcast_description,
              (SELECT questionnaire_responses FROM campaigns WHERE campaign_id = candidates.campaign_id) as questionnaire_responses;
    """
    
    # Create a processing lock identifier
    import uuid
    from datetime import datetime
    lock_id = f"PROCESSING:AI_DESC:{uuid.uuid4().hex[:8]}:{datetime.now().isoformat()}"
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                rows = await conn.fetch(query, limit, lock_id)
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"Error acquiring AI description work batch: {e}")
                return []

async def release_ai_description_lock(discovery_id: int, success: bool = True) -> bool:
    """Release the processing lock on a discovery after AI description generation."""
    query = """
    UPDATE campaign_media_discoveries
    SET enrichment_error = CASE 
            WHEN $2 = TRUE THEN NULL
            ELSE CONCAT('Failed at ', NOW()::text)
        END,
        updated_at = NOW()
    WHERE id = $1
    AND enrichment_error LIKE 'PROCESSING:%'
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(query, discovery_id, success)
            return True
        except Exception as e:
            logger.error(f"Error releasing AI description lock for discovery {discovery_id}: {e}")
            return False

async def cleanup_stale_ai_description_locks(stale_minutes: int = 60) -> int:
    """
    Clean up stale processing locks that are older than specified minutes.
    
    IMPORTANT: This function uses get_background_task_pool() instead of get_db_pool()
    because it's called from scheduled background tasks. Using the frontend pool
    can cause "Control plane request failed" errors and timeouts since the frontend
    pool has shorter timeouts (60s vs 30min) and is optimized for web requests.
    
    See: Database connection issues fix - 2025-06-20
    """
    query = """
    UPDATE campaign_media_discoveries
    SET enrichment_error = NULL,
        updated_at = NOW()
    WHERE enrichment_error LIKE 'PROCESSING:AI_DESC:%'
    AND (
        -- Extract timestamp from the lock string and check if it's stale
        SUBSTRING(enrichment_error FROM 'PROCESSING:AI_DESC:[^:]+:(.+)$')::timestamp 
        < NOW() - ($1 || ' minutes')::interval
        OR
        -- Fallback: if we can't parse timestamp, clear locks older than 60 minutes based on updated_at
        updated_at < NOW() - ($1 || ' minutes')::interval
    )
    RETURNING id;
    """
    # Use background task pool for scheduled operations to prevent timeout errors
    pool = await get_background_task_pool()
    async with pool.acquire() as conn:
        try:
            # Convert int to str for PostgreSQL interval construction
            # Fixed: "invalid input for query argument $1: 60 (expected str, got int)"
            rows = await conn.fetch(query, str(stale_minutes))
            count = len(rows)
            if count > 0:
                logger.info(f"Cleaned up {count} stale AI description locks")
            return count
        except Exception as e:
            logger.error(f"Error cleaning up stale AI description locks: {e}")
            return 0

async def cleanup_stale_vetting_locks(stale_minutes: int = 60) -> int:
    """
    Clean up stale vetting processing locks that are older than specified minutes.
    
    IMPORTANT: This function uses get_background_task_pool() instead of get_db_pool()
    because it's called from scheduled background tasks. Using the frontend pool
    can cause "Control plane request failed" errors and timeouts since the frontend
    pool has shorter timeouts (60s vs 30min) and is optimized for web requests.
    
    See: Database connection issues fix - 2025-06-20
    """
    query = """
    UPDATE campaign_media_discoveries
    SET vetting_error = NULL,
        vetting_status = CASE 
            WHEN vetting_status = 'in_progress' THEN 'pending'
            ELSE vetting_status
        END,
        updated_at = NOW()
    WHERE vetting_error LIKE 'PROCESSING:VETTING:%'
    AND updated_at < NOW() - ($1 || ' minutes')::interval
    RETURNING id;
    """
    # Use background task pool for scheduled operations to prevent timeout errors
    pool = await get_background_task_pool()
    async with pool.acquire() as conn:
        try:
            # Convert int to str for PostgreSQL interval construction
            # Fixed: "invalid input for query argument $1: 60 (expected str, got int)"
            rows = await conn.fetch(query, str(stale_minutes))
            count = len(rows)
            if count > 0:
                logger.info(f"Cleaned up {count} stale vetting locks")
            return count
        except Exception as e:
            logger.error(f"Error cleaning up stale vetting locks: {e}")
            return 0

async def update_vetting_results_enhanced(
    discovery_id: int,
    vetting_score: float,
    vetting_reasoning: str,
    vetting_criteria_met: dict,
    topic_match_analysis: str,
    vetting_criteria_scores: List[Dict[str, Any]],
    client_expertise_matched: List[str],
    status: str = 'completed'
) -> bool:
    """Update enhanced vetting results for a discovery with all vetting data."""
    # Validate vetting_criteria_met is a dict, not a JSON string
    if isinstance(vetting_criteria_met, str):
        logger.warning(f"Received JSON string instead of dict for vetting_criteria_met in discovery {discovery_id}")
        try:
            vetting_criteria_met = json.loads(vetting_criteria_met)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse vetting_criteria_met JSON string for discovery {discovery_id}")
            vetting_criteria_met = {}
    
    # Convert dicts to JSON strings for asyncpg
    if isinstance(vetting_criteria_met, dict):
        vetting_criteria_json = json.dumps(vetting_criteria_met)
    else:
        vetting_criteria_json = vetting_criteria_met
        
    if isinstance(vetting_criteria_scores, list):
        vetting_scores_json = json.dumps(vetting_criteria_scores)
    else:
        vetting_scores_json = vetting_criteria_scores
    
    query = """
    UPDATE campaign_media_discoveries
    SET vetting_status = $1,
        vetting_score = $2,
        vetting_reasoning = $3,
        vetting_criteria_met = $4::jsonb,
        topic_match_analysis = $5,
        vetting_criteria_scores = $6::jsonb,
        client_expertise_matched = $7,
        vetting_error = NULL,
        vetted_at = NOW(),
        updated_at = NOW()
    WHERE id = $8
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                query, 
                status, 
                vetting_score, 
                vetting_reasoning, 
                vetting_criteria_json, 
                topic_match_analysis,
                vetting_scores_json,
                client_expertise_matched,
                discovery_id
            )
            logger.info(f"Updated enhanced vetting results for discovery {discovery_id}: score {vetting_score}")
            logger.debug(f"Enhanced data stored - topic_match: {len(topic_match_analysis) if topic_match_analysis else 0} chars, criteria_scores: {len(vetting_criteria_scores) if vetting_criteria_scores else 0} items, expertise: {len(client_expertise_matched) if client_expertise_matched else 0} items")
            return True
        except Exception as e:
            logger.error(f"Error updating enhanced vetting results for discovery {discovery_id}: {e}", exc_info=True)
            raise  # Re-raise to trigger fallback in orchestrator