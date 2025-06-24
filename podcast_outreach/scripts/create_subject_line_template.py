#!/usr/bin/env python3
"""
Script to create a subject line template based on the legacy Airtable system.
This creates a template for generating email subject lines for pitch emails.
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


# The subject line template prompt body
SUBJECT_LINE_TEMPLATE = """Write a subject line for a podcast pitch email.

CONTEXT:
- Podcast Name: {{podcast_name}}
- Host Name: {{host_name}}
- Episode Title: {{episode_title}}
- Episode Summary: {{episode_summary}}
- AI Summary: {{ai_summary_of_best_episode}}
- Guest Name (if episode had a guest): {{guest_name}}
- Client Being Pitched: {{client_name}}

RULES:
1. If {{guest_name}} is provided and not empty, use this format: "Great episode with {{guest_name}}"
2. Otherwise, use this format: "Great episode about [topic]" where you determine the topic from the episode summary
3. The subject line should be concise and reference the specific episode content
4. Do not use generic subjects like "Podcast Guest Opportunity" or "Guest Pitch"
5. Make it sound like genuine listener feedback first, pitch second

EXAMPLES OF GOOD SUBJECT LINES:
- "Great episode with John Smith"
- "Great episode about sustainable investing"
- "Great episode about AI in healthcare"
- "Loved your conversation with Sarah Johnson"
- "Your episode on remote work trends was spot on"

OUTPUT:
Give ONLY one subject line as your only output. Nothing else."""


async def create_subject_line_template():
    """Create the subject line template in the database."""
    
    template_data = {
        'template_id': 'subject_line_v1',
        'media_type': 'podcast',
        'target_media_type': 'email',
        'language_code': 'en',
        'tone': 'friendly_listener',
        'prompt_body': SUBJECT_LINE_TEMPLATE,
        'created_by': 'system_migration'
    }
    
    try:
        # Check if template already exists
        existing = await pitch_templates.get_template_by_id('subject_line_v1')
        
        if existing:
            logger.info("Template 'subject_line_v1' already exists. Updating...")
            # Update the existing template
            result = await pitch_templates.update_template(
                'subject_line_v1',
                {
                    'prompt_body': SUBJECT_LINE_TEMPLATE,
                    'tone': 'friendly_listener',
                    'created_by': 'system_migration_update'
                }
            )
            if result:
                logger.info("✅ Successfully updated subject line template")
            else:
                logger.error("❌ Failed to update subject line template")
        else:
            # Create new template
            result = await pitch_templates.create_template(template_data)
            
            if result:
                logger.info("✅ Successfully created subject line template")
                logger.info(f"Template ID: {result['template_id']}")
                logger.info(f"Target Media Type: {result['target_media_type']}")
                logger.info(f"Tone: {result['tone']}")
            else:
                logger.error("❌ Failed to create subject line template")
                
    except Exception as e:
        logger.error(f"❌ Error creating/updating template: {e}")
        raise


async def main():
    """Main function to run the template creation."""
    logger.info("🚀 Starting subject line template creation...")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    
    try:
        # Create the subject line template
        await create_subject_line_template()
        
        logger.info("\n✅ Subject line template created successfully!")
        logger.info("Template ID: 'subject_line_v1'")
        
    except Exception as e:
        logger.error(f"❌ Script failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())