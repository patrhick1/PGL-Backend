#!/usr/bin/env python3
"""Inspect what's actually stored in vetting_criteria_met."""

import asyncio
import logging
import json

from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def inspect_vetting_data():
    """Inspect vetting data structure."""
    pool = await get_db_pool()
    
    query = """
    SELECT 
        id,
        vetting_score,
        vetting_criteria_met,
        pg_typeof(vetting_criteria_met) as data_type
    FROM campaign_media_discoveries
    WHERE campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    AND vetting_status = 'completed'
    LIMIT 3
    """
    
    async with pool.acquire() as conn:
        records = await conn.fetch(query)
    
    logger.info(f"Inspecting {len(records)} vetted records...\n")
    
    for record in records:
        logger.info(f"=== Record ID: {record['id']} ===")
        logger.info(f"Score: {record['vetting_score']}")
        logger.info(f"Data type: {record['data_type']}")
        
        vcm = record['vetting_criteria_met']
        logger.info(f"Python type: {type(vcm)}")
        
        if vcm is None:
            logger.info("vetting_criteria_met is NULL")
        elif isinstance(vcm, str):
            logger.info(f"String length: {len(vcm)}")
            logger.info(f"First 100 chars: {vcm[:100]}...")
            # Try to parse it
            try:
                parsed = json.loads(vcm)
                logger.info("✅ Valid JSON string")
                logger.info(f"Keys: {list(parsed.keys()) if isinstance(parsed, dict) else 'Not a dict'}")
            except:
                logger.info("❌ Not valid JSON")
        elif isinstance(vcm, dict):
            logger.info("✅ Already a dict")
            logger.info(f"Keys: {list(vcm.keys())}")
            
            # Check what's inside
            for key in vcm:
                value = vcm[key]
                if isinstance(value, str):
                    logger.info(f"  {key}: string ({len(value)} chars)")
                elif isinstance(value, list):
                    logger.info(f"  {key}: list ({len(value)} items)")
                elif isinstance(value, dict):
                    logger.info(f"  {key}: dict ({len(value)} keys)")
                else:
                    logger.info(f"  {key}: {type(value).__name__}")
        else:
            logger.info(f"Unexpected type: {type(vcm)}")
        
        logger.info("")

async def check_old_vs_new_storage():
    """Check how data was stored in old vs new vetting runs."""
    pool = await get_db_pool()
    
    # Check records by vetted_at date
    query = """
    SELECT 
        COUNT(*) as count,
        DATE(vetted_at) as vetted_date,
        COUNT(topic_match_analysis) as has_topic,
        COUNT(vetting_criteria_scores) as has_scores,
        COUNT(CASE WHEN vetting_criteria_met IS NOT NULL THEN 1 END) as has_jsonb
    FROM campaign_media_discoveries
    WHERE campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    AND vetting_status = 'completed'
    GROUP BY DATE(vetted_at)
    ORDER BY vetted_date DESC
    """
    
    async with pool.acquire() as conn:
        results = await conn.fetch(query)
    
    logger.info("\n=== Storage Pattern by Date ===")
    logger.info(f"{'Date':<12} {'Count':<8} {'Topic':<8} {'Scores':<8} {'JSONB':<8}")
    logger.info("-" * 44)
    
    for row in results:
        date_str = row['vetted_date'].strftime('%Y-%m-%d') if row['vetted_date'] else 'Unknown'
        logger.info(f"{date_str:<12} {row['count']:<8} {row['has_topic']:<8} {row['has_scores']:<8} {row['has_jsonb']:<8}")

async def main():
    """Main function."""
    logger.info("=== Vetting Data Inspection ===\n")
    
    await inspect_vetting_data()
    await check_old_vs_new_storage()
    
    logger.info("\n=== Inspection Complete ===")

if __name__ == "__main__":
    asyncio.run(main())