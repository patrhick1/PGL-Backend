#!/usr/bin/env python3
"""
Fix existing vetting data by migrating it from vetting_criteria_met JSONB to the new columns.
This is for records that were vetted but the data wasn't stored in the new columns.
"""

import asyncio
import logging
import json

from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate_vetting_data():
    """Migrate vetting data from JSONB to new columns."""
    pool = await get_db_pool()
    
    # Find records with vetting data in JSONB but not in new columns
    query = """
    SELECT 
        id,
        vetting_criteria_met,
        topic_match_analysis,
        vetting_criteria_scores,
        client_expertise_matched
    FROM campaign_media_discoveries
    WHERE campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    AND vetting_status = 'completed'
    AND vetting_criteria_met IS NOT NULL
    AND (
        topic_match_analysis IS NULL 
        OR vetting_criteria_scores IS NULL
    )
    """
    
    async with pool.acquire() as conn:
        records = await conn.fetch(query)
    
    logger.info(f"Found {len(records)} records to migrate")
    
    migrated = 0
    for record in records:
        vcm = record['vetting_criteria_met']
        
        # Handle case where vcm might be stored as a string
        if isinstance(vcm, str):
            try:
                vcm = json.loads(vcm)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse vetting_criteria_met for record {record['id']}")
                continue
        
        # Skip if not a dict
        if not isinstance(vcm, dict):
            logger.warning(f"Skipping record {record['id']} - vetting_criteria_met is not a dict")
            continue
        
        # Extract data from JSONB
        topic_analysis = vcm.get('topic_match_analysis', '')
        criteria_scores = vcm.get('vetting_criteria_scores', [])
        expertise_matched = vcm.get('client_expertise_matched', [])
        
        # Skip if no data to migrate
        if not topic_analysis and not criteria_scores:
            continue
        
        # Update the record
        update_query = """
        UPDATE campaign_media_discoveries
        SET topic_match_analysis = COALESCE(topic_match_analysis, $1),
            vetting_criteria_scores = COALESCE(vetting_criteria_scores, $2::jsonb),
            client_expertise_matched = COALESCE(client_expertise_matched, $3)
        WHERE id = $4
        """
        
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    update_query,
                    topic_analysis if topic_analysis else None,
                    json.dumps(criteria_scores) if criteria_scores else None,
                    expertise_matched if expertise_matched else None,
                    record['id']
                )
            
            logger.info(f"✅ Migrated record {record['id']}")
            migrated += 1
            
        except Exception as e:
            logger.error(f"Error migrating record {record['id']}: {e}")
    
    logger.info(f"\n✅ Migrated {migrated} records")

async def verify_migration():
    """Verify the migration results."""
    pool = await get_db_pool()
    
    query = """
    SELECT 
        COUNT(*) as total,
        COUNT(topic_match_analysis) as has_topic,
        COUNT(vetting_criteria_scores) as has_scores,
        COUNT(client_expertise_matched) as has_expertise
    FROM campaign_media_discoveries
    WHERE campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    AND vetting_status = 'completed'
    """
    
    async with pool.acquire() as conn:
        result = await conn.fetchrow(query)
    
    logger.info("\n=== Migration Results ===")
    logger.info(f"Total vetted records: {result['total']}")
    logger.info(f"With topic_match_analysis: {result['has_topic']}")
    logger.info(f"With vetting_criteria_scores: {result['has_scores']}")
    logger.info(f"With client_expertise_matched: {result['has_expertise']}")

async def main():
    """Main function."""
    logger.info("=== Vetting Data Migration ===\n")
    
    await migrate_vetting_data()
    await verify_migration()
    
    logger.info("\n=== Migration Complete ===")

if __name__ == "__main__":
    asyncio.run(main())