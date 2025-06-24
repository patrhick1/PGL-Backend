#!/usr/bin/env python3
"""Test the vetting system fix for email_subscribers template issue."""

import asyncio
import logging
import json
from datetime import datetime, timezone

from podcast_outreach.services.matches.enhanced_vetting_agent import EnhancedVettingAgent
from podcast_outreach.database.queries import campaigns as campaign_queries

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_vetting_with_questionnaire():
    """Test vetting with various questionnaire formats."""
    agent = EnhancedVettingAgent()
    
    # Test Case 1: Campaign with questionnaire containing email_subscribers
    test_campaign = {
        'campaign_id': 'test-123',
        'ideal_podcast_description': 'Technology podcasts focused on AI and machine learning',
        'questionnaire_responses': {
            'professionalBio': {
                'expertiseTopics': 'AI, Machine Learning, Data Science'
            },
            'atAGlanceStats': {
                'emailSubscribers': '10000',
                'yearsOfExperience': '10',
                'keynoteEngagements': '50'
            },
            'suggestedTopics': {
                'topics': 'Future of AI, Ethics in ML, Data Privacy'
            }
        }
    }
    
    logger.info("Testing vetting with questionnaire containing email_subscribers...")
    try:
        result = await agent.vet_match_enhanced(test_campaign, 1)
        if result:
            logger.info(f"✅ Test passed! Vetting score: {result['vetting_score']}")
            logger.info(f"Topic match analysis present: {'topic_match_analysis' in result}")
        else:
            logger.error("❌ Test failed - no result returned")
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
    
    # Test Case 2: Campaign with null questionnaire 
    test_campaign_null = {
        'campaign_id': 'test-456',
        'ideal_podcast_description': 'Business podcasts about entrepreneurship',
        'questionnaire_responses': None
    }
    
    logger.info("\nTesting vetting with null questionnaire...")
    try:
        result = await agent.vet_match_enhanced(test_campaign_null, 1)
        if result:
            logger.info(f"✅ Test passed! Vetting score: {result['vetting_score']}")
        else:
            logger.warning("⚠️ No result (expected if no data)")
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")

async def check_campaigns_with_ideal_description():
    """Check how many campaigns have ideal_podcast_description."""
    campaigns = await campaign_queries.get_all_campaigns()
    
    total = len(campaigns)
    with_description = sum(1 for c in campaigns if c.get('ideal_podcast_description'))
    
    logger.info(f"\nCampaign Statistics:")
    logger.info(f"Total campaigns: {total}")
    logger.info(f"With ideal_podcast_description: {with_description}")
    logger.info(f"Missing ideal_podcast_description: {total - with_description}")
    
    if with_description == 0:
        logger.warning("\n⚠️ No campaigns have ideal_podcast_description!")
        logger.info("This is likely why vetting is failing.")
        logger.info("Consider generating ideal_podcast_description from questionnaire data.")

async def main():
    """Run all tests."""
    logger.info("=== Testing Vetting System Fix ===\n")
    
    await test_vetting_with_questionnaire()
    await check_campaigns_with_ideal_description()
    
    logger.info("\n=== Tests Complete ===")

if __name__ == "__main__":
    asyncio.run(main())