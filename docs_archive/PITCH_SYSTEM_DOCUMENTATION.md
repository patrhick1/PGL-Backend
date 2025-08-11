# Pitch System Documentation

This document consolidates all pitch-related documentation for the PGL Podcast Outreach system.

## Overview

The pitch system is a core component that generates personalized outreach emails to podcast hosts. It uses AI to create compelling pitches based on client information, podcast analysis, and match data.

## System Architecture

### Components

1. **Pitch Generation Service** (`services/pitches/generator.py`)
   - Handles the creation of pitch drafts
   - Integrates with AI providers (Gemini, Claude, OpenAI)
   - Uses template system for consistency

2. **Enhanced Pitch Generator** (`services/pitches/enhanced_generator.py`)
   - Advanced version with better personalization
   - Includes episode-specific references
   - Improved subject line generation

3. **Pitch Templates** (`database/queries/pitch_templates.py`)
   - Database-managed templates
   - Support for multiple template types
   - Variable substitution system

4. **API Endpoints** (`api/routers/pitches.py`)
   - POST `/pitches/generate` - Generate new pitch
   - POST `/pitches/generate-batch` - Generate pitches for multiple matches
   - GET `/pitches/generations/{pitch_gen_id}` - Retrieve pitch
   - PATCH `/pitches/generations/{pitch_gen_id}/content` - Update pitch content
   - POST `/pitches/send-instantly/{pitch_gen_id}` - Send pitch via Instantly
   - POST `/pitches/send-nylas/{pitch_gen_id}` - Send pitch via Nylas

## Workflow

### 1. Pitch Generation Workflow

```mermaid
graph TD
    A[Match Approved] --> B[Trigger Pitch Generation]
    B --> C{Template Selection}
    C --> D[Gather Context Data]
    D --> E[AI Generation]
    E --> F[Save Draft]
    F --> G[Create Review Task]
    G --> H[Human Review]
    H --> I{Approved?}
    I -->|Yes| J[Send via Instantly]
    I -->|No| K[Edit & Regenerate]
    K --> H
```

### 2. Generation Process

1. **Context Gathering**
   - Client profile data
   - Podcast information
   - Recent episodes
   - Match reasoning

2. **Template Application**
   - Select appropriate template
   - Inject variables
   - Apply personalization

3. **AI Enhancement**
   - Generate personalized content
   - Create compelling subject line
   - Add episode-specific references

4. **Quality Checks**
   - Length validation
   - Personalization score
   - Template compliance

## Database Schema

### pitch_generations Table
```sql
- pitch_gen_id (PRIMARY KEY)
- campaign_id (FOREIGN KEY)
- media_id (FOREIGN KEY)
- template_id (FOREIGN KEY)
- draft_text
- ai_model_used
- pitch_topic
- temperature
- generated_at (DEFAULT CURRENT_TIMESTAMP)
- reviewer_id
- reviewed_at
- final_text
- send_ready_bool
- generation_status
```

### pitches Table
```sql
- pitch_id (PRIMARY KEY)
- campaign_id (FOREIGN KEY)
- media_id (FOREIGN KEY)
- pitch_gen_id (FOREIGN KEY)
- attempt_no
- match_score
- matched_keywords (TEXT[])
- score_evaluated_at
- outreach_type
- subject_line
- body_snippet
- send_ts
- reply_bool
- reply_ts
- instantly_lead_id
- placement_id (FOREIGN KEY)
- pitch_state
- client_approval_status
- created_by
- created_at (DEFAULT CURRENT_TIMESTAMP)

# Nylas Integration Fields:
- nylas_message_id
- nylas_thread_id
- nylas_draft_id
- email_provider (DEFAULT 'instantly')
- opened_ts
- clicked_ts
- bounce_type
- bounce_reason
- bounced_ts

# Enhanced Tracking Fields:
- tracking_label
- open_count (DEFAULT 0)
- click_count (DEFAULT 0)
- scheduled_send_at
- send_status (DEFAULT 'pending')
```

## API Usage

### Generate a Pitch

