#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Monitor and simulate Instantly webhook responses
"""

import json
import requests
from datetime import datetime
import time

# Load the test lead info if it exists
try:
    with open('test_lead_info.json', 'r') as f:
        lead_info = json.load(f)
        LEAD_ID = lead_info.get('lead_id', 'test_lead_123')
        print(f"Loaded lead ID from previous test: {LEAD_ID}")
except:
    LEAD_ID = input("Enter the Instantly lead ID (or press Enter for test ID): ") or "test_lead_123"

BASE_URL = "http://localhost:8000"
INSTANTLY_CAMPAIGN_ID = "5e4230db-d7df-4bfa-8e2b-b4f4d524f0f2"
TEST_EMAIL = "paschal@3rdbrain.co"

def simulate_email_sent():
    """Simulate email sent webhook"""
    print("\n" + "="*60)
    print("Simulating Email Sent Webhook")
    print("="*60)
    
    payload = {
        "event": "email_sent",
        "timestamp": datetime.utcnow().isoformat(),
        "lead_id": LEAD_ID,
        "campaign_id": INSTANTLY_CAMPAIGN_ID,
        "workspace_id": "ws_123456",
        "data": {
            "id": LEAD_ID,
            "email": TEST_EMAIL,
            "first_name": "Paschal",
            "last_name": "",
            "company_name": "3rd Brain Podcast",
            "personalization": "Hi Paschal, This is a test email from PGL...",
            "custom_variables": {
                "Client_Name": "Test Client",
                "Subject": "Test Email - PGL Webhook Integration",
                "pitch_gen_id": "test_pitch_gen_123",
                "campaign_id": "cdc33aee-b0f8-4460-beec-cce66ea3772c",
                "media_id": "test_media_456"
            }
        },
        "email": {
            "id": f"email_{datetime.utcnow().timestamp()}",
            "subject": "Test Email - PGL Webhook Integration",
            "body_text": "This is the email body text...",
            "sent_at": datetime.utcnow().isoformat()
        }
    }
    
    # Also include fields for Attio integration
    payload["airID"] = f"attio_record_{LEAD_ID}"
    payload["lead"] = payload["data"]  # Some webhook handlers expect this
    
    response = requests.post(
        f"{BASE_URL}/api/webhooks/instantly-email-sent",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Response: {response.status_code}")
    print(f"Body: {response.text}")

def simulate_email_opened():
    """Simulate email opened webhook"""
    print("\n" + "="*60)
    print("Simulating Email Opened Webhook")
    print("="*60)
    
    payload = {
        "event": "email_opened",
        "timestamp": datetime.utcnow().isoformat(),
        "lead_id": LEAD_ID,
        "campaign_id": INSTANTLY_CAMPAIGN_ID,
        "workspace_id": "ws_123456",
        "data": {
            "id": LEAD_ID,
            "email": TEST_EMAIL,
            "first_name": "Paschal",
            "opened_count": 1,
            "first_opened_at": datetime.utcnow().isoformat(),
            "last_opened_at": datetime.utcnow().isoformat()
        },
        "activity": {
            "type": "email_opened",
            "timestamp": datetime.utcnow().isoformat(),
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0..."
        }
    }
    
    response = requests.post(
        f"{BASE_URL}/api/webhooks/instantly-email-opened",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Response: {response.status_code}")
    if response.status_code != 404:
        print(f"Body: {response.text}")
    else:
        print("Email opened endpoint not implemented (expected)")

def simulate_email_replied():
    """Simulate email reply webhook"""
    print("\n" + "="*60)
    print("Simulating Email Reply Webhook")
    print("="*60)
    
    reply_text = """Hi there,

Thanks for reaching out! I'm definitely interested in learning more about your client.

A few questions:
1. What's their area of expertise in AI?
2. What specific topics would they like to discuss on the podcast?
3. Do they have any previous podcast appearances I could check out?

Looking forward to hearing more!

Best,
Paschal
Host, 3rd Brain Podcast"""
    
    payload = {
        "event": "email_replied",
        "timestamp": datetime.utcnow().isoformat(),
        "lead_id": LEAD_ID,
        "campaign_id": INSTANTLY_CAMPAIGN_ID,
        "workspace_id": "ws_123456",
        "data": {
            "id": LEAD_ID,
            "email": TEST_EMAIL,
            "first_name": "Paschal",
            "last_name": "",
            "company_name": "3rd Brain Podcast",
            "replied": True,
            "reply_timestamp": datetime.utcnow().isoformat()
        },
        "reply": {
            "id": f"reply_{datetime.utcnow().timestamp()}",
            "from": TEST_EMAIL,
            "subject": "Re: Test Email - PGL Webhook Integration",
            "body_text": reply_text,
            "body_html": f"<p>{reply_text.replace('\n', '<br>')}</p>",
            "received_at": datetime.utcnow().isoformat(),
            "snippet": reply_text[:150]
        },
        # Fields for Attio integration
        "airID": f"attio_record_{LEAD_ID}",
        "reply_text_snippet": reply_text[:150],
        "lead": {
            "email": TEST_EMAIL,
            "first_name": "Paschal"
        }
    }
    
    response = requests.post(
        f"{BASE_URL}/api/webhooks/instantly-reply-received",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Response: {response.status_code}")
    print(f"Body: {response.text}")

def main():
    """Main monitoring loop"""
    print("Instantly Webhook Monitor")
    print("="*60)
    print(f"Using Lead ID: {LEAD_ID}")
    print(f"Testing against: {BASE_URL}")
    print("="*60)
    
    while True:
        print("\nSelect webhook to simulate:")
        print("1. Email Sent")
        print("2. Email Opened")
        print("3. Email Replied")
        print("4. Run all in sequence")
        print("0. Exit")
        
        choice = input("\nEnter choice: ")
        
        if choice == "1":
            simulate_email_sent()
        elif choice == "2":
            simulate_email_opened()
        elif choice == "3":
            simulate_email_replied()
        elif choice == "4":
            simulate_email_sent()
            time.sleep(2)
            simulate_email_opened()
            time.sleep(2)
            simulate_email_replied()
        elif choice == "0":
            break
        else:
            print("Invalid choice")
        
        input("\nPress Enter to continue...")

if __name__ == "__main__":
    main()