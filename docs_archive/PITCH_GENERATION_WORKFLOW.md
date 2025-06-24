# Pitch Generation Workflow

## Current Workflow Overview

The system follows a multi-step workflow for generating pitches:

### 1. Match Suggestion Approval
When you approve a match suggestion:
- The `match_suggestions` record is updated:
  - `client_approved = TRUE`
  - `status = 'approved'`
  - `approved_at = NOW()`
- A new `review_tasks` record is created:
  - `task_type = 'pitch_review'`
  - `related_id = match_id` (from match_suggestions)
  - `status = 'pending'`

### 2. Pitch Generation (Manual Step Required)
To generate a pitch for the approved match:

**API Call:**
```bash
POST /pitches/generate
{
  "match_id": 5,
  "pitch_template_id": "generic_pitch_v1"  # Optional, uses default if not specified
}
```

This triggers:
- Creation of a `pitch_generations` record with the AI-generated pitch
- Creation of a `pitches` record linked to the pitch generation
- Update of the review task for pitch review

### 3. Pitch Review
The generated pitch needs to be reviewed and approved:
- View pending pitch review tasks
- Review the generated pitch content
- Approve or request modifications

### 4. Pitch Sending
Once approved, the pitch can be sent:
```bash
POST /pitches/{pitch_id}/send
```

## Why Pitches Aren't Auto-Generated

The system intentionally requires manual pitch generation because:
1. **Quality Control**: Allows review of match quality before spending AI credits
2. **Template Selection**: Different matches may need different pitch templates
3. **Timing Control**: Pitches can be generated when ready to send
4. **Batch Processing**: Multiple pitches can be generated together

## Viewing Pending Pitch Generation Tasks

To see matches that need pitches generated:

```bash
GET /review-tasks/enhanced?task_type=pitch_review&status=pending
```

This shows all approved matches waiting for pitch generation.

## Complete Example Flow

1. **View pending match suggestions:**
   ```bash
   GET /review-tasks/enhanced?task_type=match_suggestion&status=pending
   ```

2. **Approve a match:**
   ```bash
   POST /review-tasks/{review_task_id}/approve
   {
     "status": "approved",
     "notes": "Good fit for podcast"
   }
   ```

3. **Generate pitch for approved match:**
   ```bash
   POST /pitches/generate
   {
     "match_id": 5,
     "pitch_template_id": "generic_pitch_v1"
   }
   ```

4. **Review generated pitch:**
   ```bash
   GET /pitch-generations/{pitch_gen_id}
   ```

5. **Approve the pitch:**
   ```bash
   PATCH /pitch-generations/{pitch_gen_id}/approve
   ```

6. **Send the pitch:**
   ```bash
   POST /pitches/{pitch_id}/send
   ```

## Database Records Created

### After Match Approval:
- `match_suggestions`: Updated with approval status
- `review_tasks`: New record for pitch review

### After Pitch Generation:
- `pitch_generations`: Contains the generated pitch content
- `pitches`: Links to campaign, media, and pitch generation
- `review_tasks`: Updated or new record for pitch content review

### After Pitch Sending:
- `pitches`: Updated with send timestamp and status
- `instantly_leads`: Created if using Instantly integration

## Automation Options

To automate pitch generation after match approval, you could:
1. Create a background task that monitors for approved matches
2. Add a webhook/event system
3. Modify the match approval endpoint to optionally trigger generation

Currently, the manual step provides important quality control.