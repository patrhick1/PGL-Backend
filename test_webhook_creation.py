#!/usr/bin/env python
"""Test Nylas webhook creation via API to diagnose issues."""

import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

NYLAS_API_KEY = os.getenv('NYLAS_API_KEY')
NYLAS_API_URI = os.getenv('NYLAS_API_URI', 'https://api.us.nylas.com')

def create_webhook():
    """Create a webhook via Nylas API v3."""
    
    url = f"{NYLAS_API_URI}/v3/webhooks"
    headers = {
        "Authorization": f"Bearer {NYLAS_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "description": "Dev tunnel webhook",
        "webhook_url": "https://dbd28b6376ac.ngrok-free.app/webhooks/nylas/events",
        "triggers": ["message.created"],
        "notification_channels": ["event"]
    }
    
    print(f"Creating webhook at: {url}")
    print(f"Webhook URL: {payload['webhook_url']}")
    print(f"Triggers: {payload['triggers']}")
    print("-" * 50)
    
    response = requests.post(url, json=payload, headers=headers)
    
    print(f"Status Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print("-" * 50)
    
    try:
        response_data = response.json()
        print("Response Body:")
        print(json.dumps(response_data, indent=2))
    except:
        print("Response Text:")
        print(response.text)
    
    if response.status_code == 200:
        print("\nWebhook created successfully!")
        if 'data' in response_data:
            print(f"Webhook ID: {response_data['data'].get('id')}")
            print(f"Webhook Secret: {response_data['data'].get('webhook_secret')}")
    else:
        print("\nFailed to create webhook")
        
        # Check for specific error messages
        if response_data and 'error' in response_data:
            error_msg = response_data['error'].get('message', '')
            error_type = response_data['error'].get('type', '')
            
            if 'ngrok is not allowed' in error_msg:
                print("\n*** NGROK IS BLOCKED BY NYLAS ***")
                print("\nNylas does not allow ngrok URLs for webhooks.")
                print("\nAlternative solutions:")
                print("1. Use a different tunneling service:")
                print("   - Cloudflare Tunnel (recommended - free and reliable)")
                print("   - localtunnel (npm install -g localtunnel)")
                print("   - Serveo (ssh -R 80:localhost:8000 serveo.net)")
                print("   - PageKite")
                print("   - Tailscale Funnel")
                print("\n2. Deploy to a staging environment:")
                print("   - Deploy your webhook handler to a cloud service")
                print("   - Use services like Railway, Render, or Fly.io for quick deployments")
                print("\n3. Use a static webhook forwarding service:")
                print("   - webhook.site (for testing)")
                print("   - RequestBin")
                print("\n4. Setup Cloudflare Tunnel (recommended):")
                print("   a. Install: winget install --id Cloudflare.cloudflared")
                print("   b. Login: cloudflared tunnel login")
                print("   c. Create tunnel: cloudflared tunnel create pgl-webhook")
                print("   d. Run: cloudflared tunnel --url http://localhost:8000 run pgl-webhook")
                print("   e. Use the provided URL in Nylas dashboard")
            elif response.status_code == 400:
                print("\nPossible issues:")
                print("1. Nylas cannot reach the webhook URL")
                print("2. The webhook URL is not responding to the challenge")
                print("3. The response to the challenge is incorrect")
                print("\nTo debug:")
                print("1. Ensure your tunnel service is running and accessible")
                print("2. Verify the FastAPI app is running")
                print("3. Check that /webhooks/nylas/events endpoint responds to GET with challenge parameter")

if __name__ == "__main__":
    create_webhook()