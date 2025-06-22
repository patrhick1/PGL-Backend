# Pitch Generation Improvements Summary

## Changes Made

### 1. Automatic Pitch Generation on Match Approval
**File**: `podcast_outreach/database/queries/match_suggestions.py`
- When a match is approved, pitch generation is automatically triggered
- Uses the `generic_pitch_v1` template by default
- Handles errors gracefully with fallback review tasks

### 2. Database Query Optimizations
**Files**: 
- `podcast_outreach/database/queries/pitch_generations.py`
- `podcast_outreach/database/queries/pitches.py`

**Changes**:
- Removed `generated_at` from pitch_generations INSERT (uses DB default)
- Removed `created_at` from pitches INSERT (uses DB default)
- Cleaner timestamp handling

### 3. Template Placeholder Support
**File**: `podcast_outreach/services/pitches/generator.py`

**Added placeholders**:
- `{{podcast_name}}`, `{{host_name}}`, `{{episode_title}}`
- `{{episode_summary}}`, `{{ai_summary_of_best_episode}}`
- `{{client_name}}`, `{{client_bio_summary}}`, `{{campaign_goal}}`
- `{{client_key_talking_point_1}}`, `{{client_key_talking_point_2}}`, `{{client_key_talking_point_3}}`
- `{{specific_pitch_angle}}`, `{{link_to_client_media_kit}}`
- `{{previous_context}}`, `{{context_guidelines}}`
- `{{guest_name}}` (for subject lines)

### 4. Enhanced Review Task Display
**Files**:
- `podcast_outreach/api/routers/review_tasks.py`
- `podcast_outreach/api/schemas/discovery_schemas.py`

**Added fields for pitch_review tasks**:
- `pitch_gen_id` - Links to the pitch generation
- `pitch_subject_line` - Shows the generated subject
- `pitch_body_preview` - First 500 chars of pitch
- `pitch_template_used` - Which template was used
- `pitch_generation_status` - Current status

### 5. Pitch Content Editing
**Endpoint**: `PATCH /pitches/generations/{pitch_gen_id}/content`
- Can update draft_text (pitch body)
- Can update subject_line
- Changes are saved to database

## Database Schema Analysis

### pitch_generations Table
**Purpose**: Stores AI-generated content and metadata
- All essential fields are populated
- Timestamps use database defaults
- Links properly to campaigns, media, and templates

### pitches Table  
**Purpose**: Represents pitch attempts and sends
- Links to pitch_generations for content
- Tracks match scores and keywords
- Ready for Instantly.ai integration

## Workflow Summary

1. **Match Approved** → Automatic pitch generation
2. **AI Generates** → Creates pitch_generations and pitches records
3. **Review Task Created** → Shows generated content
4. **Editor Reviews** → Can edit via API
5. **Approval** → Marks as send_ready
6. **Send** → Via Instantly.ai integration

## Next Steps

1. **Extract talking points** from campaign data
2. **Implement context awareness** for repeat contacts
3. **Add latest podcast news** from recent episodes
4. **Track pitch versions** when edited
5. **Add vetting context** to pitch generation

## Testing Checklist

- [x] Match approval triggers pitch generation
- [x] Pitch content is generated with all placeholders
- [x] Review tasks show pitch preview
- [x] Pitch content can be edited
- [x] Database fields are properly populated
- [x] Timestamps use database defaults