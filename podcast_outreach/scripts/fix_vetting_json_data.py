#!/usr/bin/env python3
"""
Fix vetting_checklist and vetting_criteria_met fields that were incorrectly stored as JSON strings.
Run this script to convert JSON strings back to proper JSONB objects.
"""

import asyncio
import json
import logging
from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_json_string_data():
    """Fix fields that are stored as JSON strings instead of JSONB."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        try:
            # Fix campaign_media_discoveries table
            logger.info("Fixing vetting_criteria_met in campaign_media_discoveries...")
            campaign_query = """
            UPDATE campaign_media_discoveries
            SET vetting_criteria_met = vetting_criteria_met::text::jsonb
            WHERE vetting_criteria_met IS NOT NULL
              AND jsonb_typeof(vetting_criteria_met) = 'string'
            RETURNING id
            """
            campaign_rows = await conn.fetch(campaign_query)
            logger.info(f"Fixed {len(campaign_rows)} campaign_media_discoveries records")
            
            # Fix match_suggestions table
            logger.info("Fixing vetting_checklist in match_suggestions...")
            match_query = """
            UPDATE match_suggestions
            SET vetting_checklist = vetting_checklist::text::jsonb
            WHERE vetting_checklist IS NOT NULL
              AND jsonb_typeof(vetting_checklist) = 'string'
            RETURNING match_id
            """
            match_rows = await conn.fetch(match_query)
            logger.info(f"Fixed {len(match_rows)} match_suggestions records")
            
            # Verify the fixes
            verify_query = """
            SELECT 'campaign_media_discoveries' as table_name,
                   COUNT(*) as total_records,
                   COUNT(CASE WHEN jsonb_typeof(vetting_criteria_met) = 'string' THEN 1 END) as string_records,
                   COUNT(CASE WHEN jsonb_typeof(vetting_criteria_met) = 'object' THEN 1 END) as object_records
            FROM campaign_media_discoveries
            WHERE vetting_criteria_met IS NOT NULL
            
            UNION ALL
            
            SELECT 'match_suggestions' as table_name,
                   COUNT(*) as total_records,
                   COUNT(CASE WHEN jsonb_typeof(vetting_checklist) = 'string' THEN 1 END) as string_records,
                   COUNT(CASE WHEN jsonb_typeof(vetting_checklist) = 'object' THEN 1 END) as object_records
            FROM match_suggestions
            WHERE vetting_checklist IS NOT NULL
            """
            
            results = await conn.fetch(verify_query)
            logger.info("\nVerification Results:")
            for row in results:
                logger.info(f"{row['table_name']}: "
                          f"Total={row['total_records']}, "
                          f"Strings={row['string_records']}, "
                          f"Objects={row['object_records']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error fixing JSON data: {e}")
            return False

if __name__ == "__main__":
    asyncio.run(fix_json_string_data())