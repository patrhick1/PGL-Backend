# Frontend Developer Guide: New Pitch Generation Workflow

## Overview
The pitch generation workflow has been updated to provide better UX by allowing users to manually select templates for each pitch instead of auto-generating them on match approval.

## Key Changes
1. **No Automatic Pitch Generation**: Approving a match no longer automatically generates a pitch
2. **Template Selection**: Users can choose different templates for different matches
3. **Batch Operations**: Multiple pitches can be generated at once with different templates
4. **Automatic Subject Line Generation**: Subject lines are automatically generated using the `subject_line_v1` template for all pitches

## API Endpoints

### 1. List Approved Matches Without Pitches
Get all approved matches that are ready for pitch generation.

```http
GET /match-suggestions/approved-without-pitches?campaign_id={campaign_id}
```

**Query Parameters:**
- `campaign_id` (optional): Filter by specific campaign
- `skip` (default: 0): Pagination offset
- `limit` (default: 100): Number of results

**Response:**
```json
[
  {
    "match_id": 123,
    "campaign_id": "uuid-here",
    "media_id": 456,
    "media_name": "The Business Podcast",
    "media_website": "https://example.com",
    "campaign_name": "Q1 2024 Campaign",
    "client_name": "John Doe",
    "match_score": 8.5,
    "vetting_score": 7.2,
    "status": "client_approved",
    "approved_at": "2024-01-15T10:30:00Z"
  }
]
```

### 2. List Available Pitch Templates
Get templates that can be used for pitch generation.

```http
GET /pitch-templates/
```

**Response:**
```json
[
  {
    "template_id": "generic_pitch_v1",
    "template_name": "Generic Pitch V1",
    "description": "Standard pitch template for general outreach",
    "is_active": true,
    "variables": ["client_name", "podcast_name", "talking_points"]
  },
  {
    "template_id": "friendly_intro_v1", 
    "template_name": "Friendly Introduction",
    "description": "Casual, friendly pitch for lifestyle podcasts",
    "is_active": true,
    "variables": ["client_name", "podcast_name", "shared_interests"]
  }
]
```

