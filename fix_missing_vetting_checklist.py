#!/usr/bin/env python3
"""
Fix match_suggestions that are missing vetting_checklist data.
This script copies vetting_criteria_met from campaign_media_discoveries to vetting_checklist in match_suggestions.
"""

import asyncio
import logging
from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_missing_vetting_checklist():
    """Copy vetting_criteria_met data to match_suggestions where it's missing."""
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        try:
            # First, check how many matches are missing vetting_checklist
            check_query = """
            SELECT COUNT(*) as count
            FROM match_suggestions ms
            JOIN campaign_media_discoveries cmd ON cmd.match_suggestion_id = ms.match_id
            WHERE ms.vetting_checklist IS NULL
              AND cmd.vetting_criteria_met IS NOT NULL
            """
            
            result = await conn.fetchrow(check_query)
            missing_count = result['count'] if result else 0
            logger.info(f"Found {missing_count} match_suggestions missing vetting_checklist data")
            
            if missing_count > 0:
                # Update missing vetting_checklist from campaign_media_discoveries
                update_query = """
                UPDATE match_suggestions ms
                SET vetting_checklist = cmd.vetting_criteria_met,
                    updated_at = NOW()
                FROM campaign_media_discoveries cmd
                WHERE cmd.match_suggestion_id = ms.match_id
                  AND ms.vetting_checklist IS NULL
                  AND cmd.vetting_criteria_met IS NOT NULL
                RETURNING ms.match_id
                """
                
                updated_rows = await conn.fetch(update_query)
                logger.info(f"Updated {len(updated_rows)} match_suggestions with vetting_checklist data")
            
            # Also check for matches that have vetting_score but no vetting_checklist
            orphaned_query = """
            SELECT ms.match_id, ms.campaign_id, ms.media_id, ms.vetting_score
            FROM match_suggestions ms
            WHERE ms.vetting_score IS NOT NULL
              AND ms.vetting_score > 0
              AND ms.vetting_checklist IS NULL
            """
            
            orphaned = await conn.fetch(orphaned_query)
            if orphaned:
                logger.warning(f"Found {len(orphaned)} matches with vetting_score but no vetting_checklist")
                for row in orphaned[:5]:  # Show first 5
                    logger.warning(f"  Match {row['match_id']}: score={row['vetting_score']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error fixing missing vetting_checklist: {e}")
            return False

if __name__ == "__main__":
    asyncio.run(fix_missing_vetting_checklist())