```bash
POST /pitches/generate
Content-Type: application/json

{
  "match_id": 123,
  "pitch_template_id": "friendly_intro_template"
}
```

### Generate Multiple Pitches (Batch)

```bash
POST /pitches/generate-batch
Content-Type: application/json

[
  {"match_id": 1, "pitch_template_id": "template_1"},
  {"match_id": 2, "pitch_template_id": "template_2"},
  {"match_id": 3, "pitch_template_id": "template_1"}
]
```

### Update Pitch Content

```bash
PATCH /pitches/generations/{pitch_gen_id}/content
Content-Type: application/json

{
  "draft_text": "Updated pitch content...",
  "new_subject_line": "New subject line"
}
```

### Send Pitch via Instantly

```bash
POST /pitches/send-instantly/{pitch_gen_id}
Content-Type: application/json
```

### Send Pitch via Nylas

```bash
POST /pitches/send-nylas/{pitch_gen_id}
Content-Type: application/json
```

## Templates

### Available Templates

1. **Friendly Introduction** (`friendly_intro_template.txt`)
   - Casual, conversational tone
   - References recent episodes
   - Focuses on value proposition

2. **B2B Startup** (`b2b_startup_template.txt`)
   - Professional tone
   - Emphasizes business expertise
   - Data-driven approach

3. **Bold Follow-up** (`bold_followup_template.txt`)
   - Direct approach
   - Used for second outreach
   - Creates urgency

### Template Variables

Common variables available in all templates:

- `{host_name}` - Podcast host's name
- `{podcast_name}` - Name of the podcast
- `{client_name}` - Client's full name
- `{client_bio}` - Generated client biography
- `{recent_episode_topic}` - Recent episode reference
- `{talking_points}` - Key discussion topics
- `{client_expertise}` - Areas of expertise

## Frontend Integration

### Review Interface

The frontend provides a comprehensive pitch review interface:

1. **Draft Display**
   - Formatted pitch preview
   - Subject line editing
   - Character/word count

2. **Editing Tools**
   - Rich text editor
   - Variable highlighting
   - Template switching

3. **Actions**
   - Approve & Send
   - Request Regeneration
   - Manual Edit
   - Save Draft

### API Integration Points

```javascript
// Generate pitch
const response = await fetch('/api/pitches/generations', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ match_id, template_id })
});

// Update pitch
await fetch(`/api/pitches/generations/${id}/content`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ draft_text, new_subject_line })
});
```

## Best Practices

### 1. Personalization
- Always include specific episode references
- Use the host's actual name (not "Host")
- Reference recent content (within 3 months)

### 2. Length Guidelines
- Subject lines: 50-70 characters
- Email body: 150-250 words
- 3-4 paragraphs maximum

### 3. Quality Checks
- No generic greetings
- Specific value propositions
- Clear call-to-action
- Professional but friendly tone

## Monitoring & Analytics

### Metrics Tracked
- Generation success rate
- AI model performance
- Template effectiveness
- Response rates by template
- Edit frequency

### Cost Tracking
- AI usage per generation
- Average cost per pitch
- Model comparison costs

## Troubleshooting

### Common Issues

1. **Generation Failures**
   - Check AI API keys
   - Verify template exists
   - Ensure match data is complete

2. **Sending Failures**
   - Verify Instantly API key
   - Check email validation
   - Ensure pitch is approved

3. **Poor Quality Output**
   - Review template effectiveness
   - Check context data quality
   - Consider model switching

## Future Enhancements

1. **A/B Testing Framework**
   - Multiple template variations
   - Automated performance tracking
   - Winner selection algorithms

2. **Advanced Personalization**
   - Social media integration
   - Sentiment analysis
   - Dynamic content blocks

3. **Automation Improvements**
   - Batch generation
   - Scheduled sending
   - Follow-up sequences

---

For implementation details, see:
- [Frontend Pitch Generation Guide](FRONTEND_PITCH_GENERATION_GUIDE.md)
- [API Documentation](API_DOCUMENTATION.md#pitch-endpoints)