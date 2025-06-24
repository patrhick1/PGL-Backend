#!/usr/bin/env python3
"""
Add basic ideal_podcast_description to campaigns based on their names.
This is a simpler approach since most campaigns don't have questionnaire data.
"""

import asyncio
import logging
from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Basic descriptions based on campaign names
CAMPAIGN_DESCRIPTIONS = {
    "Jake - Targeted": "Technology and entrepreneurship podcasts focused on startup growth, SaaS businesses, and venture capital for founders and tech leaders.",
    "Akash - Targeted": "AI and machine learning podcasts for technical audiences interested in practical ML applications, data science, and emerging AI technologies.",
    "Brandon - Targeted": "Marketing and business growth podcasts targeting B2B marketers, covering content strategy, digital marketing, and growth hacking.",
    "Anna - Targeted": "Leadership and workplace culture podcasts for executives and HR professionals focused on building inclusive, high-performing teams.",
    "Test Campaign": "Education and professional development podcasts for educators and school administrators interested in innovative teaching methods.",
    "Michael Greenberg": "Business strategy and entrepreneurship podcasts for founders and business leaders looking to scale their companies.",
    "Ashwin - Targeted": "Technology and innovation podcasts focused on software development, cloud computing, and digital transformation.",
    "Daniel - Targeted": "Finance and investment podcasts for financial professionals and investors interested in market analysis and wealth management.",
    "Tom - Targeted": "Health and wellness podcasts targeting fitness enthusiasts and health professionals interested in evidence-based wellness strategies.",
    "Kevin Targeted": "Real estate and property investment podcasts for investors and real estate professionals looking for market insights.",
    "Erick - Targeted (Christian)": "Faith-based and inspirational podcasts for Christian audiences interested in spiritual growth and faith in the workplace.",
    "William - Targeted": "Sales and business development podcasts for sales professionals and business leaders focused on modern selling techniques.",
    "MGG Targeted": "Media and entertainment podcasts for creative professionals and content creators interested in digital media trends.",
    "Erick - Targeted (Construction)": "Construction and engineering podcasts for contractors and construction professionals interested in industry innovation.",
    "Cody - Business": "Small business and entrepreneurship podcasts for business owners and aspiring entrepreneurs focused on practical business strategies.",
    "Test AI Automation": "Technology and automation podcasts for IT professionals and business leaders interested in AI implementation and digital transformation.",
    "Phillip - Targeted": "AI governance and responsible technology podcasts for executives and policy makers focused on ethical AI implementation and compliance."
}

async def add_ideal_descriptions():
    """Add ideal_podcast_description to campaigns."""
    pool = await get_db_pool()
    
    # Get all campaigns
    query = """
    SELECT campaign_id, campaign_name, ideal_podcast_description
    FROM campaigns
    ORDER BY campaign_name
    """
    
    async with pool.acquire() as conn:
        campaigns = await conn.fetch(query)
    
    updated_count = 0
    
    for campaign in campaigns:
        campaign_name = campaign['campaign_name']
        campaign_id = campaign['campaign_id']
        
        # Skip if already has description
        if campaign['ideal_podcast_description']:
            logger.info(f"✓ '{campaign_name}' already has ideal_podcast_description")
            continue
        
        # Get description from our mapping
        description = CAMPAIGN_DESCRIPTIONS.get(campaign_name)
        
        if not description:
            logger.warning(f"✗ No description mapping for '{campaign_name}'")
            continue
        
        # Update campaign
        update_query = """
        UPDATE campaigns
        SET ideal_podcast_description = $1
        WHERE campaign_id = $2
        """
        
        async with pool.acquire() as conn:
            await conn.execute(update_query, description, campaign_id)
        
        logger.info(f"✅ Updated '{campaign_name}' with ideal_podcast_description")
        updated_count += 1
    
    logger.info(f"\n✅ Updated {updated_count} campaigns with ideal_podcast_description")

async def verify_results():
    """Verify the results."""
    pool = await get_db_pool()
    
    query = """
    SELECT 
        COUNT(*) as total,
        COUNT(ideal_podcast_description) as with_description,
        COUNT(questionnaire_responses) as with_questionnaire
    FROM campaigns
    """
    
    async with pool.acquire() as conn:
        result = await conn.fetchrow(query)
    
    logger.info("\n=== Final Campaign Statistics ===")
    logger.info(f"Total campaigns: {result['total']}")
    logger.info(f"With ideal_podcast_description: {result['with_description']}")
    logger.info(f"With questionnaire_responses: {result['with_questionnaire']}")
    logger.info(f"Missing ideal_podcast_description: {result['total'] - result['with_description']}")

async def main():
    """Main function."""
    logger.info("=== Adding Basic Ideal Descriptions ===\n")
    
    await add_ideal_descriptions()
    await verify_results()
    
    logger.info("\n=== Complete ===")

if __name__ == "__main__":
    asyncio.run(main())