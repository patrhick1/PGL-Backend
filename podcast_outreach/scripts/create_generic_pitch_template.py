#!/usr/bin/env python3
"""
Script to create a generic pitch template based on the legacy Airtable system.
This template will be the default pitch template until further notice.

This script creates a pitch template that includes:
- Context-aware guidelines for handling previous contacts
- Dynamic placeholders for campaign and media data
- Media kit integration
- Personalized approach based on episode content
"""

import asyncio
import logging
from datetime import datetime
from podcast_outreach.database.queries import pitch_templates

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# The generic pitch template prompt body with placeholders
GENERIC_PITCH_TEMPLATE = """You are writing a pitch email for a podcast guest appearance. Your goal is to craft a personalized, compelling pitch that will make the podcast host want to interview the proposed guest.

Here are the details:

PODCAST INFORMATION
- Podcast Name: {{podcast_name}}
- Host Name: {{host_name}}
- Episode Title (for reference): {{episode_title}}
- Episode Summary: {{episode_summary}}
- AI Summary: {{ai_summary_of_best_episode}}
- Latest News: {{latest_news_from_podcast}}

CLIENT INFORMATION
- Client Name: {{client_name}}
- Client Bio: {{client_bio_summary}}
- Campaign Goal: {{campaign_goal}}
- Key Talking Points:
  - {{client_key_talking_point_1}}
  - {{client_key_talking_point_2}}
  - {{client_key_talking_point_3}}

PITCH ANGLE
{{specific_pitch_angle}}

MEDIA KIT
- Media Kit URL: {{link_to_client_media_kit}}
- Media Kit Highlights:
{{media_kit_highlights}}

PREVIOUS OUTREACH CONTEXT:
{{previous_context}}

CONTEXT-AWARE GUIDELINES:
{{context_guidelines}}

GENERAL GUIDELINES:
1. Start with a friendly, personalized greeting using the host's name.
2. Mention you've listened to the podcast, referencing the specific episode content provided.
3. If there's a recent episode with a guest mentioned, highlight that you enjoyed it.
4. Briefly introduce your client with 1-2 key credentials. When using the MEDIA KIT HIGHLIGHTS, specifically look for and incorporate:
   - Impressive follower counts or social media statistics
   - Links to notable previous podcast appearances or other significant work/achievements
   - Unique selling points or accolades that would appeal to the podcast host and their audience
5. Clearly state that you're pitching {{client_name}} as a guest for {{podcast_name}}.
6. Outline 2-3 specific topics they can discuss based on the talking points and pitch angle provided.
7. Explain why {{client_name}} is a good fit for this podcast, using their bio and campaign goal to support this.
8. Keep the email concise (250-300 words).
9. End with a clear call to action asking if they'd be interested in having {{client_name}} as a guest.
10. DO NOT include any signature at the end (no "Thanks," or any other sign-off).

IMPORTANT CONTEXT-AWARE INSTRUCTIONS:
- If {{previous_context}} indicates previous contact, follow the specific guidelines in {{context_guidelines}}
- If this is a follow-up to previous outreach, acknowledge it appropriately
- If we've pitched other clients before, differentiate why THIS client is unique
- Adjust your tone based on the recommendation in {{context_guidelines}}

TONE AND STYLE:
- Use a conversational, authentic tone that doesn't sound templated
- Match the podcast's style (professional, casual, academic, etc.) based on the episode content
- Be enthusiastic but not overly salesy
- Show genuine interest in their podcast and audience

OUTPUT:
ONLY write the pitch email text, nothing else. Do not include the subject line.
If any placeholder data is missing or shows "N/A", work around it gracefully without mentioning the missing information."""


async def create_generic_template():
    """Create the generic pitch template in the database."""
    
    template_data = {
        'template_id': 'generic_pitch_v1',
        'media_type': 'podcast',
        'target_media_type': 'podcast',
        'language_code': 'en',
        'tone': 'friendly_professional',
        'prompt_body': GENERIC_PITCH_TEMPLATE,
        'created_by': 'system_migration'
    }
    
    try:
        # Check if template already exists
        existing = await pitch_templates.get_template_by_id('generic_pitch_v1')
        
        if existing:
            logger.info("Template 'generic_pitch_v1' already exists. Updating...")
            # Update the existing template
            result = await pitch_templates.update_template(
                'generic_pitch_v1',
                {
                    'prompt_body': GENERIC_PITCH_TEMPLATE,
                    'tone': 'friendly_professional',
                    'created_by': 'system_migration_update'
                }
            )
            if result:
                logger.info("✅ Successfully updated generic pitch template")
                logger.info(f"Template ID: {result['template_id']}")
                logger.info(f"Media Type: {result['media_type']}")
                logger.info(f"Tone: {result['tone']}")
                logger.info(f"Created By: {result['created_by']}")
                logger.info(f"Prompt Body Length: {len(result['prompt_body'])} characters")
            else:
                logger.error("❌ Failed to update generic pitch template")
        else:
            # Create new template
            result = await pitch_templates.create_template(template_data)
            
            if result:
                logger.info("✅ Successfully created generic pitch template")
                logger.info(f"Template ID: {result['template_id']}")
                logger.info(f"Media Type: {result['media_type']}")
                logger.info(f"Target Media Type: {result['target_media_type']}")
                logger.info(f"Language: {result['language_code']}")
                logger.info(f"Tone: {result['tone']}")
                logger.info(f"Created By: {result['created_by']}")
                logger.info(f"Created At: {result['created_at']}")
                logger.info(f"Prompt Body Length: {len(result['prompt_body'])} characters")
            else:
                logger.error("❌ Failed to create generic pitch template")
                
    except Exception as e:
        logger.error(f"❌ Error creating/updating template: {e}")
        raise


async def list_all_templates():
    """List all existing templates for verification."""
    templates = await pitch_templates.list_templates()
    
    logger.info(f"\n📋 Total templates in database: {len(templates)}")
    for template in templates:
        logger.info(f"  - {template['template_id']} ({template['tone']}) - Created: {template['created_at']}")


async def main():
    """Main function to run the template creation."""
    logger.info("🚀 Starting generic pitch template creation...")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    
    try:
        # Create the generic template
        await create_generic_template()
        
        # List all templates to verify
        await list_all_templates()
        
        logger.info("\n✅ Script completed successfully!")
        
        # Print usage instructions
        logger.info("\n📝 Usage Instructions:")
        logger.info("1. This template is now available with ID: 'generic_pitch_v1'")
        logger.info("2. Use it when generating pitches by referencing this template_id")
        logger.info("3. The template supports the following placeholders:")
        logger.info("   - {{podcast_name}}, {{host_name}}, {{episode_title}}, etc.")
        logger.info("   - {{client_name}}, {{client_bio_summary}}, {{campaign_goal}}")
        logger.info("   - {{client_key_talking_point_1}}, {{client_key_talking_point_2}}, etc.")
        logger.info("   - {{link_to_client_media_kit}}, {{specific_pitch_angle}}")
        logger.info("   - {{previous_context}}, {{context_guidelines}} for repeat contacts")
        logger.info("\n4. The system will replace these placeholders with actual data before sending to AI")
        
    except Exception as e:
        logger.error(f"❌ Script failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())