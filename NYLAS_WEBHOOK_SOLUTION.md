# Nylas Webhook Setup Solution

## Problem
Nylas blocks ngrok URLs for webhook creation with error: `"unable.verify.webhook_url : ngrok is not allowed"`

## Root Cause
Nylas has explicitly blocked ngrok domains for security reasons. This is a policy restriction, not a technical issue with your webhook implementation.

## Your Webhook Implementation Status
✅ **Your webhook code is correctly implemented:**
- `/webhooks/nylas/events` GET endpoint handles challenge correctly (lines 66-77 in nylas_webhooks.py)
- Returns raw challenge value with `PlainTextResponse`
- POST endpoint handles v3 CloudEvents format
- Signature verification is implemented

## Solutions

### Option 1: Cloudflare Tunnel (Recommended)
Free, reliable, and accepted by Nylas.

```bash
# Install on Windows
winget install --id Cloudflare.cloudflared

# Or download from: https://github.com/cloudflare/cloudflared/releases

# Login to Cloudflare (opens browser)
cloudflared tunnel login

# Create a tunnel
cloudflared tunnel create pgl-webhook

# Run the tunnel (replace 8000 with your FastAPI port)
cloudflared tunnel --url http://localhost:8000 run pgl-webhook

# You'll get a URL like: https://pgl-webhook.username.cloudflared.com
# Use this URL in Nylas: https://pgl-webhook.username.cloudflared.com/webhooks/nylas/events
```

### Option 2: Localtunnel
Simple npm-based solution.

```bash
# Install
npm install -g localtunnel

# Run (replace 8000 with your FastAPI port)
lt --port 8000 --subdomain pgl-webhook

# You'll get: https://pgl-webhook.loca.lt
# Use in Nylas: https://pgl-webhook.loca.lt/webhooks/nylas/events
```

### Option 3: Serveo (SSH-based)
No installation required.

```bash
# Run SSH tunnel
ssh -R 80:localhost:8000 serveo.net

# You'll get a URL like: https://xxxxx.serveo.net
# Use in Nylas: https://xxxxx.serveo.net/webhooks/nylas/events
```

### Option 4: Deploy to Staging
Deploy your webhook handler to a cloud service:
- Railway.app (easy deployment)
- Render.com (free tier available)
- Fly.io
- Heroku
- AWS Lambda with API Gateway

## Testing Your Webhook

### 1. Test Challenge Response Locally
```bash
cd "/mnt/c/Users/ebube/Documents/PGL - Postgres"
./pgl_env/Scripts/python.exe test_webhook_challenge.py
```

### 2. Create Webhook via API
After setting up a tunnel service, update the webhook URL in `test_webhook_creation.py`:

```python
# Line 24 in test_webhook_creation.py
"webhook_url": "https://your-tunnel-url.cloudflared.com/webhooks/nylas/events",
```

Then run:
```bash
./pgl_env/Scripts/python.exe test_webhook_creation.py
```

### 3. Create Webhook via Dashboard
1. Go to Nylas Dashboard: https://dashboard.nylas.com
2. Navigate to Webhooks section
3. Click "Create Webhook"
4. Enter:
   - URL: `https://your-tunnel-url/webhooks/nylas/events`
   - Description: "Email event notifications"
   - Triggers: Select the events you want (message.created, thread.replied, etc.)
5. Click "Create"

## Important Configuration

### Environment Variables
After successful webhook creation, save the webhook secret:

```bash
# Add to your .env file
NYLAS_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxx
```

### Webhook Events to Subscribe To
For your use case, subscribe to these v3 events:
- `message.created` - New messages (including sent messages)
- `message.updated` - Message changes
- `thread.replied` - Thread replies (requires tracking enabled)
- `message.opened` - Email opened (requires tracking)
- `message.link_clicked` - Link clicked (requires tracking)
- `message.bounce_detected` - Bounce detection

## Troubleshooting

### If webhook creation still fails:
1. **Verify your app is running:** `curl http://localhost:8000/webhooks/nylas/health`
2. **Check tunnel is working:** Visit your tunnel URL in a browser
3. **Test challenge manually:** 
   ```bash
   curl "https://your-tunnel-url/webhooks/nylas/events?challenge=test123"
   # Should return: test123
   ```
4. **Check ngrok alternative is not blocked:** Some free tier services might also be blocked

### Common Issues:
- **Challenge response has quotes:** Make sure using `PlainTextResponse` not `JSONResponse`
- **Auth middleware blocking GET:** Ensure GET /events has no auth requirements
- **Timeout:** Nylas requires response within 10 seconds
- **Wrong region:** Make sure using correct API region (US: api.us.nylas.com, EU: api.eu.nylas.com)

## Next Steps
1. Choose a tunneling solution (Cloudflare Tunnel recommended)
2. Set up the tunnel
3. Update webhook URL in test script
4. Run webhook creation test
5. Save webhook secret to .env file
6. Test webhook events

## Contact
If issues persist after trying alternatives, contact Nylas support with your specific use case.