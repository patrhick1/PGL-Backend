# Instantly Pitch Sending Workflow

## What Happens When a Pitch is Sent to Instantly

### 1. Initial Send Process (POST /pitches/{pitch_id}/send)

When you send a pitch to Instantly, the following steps occur:

1. **Validation**:
   - Verifies the pitch exists
   - Checks if pitch_gen_id is linked
   - Confirms pitch generation is marked as `send_ready_bool = true`

2. **Data Preparation**:
   - Retrieves campaign data (including `instantly_campaign_id`)
   - Gets media/podcast contact email
   - Prepares Instantly API payload with:
     - Campaign ID (from `campaigns.instantly_campaign_id`)
     - Recipient email
     - Pitch body (from `pitch_generations.final_text` or `draft_text`)
     - Subject line (from `pitches.subject_line`)
     - Custom variables (client name, pitch_gen_id, campaign_id, media_id)

3. **Instantly API Call**:
   - Calls `instantly_client.add_lead_v2()` to create lead in Instantly
   - Receives back an Instantly lead ID

4. **Database Update**:
   ```sql
   UPDATE pitches SET
     send_ts = NOW(),
     pitch_state = 'sent',
     instantly_lead_id = 'da5f91c1-f2c3-4e46-b1ac-92d4ab2c9923'
   WHERE pitch_id = 3;
   ```

### 2. Tracking Pitch States

The system tracks various pitch states in the `pitches.pitch_state` field:

- **draft**: Initial state when pitch is generated
- **ready_to_send**: After pitch review approval
- **sent**: After successful send to Instantly
- **opened**: When recipient opens the email (via webhook)
- **clicked**: When recipient clicks a link (via webhook)
- **replied**: When recipient replies (via webhook)
- **replied_interested**: When reply indicates interest
- **live**: When placement is confirmed
- **paid**: When payment is received
- **lost**: When opportunity is lost

### 3. Viewing Sent Pitches

#### List All Sent Pitches
```http
GET /pitches/?pitch_state__in=sent
```

#### List Multiple States
```http
GET /pitches/?pitch_state__in=sent&pitch_state__in=opened&pitch_state__in=replied
```

From your logs, the frontend uses:
```http
GET /pitches/?pitch_state__in=sent,opened,replied,clicked,replied_interested,live,paid,lost
```

#### Response Includes:
- Pitch details (subject, body snippet)
- Campaign and media information
- Instantly lead ID
- Send timestamp
- Current state

### 4. Webhook Integration

The system has a `record_response()` method in PitchSenderService that handles Instantly webhooks:

```python
# When email is opened
await record_response(instantly_lead_id, 'opened', timestamp)

# When email gets a reply
await record_response(instantly_lead_id, 'replied', timestamp)

# When link is clicked
await record_response(instantly_lead_id, 'clicked', timestamp)
```

These webhooks update the pitch state automatically.

## Placements Table

### When Are Placements Created?

Placements are **NOT automatically created** when pitches are sent. They represent confirmed podcast bookings and are created manually when:

1. **Interest is Confirmed**: After a positive reply (`replied_interested` state)
2. **Booking is Scheduled**: When a podcast agrees to have the guest
3. **Manual Creation**: Via POST /placements/ endpoint (staff/admin only)

### Placement Fields:
- `pitch_id`: Links to the pitch that resulted in this placement
- `current_status`: Booking status (scheduled, recorded, live, etc.)
- `meeting_date`: Initial meeting/call date
- `recording_date`: When podcast will be/was recorded
- `go_live_date`: When episode will air
- `episode_link`: Final podcast episode URL

### Placement Workflow:
1. Pitch sent → replied_interested
2. Staff creates placement record
3. Track through various stages (scheduled → recorded → live)
4. Update with episode link when published

## Key Integration Points

1. **Campaign Setup**: Must have `instantly_campaign_id` set
2. **Media Records**: Must have valid `contact_email`
3. **Pitch Generation**: Must be marked as `send_ready_bool`
4. **Webhooks**: Should be configured in Instantly to update pitch states

## API Endpoints Summary

### Sending Pitches
- `POST /pitches/{pitch_id}/send` - Send single pitch
- `POST /pitches/bulk-send` - Send multiple pitches

### Viewing Pitches
- `GET /pitches/?pitch_state__in=sent` - View sent pitches
- `GET /pitches/?pitch_state__in=ready_to_send` - View pitches ready to send

### Managing Placements
- `POST /placements/` - Create placement (staff only)
- `GET /placements/` - List placements
- `PUT /placements/{placement_id}` - Update placement status