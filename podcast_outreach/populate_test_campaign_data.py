#!/usr/bin/env python3
"""
Populate test campaign data for campaigns that don't have questionnaire_responses or ideal_podcast_description.
This will help test the vetting system.
"""

import asyncio
import logging
import json
from typing import Dict, Any
from datetime import datetime

from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test data templates for different campaign types
TEST_CAMPAIGN_DATA = {
    "Jake - Targeted": {
        "ideal_podcast_description": "Technology and entrepreneurship podcasts focused on startup growth, venture capital, and scaling SaaS businesses to enterprise audiences.",
        "questionnaire_responses": {
            "professionalBio": {
                "expertiseTopics": "SaaS, Startup Growth, Venture Capital, B2B Sales, Product-Market Fit",
                "aboutWork": "Jake is a serial entrepreneur with 3 successful exits in the SaaS space.",
                "achievements": "Raised $50M in venture funding, scaled 2 companies to $10M ARR"
            },
            "atAGlanceStats": {
                "emailSubscribers": "5000",
                "yearsOfExperience": "12", 
                "keynoteEngagements": "30"
            },
            "suggestedTopics": {
                "topics": "Building a SaaS from 0 to $10M ARR, Raising Series A funding, Product-Market Fit strategies"
            }
        }
    },
    "Akash - Targeted": {
        "ideal_podcast_description": "AI and machine learning podcasts targeting technical audiences, data scientists, and ML engineers interested in practical applications.",
        "questionnaire_responses": {
            "professionalBio": {
                "expertiseTopics": "Machine Learning, Deep Learning, Computer Vision, NLP, AI Ethics",
                "aboutWork": "Akash is a Principal ML Engineer at a leading tech company.",
                "achievements": "Published 15 papers in top ML conferences, 2 patents in computer vision"
            },
            "atAGlanceStats": {
                "emailSubscribers": "3000",
                "yearsOfExperience": "8",
                "keynoteEngagements": "25"
            },
            "suggestedTopics": {
                "topics": "Practical ML in production, AI Ethics and bias, Future of computer vision"
            }
        }
    },
    "Brandon - Targeted": {
        "ideal_podcast_description": "Marketing and growth podcasts for B2B marketers, focusing on content strategy, SEO, and demand generation.",
        "questionnaire_responses": {
            "professionalBio": {
                "expertiseTopics": "Content Marketing, SEO, Demand Generation, Marketing Analytics, Growth Hacking",
                "aboutWork": "Brandon leads growth marketing at a unicorn startup.",
                "achievements": "Grew organic traffic from 10k to 1M monthly visitors"
            },
            "atAGlanceStats": {
                "emailSubscribers": "8000",
                "yearsOfExperience": "10",
                "keynoteEngagements": "15"
            },
            "suggestedTopics": {
                "topics": "Building a content engine, SEO in the age of AI, B2B demand generation strategies"
            }
        }
    },
    "Anna - Targeted": {
        "ideal_podcast_description": "Leadership and diversity podcasts targeting executives and HR professionals interested in building inclusive workplaces.",
        "questionnaire_responses": {
            "professionalBio": {
                "expertiseTopics": "Leadership Development, DEI, Organizational Culture, Executive Coaching, Change Management",
                "aboutWork": "Anna is a C-suite executive coach and DEI consultant.",
                "achievements": "Coached 100+ executives, implemented DEI programs at Fortune 500 companies"
            },
            "atAGlanceStats": {
                "emailSubscribers": "4000",
                "yearsOfExperience": "15",
                "keynoteEngagements": "40"
            },
            "suggestedTopics": {
                "topics": "Building inclusive leadership, Measuring DEI impact, Culture transformation"
            }
        }
    },
    "Test Campaign": {
        "ideal_podcast_description": "Education and edtech podcasts for K-12 educators and administrators interested in innovative teaching methods.",
        "questionnaire_responses": {
            "professionalBio": {
                "expertiseTopics": "Educational Technology, K-12 Innovation, STEM Education, Curriculum Design",
                "aboutWork": "Leading educational transformation initiatives in public schools.",
                "achievements": "Implemented district-wide STEM program affecting 10,000 students"
            },
            "atAGlanceStats": {
                "emailSubscribers": "2000",
                "yearsOfExperience": "7",
                "keynoteEngagements": "10"
            },
            "suggestedTopics": {
                "topics": "Future of K-12 education, Implementing STEM programs, EdTech best practices"
            }
        }
    }
}

async def populate_campaign_data():
    """Populate campaign data for testing."""
    pool = await get_db_pool()
    
    updated_count = 0
    
    for campaign_name, test_data in TEST_CAMPAIGN_DATA.items():
        # Find campaign by name
        query = """
        SELECT campaign_id, campaign_name, questionnaire_responses, ideal_podcast_description
        FROM campaigns
        WHERE campaign_name = $1
        """
        
        async with pool.acquire() as conn:
            campaign = await conn.fetchrow(query, campaign_name)
        
        if not campaign:
            logger.warning(f"Campaign '{campaign_name}' not found")
            continue
        
        campaign_id = campaign['campaign_id']
        
        # Check if already has data
        if campaign['questionnaire_responses'] or campaign['ideal_podcast_description']:
            logger.info(f"Campaign '{campaign_name}' already has data, skipping")
            continue
        
        # Update with test data
        update_query = """
        UPDATE campaigns
        SET questionnaire_responses = $1::jsonb,
            ideal_podcast_description = $2
        WHERE campaign_id = $3
        """
        
        async with pool.acquire() as conn:
            await conn.execute(
                update_query,
                json.dumps(test_data['questionnaire_responses']),
                test_data['ideal_podcast_description'],
                campaign_id
            )
        
        logger.info(f"✅ Updated campaign '{campaign_name}' with test data")
        updated_count += 1
    
    logger.info(f"\n✅ Updated {updated_count} campaigns with test data")

async def verify_campaign_data():
    """Verify campaigns now have data."""
    pool = await get_db_pool()
    
    query = """
    SELECT 
        campaign_name,
        ideal_podcast_description IS NOT NULL as has_description,
        questionnaire_responses IS NOT NULL as has_questionnaire
    FROM campaigns
    ORDER BY campaign_name
    """
    
    async with pool.acquire() as conn:
        campaigns = await conn.fetch(query)
    
    logger.info("\n=== Campaign Data Status ===")
    for campaign in campaigns:
        status = []
        if campaign['has_description']:
            status.append("✓ description")
        else:
            status.append("✗ description")
            
        if campaign['has_questionnaire']:
            status.append("✓ questionnaire")
        else:
            status.append("✗ questionnaire")
            
        logger.info(f"{campaign['campaign_name']:<30} {' | '.join(status)}")

async def main():
    """Main function."""
    logger.info("=== Populating Test Campaign Data ===\n")
    
    await populate_campaign_data()
    await verify_campaign_data()
    
    logger.info("\n=== Complete ===")

if __name__ == "__main__":
    asyncio.run(main())