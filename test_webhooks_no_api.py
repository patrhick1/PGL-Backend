#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Test Instantly webhooks without needing API key
Just simulates the webhook payloads that Instantly would send
"""

import requests
import json
from datetime import datetime
import uuid

# Your test data
NGROK_URL = "https://b8eb-198-252-15-187.ngrok-free.app"
LOCAL_URL = "http://localhost:8000"
TEST_EMAIL = "paschal@3rdbrain.co"
INSTANTLY_CAMPAIGN_ID = "5e4230db-d7df-4bfa-8e2b-b4f4d524f0f2"
PGL_CAMPAIGN_ID = "cdc33aee-b0f8-4460-beec-cce66ea3772c"

# Generate a fake lead ID for testing
TEST_LEAD_ID = f"lead_{uuid.uuid4().hex[:12]}"

def test_webhooks_locally():
    """Test webhooks against localhost"""
    print("\n" + "="*60)
    print("Testing Webhooks Locally (No API Key Needed)")
    print("="*60)
    print(f"Lead ID: {TEST_LEAD_ID}")
    print(f"Email: {TEST_EMAIL}")
    print("="*60)
    
    # 1. Simulate Email Sent
    print("\n1. Testing Email Sent Webhook...")
    email_sent_payload = {
        "event": "email_sent",
        "timestamp": datetime.utcnow().isoformat(),
        "lead_id": TEST_LEAD_ID,
        "campaign_id": INSTANTLY_CAMPAIGN_ID,
        "workspace_id": "ws_test_123",
        "data": {
            "id": TEST_LEAD_ID,
            "email": TEST_EMAIL,
            "first_name": "Paschal",
            "last_name": "",
            "company_name": "3rd Brain Podcast",
            "personalization": """Hi Paschal,

I noticed you host the 3rd Brain Podcast focusing on AI and technology. 

We work with an AI startup founder who has fascinating insights on building AI-powered solutions for enterprise. They've recently raised $5M and have some compelling stories about the challenges of scaling AI products.

Would you be interested in having them as a guest on your show?

Best regards,
Sarah from Podcast Guest Logistics""",
            "custom_variables": {
                "Client_Name": "AI Startup Founder",
                "Subject": "AI Founder Guest Opportunity for 3rd Brain Podcast",
                "pitch_gen_id": "123",
                "campaign_id": PGL_CAMPAIGN_ID,
                "media_id": "456"
            }
        },
        # Fields for Attio integration
        "airID": "attio_test_record_123",
        "lead": {
            "email": TEST_EMAIL,
            "first_name": "Paschal"
        }
    }
    
    try:
        response = requests.post(
            f"{LOCAL_URL}/api/webhooks/instantly-email-sent",
            json=email_sent_payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")
    
    input("\nPress Enter to simulate reply...")
    
    # 2. Simulate Reply
    print("\n2. Testing Reply Received Webhook...")
    reply_payload = {
        "event": "email_replied",
        "timestamp": datetime.utcnow().isoformat(),
        "lead_id": TEST_LEAD_ID,
        "campaign_id": INSTANTLY_CAMPAIGN_ID,
        "workspace_id": "ws_test_123",
        "data": {
            "id": TEST_LEAD_ID,
            "email": TEST_EMAIL,
            "first_name": "Paschal",
            "replied": True,
            "reply_timestamp": datetime.utcnow().isoformat()
        },
        "reply": {
            "from": TEST_EMAIL,
            "subject": "Re: AI Founder Guest Opportunity for 3rd Brain Podcast",
            "body_text": """Hi Sarah,

Thanks for reaching out! This sounds really interesting.

I'd love to learn more about your client. Could you share:
- What specific area of AI are they working in?
- What kind of enterprise problems are they solving?
- Any notable customers or case studies they can discuss?

Also, are they available for a remote recording in the next few weeks?

Best,
Paschal""",
            "received_at": datetime.utcnow().isoformat()
        },
        # Fields for Attio
        "airID": "attio_test_record_123",
        "reply_text_snippet": "Thanks for reaching out! This sounds really interesting...",
        "lead": {
            "email": TEST_EMAIL,
            "first_name": "Paschal"
        }
    }
    
    try:
        response = requests.post(
            f"{LOCAL_URL}/api/webhooks/instantly-reply-received",
            json=reply_payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Error: {e}")

def show_webhook_urls():
    """Display the webhook URLs for Instantly configuration"""
    print("\n" + "="*60)
    print("Webhook URLs for Instantly")
    print("="*60)
    print("\nWhen you're ready to use real Instantly webhooks, configure these:")
    print(f"\nEmail Sent Webhook:")
    print(f"{NGROK_URL}/api/webhooks/instantly-email-sent")
    print(f"\nReply Received Webhook:")
    print(f"{NGROK_URL}/api/webhooks/instantly-reply-received")
    print("\nThese will forward real Instantly events to your local server")
    print("="*60)

def main():
    print("Instantly Webhook Tester (No API Key Required)")
    print("="*60)
    print("This tests your webhook handlers without sending real emails")
    print("="*60)
    
    print("\nWhat would you like to do?")
    print("1. Test webhooks locally")
    print("2. Show webhook URLs for Instantly")
    print("3. Both")
    
    choice = input("\nEnter choice (1-3): ")
    
    if choice in ["1", "3"]:
        test_webhooks_locally()
    
    if choice in ["2", "3"]:
        show_webhook_urls()
    
    print("\n" + "="*60)
    print("Testing Complete!")
    print("Check your FastAPI logs to see how the webhooks were processed")
    print("="*60)

if __name__ == "__main__":
    main()