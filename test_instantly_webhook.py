#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Test script to simulate Instantly webhook calls to your FastAPI endpoint
"""

import requests
import json
from datetime import datetime

# Your localhost FastAPI endpoint
BASE_URL = "http://localhost:8000"
WEBHOOK_ENDPOINT = f"{BASE_URL}/api/webhooks/instantly"  # Adjust to your actual endpoint

# Example Instantly webhook payloads
# Based on common Instantly webhook events

# Campaign completed webhook
campaign_completed_payload = {
    "event": "campaign_completed",
    "timestamp": datetime.utcnow().isoformat(),
    "campaign": {
        "id": "camp_123456",
        "name": "Test Campaign",
        "status": "completed"
    },
    "stats": {
        "sent": 100,
        "opened": 45,
        "clicked": 12,
        "replied": 5
    }
}

# Email opened webhook
email_opened_payload = {
    "event": "email_opened",
    "timestamp": datetime.utcnow().isoformat(),
    "campaign_id": "camp_123456",
    "lead": {
        "email": "test@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "company": "Test Company"
    },
    "email_details": {
        "subject": "Your podcast would be perfect for...",
        "sent_at": datetime.utcnow().isoformat(),
        "opened_at": datetime.utcnow().isoformat()
    }
}

# Email replied webhook
email_replied_payload = {
    "event": "email_replied",
    "timestamp": datetime.utcnow().isoformat(),
    "campaign_id": "camp_123456",
    "lead": {
        "email": "host@podcast.com",
        "first_name": "Jane",
        "last_name": "Smith"
    },
    "reply": {
        "subject": "Re: Your podcast would be perfect for...",
        "body": "Thanks for reaching out! I'd love to learn more about your client.",
        "received_at": datetime.utcnow().isoformat()
    }
}

# Email bounced webhook
email_bounced_payload = {
    "event": "email_bounced",
    "timestamp": datetime.utcnow().isoformat(),
    "campaign_id": "camp_123456",
    "lead": {
        "email": "invalid@example.com"
    },
    "bounce_details": {
        "type": "hard_bounce",
        "reason": "Mailbox does not exist"
    }
}

def test_webhook(payload, description):
    """Send a test webhook request to your FastAPI endpoint"""
    print(f"\n{'='*60}")
    print(f"Testing: {description}")
    print(f"{'='*60}")
    
    try:
        # Instantly typically sends webhooks with these headers
        headers = {
            "Content-Type": "application/json",
            "X-Instantly-Signature": "test_signature_123",  # In production, this would be HMAC
            "User-Agent": "Instantly-Webhook/1.0"
        }
        
        response = requests.post(
            WEBHOOK_ENDPOINT,
            json=payload,
            headers=headers
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code == 200:
            print(f"Success! Response: {response.json()}")
        else:
            print(f"Error! Response: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("ERROR: Could not connect to FastAPI server.")
        print("Make sure your FastAPI app is running on http://localhost:8000")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")

def main():
    """Run all webhook tests"""
    print("Instantly Webhook Test Script")
    print("Make sure your FastAPI server is running!")
    
    # Test all webhook types
    test_webhook(campaign_completed_payload, "Campaign Completed Event")
    test_webhook(email_opened_payload, "Email Opened Event")
    test_webhook(email_replied_payload, "Email Replied Event")
    test_webhook(email_bounced_payload, "Email Bounced Event")
    
    # Test invalid payload
    print(f"\n{'='*60}")
    print("Testing: Invalid Payload")
    print(f"{'='*60}")
    test_webhook({"invalid": "data"}, "Invalid Payload")

if __name__ == "__main__":
    main()