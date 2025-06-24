# Automatic Pitch Generation Implementation

## Overview
This document describes the implementation of automatic pitch generation when a match suggestion is approved.

## Changes Made

### 1. Match Approval Process Enhancement
**File**: `podcast_outreach/database/queries/match_suggestions.py`

Modified the `approve_match_and_create_pitch_task` function to:
- Automatically trigger pitch generation using the PitchGeneratorService
- Use the `generic_pitch_v1` template by default
- Create proper review tasks with pitch_gen_id when successful
- Handle failures gracefully with fallback review tasks

### 2. Template Integration
**File**: `podcast_outreach/services/pitches/generator.py`

Updated:
- Default pitch template from `default_pitch_template` to `generic_pitch_v1`
- Subject line template to use `subject_line_v1`

### 3. Enhanced Review Task Display
**Files**: 
- `podcast_outreach/api/routers/review_tasks.py`
- `podcast_outreach/api/schemas/discovery_schemas.py`

Added support for pitch_review tasks to display:
- Pitch subject line
- Pitch body preview (first 500 characters)
- Pitch generation ID
- Template used
- Generation status

## Workflow After Implementation

### When a Match is Approved:
1. Match suggestion is updated (approved status)
2. Pitch generation is automatically triggered
3. AI generates pitch using the campaign and media data
4. Creates records in:
   - `pitch_generations` - Contains the full pitch text
   - `pitches` - Links everything together
   - `review_tasks` - Creates a pitch_review task

### Viewing Pitch Reviews:
The `/review-tasks/enhanced` endpoint now returns:
- For `match_suggestion` tasks: Vetting scores, media info, etc.
- For `pitch_review` tasks: Generated pitch preview, subject line, etc.

### Updating Pitch Content:
Use the endpoint:
```
PATCH /pitches/generations/{pitch_gen_id}/content
{
  "draft_text": "Updated pitch body...",
  "new_subject_line": "Updated subject line"
}
```

## Database Flow

1. **Match Approval**:
   - `match_suggestions.client_approved = TRUE`
   - `match_suggestions.status = 'approved'`

2. **Automatic Pitch Generation**:
   - `pitch_generations` record created with AI content
   - `pitches` record created linking to campaign/media
   - `review_tasks` record created (type: pitch_review)

3. **Pitch Review**:
   - View generated content
   - Edit if needed
   - Approve for sending

## Error Handling

If pitch generation fails:
- A review task is still created with error notes
- The match doesn't get lost
- Manual pitch generation can be triggered later

## Benefits

1. **Streamlined Workflow**: No manual step needed between match approval and pitch generation
2. **Immediate Feedback**: Users can see generated pitches right after approving matches
3. **Error Recovery**: Failures don't break the workflow
4. **Audit Trail**: All steps are tracked in review_tasks

## Testing

To test the implementation:
1. Approve a match suggestion
2. Check logs for pitch generation
3. View pitch review tasks with enhanced endpoint
4. Verify pitch content is displayed
5. Test editing pitch content

## Future Enhancements

1. Allow template selection during match approval
2. Batch pitch generation for multiple matches
3. Add regeneration capability with different templates
4. Implement pitch version history