#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Simple script to test Instantly webhooks without authentication
"""

import requests
import json
from datetime import datetime
import time

# Configuration
BASE_URL = "http://localhost:8000"  # Your FastAPI localhost
TEST_EMAIL = "paschal@3rdbrain.co"
CAMPAIGN_ID = "cdc33aee-b0f8-4460-beec-cce66ea3772c"

def test_email_sent_webhook():
    """Test the email sent webhook"""
    print("\n" + "="*60)
    print("Testing Email Sent Webhook")
    print("="*60)
    
    webhook_data = {
        "event": "email_sent",
        "timestamp": datetime.utcnow().isoformat(),
        "lead_id": "test_lead_123",
        "campaign_id": CAMPAIGN_ID,
        "lead": {
            "email": TEST_EMAIL,
            "first_name": "Paschal",
            "last_name": "Test",
            "company": "3rd Brain",
            "linkedin": "https://linkedin.com/in/paschal"
        },
        "email_details": {
            "subject": "Your podcast expertise would be perfect for our AI startup client",
            "sent_at": datetime.utcnow().isoformat(),
            "template_id": "template_001",
            "from_email": "outreach@podcastguests.com"
        },
        # Fields that might be expected by Attio integration
        "airID": "rec_test_123456",  # Attio record ID
        "personalization": """Hi Paschal,

I came across your work at 3rd Brain and was really impressed by your expertise in AI and technology.

We're working with an AI startup founder who's looking to share their insights on building AI-powered solutions. Given your background, I think your podcast would be a perfect fit for this conversation.

Would you be interested in having them as a guest on your show?

Best regards,
Sarah from Podcast Guest Logistics"""
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/webhooks/instantly-email-sent",
            json=webhook_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Instantly-Webhook/1.0",
                "X-Instantly-Signature": "test_signature_123"
            }
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✓ Email sent webhook processed successfully!")
        else:
            print("✗ Email sent webhook failed!")
            
    except Exception as e:
        print(f"Error: {e}")

def test_reply_received_webhook():
    """Test the reply received webhook"""
    print("\n" + "="*60)
    print("Testing Reply Received Webhook")
    print("="*60)
    
    reply_body = """Hi Sarah,

Thanks for reaching out! I'm definitely interested in learning more about your AI startup founder client.

Could you share:
1. What specific AI topics they're most passionate about?
2. Their background and current venture
3. Availability for recording in the next 2-3 weeks

Also, do they have any previous podcast appearances I could check out?

Best,
Paschal

--
Paschal | 3rd Brain
Host of The AI Podcast"""
    
    webhook_data = {
        "event": "reply_received",
        "timestamp": datetime.utcnow().isoformat(),
        "lead_id": "test_lead_123",
        "campaign_id": CAMPAIGN_ID,
        "lead": {
            "email": TEST_EMAIL,
            "first_name": "Paschal",
            "last_name": "Test",
            "company": "3rd Brain"
        },
        "email": {
            "from": TEST_EMAIL,
            "to": "outreach@podcastguests.com",
            "subject": "Re: Your podcast expertise would be perfect for our AI startup client"
        },
        "reply": {
            "body": reply_body,
            "received_at": datetime.utcnow().isoformat(),
            "snippet": reply_body[:150] + "..."
        },
        # Fields for Attio integration
        "airID": "rec_test_123456",
        "reply_text_snippet": reply_body[:150] + "...",
        "full_reply": reply_body
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/webhooks/instantly-reply-received",
            json=webhook_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Instantly-Webhook/1.0",
                "X-Instantly-Signature": "test_signature_456"
            }
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✓ Reply received webhook processed successfully!")
        else:
            print("✗ Reply received webhook failed!")
            
    except Exception as e:
        print(f"Error: {e}")

def test_email_opened_webhook():
    """Test email opened webhook (bonus)"""
    print("\n" + "="*60)
    print("Testing Email Opened Webhook (if endpoint exists)")
    print("="*60)
    
    webhook_data = {
        "event": "email_opened",
        "timestamp": datetime.utcnow().isoformat(),
        "lead_id": "test_lead_123",
        "campaign_id": CAMPAIGN_ID,
        "lead": {
            "email": TEST_EMAIL,
            "first_name": "Paschal"
        },
        "email_details": {
            "opened_at": datetime.utcnow().isoformat(),
            "opens_count": 1,
            "ip_address": "192.168.1.1",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/webhooks/instantly-email-opened",
            json=webhook_data,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status Code: {response.status_code}")
        if response.status_code != 404:
            print(f"Response: {response.text}")
        else:
            print("Email opened webhook endpoint not found (expected if not implemented)")
            
    except Exception as e:
        print(f"Error: {e}")

def main():
    """Run all webhook tests"""
    print("Instantly Webhook Test Script")
    print("="*60)
    print(f"Testing webhooks against: {BASE_URL}")
    print(f"Campaign ID: {CAMPAIGN_ID}")
    print(f"Test Email: {TEST_EMAIL}")
    print("="*60)
    
    print("\nMake sure your FastAPI server is running!")
    print("Run: pgl_env/Scripts/python.exe -m uvicorn podcast_outreach.main:app --reload")
    
    input("\nPress Enter to start testing...")
    
    # Test email sent
    test_email_sent_webhook()
    
    # Wait a bit
    print("\nWaiting 2 seconds...")
    time.sleep(2)
    
    # Test reply received
    test_reply_received_webhook()
    
    # Test email opened (optional)
    print("\nWaiting 2 seconds...")
    time.sleep(2)
    test_email_opened_webhook()
    
    print("\n" + "="*60)
    print("Testing completed!")
    print("Check your FastAPI server logs to see how the webhooks were processed")
    print("="*60)

if __name__ == "__main__":
    main()