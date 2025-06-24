# Pitch Templates Documentation

## Overview
This document describes the pitch template system migrated from the legacy Airtable system to the PostgreSQL-based PGL system.

## Templates Created

### 1. Generic Pitch Template (`generic_pitch_v1`)
The main template for generating personalized pitch emails to podcast hosts.

**Key Features:**
- Context-aware handling of previous contacts
- Dynamic placeholder system for personalization
- Media kit integration
- Tone adjustment based on previous interactions

### 2. Subject Line Template (`subject_line_v1`)
Template for generating email subject lines that feel like genuine listener feedback.

**Key Features:**
- References specific episode content
- Uses "Great episode with [guest]" or "Great episode about [topic]" format
- Avoids generic pitch subject lines

## Setup Instructions

### Running the Setup Script
```bash
cd podcast_outreach/scripts
python setup_pitch_templates.py
```

This will create both templates in the database.

### Individual Template Creation
If you need to create templates individually:

```bash
# For generic pitch template
python create_generic_pitch_template.py

# For subject line template
python create_subject_line_template.py
```

## Available Placeholders

The templates support the following placeholders that will be dynamically replaced with actual data:

### Podcast Information
- `{{podcast_name}}` - Name of the podcast
- `{{host_name}}` - Podcast host's name
- `{{episode_title}}` - Title of a relevant episode
- `{{episode_summary}}` - Short summary of a relevant episode
- `{{ai_summary_of_best_episode}}` - AI-generated summary of the best matching episode
- `{{latest_news_from_podcast}}` - Recent updates or news about the podcast
- `{{guest_name}}` - Guest name from the episode (for subject lines)

### Client Information
- `{{client_name}}` - Client's full name
- `{{client_bio_summary}}` - Summary of client's bio from campaign
- `{{campaign_goal}}` - Primary goal of the client's campaign
- `{{client_key_talking_point_1}}` - First key talking point
- `{{client_key_talking_point_2}}` - Second key talking point
- `{{client_key_talking_point_3}}` - Third key talking point

### Media Kit & Pitch Details
- `{{link_to_client_media_kit}}` - Public URL to client's media kit
- `{{media_kit_highlights}}` - Extracted highlights from media kit
- `{{specific_pitch_angle}}` - Specific angle tailored for this outreach

### Context Awareness (for repeat contacts)
- `{{previous_context}}` - Information about previous interactions
- `{{context_guidelines}}` - Specific guidelines based on contact history

## Integration with Pitch Generation

When generating pitches, the system should:

1. Load the appropriate template from the database
2. Gather all required data for the placeholders
3. Replace placeholders with actual values
4. Send the formatted prompt to the AI model
5. Handle any missing data gracefully

### Example Usage in Code

```python
from podcast_outreach.database.queries import pitch_templates

# Get the template
template = await pitch_templates.get_template_by_id('generic_pitch_v1')

# Replace placeholders
prompt = template['prompt_body']
prompt = prompt.replace('{{podcast_name}}', podcast_data['name'])
prompt = prompt.replace('{{client_name}}', campaign_data['client_name'])
# ... continue for all placeholders

# Send to AI model for generation
```

## Context-Aware Features

The generic pitch template includes sophisticated handling for repeat contacts:

### First Contact
- Standard introduction approach
- Full pitch with all details

### Previous Interest Shown
- References positive past interactions
- Builds on previous engagement
- More enthusiastic tone

### No Previous Response
- Gentle follow-up approach
- Shorter, more direct pitch
- Acknowledges they may be busy

### Multiple Clients Pitched
- Acknowledges representing multiple clients
- Emphasizes what makes THIS client unique
- Completely different approach

### Previous Rejection
- Significantly different angle
- Focuses on unique value proposition
- Avoids repeating rejected topics

## Best Practices

1. **Always check for previous contacts** before generating a pitch
2. **Gather comprehensive data** for all placeholders before generation
3. **Handle missing data gracefully** - the template includes instructions for this
4. **Monitor template performance** and update based on response rates
5. **Keep templates updated** as the pitch strategy evolves

## Maintenance

### Updating Templates
Use the update functionality in the scripts or directly through the database queries:

```python
await pitch_templates.update_template(
    'generic_pitch_v1',
    {'prompt_body': updated_prompt}
)
```

### Adding New Templates
Create new templates following the same pattern, with unique template IDs.

## Troubleshooting

### Template Not Found
- Ensure setup scripts have been run
- Check database connection
- Verify template_id matches exactly

### Placeholders Not Replaced
- Ensure all data is gathered before replacement
- Check for typos in placeholder names
- Handle None/null values appropriately

### Poor Pitch Quality
- Review the data being passed to placeholders
- Ensure context guidelines are being followed
- Check AI model parameters (temperature, etc.)