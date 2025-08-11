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
        'previous_shows': [],
        'current_role': '',
        'unique_perspective': '',
        'ideal_podcast_preference': ''  # New field for user's preference
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
    
    # Extract current role and unique perspective
    contact_info = questionnaire.get('contactInfo', {})
    if isinstance(contact_info, dict):
        info['current_role'] = contact_info.get('title', '')
    
    unique_value = questionnaire.get('uniqueValue', {})
    if isinstance(unique_value, dict):
        info['unique_perspective'] = unique_value.get('description', '')
    
    # Extract target audience
    target_audience = questionnaire.get('targetAudience', {})
    if isinstance(target_audience, dict):
        info['target_audience'] = target_audience.get('description', '')
    
    # Extract key messages
    suggested_topics = questionnaire.get('suggestedTopics', {})
    if isinstance(suggested_topics, dict):
        topics = suggested_topics.get('topics', '')
        key_message = suggested_topics.get('keyMessage', '')
        
        if topics:
            if isinstance(topics, list):
                info['key_messages'] = topics
            else:
                import re
                topic_list = re.split(r'\d+\.\s*|\n|,', str(topics))
                info['key_messages'] = [t.strip() for t in topic_list if t.strip()]
        
        # Also capture the key message if available
        if key_message and key_message not in info['key_messages']:
            info['key_messages'].append(key_message)
    
    # Extract previous shows
    media_exp = questionnaire.get('mediaExperience', {})
    if isinstance(media_exp, dict):
        previous = media_exp.get('previousAppearances', [])
        if isinstance(previous, list):
            info['previous_shows'] = [
                show.get('showName', '') for show in previous 
                if isinstance(show, dict) and show.get('showName')
            ]
    
    # Extract ideal podcast preference if available
    # This field may be added by chatbot in future
    ideal_podcast = questionnaire.get('idealPodcast', {})
    if isinstance(ideal_podcast, dict):
        info['ideal_podcast_preference'] = ideal_podcast.get('description', '')
    
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
    
    # Identify top 2-3 primary expertise areas
    primary_expertise = info['expertise_topics'][:3] if info['expertise_topics'] else []
    primary_topics = info['key_messages'][:3] if info['key_messages'] else []
    
    # Use the user's preference if available
    if info['ideal_podcast_preference']:
        prompt = f"""Based on the following client information and their stated preference, create a 2-3 sentence description of the ideal podcasts they should appear on:

Client's Stated Preference: {info['ideal_podcast_preference']}

Additional Context:
- Current Role: {info['current_role']}
- Primary Expertise Areas: {', '.join(primary_expertise)}
- Main Discussion Topics: {', '.join(primary_topics)}
- Target Audience: {info['target_audience']}
- Unique Perspective: {info['unique_perspective']}

IMPORTANT GUIDELINES:
1. Use "OR" logic to make the description inclusive (e.g., "podcasts focusing on X, Y, or Z")
2. Focus on the 1-2 PRIMARY areas of expertise, not all areas
3. Keep the description flexible to allow for broader matching
4. Avoid requiring ALL criteria to be met - use phrases like "particularly those" or "especially shows that"

Create a flexible, inclusive description that will match a good range of relevant podcasts."""
    else:
        # Fallback to generating based on available data
        prompt = f"""Based on the following client information, create a 2-3 sentence description of the ideal podcasts they should appear on:

Professional Background:
- Current Role: {info['current_role']}
- Primary Expertise Areas (TOP 2-3): {', '.join(primary_expertise)}
- Unique Perspective: {info['unique_perspective']}

Content Focus:
- Main Discussion Topics (TOP 2-3): {', '.join(primary_topics)}
- Target Audience: {info['target_audience']}
- Previous Podcast Experience: {', '.join(info['previous_shows'][:3]) if info['previous_shows'] else 'None mentioned'}

IMPORTANT GUIDELINES:
1. Use "OR" logic instead of "AND" logic (e.g., "Podcasts focusing on web development, entrepreneurship, or digital marketing")
2. Focus ONLY on the 1-2 PRIMARY areas, not all expertise areas
3. Use inclusive language like "particularly those discussing" or "especially shows that cover"
4. Make the description flexible enough to match 30-40% of relevant podcasts, not just 5-10%
5. Avoid overly specific requirements that few podcasts would meet

Example of GOOD description:
"Podcasts focusing on web development, technology careers, or leadership in tech, particularly those discussing career transitions or building technical skills."

Example of BAD description:
"Podcasts focused on Sales, Web Development, Customer interaction, Leadership with audiences interested in specific demographic."

Generate a flexible, inclusive description that prioritizes the PRIMARY expertise areas."""

    try:
        response = await openai_service.create_chat_completion(
            system_prompt="You are an expert at matching podcast guests with ideal podcasts. Generate flexible, inclusive descriptions that focus on PRIMARY expertise areas using OR logic, not AND logic. Your descriptions should help match a good range of relevant podcasts (30-40%), not just a narrow few (5-10%).",
            prompt=prompt,
            workflow="ideal_podcast_generation"
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