#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Test script to send a FRESH lead to Instantly TEST campaign
"""

import os
import requests
import json
from datetime import datetime
from dotenv import load_dotenv
import random
import string

load_dotenv()

INSTANTLY_API_KEY = os.getenv('INSTANTLY_API_KEY')
INSTANTLY_BASE_URL = "https://api.instantly.ai/api/v2"
TEST_CAMPAIGN_ID = "5e4230db-d7df-4bfa-8e2b-b4f4d524f0f2"  # Your TEST Campaign

def generate_test_email():
    """Generate a unique test email"""
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"test_{random_str}@3rdbrain.co"

def delete_lead_if_exists(email):
    """Check if lead exists and optionally delete it"""
    headers = {
        "Authorization": f"Bearer {INSTANTLY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Search for the lead across all campaigns
    print(f"Searching for {email} in all campaigns...")
    
    # Get leads from TEST campaign
    payload = {
        "campaign": TEST_CAMPAIGN_ID,
        "search": email,
        "limit": 10
    }
    
    response = requests.post(
        f"{INSTANTLY_BASE_URL}/leads/list",
        json=payload,
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        leads = data.get('items', [])
        
        if leads:
            print(f"\n⚠️  Found existing lead in TEST campaign!")
            lead = leads[0]
            print(f"Lead ID: {lead.get('id')}")
            print(f"Status: {lead.get('status')}")
            
            choice = input("\nDelete this lead and create fresh? (y/n): ")
            if choice.lower() == 'y':
                # Delete the lead
                delete_response = requests.delete(
                    f"{INSTANTLY_BASE_URL}/leads/{lead.get('id')}",
                    headers=headers
                )
                if delete_response.status_code == 200:
                    print("✓ Lead deleted successfully")
                    return True
                else:
                    print(f"✗ Failed to delete: {delete_response.text}")
                    return False
    
    return True

def send_fresh_lead():
    """Send a fresh test lead to the TEST campaign"""
    headers = {
        "Authorization": f"Bearer {INSTANTLY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Option to use custom email or generate one
    print("\nEmail options:")
    print("1. Use paschal@3rdbrain.co (will update existing)")
    print("2. Generate a unique test email")
    print("3. Enter custom email")
    
    choice = input("\nChoice (1-3): ")
    
    if choice == "1":
        test_email = "paschal@3rdbrain.co"
        skip_params = False  # Don't skip for existing
    elif choice == "2":
        test_email = generate_test_email()
        skip_params = True
    else:
        test_email = input("Enter email: ")
        skip_params = True
    
    print(f"\nUsing email: {test_email}")
    
    # Prepare payload
    payload = {
        "campaign": TEST_CAMPAIGN_ID,  # Force TEST campaign
        "email": test_email,
        "first_name": "Test",
        "last_name": "User",
        "company_name": "3rd Brain Test",
        "personalization": f"""Hi there,

This is a TEST email from the PGL webhook integration test.

Details:
- Campaign: TEST Campaign ({TEST_CAMPAIGN_ID})
- Timestamp: {datetime.utcnow().isoformat()}
- Purpose: Testing Instantly webhooks

When you receive this:
1. Open it to trigger 'email opened' webhook
2. Reply to trigger 'reply received' webhook

Thanks!
PGL Test System""",
        "verify_leads_for_lead_finder": False,
        "verify_leads_on_import": False,
        "custom_variables": {
            "Client_Name": "Test Client",
            "Subject": "TEST - PGL Webhook Integration",
            "pitch_gen_id": "test_123",
            "campaign_id": "cdc33aee-b0f8-4460-beec-cce66ea3772c",
            "media_id": "test_456"
        }
    }
    
    # Add skip parameters based on choice
    if skip_params:
        payload["skip_if_in_campaign"] = True
    
    print(f"\nSending to campaign: {TEST_CAMPAIGN_ID}")
    print(f"Skip if exists: {skip_params}")
    
    response = requests.post(
        f"{INSTANTLY_BASE_URL}/leads",
        json=payload,
        headers=headers
    )
    
    print(f"\nResponse Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Check which campaign it went to
        actual_campaign = data.get('campaign')
        if actual_campaign != TEST_CAMPAIGN_ID:
            print(f"\n⚠️  WARNING: Lead went to different campaign!")
            print(f"Expected: {TEST_CAMPAIGN_ID}")
            print(f"Actual: {actual_campaign}")
        else:
            print(f"\n✓ Lead successfully added to TEST campaign!")
        
        return data.get('id')
    else:
        print(f"Error: {response.text}")
        return None

def configure_webhooks():
    """Show webhook configuration"""
    print("\n" + "="*60)
    print("Configure these webhooks in your TEST campaign:")
    print(f"Campaign ID: {TEST_CAMPAIGN_ID}")
    print("\n1. Go to Instantly")
    print("2. Find 'TEST Campaign'")
    print("3. Go to Settings > Webhooks")
    print("4. Add these URLs:")
    print(f"\n   Email Sent: https://b8eb-198-252-15-187.ngrok-free.app/webhooks/instantly-email-sent")
    print(f"   Reply Received: https://b8eb-198-252-15-187.ngrok-free.app/webhooks/instantly-reply-received")
    print("="*60)

def main():
    print("Instantly TEST Campaign Lead Sender")
    print("="*60)
    
    # Send fresh lead
    lead_id = send_fresh_lead()
    
    if lead_id:
        # Save for webhook testing
        with open('test_lead_info.json', 'w') as f:
            json.dump({
                'lead_id': lead_id,
                'campaign_id': TEST_CAMPAIGN_ID,
                'timestamp': datetime.utcnow().isoformat()
            }, f, indent=2)
        
        configure_webhooks()
        
        print("\n✓ Ready for webhook testing!")
        print(f"Lead ID: {lead_id}")
        print("\nNow you can:")
        print("1. Check the TEST campaign in Instantly")
        print("2. Wait for the email to be sent")
        print("3. Monitor webhooks at http://127.0.0.1:4040")

if __name__ == "__main__":
    main()