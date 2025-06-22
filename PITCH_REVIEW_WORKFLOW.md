# Pitch Review Workflow with Editing

## Overview
This document describes the complete workflow for reviewing and editing pitch emails before approval in the PGL system.

## API Endpoints

### 1. Get Pending Pitch Reviews
```http
GET /review-tasks/enhanced?task_type=pitch_review&status=pending
```

**Response includes:**
- `pitch_gen_id` - ID for the pitch generation (used for editing)
- `pitch_subject_line` - Current email subject line
- `pitch_body_full` - **Complete pitch email body** (not just preview)
- `pitch_template_used` - Template ID used
- `media_name`, `host_names` - Podcast information
- `campaign_name`, `client_name` - Campaign context

### 2. Edit Pitch Content
```http
PATCH /pitches/generations/{pitch_gen_id}/content
```

**Request Body:**
```json
{
  "draft_text": "Updated full email body text...",
  "new_subject_line": "Updated subject line"
}
```

**Notes:**
- Both fields are optional - you can update just the body or just the subject
- Returns the updated pitch generation data

### 3. Approve/Reject Pitch
```http
POST /review-tasks/{review_task_id}/approve
```

**Request Body:**
```json
{
  "status": "approved",  // or "rejected"
  "notes": "Looks good after edits"
}
```

## Frontend Implementation Flow

### 1. List View
```javascript
// Fetch all pending pitch reviews
const response = await fetch('/review-tasks/enhanced?task_type=pitch_review&status=pending');
const reviews = await response.json();

// Display list showing:
// - Podcast name
// - Campaign/Client name
// - Generated date
// - Subject line preview
```

### 2. Detail/Edit View
When user clicks on a pitch to review:

```javascript
// The review task already contains the full pitch body
const reviewTask = reviews[selectedIndex];

// Display in editor:
const editorState = {
  pitchGenId: reviewTask.pitch_gen_id,
  reviewTaskId: reviewTask.review_task_id,
  subject: reviewTask.pitch_subject_line,
  body: reviewTask.pitch_body_full,  // Full email body
  originalSubject: reviewTask.pitch_subject_line,
  originalBody: reviewTask.pitch_body_full
};

// Show podcast context:
// - Podcast: reviewTask.media_name
// - Hosts: reviewTask.host_names.join(', ')
// - Client: reviewTask.client_name
// - Campaign: reviewTask.campaign_name
```

### 3. Save Edits
When user makes changes:

```javascript
async function savePitchEdits(pitchGenId, updates) {
  const response = await fetch(`/pitches/generations/${pitchGenId}/content`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      draft_text: updates.body,
      new_subject_line: updates.subject
    })
  });
  
  return await response.json();
}
```

### 4. Approve/Reject
After editing (or without editing):

```javascript
async function approvePitch(reviewTaskId, approved = true) {
  const response = await fetch(`/review-tasks/${reviewTaskId}/approve`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
      status: approved ? 'approved' : 'rejected',
      notes: 'Reviewed and edited'
    })
  });
  
  return await response.json();
}
```

## UI/UX Recommendations

### Editor Features
1. **Rich Text Editor** for the email body
   - Basic formatting (bold, italic, links)
   - Preserve line breaks and paragraphs
   
2. **Subject Line Input** 
   - Character count indicator
   - Preview how it looks in email client

3. **Side Panel** showing:
   - Podcast details
   - Host information
   - Campaign context
   - Original vs. edited indicator

4. **Action Buttons**:
   - "Save Draft" - Saves edits without approving
   - "Approve & Send" - Saves edits and approves
   - "Reject" - With required reason field
   - "Reset to Original" - Discards all edits

### Workflow States
1. **Unedited**: Show original generated content
2. **Edited**: Highlight that changes were made
3. **Saving**: Disable buttons during API calls
4. **Approved**: Move to approved list
5. **Rejected**: Archive with reason

## Complete Example Flow

```javascript
// 1. Component State
const [reviews, setReviews] = useState([]);
const [selectedReview, setSelectedReview] = useState(null);
const [editedContent, setEditedContent] = useState({ subject: '', body: '' });
const [hasChanges, setHasChanges] = useState(false);

// 2. Load Reviews
useEffect(() => {
  loadPendingReviews();
}, []);

async function loadPendingReviews() {
  const response = await fetch('/review-tasks/enhanced?task_type=pitch_review&status=pending');
  const data = await response.json();
  setReviews(data);
}

// 3. Select Review for Editing
function selectReview(review) {
  setSelectedReview(review);
  setEditedContent({
    subject: review.pitch_subject_line,
    body: review.pitch_body_full
  });
  setHasChanges(false);
}

// 4. Handle Edits
function updateContent(field, value) {
  setEditedContent(prev => ({ ...prev, [field]: value }));
  setHasChanges(true);
}

// 5. Save and Approve
async function saveAndApprove() {
  try {
    // Save edits if any changes were made
    if (hasChanges) {
      await savePitchEdits(selectedReview.pitch_gen_id, editedContent);
    }
    
    // Approve the review task
    await approvePitch(selectedReview.review_task_id, true);
    
    // Refresh list and clear selection
    await loadPendingReviews();
    setSelectedReview(null);
    
    showNotification('Pitch approved successfully!');
  } catch (error) {
    showError('Failed to save/approve pitch: ' + error.message);
  }
}
```

## Error Handling

1. **Network Errors**: Show retry button
2. **Validation Errors**: 
   - Empty subject line
   - Empty body
   - Body too long (>10,000 chars)
3. **Permission Errors**: Only staff/admin can edit
4. **Concurrent Edit Warning**: If another user edited while you were editing

## Performance Considerations

1. **Auto-save**: Consider auto-saving drafts every 30 seconds
2. **Debounce**: Debounce edit tracking to avoid too many state updates
3. **Loading States**: Show skeleton screens while loading
4. **Pagination**: If many reviews, implement pagination or infinite scroll