#!/usr/bin/env python3
"""
Health Checker Service - Automatically detects and fixes common workflow issues
"""

import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
from podcast_outreach.services.enrichment.quality_score import QualityService
from podcast_outreach.database.models.media_models import EnrichedPodcastProfile

logger = logging.getLogger(__name__)


class WorkflowHealthChecker:
    """
    Automatically detects and fixes common workflow issues:
    1. Stuck discoveries (enrichment marked complete but status still pending)
    2. Missing episode summaries compilation
    3. Stale processing locks
    4. Failed vetting that should be retried
    """
    
    def __init__(self):
        self.quality_service = QualityService()
        logger.info("WorkflowHealthChecker initialized")
    
    async def run_health_check(self) -> Dict[str, Any]:
        """Run all health checks and fixes."""
        results = {
            "checks_run": [],
            "issues_found": 0,
            "issues_fixed": 0,
            "details": []
        }
        
        # 1. Fix missing episode summaries
        summaries_result = await self._fix_missing_episode_summaries()
        results["checks_run"].append("missing_episode_summaries")
        results["issues_found"] += summaries_result["found"]
        results["issues_fixed"] += summaries_result["fixed"]
        results["details"].append(summaries_result)
        
        # 2. Fix stuck enrichment statuses
        enrichment_result = await self._fix_stuck_enrichment_statuses()
        results["checks_run"].append("stuck_enrichment_statuses")
        results["issues_found"] += enrichment_result["found"]
        results["issues_fixed"] += enrichment_result["fixed"]
        results["details"].append(enrichment_result)
        
        # 3. Clear stale locks
        locks_result = await self._clear_all_stale_locks()
        results["checks_run"].append("stale_locks")
        results["issues_found"] += locks_result["found"]
        results["issues_fixed"] += locks_result["fixed"]
        results["details"].append(locks_result)
        
        # 4. Reset failed vetting for retry
        vetting_result = await self._reset_failed_vetting()
        results["checks_run"].append("failed_vetting")
        results["issues_found"] += vetting_result["found"]
        results["issues_fixed"] += vetting_result["fixed"]
        results["details"].append(vetting_result)
        
        logger.info(f"Health check complete: {results['issues_found']} issues found, {results['issues_fixed']} fixed")
        return results
    
    async def _fix_missing_episode_summaries(self) -> Dict[str, Any]:
        """Find and fix media with transcribed episodes but no compiled summaries."""
        query = """
        WITH media_needing_compilation AS (
            SELECT DISTINCT m.media_id, m.name, m.quality_score,
                   COUNT(e.episode_id) as transcribed_count
            FROM media m
            JOIN episodes e ON m.media_id = e.media_id
            WHERE e.ai_episode_summary IS NOT NULL
            AND (m.episode_summaries_compiled IS NULL OR m.episode_summaries_compiled = '')
            GROUP BY m.media_id, m.name, m.quality_score
            HAVING COUNT(e.episode_id) > 0
        )
        SELECT * FROM media_needing_compilation
        ORDER BY transcribed_count DESC
        LIMIT 50;
        """
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            
        result = {
            "check": "missing_episode_summaries",
            "found": len(rows),
            "fixed": 0,
            "details": []
        }
        
        for row in rows:
            media_id = row['media_id']
            try:
                # If has quality score, use update_media_quality_score
                if row['quality_score'] is not None:
                    success = await media_queries.update_media_quality_score(
                        media_id, row['quality_score']
                    )
                else:
                    # Just compile summaries
                    success = await cmd_queries.update_media_episode_summaries_compiled(media_id)
                
                if success:
                    result["fixed"] += 1
                    result["details"].append({
                        "media_id": media_id,
                        "name": row['name'],
                        "status": "fixed"
                    })
                    logger.info(f"Fixed episode summaries for media {media_id}")
            except Exception as e:
                logger.error(f"Error fixing episode summaries for media {media_id}: {e}")
                result["details"].append({
                    "media_id": media_id,
                    "name": row['name'],
                    "status": "error",
                    "error": str(e)
                })
        
        return result
    
    async def _fix_stuck_enrichment_statuses(self) -> Dict[str, Any]:
        """Fix discoveries where core enrichment is done but status is wrong."""
        query = """
        SELECT cmd.id, cmd.media_id, cmd.enrichment_status, m.name
        FROM campaign_media_discoveries cmd
        JOIN media m ON cmd.media_id = m.media_id
        WHERE cmd.enrichment_status IN ('pending', 'in_progress')
        AND m.last_enriched_timestamp IS NOT NULL
        AND cmd.updated_at < NOW() - INTERVAL '5 minutes'
        LIMIT 50;
        """
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        result = {
            "check": "stuck_enrichment_statuses",
            "found": len(rows),
            "fixed": 0,
            "details": []
        }
        
        for row in rows:
            try:
                success = await cmd_queries.update_enrichment_status(
                    row['id'], 'completed'
                )
                if success:
                    result["fixed"] += 1
                    result["details"].append({
                        "discovery_id": row['id'],
                        "media_id": row['media_id'],
                        "status": "fixed"
                    })
                    logger.info(f"Fixed enrichment status for discovery {row['id']}")
            except Exception as e:
                logger.error(f"Error fixing enrichment status for discovery {row['id']}: {e}")
                result["details"].append({
                    "discovery_id": row['id'],
                    "status": "error",
                    "error": str(e)
                })
        
        return result
    
    async def _clear_all_stale_locks(self) -> Dict[str, Any]:
        """Clear all types of stale processing locks."""
        result = {
            "check": "stale_locks",
            "found": 0,
            "fixed": 0,
            "details": []
        }
        
        # Clear AI description locks (older than 60 minutes)
        ai_locks_cleared = await cmd_queries.cleanup_stale_ai_description_locks(60)
        result["found"] += ai_locks_cleared
        result["fixed"] += ai_locks_cleared
        if ai_locks_cleared > 0:
            result["details"].append(f"Cleared {ai_locks_cleared} AI description locks")
        
        # Clear vetting locks (older than 60 minutes)
        vetting_locks_cleared = await cmd_queries.cleanup_stale_vetting_locks(60)
        result["found"] += vetting_locks_cleared
        result["fixed"] += vetting_locks_cleared
        if vetting_locks_cleared > 0:
            result["details"].append(f"Cleared {vetting_locks_cleared} vetting locks")
        
        return result
    
    async def _reset_failed_vetting(self) -> Dict[str, Any]:
        """Reset failed vetting for retry if media is ready."""
        query = """
        SELECT cmd.id, cmd.media_id, cmd.vetting_reasoning, m.name
        FROM campaign_media_discoveries cmd
        JOIN media m ON cmd.media_id = m.media_id
        JOIN campaigns c ON cmd.campaign_id = c.campaign_id
        WHERE cmd.vetting_status = 'failed'
        AND cmd.enrichment_status = 'completed'
        AND m.ai_description IS NOT NULL
        AND c.ideal_podcast_description IS NOT NULL
        AND cmd.vetted_at < NOW() - INTERVAL '2 hours'
        AND (
            cmd.vetting_reasoning LIKE '%failed to produce results%'
            OR cmd.vetting_reasoning LIKE '%timeout%'
            OR cmd.vetting_reasoning LIKE '%error%'
        )
        LIMIT 20;
        """
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        result = {
            "check": "failed_vetting",
            "found": len(rows),
            "fixed": 0,
            "details": []
        }
        
        for row in rows:
            try:
                # Reset to pending for retry
                update_query = """
                UPDATE campaign_media_discoveries
                SET vetting_status = 'pending',
                    vetting_error = NULL,
                    vetting_score = NULL,
                    vetting_reasoning = NULL,
                    updated_at = NOW()
                WHERE id = $1
                """
                async with pool.acquire() as conn:
                    await conn.execute(update_query, row['id'])
                
                result["fixed"] += 1
                result["details"].append({
                    "discovery_id": row['id'],
                    "media_id": row['media_id'],
                    "status": "reset_for_retry"
                })
                logger.info(f"Reset failed vetting for discovery {row['id']}")
            except Exception as e:
                logger.error(f"Error resetting vetting for discovery {row['id']}: {e}")
                result["details"].append({
                    "discovery_id": row['id'],
                    "status": "error",
                    "error": str(e)
                })
        
        return result


async def run_workflow_health_check():
    """Run health check as a standalone function."""
    checker = WorkflowHealthChecker()
    return await checker.run_health_check()