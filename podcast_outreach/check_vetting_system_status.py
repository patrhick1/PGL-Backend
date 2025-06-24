#!/usr/bin/env python3
"""Check the current status of the vetting system and data."""

import asyncio
import logging
import json
from datetime import datetime, timezone, timedelta

from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_database_schema():
    """Check if the enhanced vetting columns exist."""
    pool = await get_db_pool()
    
    logger.info("=== Database Schema Check ===\n")
    
    query = """
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = 'public'
    AND table_name = 'campaign_media_discoveries'
    AND column_name IN (
        'vetting_score',
        'vetting_reasoning', 
        'vetting_criteria_met',
        'topic_match_analysis',
        'vetting_criteria_scores',
        'client_expertise_matched'
    )
    ORDER BY ordinal_position
    """
    
    async with pool.acquire() as conn:
        columns = await conn.fetch(query)
    
    logger.info("Vetting-related columns:")
    for col in columns:
        logger.info(f"  ✅ {col['column_name']:<30} {col['data_type']}")
    
    # Check which columns are missing
    expected_columns = {
        'vetting_score', 'vetting_reasoning', 'vetting_criteria_met',
        'topic_match_analysis', 'vetting_criteria_scores', 'client_expertise_matched'
    }
    found_columns = {col['column_name'] for col in columns}
    missing_columns = expected_columns - found_columns
    
    if missing_columns:
        logger.warning(f"\nMissing columns: {', '.join(missing_columns)}")
    else:
        logger.info("\n✅ All enhanced vetting columns are present!")

async def check_vetting_statistics():
    """Check vetting statistics for Mary Uwa's campaign."""
    pool = await get_db_pool()
    
    logger.info("\n=== Vetting Statistics ===\n")
    
    mary_campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    
    # Overall statistics
    query = """
    SELECT 
        COUNT(*) as total_discoveries,
        COUNT(CASE WHEN enrichment_status = 'completed' THEN 1 END) as enriched,
        COUNT(CASE WHEN vetting_status = 'completed' THEN 1 END) as vetted,
        COUNT(CASE WHEN vetting_status = 'in_progress' THEN 1 END) as vetting_in_progress,
        COUNT(CASE WHEN vetting_status = 'failed' THEN 1 END) as vetting_failed,
        COUNT(CASE WHEN vetting_score >= 5.0 THEN 1 END) as high_score,
        AVG(vetting_score) FILTER (WHERE vetting_score IS NOT NULL) as avg_score
    FROM campaign_media_discoveries
    WHERE campaign_id = $1
    """
    
    async with pool.acquire() as conn:
        stats = await conn.fetchrow(query, mary_campaign_id)
    
    logger.info(f"Campaign: Mary Uwa's Media Kit Preview")
    logger.info(f"Total discoveries: {stats['total_discoveries']}")
    logger.info(f"Enriched: {stats['enriched']}")
    logger.info(f"Vetted: {stats['vetted']}")
    logger.info(f"Vetting in progress: {stats['vetting_in_progress']}")
    logger.info(f"Vetting failed: {stats['vetting_failed']}")
    logger.info(f"High score (≥5.0): {stats['high_score']}")
    logger.info(f"Average vetting score: {stats['avg_score']:.2f}" if stats['avg_score'] else "Average vetting score: N/A")

async def check_recent_vetting_data():
    """Check recent vetting data to see what's being stored."""
    pool = await get_db_pool()
    
    logger.info("\n=== Recent Vetting Data ===\n")
    
    query = """
    SELECT 
        id,
        media_id,
        vetting_score,
        vetting_status,
        vetted_at,
        -- Check if new columns have data
        CASE WHEN topic_match_analysis IS NOT NULL THEN 'YES' ELSE 'NO' END as has_topic_analysis,
        CASE WHEN vetting_criteria_scores IS NOT NULL THEN 'YES' ELSE 'NO' END as has_criteria_scores,
        CASE WHEN client_expertise_matched IS NOT NULL THEN 'YES' ELSE 'NO' END as has_expertise_matched,
        -- Check if data is in vetting_criteria_met
        CASE WHEN vetting_criteria_met ? 'topic_match_analysis' THEN 'YES' ELSE 'NO' END as topic_in_jsonb,
        CASE WHEN vetting_criteria_met ? 'vetting_criteria_scores' THEN 'YES' ELSE 'NO' END as scores_in_jsonb,
        CASE WHEN vetting_criteria_met ? 'client_expertise_matched' THEN 'YES' ELSE 'NO' END as expertise_in_jsonb
    FROM campaign_media_discoveries
    WHERE campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    AND vetting_status = 'completed'
    ORDER BY vetted_at DESC
    LIMIT 5
    """
    
    async with pool.acquire() as conn:
        results = await conn.fetch(query)
    
    if not results:
        logger.info("No completed vetting records found")
        return
    
    logger.info(f"Latest {len(results)} vetted records:")
    logger.info(f"\n{'ID':<10} {'Score':<8} {'New Cols':<25} {'In JSONB':<25} {'Vetted At'}")
    logger.info("-" * 90)
    
    for result in results:
        new_cols = f"{result['has_topic_analysis']}/{result['has_criteria_scores']}/{result['has_expertise_matched']}"
        in_jsonb = f"{result['topic_in_jsonb']}/{result['scores_in_jsonb']}/{result['expertise_in_jsonb']}"
        vetted_at = result['vetted_at'].strftime('%Y-%m-%d %H:%M') if result['vetted_at'] else 'N/A'
        
        logger.info(f"{result['id']:<10} {result['vetting_score']:<8.1f} {new_cols:<25} {in_jsonb:<25} {vetted_at}")

async def check_pending_vetting_work():
    """Check how much work is pending for vetting."""
    pool = await get_db_pool()
    
    logger.info("\n=== Pending Vetting Work ===\n")
    
    query = """
    SELECT 
        COUNT(*) as ready_for_vetting
    FROM campaign_media_discoveries cmd
    JOIN media m ON cmd.media_id = m.media_id
    JOIN campaigns c ON cmd.campaign_id = c.campaign_id
    WHERE cmd.enrichment_status = 'completed'
    AND cmd.vetting_status = 'pending'
    AND m.ai_description IS NOT NULL
    AND c.ideal_podcast_description IS NOT NULL
    AND cmd.campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    """
    
    async with pool.acquire() as conn:
        result = await conn.fetchrow(query)
    
    logger.info(f"Discoveries ready for vetting: {result['ready_for_vetting']}")
    
    if result['ready_for_vetting'] > 0:
        logger.info("\nTo run vetting, you can:")
        logger.info("1. Wait for the scheduler to pick them up")
        logger.info("2. Manually trigger vetting with a script")

async def main():
    """Run all checks."""
    logger.info("=== Vetting System Status Check ===\n")
    
    await check_database_schema()
    await check_vetting_statistics()
    await check_recent_vetting_data()
    await check_pending_vetting_work()
    
    logger.info("\n=== Status Check Complete ===")

if __name__ == "__main__":
    asyncio.run(main())