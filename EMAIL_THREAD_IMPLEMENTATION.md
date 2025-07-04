# Email Thread Implementation for Placements

## Overview
Added email thread tracking to the placements table to store the full email conversation history between the podcast outreach team and podcast hosts.

## Database Changes

### 1. Schema Update
Added `email_thread JSONB DEFAULT '[]'::jsonb` column to the placements table.

### 2. Migration Script
Run the migration to add the column to existing database:
```bash
pgl_env/Scripts/python.exe podcast_outreach/migrations/add_email_thread_to_placements.py
```

## Email Thread Structure

Each message in the thread is a JSON object with:
```json
{
    "timestamp": "2025-07-02T16:16:43.428Z",
    "direction": "sent" | "received",
    "from": "sender@email.com",
    "to": "recipient@email.com", 
    "subject": "Email subject line",
    "body_text": "Plain text email body",
    "body_html": "<div>HTML email body</div>",
    "message_id": "unique-email-id",
    "instantly_data": {
        // Original webhook data from Instantly
    }
}
```

## Webhook Integration

### Email Sent Webhook
- No change needed - pitches are sent before placement exists

### Reply Received Webhook
When a reply is received:
1. Updates pitch state to 'replied'
2. Creates placement record with initial email thread containing:
   - The original sent pitch (if available)
   - The reply just received

## Subsequent Replies

For ongoing conversations, use the helper functions:

```python
from podcast_outreach.database.queries.placement_thread_updates import (
    append_to_email_thread,
    update_thread_for_subsequent_reply,
    update_thread_for_sent_email
)

# When host replies again
await update_thread_for_subsequent_reply(webhook_data, placement_id)

# When we send a follow-up
await update_thread_for_sent_email(webhook_data, placement_id)
```

## Viewing Email Threads

To retrieve the conversation history:
```python
# Get full placement with thread
placement = await get_placement_by_id(placement_id)
email_thread = placement['email_thread']

# Or just the thread
from podcast_outreach.database.queries.placement_thread_updates import get_email_thread
thread = await get_email_thread(placement_id)
```

## Benefits

1. **Complete History**: Full email conversation stored in one place
2. **Context**: Team can see entire conversation when managing bookings
3. **Searchable**: JSONB allows querying specific messages
4. **Flexible**: Can store any email metadata from Instantly

## Next Steps

1. Update UI to display email threads in placement details
2. Add webhook handler for subsequent replies to append to thread
3. Consider adding email composition UI to send replies from within the app