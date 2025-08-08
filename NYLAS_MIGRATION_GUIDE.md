# Nylas Migration Guide for PGL

This guide provides a step-by-step process for migrating from Instantly to Nylas for email sending and processing in the PGL system.

## Overview

The migration allows you to:
- Send emails directly from your email account via Nylas
- Read and process replies in real-time
- Better email threading and conversation management
- More detailed tracking (opens, clicks, bounces)
- Support for multiple email accounts

## Migration Strategy

### Phase 1: Parallel Operation (Recommended)
Run both Instantly and Nylas side-by-side, migrating campaigns gradually.

### Phase 2: Full Migration
Switch completely to Nylas once comfortable with the system.

## Setup Steps

### 1. Environment Configuration

Add these environment variables to your `.env` file:

```bash
# Nylas Configuration
NYLAS_API_KEY=your_nylas_api_key
NYLAS_API_URI=https://api.us.nylas.com
NYLAS_GRANT_ID=your_grant_id
NYLAS_WEBHOOK_SECRET=your_webhook_secret

# Email Provider Settings
DEFAULT_EMAIL_PROVIDER=nylas  # or 'instantly' for gradual migration
ENABLE_DUAL_EMAIL_MODE=true    # Enable both providers
```

### 2. Database Migration

Run the database migration to add Nylas fields:

```bash
cd /mnt/c/Users/ebube/Documents/PGL\ -\ Postgres/
pgl_env/Scripts/python.exe podcast_outreach/database/migrations/add_nylas_fields.py
```

This adds:
- `nylas_grant_id` to campaigns and people tables
- `nylas_message_id`, `nylas_thread_id` to pitches table
- New tracking fields for opens, clicks, bounces
- Email sync status tracking tables

### 3. Nylas Account Setup

1. **Create Nylas Application**:
   - Go to https://dashboard.nylas.com
   - Create a new application
   - Note your Client ID and Client Secret

2. **Authenticate Email Account**:
   - Use Nylas Hosted Authentication or build your own flow
   - Get the Grant ID for your email account
   - Store the Grant ID in your environment variables

3. **Configure Webhooks**:
   - In Nylas Dashboard, add webhook endpoint: `https://your-domain.com/webhooks/nylas/events`
   - Select events: message.sent, message.opened, message.replied, message.bounced
   - Note the webhook secret for signature verification

### 4. Update Application Code

1. **Import new routers** in your main FastAPI app:

```python
# In your main.py or app.py
from podcast_outreach.api.routers import nylas_webhooks

# Add the router
app.include_router(nylas_webhooks.router)
```

2. **Update pitch sender** to use the new service:

```python
# Replace old import
# from podcast_outreach.services.pitches.sender import PitchSenderService

# With new import
from podcast_outreach.services.pitches.sender_v2 import PitchSenderServiceV2 as PitchSenderService
```

### 5. Campaign Migration

For existing campaigns using Instantly:

```python
# Add Nylas grant ID to a campaign
UPDATE campaigns 
SET nylas_grant_id = 'your_grant_id',
    email_provider = 'nylas'
WHERE campaign_id = 'campaign_uuid';
```

### 6. Start Email Monitor

Run the email monitor to process incoming replies:

```python
# Create a script to run the monitor
import asyncio
from podcast_outreach.services.email.monitor import NylasEmailMonitor

async def main():
    monitor = NylasEmailMonitor(check_interval=30)
    await monitor.run_continuous()

if __name__ == "__main__":
    asyncio.run(main())
```

## Testing the Integration

### 1. Test Nylas Connection

```python
from podcast_outreach.integrations.nylas import NylasAPIClient

client = NylasAPIClient()
if client.test_connection():
    print("Nylas connection successful!")
```

### 2. Test Email Sending

```python
# Send a test pitch using Nylas
result = await pitch_sender_service.send_pitch(pitch_gen_id)
print(f"Send result: {result}")
```

### 3. Test Webhook Reception

Send a test email and verify webhooks are received:
- Check logs for webhook processing
- Verify pitch states are updated
- Confirm placement records are created for replies

## Gradual Migration Process

### Step 1: Enable Dual Mode
Keep Instantly as default, test Nylas with specific campaigns:

```python
# Update specific campaign to use Nylas
UPDATE campaigns 
SET email_provider = 'nylas',
    nylas_grant_id = 'your_grant_id'
WHERE campaign_id = 'test_campaign_id';
```

### Step 2: Monitor Performance
- Compare delivery rates
- Check reply detection accuracy
- Monitor webhook reliability

### Step 3: Migrate More Campaigns
Gradually move campaigns to Nylas:

```python
# Bulk update campaigns
UPDATE campaigns 
SET email_provider = 'nylas',
    nylas_grant_id = 'your_grant_id'
WHERE created_at > '2024-01-01'
AND instantly_campaign_id IS NOT NULL;
```

### Step 4: Switch Default Provider
Once confident, make Nylas the default:

```bash
DEFAULT_EMAIL_PROVIDER=nylas
```

## Rollback Process

If issues arise, you can rollback:

### 1. Switch Provider Back
```python
UPDATE campaigns 
SET email_provider = 'instantly'
WHERE email_provider = 'nylas';
```

### 2. Revert Environment
```bash
DEFAULT_EMAIL_PROVIDER=instantly
```

### 3. Database Rollback (if needed)
```bash
pgl_env/Scripts/python.exe podcast_outreach/database/migrations/add_nylas_fields.py rollback
```

## Monitoring and Maintenance

### 1. Email Sync Status
Monitor the email sync status:

```sql
SELECT * FROM email_sync_status 
ORDER BY last_sync_timestamp DESC;
```

### 2. Processing Metrics
Check processed emails:

```sql
SELECT 
    processing_type,
    COUNT(*) as count,
    DATE(processed_at) as date
FROM processed_emails
GROUP BY processing_type, DATE(processed_at)
ORDER BY date DESC;
```

### 3. Error Monitoring
Watch for errors in logs:
- Nylas API errors
- Webhook processing failures
- Email monitor issues

## Best Practices

1. **Grant Management**: Use separate grants for different email accounts
2. **Rate Limits**: Respect Nylas API rate limits (varies by plan)
3. **Webhook Security**: Always verify webhook signatures
4. **Error Handling**: Implement retry logic for transient failures
5. **Monitoring**: Set up alerts for failed sends or processing errors

## Troubleshooting

### Common Issues

1. **Authentication Errors**
   - Verify Grant ID is correct
   - Check if grant has proper scopes
   - Ensure API key is valid

2. **Webhook Not Receiving**
   - Verify webhook URL is publicly accessible
   - Check webhook secret matches
   - Ensure events are selected in Nylas dashboard

3. **Emails Not Sending**
   - Check grant has send permissions
   - Verify recipient email is valid
   - Check for API errors in logs

### Debug Mode

Enable detailed logging:

```python
import logging
logging.getLogger('podcast_outreach.integrations.nylas').setLevel(logging.DEBUG)
logging.getLogger('podcast_outreach.services.email').setLevel(logging.DEBUG)
```

## Support

For issues or questions:
1. Check Nylas API documentation: https://developer.nylas.com/docs/
2. Review application logs
3. Test with Nylas API directly using their SDK

## Next Steps

After successful migration:
1. Implement advanced features (scheduling, templates)
2. Add multi-account support
3. Build email analytics dashboard
4. Integrate calendar for meeting scheduling