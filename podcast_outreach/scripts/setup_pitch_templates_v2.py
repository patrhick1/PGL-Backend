#!/usr/bin/env python3
"""
Updated pitch templates setup script with single braces for LangChain compatibility.
This version ensures templates work properly with the enhanced generator.

Run this script to update the pitch templates in the database.
"""

import asyncio
import logging
import sys
from datetime import datetime
from podcast_outreach.database.queries import pitch_templates

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# The generic pitch template with single braces for LangChain
GENERIC_PITCH_TEMPLATE = """You are writing a pitch email for a podcast guest appearance. Your goal is to craft a personalized, compelling pitch that will make the podcast host want to interview the proposed guest.

Here are the details:

PODCAST INFORMATION
- Podcast Name: {podcast_name}
- Host Name: {host_name}
- Episode Title (for reference): {episode_title}
- Episode Summary: {episode_summary}
- AI Summary: {ai_summary_of_best_episode}
- Latest News: {latest_news_from_podcast}

CLIENT INFORMATION
- Client Name: {client_name}
- Client Bio: {client_bio_summary}
- Campaign Goal: {campaign_goal}
- Key Talking Points:
  - {client_key_talking_point_1}
  - {client_key_talking_point_2}
  - {client_key_talking_point_3}

PITCH ANGLE
{specific_pitch_angle}

MEDIA KIT
- Media Kit URL: {link_to_client_media_kit}
- Media Kit Highlights:
{media_kit_highlights}

PREVIOUS OUTREACH CONTEXT:
{previous_context}

CONTEXT-AWARE GUIDELINES:
{context_guidelines}

GENERAL GUIDELINES:
1. Start with a friendly, personalized greeting using the host's name.
2. Mention you've listened to the podcast, referencing the specific episode content provided.
3. If there's a recent episode with a guest mentioned, highlight that you enjoyed it.
4. Briefly introduce your client with 1-2 key credentials. When using the MEDIA KIT HIGHLIGHTS, specifically look for and incorporate:
   - Impressive follower counts or social media statistics
   - Links to notable previous podcast appearances or other significant work/achievements
   - Unique selling points or accolades that would appeal to the podcast host and their audience
5. Clearly state that you're pitching {client_name} as a guest for {podcast_name}.
6. Outline 2-3 specific topics they can discuss based on the talking points and pitch angle provided.
7. Explain why {client_name} is a good fit for this podcast, using their bio and campaign goal to support this.
8. Keep the email concise (250-300 words).
9. End with a clear call to action asking if they'd be interested in having {client_name} as a guest.
10. DO NOT include any signature at the end (no "Thanks," or any other sign-off).

IMPORTANT CONTEXT-AWARE INSTRUCTIONS:
- If {previous_context} indicates previous contact, follow the specific guidelines in {context_guidelines}
- If this is a follow-up to previous outreach, acknowledge it appropriately
- If we've pitched other clients before, differentiate why THIS client is unique
- Adjust your tone based on the recommendation in {context_guidelines}

TONE AND STYLE:
- Use a conversational, authentic tone that doesn't sound templated
- Match the podcast's style (professional, casual, academic, etc.) based on the episode content
- Be enthusiastic but not overly salesy
- Show genuine interest in their podcast and audience

OUTPUT:
ONLY write the pitch email text, nothing else. Do not include the subject line.
If any placeholder data is missing or shows "N/A", work around it gracefully without mentioning the missing information."""

# The subject line template with single braces
SUBJECT_LINE_TEMPLATE = """Write a subject line for a podcast pitch email.

CONTEXT:
- Podcast Name: {podcast_name}
- Host Name: {host_name}
- Episode Title: {episode_title}
- Episode Summary: {episode_summary}
- AI Summary: {ai_summary_of_best_episode}
- Guest Name (if episode had a guest): {guest_name}
- Client Being Pitched: {client_name}

RULES:
1. If {guest_name} is provided and not empty, use this format: "Great episode with {guest_name}"
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


async def update_templates():
    """Update both pitch templates with single-brace format."""
    
    success_count = 0
    
    # Update generic pitch template
    try:
        logger.info("Updating generic_pitch_v1 template...")
        result = await pitch_templates.update_template(
            'generic_pitch_v1',
            {
                'prompt_body': GENERIC_PITCH_TEMPLATE,
                'tone': 'friendly_professional',
                'created_by': 'system_v2_update'
            }
        )
        if result:
            logger.info("✅ Successfully updated generic pitch template")
            success_count += 1
        else:
            logger.error("❌ Failed to update generic pitch template")
    except Exception as e:
        logger.error(f"❌ Error updating generic template: {e}")
    
    # Update subject line template
    try:
        logger.info("\nUpdating subject_line_v1 template...")
        result = await pitch_templates.update_template(
            'subject_line_v1',
            {
                'prompt_body': SUBJECT_LINE_TEMPLATE,
                'tone': 'friendly_listener',
                'created_by': 'system_v2_update'
            }
        )
        if result:
            logger.info("✅ Successfully updated subject line template")
            success_count += 1
        else:
            logger.error("❌ Failed to update subject line template")
    except Exception as e:
        logger.error(f"❌ Error updating subject line template: {e}")
    
    return success_count == 2


async def verify_templates():
    """Verify that templates have been updated correctly."""
    templates = await pitch_templates.list_templates()
    
    for template in templates:
        if template['template_id'] in ['generic_pitch_v1', 'subject_line_v1']:
            # Check if template uses single braces
            prompt_body = template.get('prompt_body', '')
            double_brace_count = prompt_body.count('{{')
            single_brace_count = prompt_body.count('{') - double_brace_count * 2
            
            logger.info(f"\nTemplate: {template['template_id']}")
            logger.info(f"  Single braces: {single_brace_count}")
            logger.info(f"  Double braces: {double_brace_count}")
            logger.info(f"  Updated by: {template.get('created_by', 'unknown')}")
            
            if double_brace_count > 0:
                logger.warning(f"  ⚠️  Template still contains double braces!")
            else:
                logger.info(f"  ✅ Template is using single braces correctly")


async def main():
    """Main function to update pitch templates."""
    logger.info("🚀 Starting pitch templates update to single-brace format...")
    logger.info("=" * 60)
    
    try:
        # Update templates
        success = await update_templates()
        
        if not success:
            logger.error("\n❌ Failed to update all templates")
            return False
        
        # Verify updates
        logger.info("\n🔍 Verifying template updates...")
        await verify_templates()
        
        logger.info("\n" + "=" * 60)
        logger.info("✅ Templates have been updated to single-brace format!")
        logger.info("\n📌 Key Changes:")
        logger.info("   - {{placeholder}} → {placeholder}")
        logger.info("   - Compatible with LangChain PromptTemplate")
        logger.info("   - Enhanced pitch generator will now work correctly")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Update failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)