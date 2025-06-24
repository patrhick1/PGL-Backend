#!/usr/bin/env python3
"""
Generate ideal_podcast_description for campaigns that don't have it.
This uses the questionnaire data to create a description of what kind of podcasts would be ideal for the client.
"""

import asyncio
import logging
from typing import Dict, Any

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.services.ai.openai_client import OpenAIService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def extract_topics_from_questionnaire(questionnaire: Dict[str, Any]) -> Dict[str, Any]:
    """Extract key information from questionnaire responses."""
    info = {
        'expertise_topics': [],
        'target_audience': '',
        'key_messages': [],
        'previous_shows': []
    }
    
    # Extract expertise topics
    professional_bio = questionnaire.get('professionalBio', {})
    if isinstance(professional_bio, dict):
        expertise = professional_bio.get('expertiseTopics', '')
        if expertise:
            if isinstance(expertise, list):
                info['expertise_topics'] = expertise
            else:
                info['expertise_topics'] = [t.strip() for t in str(expertise).split(',') if t.strip()]
    
    # Extract target audience
    target_audience = questionnaire.get('targetAudience', {})
    if isinstance(target_audience, dict):
        info['target_audience'] = target_audience.get('description', '')
    
    # Extract key messages
    suggested_topics = questionnaire.get('suggestedTopics', {})
    if isinstance(suggested_topics, dict):
        topics = suggested_topics.get('topics', '')
        if topics:
            if isinstance(topics, list):
                info['key_messages'] = topics
            else:
                import re
                topic_list = re.split(r'\d+\.\s*|\n|,', str(topics))
                info['key_messages'] = [t.strip() for t in topic_list if t.strip()]
    
    # Extract previous shows
    media_exp = questionnaire.get('mediaExperience', {})
    if isinstance(media_exp, dict):
        previous = media_exp.get('previousAppearances', [])
        if isinstance(previous, list):
            info['previous_shows'] = [
                show.get('showName', '') for show in previous 
                if isinstance(show, dict) and show.get('showName')
            ]
    
    return info

async def generate_ideal_description(campaign_data: Dict[str, Any], openai_service: OpenAIService) -> str:
    """Generate ideal podcast description using AI."""
    questionnaire = campaign_data.get('questionnaire_responses', {})
    if not questionnaire:
        return ""
    
    info = await extract_topics_from_questionnaire(questionnaire)
    
    # If we don't have enough data, skip
    if not info['expertise_topics'] and not info['key_messages']:
        return ""
    
    prompt = f"""Based on the following client information, create a 2-3 sentence description of the ideal podcasts they should appear on:

Client Expertise: {', '.join(info['expertise_topics'][:10])}
Key Discussion Topics: {', '.join(info['key_messages'][:10])}
Target Audience: {info['target_audience']}
Previous Shows: {', '.join(info['previous_shows'][:5])}

Write a clear, specific description that captures:
1. The type of podcasts (topic/industry focus)
2. The ideal audience demographic
3. The show format or style that would work best

Keep it concise and actionable for matching purposes."""

    try:
        response = await openai_service.get_completion(
            prompt=prompt,
            max_tokens=150,
            temperature=0.7
        )
        return response.strip()
    except Exception as e:
        logger.error(f"Error generating description: {e}")
        return ""

async def update_campaign_descriptions():
    """Update campaigns with missing ideal_podcast_description."""
    pool = await get_db_pool()
    openai_service = OpenAIService()
    
    # Get campaigns without ideal_podcast_description
    query = """
    SELECT campaign_id, questionnaire_responses, campaign_name
    FROM campaigns
    WHERE (ideal_podcast_description IS NULL OR ideal_podcast_description = '')
    AND questionnaire_responses IS NOT NULL
    """
    
    async with pool.acquire() as conn:
        campaigns = await conn.fetch(query)
    
    logger.info(f"Found {len(campaigns)} campaigns without ideal_podcast_description")
    
    updated_count = 0
    for campaign in campaigns:
        campaign_id = campaign['campaign_id']
        campaign_name = campaign['campaign_name']
        
        logger.info(f"Processing campaign: {campaign_name} ({campaign_id})")
        
        # Generate description
        description = await generate_ideal_description(dict(campaign), openai_service)
        
        if description:
            # Update the campaign
            update_query = """
            UPDATE campaigns
            SET ideal_podcast_description = $1
            WHERE campaign_id = $2
            """
            
            async with pool.acquire() as conn:
                await conn.execute(update_query, description, campaign_id)
            
            logger.info(f"✅ Updated campaign {campaign_id} with description: {description[:100]}...")
            updated_count += 1
        else:
            logger.warning(f"⚠️ Could not generate description for campaign {campaign_id}")
        
        # Small delay to avoid rate limits
        await asyncio.sleep(1)
    
    logger.info(f"\n✅ Updated {updated_count} campaigns with ideal_podcast_description")

async def main():
    """Main function."""
    logger.info("=== Generating Ideal Podcast Descriptions ===\n")
    
    await update_campaign_descriptions()
    
    logger.info("\n=== Complete ===")

if __name__ == "__main__":
    asyncio.run(main())