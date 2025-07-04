#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Test the full webhook flow with the updated handlers
"""

import requests
import json
from datetime import datetime, timezone

# Configuration
LOCAL_URL = "http://localhost:8000"
TEST_EMAIL = "ebube4u@gmail.com"
INSTANTLY_CAMPAIGN_ID = "5e4230db-d7df-4bfa-8e2b-b4f4d524f0f2"
PGL_CAMPAIGN_ID = "cdc33aee-b0f8-4460-beec-cce66ea3772c"

# Use the actual webhook data structure from ngrok
def test_email_sent_webhook():
    """Test email sent webhook with real Instantly data structure"""
    print("\n" + "="*60)
    print("Testing Email Sent Webhook")
    print("="*60)
    
    # Real webhook payload structure from your ngrok log
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "email_sent",
        "workspace": "0462b242-8088-4dac-a640-453777ba421f",
        "campaign_id": PGL_CAMPAIGN_ID,
        "unibox_url": None,
        "campaign_name": "TEST Campaign",
        "email_account": "aidrian@digitalpodcastguest.com",
        "is_first": True,
        "lead_email": TEST_EMAIL,
        "email": TEST_EMAIL,
        "Subject": "Test Email - PGL Webhook Integration",
        "website": "",
        "campaign": INSTANTLY_CAMPAIGN_ID,
        "lastName": "",
        "media_id": "test_media_456",
        "firstName": "Ebube",
        "Client_Name": "Test Client",
        "companyName": "Test Podcast",
        "pitch_gen_id": "test_pitch_gen_123",  # This is the key field
        "personalization": "Hi Ebube,\n\nThis is a test email...",
        "step": 1,
        "variant": 1,
        "email_subject": "Test Email - PGL Webhook Integration",
        "email_html": "<div>Hi Ebube...</div>"
    }
    
    try:
        response = requests.post(
            f"{LOCAL_URL}/webhooks/instantly-email-sent",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✓ Email sent webhook processed successfully")
        else:
            print("✗ Email sent webhook failed")
            
    except Exception as e:
        print(f"Error: {e}")

def test_reply_received_webhook():
    """Test reply received webhook"""
    print("\n" + "="*60)
    print("Testing Reply Received Webhook")
    print("="*60)
    
    # Simulate reply webhook payload
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "email_replied",
        "workspace": "0462b242-8088-4dac-a640-453777ba421f",
        "campaign_id": PGL_CAMPAIGN_ID,
        "campaign_name": "TEST Campaign",
        "lead_email": TEST_EMAIL,
        "email": TEST_EMAIL,
        "pitch_gen_id": "test_pitch_gen_123",  # Key field for linking
        "media_id": "test_media_456",
        "campaign": INSTANTLY_CAMPAIGN_ID,
        "firstName": "Ebube",
        "lastName": "",
        "companyName": "Test Podcast",
        "reply": {
            "from": TEST_EMAIL,
            "subject": "Re: Test Email - PGL Webhook Integration",
            "body_text": "Hi there,\n\nThanks for reaching out! I'm interested in learning more...",
            "received_at": datetime.now(timezone.utc).isoformat()
        },
        "reply_text_snippet": "Thanks for reaching out! I'm interested..."
    }
    
    try:
        response = requests.post(
            f"{LOCAL_URL}/webhooks/instantly-reply-received",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✓ Reply received webhook processed successfully")
            print("\nThis should have:")
            print("1. Updated the pitch state to 'replied'")
            print("2. Created a placement record for booking tracking")
        else:
            print("✗ Reply received webhook failed")
            
    except Exception as e:
        print(f"Error: {e}")

def check_database_state():
    """Optional: Check database state after webhooks"""
    print("\n" + "="*60)
    print("Database State Check")
    print("="*60)
    print("\nTo verify the webhooks worked:")
    print("1. Check pitches table for pitch_state = 'sent' or 'replied'")
    print("2. Check placements table for new booking records")
    print("\nSQL queries to run:")
    print("-- Check pitch states")
    print("SELECT pitch_id, pitch_state, send_ts, reply_bool, reply_ts")
    print("FROM pitches")
    print("WHERE pitch_gen_id = 'test_pitch_gen_123';")
    print("\n-- Check placements")
    print("SELECT placement_id, current_status, notes")
    print("FROM placements")
    print("WHERE pitch_id IN (SELECT pitch_id FROM pitches WHERE pitch_gen_id = 'test_pitch_gen_123');")

def main():
    print("Full Webhook Flow Test")
    print("="*60)
    print("This tests the updated webhook handlers that:")
    print("1. Update pitch states when emails are sent")
    print("2. Create placement records when replies are received")
    print("="*60)
    
    # Test email sent
    input("\nPress Enter to test Email Sent webhook...")
    test_email_sent_webhook()
    
    # Test reply received
    input("\nPress Enter to test Reply Received webhook...")
    test_reply_received_webhook()
    
    # Show how to check database
    check_database_state()
    
    print("\n" + "="*60)
    print("Testing Complete!")
    print("Check your FastAPI logs for detailed processing info")
    print("="*60)

if __name__ == "__main__":
    main()