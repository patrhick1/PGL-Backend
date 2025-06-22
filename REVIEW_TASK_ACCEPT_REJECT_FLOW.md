# Review Task Accept/Reject Flow Documentation

## Overview
This document traces the complete flow when a user clicks accept or reject on a review task in the UI.

## API Endpoints

### 1. Main Approval Endpoint
**Endpoint**: `POST /review-tasks/{review_task_id}/approve`
- **Location**: `podcast_outreach/api/routers/review_tasks.py:217-264`
- **Handler**: `approve_review_task()`

### 2. Alternative Update Endpoint  
**Endpoint**: `PATCH /review-tasks/{review_task_id}`
- **Location**: `podcast_outreach/api/routers/review_tasks.py:148-215`
- **Handler**: `update_review_task()`

## Flow Sequence

### Step 1: Frontend API Call
The frontend makes a POST request to `/review-tasks/{review_task_id}/approve` with:
```json
{
  "status": "approved" | "rejected",
  "notes": "Optional reviewer notes"
}
```

### Step 2: Review Task Router Processing
1. The `approve_review_task()` function validates the review task exists
2. For `match_suggestion` task type with status `approved` or `rejected`:
   - Calls `process_match_suggestion_approval()` from `review_tasks.py:82-123`

### Step 3: Process Match Suggestion Approval
**Location**: `podcast_outreach/database/queries/review_tasks.py:82-123`

The function performs these operations:

1. **Fetches the review task** to get details (task_type, related_id)
2. **Updates the review task status**:
   - Sets status to 'approved' or 'rejected'
   - Sets completed_at timestamp to NOW()
   - Adds any reviewer notes

3. **For APPROVED match suggestions**:
   - Calls `approve_match_and_create_pitch_task()` from match_suggestions.py:135-170
   - This function:
     - Updates match_suggestions table:
       - `client_approved = TRUE`
       - `status = 'approved'`
       - `approved_at = NOW()`
     - Creates a new review task of type `pitch_review`:
       ```python
       {
           "task_type": "pitch_review",
           "related_id": match["match_id"],
           "campaign_id": match["campaign_id"],
           "status": "pending"
       }
       ```

4. **For REJECTED match suggestions**:
   - Currently logs the rejection but doesn't update the match_suggestions table
   - Comment indicates future logic can be added here

### Step 4: Response to Frontend
The endpoint returns an `EnhancedReviewTaskResponse` with:
- Updated review task details
- Full context including media, campaign, and vetting information
- The response is built by `_build_enhanced_review_task()` helper function

## Database Changes

### When APPROVED:
1. **review_tasks table**:
   - `status` → 'approved'
   - `completed_at` → NOW()
   - `notes` → reviewer notes (if provided)

2. **match_suggestions table**:
   - `client_approved` → TRUE
   - `status` → 'approved'
   - `approved_at` → NOW()

3. **New review_tasks record created**:
   - `task_type` → 'pitch_review'
   - `related_id` → match_id
   - `campaign_id` → from match suggestion
   - `status` → 'pending'

### When REJECTED:
1. **review_tasks table**:
   - `status` → 'rejected'
   - `completed_at` → NOW()
   - `notes` → reviewer notes (if provided)

2. **match_suggestions table**:
   - No changes currently (but infrastructure exists to update)

## Next Steps After Approval

When a match is approved:
1. A `pitch_review` task is created
2. The system can now generate a pitch for this approved match
3. The pitch will need its own review process
4. Eventually, approved pitches are sent to podcasts

## Error Handling

- If review task not found: Returns 404
- If processing fails: Returns 500 with error details
- Pitch task creation failures are logged but don't block the approval

## Notes for Frontend Implementation

1. Use the `/review-tasks/{id}/approve` endpoint for accept/reject actions
2. Pass `{"status": "approved"}` for accept, `{"status": "rejected"}` for reject
3. Include optional `notes` field for reviewer comments
4. The response includes the full updated task context
5. After approval, a new pitch_review task is automatically created