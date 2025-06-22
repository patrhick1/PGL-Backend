#!/usr/bin/env python3
"""
Script to update existing match suggestions with vetting data from campaign_media_discoveries.
"""

import asyncio
import logging
from podcast_outreach.database.connection import get_db_pool

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def update_match_vetting_data():
    """Update match suggestions with vetting data from campaign_media_discoveries."""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Get all match suggestions with their corresponding discovery data
            query = """
            SELECT 
                ms.match_id,
                ms.campaign_id,
                ms.media_id,
                ms.vetting_score as ms_vetting_score,
                ms.vetting_reasoning as ms_vetting_reasoning,
                ms.vetting_checklist as ms_vetting_checklist,
                cmd.vetting_score as cmd_vetting_score,
                cmd.vetting_reasoning as cmd_vetting_reasoning,
                cmd.vetting_criteria_met as cmd_vetting_criteria_met,
                cmd.vetted_at
            FROM match_suggestions ms
            LEFT JOIN campaign_media_discoveries cmd 
                ON ms.campaign_id = cmd.campaign_id 
                AND ms.media_id = cmd.media_id
            ORDER BY ms.match_id;
            """
            
            matches = await conn.fetch(query)
            logger.info(f"Found {len(matches)} match suggestions to check")
            
            updated_count = 0
            
            for match in matches:
                match_id = match['match_id']
                
                # Check if we need to update (vetting data is null in match_suggestions but exists in discoveries)
                if (match['ms_vetting_score'] is None and 
                    match['cmd_vetting_score'] is not None):
                    
                    # Update the match suggestion with vetting data
                    update_query = """
                    UPDATE match_suggestions
                    SET 
                        vetting_score = $1,
                        vetting_reasoning = $2,
                        vetting_checklist = $3,
                        last_vetted_at = $4
                    WHERE match_id = $5
                    RETURNING match_id;
                    """
                    
                    result = await conn.fetchrow(
                        update_query, 
                        match['cmd_vetting_score'],
                        match['cmd_vetting_reasoning'],
                        match['cmd_vetting_criteria_met'],  # This is vetting_criteria_met in discoveries table
                        match['vetted_at'],
                        match_id
                    )
                    
                    if result:
                        logger.info(
                            f"✓ Updated match {match_id} with vetting score {match['cmd_vetting_score']}"
                        )
                        updated_count += 1
                    else:
                        logger.error(f"Failed to update match {match_id}")
                else:
                    if match['ms_vetting_score'] is not None:
                        logger.info(f"Match {match_id} already has vetting data (score: {match['ms_vetting_score']})")
                    else:
                        logger.warning(f"Match {match_id} has no vetting data in campaign_media_discoveries")
            
            logger.info(f"\nCompleted! Updated {updated_count} match suggestions with vetting data")
            
    except Exception as e:
        logger.error(f"Error updating match suggestions: {e}")
        raise


async def main():
    """Main function."""
    logger.info("Starting match suggestions vetting data fix...")
    
    try:
        await update_match_vetting_data()
        logger.info("Update completed successfully!")
    except Exception as e:
        logger.error(f"Script failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())