### 3. Generate Single Pitch
Generate a pitch for one approved match with a specific template. This automatically generates both the email body (using your specified template) and the subject line (using the system's subject_line_v1 template).

```http
POST /pitches/generate
```

**Request Body:**
```json
{
  "match_id": 123,
  "pitch_template_id": "generic_pitch_v1"
}
```

**Response (202 Accepted):**
```json
{
  "status": "success",
  "message": "Pitch generation initiated successfully",
  "pitch_gen_id": 789,
  "estimated_completion_seconds": 30,
  "subject_line_preview": "Great episode with Sarah Johnson",
  "pitch_text_preview": "Hi [Host Name], I just listened to your episode..."
}
```

**Note**: The subject line is automatically generated using the `subject_line_v1` template, which creates subject lines that feel like genuine listener feedback (e.g., "Great episode with [guest]" or "Great episode about [topic]")

### 4. Generate Multiple Pitches (Batch)
Generate pitches for multiple matches, each with its own template. Like single generation, this automatically creates both email bodies and subject lines for all pitches.

```http
POST /pitches/generate-batch
```

**Request Body:**
```json
[
  {
    "match_id": 123,
    "pitch_template_id": "generic_pitch_v1"
  },
  {
    "match_id": 124,
    "pitch_template_id": "friendly_intro_v1"
  },
  {
    "match_id": 125,
    "pitch_template_id": "generic_pitch_v1"
  }
]
```

**Response (202 Accepted):**
```json
{
  "status": "completed",
  "message": "Batch generation completed. Success: 3, Failed: 0",
  "results": {
    "successful": [
      {
        "match_id": 123,
        "pitch_gen_id": 789,
        "message": "Pitch generated successfully"
      },
      {
        "match_id": 124,
        "pitch_gen_id": 790,
        "message": "Pitch generated successfully"
      }
    ],
    "failed": []
  }
}
```

**What Gets Generated:**
- **Email Body**: Uses the template you specify (e.g., `generic_pitch_v1`, `friendly_intro_v1`)
- **Subject Line**: Always uses `subject_line_v1` template to create authentic-sounding subject lines

### 5. List Generated Pitches
View all pitches with filtering options.

```http
GET /pitches/?campaign_id={campaign_id}&pitch_state__in=draft&pitch_state__in=ready_to_send
```

**Query Parameters:**
- `campaign_id`: Filter by campaign
- `pitch_state__in`: Filter by states (can specify multiple)
  - Values: `draft`, `ready_to_send`, `sent`
- `skip`, `limit`: Pagination

**Response:**
```json
[
  {
    "pitch_id": 456,
    "campaign_id": "uuid-here",
    "media_id": 789,
    "media_name": "The Business Podcast",
    "subject_line": "Exciting Collaboration Opportunity",
    "pitch_state": "ready_to_send",
    "pitch_gen_id": 790,
    "created_at": "2024-01-15T11:00:00Z"
  }
]
```

### 6. Send Pitches to Instantly
Send approved pitches via Instantly.ai.

**Single Pitch:**
```http
POST /pitches/{pitch_id}/send
```

**Bulk Send:**
```http
POST /pitches/bulk-send
```

**Request Body (Bulk):**
```json
{
  "pitch_ids": [456, 457, 458]
}
```

## Recommended UI Flow

### 1. Match Review & Approval Page
```
┌─────────────────────────────────────────┐
│ Pending Match Reviews                   │
├─────────────────────────────────────────┤
│ □ The Business Podcast    Score: 8.5   │
│ □ Marketing Masters       Score: 7.9   │
│ □ Startup Stories         Score: 7.2   │
│                                         │
│ [Approve Selected] [Reject Selected]    │
└─────────────────────────────────────────┘
```

### 2. Pitch Generation Page
After approving matches, redirect to pitch generation:

```
┌─────────────────────────────────────────┐
│ Generate Pitches for Approved Matches   │
├─────────────────────────────────────────┤
│ Match                  Template         │
│ ─────────────────────────────────────── │
│ The Business Podcast   [Generic V1  ▼] │
│ Marketing Masters      [Friendly    ▼] │
│ Startup Stories        [Generic V1  ▼] │
│                                         │
│ [Generate All Pitches]                  │
└─────────────────────────────────────────┘
```

### 3. Pitch Review & Send Page
```
┌─────────────────────────────────────────┐
│ Ready to Send Pitches                   │
├─────────────────────────────────────────┤
│ □ The Business Podcast                  │
│   Subject: Collaboration Opportunity    │
│   [Preview] [Edit]                      │
│                                         │
│ □ Marketing Masters                     │
│   Subject: Guest Appearance Request     │
│   [Preview] [Edit]                      │
│                                         │
│ [Send Selected Pitches]                 │
└─────────────────────────────────────────┘
```

## Implementation Example (React)

```jsx
// Component to handle pitch generation
const PitchGenerationManager = ({ campaignId }) => {
  const [approvedMatches, setApprovedMatches] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplates, setSelectedTemplates] = useState({});
  
  useEffect(() => {
    // Fetch approved matches without pitches
    fetchApprovedMatches();
    // Fetch available templates
    fetchTemplates();
  }, [campaignId]);
  
  const fetchApprovedMatches = async () => {
    const response = await fetch(
      `/api/match-suggestions/approved-without-pitches?campaign_id=${campaignId}`
    );
    const data = await response.json();
    setApprovedMatches(data);
    
    // Initialize template selection with default
    const defaultSelections = {};
    data.forEach(match => {
      defaultSelections[match.match_id] = 'generic_pitch_v1';
    });
    setSelectedTemplates(defaultSelections);
  };
  
  const fetchTemplates = async () => {
    const response = await fetch('/api/pitch-templates/');
    const data = await response.json();
    setTemplates(data);
  };
  
  const generatePitches = async () => {
    const requests = approvedMatches.map(match => ({
      match_id: match.match_id,
      pitch_template_id: selectedTemplates[match.match_id]
    }));
    
    const response = await fetch('/api/pitches/generate-batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requests)
    });
    
    const result = await response.json();
    
    // Handle success/failure
    if (result.results.successful.length > 0) {
      toast.success(`Generated ${result.results.successful.length} pitches`);
      // Redirect to pitch review page
    }
    
    if (result.results.failed.length > 0) {
      toast.error(`Failed to generate ${result.results.failed.length} pitches`);
    }
  };
  
  return (
    <div>
      <h2>Generate Pitches for Approved Matches</h2>
      {approvedMatches.map(match => (
        <div key={match.match_id}>
          <span>{match.media_name}</span>
          <select 
            value={selectedTemplates[match.match_id]}
            onChange={(e) => setSelectedTemplates({
              ...selectedTemplates,
              [match.match_id]: e.target.value
            })}
          >
            {templates.map(template => (
              <option key={template.template_id} value={template.template_id}>
                {template.template_name}
              </option>
            ))}
          </select>
        </div>
      ))}
      <button onClick={generatePitches}>Generate All Pitches</button>
    </div>
  );
};
```

## WebSocket Notifications

Connect to WebSocket for real-time updates:

```javascript
const ws = new WebSocket(`ws://your-api/ws/${userId}?campaign_id=${campaignId}`);

ws.onmessage = (event) => {
  const notification = JSON.parse(event.data);
  
  switch(notification.type) {
    case 'review_ready':
      // New match ready for review
      updateMatchList();
      break;
    case 'pitch_generated':
      // Pitch generation completed
      updatePitchList();
      break;
    case 'pitch_sent':
      // Pitch sent successfully
      updateSentStatus(notification.data.pitch_id);
      break;
  }
};
```

## Error Handling

Always handle potential errors:

```javascript
try {
  const response = await fetch('/api/pitches/generate-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requests)
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to generate pitches');
  }
  
  const result = await response.json();
  // Handle result
} catch (error) {
  console.error('Pitch generation error:', error);
  toast.error(error.message);
}
```

## Best Practices

1. **Template Selection Memory**: Store user's template preferences per campaign/media type
2. **Bulk Operations**: Always prefer batch endpoints when dealing with multiple items
3. **Progress Indication**: Show loading states during pitch generation
4. **Preview Before Send**: Allow users to preview/edit pitches before sending
5. **Error Recovery**: Provide retry options for failed operations

## Migration Notes

If you have existing code that expects automatic pitch generation:

**Old Flow:**
1. Approve match → Pitch auto-generated → Review pitch → Send

**New Flow:**
1. Approve match → Select template → Generate pitch → Review pitch → Send

The main change is adding the template selection step, giving users more control over the pitch generation process.