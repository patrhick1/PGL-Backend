#!/usr/bin/env python3
"""
Fix vetting_checklist data that was incorrectly stored as JSON strings.
This script will convert JSON strings back to proper JSONB objects.
"""

import asyncio
import json
import logging
from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_vetting_checklist_data():
    """Fix vetting_checklist fields that are stored as JSON strings instead of JSONB."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        # First, check how many records have string data
        check_query = """
        SELECT COUNT(*) as count
        FROM match_suggestions
        WHERE vetting_checklist IS NOT NULL
        AND jsonb_typeof(vetting_checklist::jsonb) = 'string'
        """
        
        try:
            count_result = await conn.fetchone(check_query)
            affected_count = count_result['count'] if count_result else 0
            logger.info(f"Found {affected_count} records with string vetting_checklist data")
        except Exception as e:
            logger.warning(f"Could not check for string data: {e}")
            affected_count = None
        
        # Fix campaign_media_discoveries table
        fix_campaign_query = """
        UPDATE campaign_media_discoveries
        SET vetting_criteria_met = vetting_criteria_met::jsonb
        WHERE vetting_criteria_met IS NOT NULL
        AND jsonb_typeof(vetting_criteria_met::jsonb) = 'string'
        RETURNING id
        """
        
        # Fix match_suggestions table
        fix_matches_query = """
        UPDATE match_suggestions
        SET vetting_checklist = vetting_checklist::jsonb
        WHERE vetting_checklist IS NOT NULL
        AND jsonb_typeof(vetting_checklist::jsonb) = 'string'
        RETURNING match_id
        """
        
        try:
            # Fix campaign_media_discoveries
            campaign_rows = await conn.fetch(fix_campaign_query)
            logger.info(f"Fixed {len(campaign_rows)} campaign_media_discoveries records")
            
            # Fix match_suggestions
            match_rows = await conn.fetch(fix_matches_query)
            logger.info(f"Fixed {len(match_rows)} match_suggestions records")
            
            return True
            
        except Exception as e:
            logger.error(f"Error fixing vetting data: {e}")
            return False

async def main():
    try:
        success = await fix_vetting_checklist_data()
        if success:
            logger.info("Successfully fixed vetting checklist data")
        else:
            logger.error("Failed to fix vetting checklist data")
    except Exception as e:
        logger.error(f"Script failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())