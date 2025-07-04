#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Test script to send email directly to Instantly API and monitor webhook responses
"""

import os
import sys
import requests
import json
from datetime import datetime, timezone
import time
import asyncio
from dotenv import load_dotenv

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()

# Configuration
INSTANTLY_API_KEY = os.getenv('INSTANTLY_API_KEY')
INSTANTLY_BASE_URL = "https://api.instantly.ai/api/v2"
INSTANTLY_CAMPAIGN_ID = "5e4230db-d7df-4bfa-8e2b-b4f4d524f0f2"
NGROK_URL = "https://b8eb-198-252-15-187.ngrok-free.app"  # Your ngrok URL

# Test data
TEST_CAMPAIGN_ID = "cdc33aee-b0f8-4460-beec-cce66ea3772c"
TEST_EMAIL = "ebube4u@gmail.com"  # Real email for actual testing

def send_to_instantly_direct():
    """Send a test email directly to Instantly API"""
    print("\n" + "="*60)
    print("Sending Test Email to Instantly")
    print("="*60)
    
    # Prepare the payload as per the sender service structure
    payload = {
        "campaign": INSTANTLY_CAMPAIGN_ID,
        "skip_if_in_campaign": False,  # Force add to specific campaign
        "email": TEST_EMAIL,
        "first_name": "Ebube",
        "company_name": "Test Podcast",
        "personalization": """Hi Ebube,

This is a test email from the Podcast Guest Logistics system.

We're testing the Instantly webhook integration. When you receive this email:
1. Open it - this should trigger the 'email opened' webhook
2. Reply to it - this should trigger the 'reply received' webhook

The webhooks will be sent to: {ngrok_url}

Test Details:
- Campaign ID: {campaign_id}
- Instantly Campaign: {instantly_id}
- Timestamp: {timestamp}

Best regards,
PGL Test System""".format(
            ngrok_url=NGROK_URL,
            campaign_id=TEST_CAMPAIGN_ID,
            instantly_id=INSTANTLY_CAMPAIGN_ID,
            timestamp=datetime.now(timezone.utc).isoformat()
        ),
        "verify_leads_for_lead_finder": True,
        "verify_leads_on_import": True,
        "custom_variables": {
            "Client_Name": "Test Client",
            "Subject": "Test Email - PGL Webhook Integration",
            "pitch_gen_id": "test_pitch_gen_123",
            "campaign_id": TEST_CAMPAIGN_ID,
            "media_id": "test_media_456"
        }
    }
    
    # Send to Instantly
    headers = {
        "Authorization": f"Bearer {INSTANTLY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        print(f"\nSending to Instantly API...")
        print(f"URL: {INSTANTLY_BASE_URL}/leads")
        print(f"Campaign: {INSTANTLY_CAMPAIGN_ID}")
        print(f"Recipient: {TEST_EMAIL}")
        
        response = requests.post(
            f"{INSTANTLY_BASE_URL}/leads",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"\nResponse Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response Data: {json.dumps(data, indent=2)}")
            
            if data.get('id'):
                lead_id = data['id']
                print(f"\n✓ Lead created successfully!")
                print(f"Lead ID: {lead_id}")
                print(f"\nIMPORTANT: Save this Lead ID for webhook testing!")
                
                # Save lead info for webhook testing
                with open('test_lead_info.json', 'w') as f:
                    json.dump({
                        'lead_id': lead_id,
                        'email': TEST_EMAIL,
                        'campaign_id': INSTANTLY_CAMPAIGN_ID,
                        'test_campaign_id': TEST_CAMPAIGN_ID,
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'custom_variables': payload['custom_variables']
                    }, f, indent=2)
                
                print("\nLead info saved to test_lead_info.json")
                return lead_id
            else:
                print("\n✗ Response did not contain lead ID")
                return None
        else:
            print(f"Error Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"\nError sending to Instantly: {e}")
        return None

def configure_webhooks():
    """Display webhook configuration instructions"""
    print("\n" + "="*60)
    print("Webhook Configuration")
    print("="*60)
    print("\nConfigure these webhooks in your Instantly campaign:")
    print(f"\n1. Email Sent Webhook:")
    print(f"   URL: {NGROK_URL}/webhooks/instantly-email-sent")
    print(f"\n2. Reply Received Webhook:")
    print(f"   URL: {NGROK_URL}/webhooks/instantly-reply-received")
    print(f"\n3. Email Opened Webhook (if available):")
    print(f"   URL: {NGROK_URL}/webhooks/instantly-email-opened")
    print("\nTo configure webhooks:")
    print("1. Go to your Instantly campaign")
    print("2. Navigate to Settings > Webhooks")
    print("3. Add the URLs above for the corresponding events")
    print("="*60)

def monitor_ngrok():
    """Display ngrok monitoring instructions"""
    print("\n" + "="*60)
    print("Monitoring Webhooks")
    print("="*60)
    print("\nTo monitor incoming webhooks:")
    print(f"1. Open your browser to: http://127.0.0.1:4040")
    print("2. This is ngrok's web interface showing all requests")
    print("3. You'll see webhook payloads as they arrive")
    print("\nAlternatively, check your FastAPI logs for webhook processing")
    print("="*60)

def test_webhook_locally(lead_id):
    """Test webhooks locally to verify they work"""
    print("\n" + "="*60)
    print("Testing Webhooks Locally")
    print("="*60)
    
    # Test email sent webhook
    print("\nTesting Email Sent webhook...")
    sent_payload = {
        "event": "email_sent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "lead_id": lead_id,
        "campaign_id": INSTANTLY_CAMPAIGN_ID,
        "lead": {
            "email": TEST_EMAIL,
            "first_name": "Ebube",
            "company_name": "3rd Brain Podcast"
        },
        "email_details": {
            "subject": "Test Email - PGL Webhook Integration",
            "sent_at": datetime.now(timezone.utc).isoformat()
        },
        "airID": f"test_attio_{lead_id}",
        "personalization": "Test email content..."
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/webhooks/instantly-email-sent",
            json=sent_payload
        )
        print(f"Email Sent webhook response: {response.status_code}")
    except Exception as e:
        print(f"Error testing email sent webhook: {e}")

def main():
    """Main test flow"""
    print("Instantly Direct API Test")
    print("="*60)
    
    if not INSTANTLY_API_KEY:
        print("ERROR: INSTANTLY_API_KEY not found in environment variables")
        print("Please add it to your .env file")
        return
    
    print(f"\nUsing Instantly Campaign: {INSTANTLY_CAMPAIGN_ID}")
    print(f"Sending to: {TEST_EMAIL}")
    print(f"Webhook URL: {NGROK_URL}")
    
    # Send test email
    lead_id = send_to_instantly_direct()
    
    if lead_id:
        # Show webhook configuration
        configure_webhooks()
        
        # Show monitoring instructions
        monitor_ngrok()
        
        # Test webhooks locally
        input("\nPress Enter to test webhooks locally...")
        test_webhook_locally(lead_id)
        
        print("\n" + "="*60)
        print("Next Steps:")
        print("1. Check your email for the test message")
        print("2. Open the email to trigger 'email opened' webhook")
        print("3. Reply to the email to trigger 'reply received' webhook")
        print("4. Monitor webhooks at http://127.0.0.1:4040")
        print("5. Check FastAPI logs for webhook processing")
        print("="*60)

if __name__ == "__main__":
    main()