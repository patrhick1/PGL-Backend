#!/usr/bin/env python3
"""
Sync ideal_podcast_description from questionnaire responses to the campaigns table.
This ensures the vetting pipeline has access to the description.
"""

import asyncio
import logging
import json

from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def sync_descriptions():
    """Sync ideal podcast descriptions from questionnaire to campaign field."""
    pool = await get_db_pool()
    
    # Find campaigns with questionnaire data but no ideal_podcast_description
    query = """
    SELECT 
        campaign_id,
        campaign_name,
        questionnaire_responses,
        ideal_podcast_description
    FROM campaigns
    WHERE questionnaire_responses IS NOT NULL
    ORDER BY campaign_name
    """
    
    async with pool.acquire() as conn:
        campaigns = await conn.fetch(query)
    
    logger.info(f"Checking {len(campaigns)} campaigns with questionnaire data...\n")
    
    synced = 0
    already_synced = 0
    no_description_in_questionnaire = 0
    
    for campaign in campaigns:
        campaign_id = campaign['campaign_id']
        campaign_name = campaign['campaign_name']
        current_description = campaign['ideal_podcast_description']
        
        # Parse questionnaire
        try:
            questionnaire = campaign['questionnaire_responses']
            if isinstance(questionnaire, str):
                questionnaire = json.loads(questionnaire)
            
            # Extract ideal podcast description from questionnaire
            ideal_from_questionnaire = None
            
            # Check different possible locations
            if isinstance(questionnaire, dict):
                # Location 1: finalNotes.idealPodcastDescription
                final_notes = questionnaire.get('finalNotes', {})
                if isinstance(final_notes, dict):
                    ideal_from_questionnaire = final_notes.get('idealPodcastDescription')
                
                # Location 2: Direct field (if structure is different)
                if not ideal_from_questionnaire:
                    ideal_from_questionnaire = questionnaire.get('idealPodcastDescription')
            
            if ideal_from_questionnaire:
                if current_description:
                    # Already has description - check if they match
                    if current_description.strip() != ideal_from_questionnaire.strip():
                        logger.warning(f"⚠️  {campaign_name}: Descriptions don't match!")
                        logger.info(f"   DB: {current_description[:50]}...")
                        logger.info(f"   Questionnaire: {ideal_from_questionnaire[:50]}...")
                    else:
                        already_synced += 1
                else:
                    # No description in DB - sync it
                    update_query = """
                    UPDATE campaigns
                    SET ideal_podcast_description = $1
                    WHERE campaign_id = $2
                    """
                    
                    async with pool.acquire() as conn:
                        await conn.execute(update_query, ideal_from_questionnaire, campaign_id)
                    
                    logger.info(f"✅ {campaign_name}: Synced description from questionnaire")
                    synced += 1
            else:
                if not current_description:
                    logger.info(f"❌ {campaign_name}: No ideal description in questionnaire or DB")
                    no_description_in_questionnaire += 1
                
        except Exception as e:
            logger.error(f"Error processing {campaign_name}: {e}")
    
    logger.info(f"\n=== Sync Summary ===")
    logger.info(f"Already synced: {already_synced}")
    logger.info(f"Newly synced: {synced}")
    logger.info(f"No description in questionnaire: {no_description_in_questionnaire}")
    logger.info(f"Total campaigns checked: {len(campaigns)}")

async def verify_vetting_data():
    """Verify which campaigns can be vetted."""
    pool = await get_db_pool()
    
    query = """
    SELECT 
        COUNT(*) as total,
        COUNT(ideal_podcast_description) as has_description,
        COUNT(questionnaire_responses) as has_questionnaire,
        COUNT(CASE WHEN ideal_podcast_description IS NOT NULL 
                   AND questionnaire_responses IS NOT NULL THEN 1 END) as has_both,
        COUNT(CASE WHEN ideal_podcast_description IS NULL 
                   AND questionnaire_responses IS NULL THEN 1 END) as has_neither
    FROM campaigns
    """
    
    async with pool.acquire() as conn:
        stats = await conn.fetchrow(query)
    
    logger.info(f"\n=== Campaign Vetting Readiness ===")
    logger.info(f"Total campaigns: {stats['total']}")
    logger.info(f"Has ideal_podcast_description: {stats['has_description']}")
    logger.info(f"Has questionnaire_responses: {stats['has_questionnaire']}")
    logger.info(f"Has both (fully ready): {stats['has_both']}")
    logger.info(f"Has neither (cannot vet): {stats['has_neither']}")

async def main():
    """Main function."""
    logger.info("=== Ideal Podcast Description Sync ===\n")
    
    await sync_descriptions()
    await verify_vetting_data()
    
    logger.info("\n=== Sync Complete ===")

if __name__ == "__main__":
    asyncio.run(main())