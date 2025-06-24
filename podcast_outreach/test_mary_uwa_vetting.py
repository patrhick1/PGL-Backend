#!/usr/bin/env python3
"""Test the vetting system with Mary Uwa's campaign data."""

import asyncio
import logging
from datetime import datetime

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
from podcast_outreach.services.matches.enhanced_vetting_agent import EnhancedVettingAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_mary_uwa_vetting():
    """Test vetting with Mary Uwa's campaign."""
    pool = await get_db_pool()
    agent = EnhancedVettingAgent()
    
    # Get Mary Uwa's campaign
    mary_campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    
    logger.info(f"=== Testing Vetting for Mary Uwa's Campaign ===\n")
    
    # Get campaign data
    campaign_data = await campaign_queries.get_campaign_by_id(mary_campaign_id)
    
    if not campaign_data:
        logger.error(f"Campaign {mary_campaign_id} not found!")
        return
    
    logger.info(f"Campaign: {campaign_data['campaign_name']}")
    logger.info(f"Has ideal_podcast_description: {bool(campaign_data.get('ideal_podcast_description'))}")
    logger.info(f"Has questionnaire_responses: {bool(campaign_data.get('questionnaire_responses'))}")
    
    # Get a few discoveries for this campaign
    query = """
    SELECT cmd.*, m.name as media_name
    FROM campaign_media_discoveries cmd
    JOIN media m ON cmd.media_id = m.media_id
    WHERE cmd.campaign_id = $1
    AND cmd.enrichment_status = 'completed'
    LIMIT 3
    """
    
    async with pool.acquire() as conn:
        discoveries = await conn.fetch(query, mary_campaign_id)
    
    logger.info(f"\nFound {len(discoveries)} enriched discoveries to test")
    
    # Test vetting on each discovery
    for i, discovery in enumerate(discoveries, 1):
        logger.info(f"\n--- Test {i}: {discovery['media_name']} ---")
        
        try:
            # Run vetting
            vetting_result = await agent.vet_match(campaign_data, discovery['media_id'])
            
            if vetting_result:
                logger.info(f"✅ Vetting successful!")
                logger.info(f"Score: {vetting_result['vetting_score']}")
                logger.info(f"Has topic_match_analysis: {bool(vetting_result.get('topic_match_analysis'))}")
                logger.info(f"Has vetting_criteria_scores: {bool(vetting_result.get('vetting_criteria_scores'))}")
                logger.info(f"Has client_expertise_matched: {bool(vetting_result.get('client_expertise_matched'))}")
                
                # Show a preview of the topic match analysis
                if vetting_result.get('topic_match_analysis'):
                    logger.info(f"\nTopic Match Analysis Preview:")
                    logger.info(vetting_result['topic_match_analysis'][:200] + "...")
            else:
                logger.warning(f"❌ Vetting returned no results")
                
        except Exception as e:
            logger.error(f"❌ Vetting failed with error: {e}")

async def check_vetting_data_storage():
    """Check if vetting data is being stored properly."""
    pool = await get_db_pool()
    
    logger.info("\n=== Checking Vetting Data Storage ===\n")
    
    # Check recent vetting results
    query = """
    SELECT 
        id,
        media_id,
        vetting_score,
        vetting_criteria_met,
        topic_match_analysis,
        vetting_criteria_scores,
        client_expertise_matched,
        vetted_at
    FROM campaign_media_discoveries
    WHERE campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    AND vetting_status = 'completed'
    AND vetted_at > NOW() - INTERVAL '1 day'
    ORDER BY vetted_at DESC
    LIMIT 3
    """
    
    async with pool.acquire() as conn:
        results = await conn.fetch(query)
    
    if not results:
        logger.info("No recently vetted records found")
        return
    
    logger.info(f"Found {len(results)} recently vetted records:")
    
    for result in results:
        logger.info(f"\nDiscovery ID: {result['id']}")
        logger.info(f"Vetting Score: {result['vetting_score']}")
        logger.info(f"Vetted At: {result['vetted_at']}")
        
        # Check new columns
        if result['topic_match_analysis']:
            logger.info(f"✅ topic_match_analysis: {len(result['topic_match_analysis'])} chars")
        else:
            logger.info(f"❌ topic_match_analysis: NULL")
            
        if result['vetting_criteria_scores']:
            logger.info(f"✅ vetting_criteria_scores: {len(result['vetting_criteria_scores'])} items")
        else:
            logger.info(f"❌ vetting_criteria_scores: NULL")
            
        if result['client_expertise_matched']:
            logger.info(f"✅ client_expertise_matched: {len(result['client_expertise_matched'])} items")
        else:
            logger.info(f"❌ client_expertise_matched: NULL")
        
        # Check if data is in vetting_criteria_met (backward compatible)
        if result['vetting_criteria_met']:
            vcm = result['vetting_criteria_met']
            logger.info(f"\nvetting_criteria_met contains:")
            if 'vetting_checklist' in vcm:
                logger.info(f"  - vetting_checklist: ✅")
            if 'topic_match_analysis' in vcm:
                logger.info(f"  - topic_match_analysis: ✅ (in JSONB)")
            if 'vetting_criteria_scores' in vcm:
                logger.info(f"  - vetting_criteria_scores: ✅ (in JSONB)")
            if 'client_expertise_matched' in vcm:
                logger.info(f"  - client_expertise_matched: ✅ (in JSONB)")

async def main():
    """Run all tests."""
    await test_mary_uwa_vetting()
    await check_vetting_data_storage()
    
    logger.info("\n=== Test Complete ===")

if __name__ == "__main__":
    asyncio.run(main())