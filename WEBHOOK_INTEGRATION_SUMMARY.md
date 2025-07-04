# Instantly Webhook Integration Summary

## Overview
The webhook integration is fully set up to track pitch states and create placement records when replies are received.

## Webhook Endpoints

### 1. Email Sent Webhook
- **URL**: `https://your-ngrok-url.app/webhooks/instantly-email-sent`
- **Purpose**: Updates pitch state to 'sent' when email is delivered

### 2. Reply Received Webhook  
- **URL**: `https://your-ngrok-url.app/webhooks/instantly-reply-received`
- **Purpose**: Updates pitch state to 'replied' and creates placement record

## Actual Webhook Data Structures

### Email Sent Webhook
```json
{
    "timestamp": "2025-07-02T16:07:47.353Z",
    "event_type": "email_sent",
    "workspace": "0462b242-8088-4dac-a640-453777ba421f",
    "campaign_id": "cdc33aee-b0f8-4460-beec-cce66ea3772c",  // PGL Campaign ID
    "campaign": "5e4230db-d7df-4bfa-8e2b-b4f4d524f0f2",      // Instantly Campaign ID
    "campaign_name": "TEST Campaign",
    "email_account": "aidrian@digitalpodcastguest.com",
    "email": "ebube4u@gmail.com",
    "lead_email": "ebube4u@gmail.com",
    "pitch_gen_id": "test_pitch_gen_123",  // KEY FIELD - links to pitch_generations
    "media_id": "test_media_456",          // KEY FIELD - links to media
    "firstName": "Ebube",
    "lastName": "",
    "companyName": "Test Podcast",
    "Subject": "Test Email - PGL Webhook Integration",
    "email_subject": "Test Email - PGL Webhook Integration",
    "email_html": "<div>Email HTML content...</div>",
    "personalization": "Email body text...",
    "Client_Name": "Test Client",
    "is_first": true,
    "step": 1,
    "variant": 1
}
```

### Reply Received Webhook
```json
{
    "timestamp": "2025-07-02T16:16:43.428Z",
    "event_type": "reply_received",
    "workspace": "0462b242-8088-4dac-a640-453777ba421f",
    "campaign_id": "cdc33aee-b0f8-4460-beec-cce66ea3772c",  // PGL Campaign ID
    "campaign": "5e4230db-d7df-4bfa-8e2b-b4f4d524f0f2",      // Instantly Campaign ID
    "campaign_name": "TEST Campaign",
    "email": "ebube4u@gmail.com",
    "lead_email": "ebube4u@gmail.com",
    "pitch_gen_id": "test_pitch_gen_123",  // KEY FIELD - links to find pitch
    "media_id": "test_media_456",          // KEY FIELD - for placement
    "reply_text_snippet": "Okay rest is working\nThis is Ebube responding",
    "reply_text": "Full reply text with quoted history...",
    "reply_html": "<div>HTML formatted reply...</div>",
    "reply_subject": "Re: Test Email - PGL Webhook Integration",
    "email_id": "0197cbed-0bed-7e1f-a3c9-608aca600b4f",
    "is_first": true,
    "unibox_url": "https://app.instantly.ai/app/unibox?thread_search=..."
}
```

## Database Flow

### When Email is Sent:
1. Webhook receives `pitch_gen_id`
2. Finds pitch record: `SELECT * FROM pitches WHERE pitch_gen_id = ?`
3. Updates pitch:
   ```sql
   UPDATE pitches 
   SET pitch_state = 'sent', 
       send_ts = NOW() 
   WHERE pitch_id = ?
   ```

### When Reply is Received:
1. Webhook receives `pitch_gen_id`
2. Finds pitch record using same query
3. Updates pitch:
   ```sql
   UPDATE pitches 
   SET pitch_state = 'replied',
       reply_bool = true,
       reply_ts = NOW()
   WHERE pitch_id = ?
   ```
4. Creates placement:
   ```sql
   INSERT INTO placements (
       campaign_id, media_id, pitch_id,
       current_status, status_ts, notes
   ) VALUES (?, ?, ?, 'initial_reply', NOW(), ?)
   ```
5. Updates pitch with placement_id

## Testing Instructions

### With Test Data:
1. The test webhooks have been successfully received
2. No database updates occurred because `pitch_gen_id = "test_pitch_gen_123"` doesn't exist

### With Real Data:
1. Create a pitch through the UI
2. Send it via Instantly (it will have a real pitch_gen_id)
3. When email is sent, webhook updates pitch state
4. When recipient replies, webhook creates placement for booking tracking

## Configuration in Instantly

Go to your Instantly campaign settings and add:
- **Email Sent**: `https://your-ngrok-url.app/webhooks/instantly-email-sent`
- **Reply Received**: `https://your-ngrok-url.app/webhooks/instantly-reply-received`

## Important Notes

1. The `pitch_gen_id` is the key linking field - it must be included in the Instantly lead custom variables
2. The webhook handlers also attempt to update Attio but won't fail if Attio update fails
3. Placement records track the booking conversation after a reply is received
4. The webhook URLs do NOT include `/api/` prefix - they're directly under `/webhooks/`