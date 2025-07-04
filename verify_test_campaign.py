#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Verify that the TEST campaign exists in Instantly
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

INSTANTLY_API_KEY = os.getenv('INSTANTLY_API_KEY')
INSTANTLY_BASE_URL = "https://api.instantly.ai/api/v2"
TEST_CAMPAIGN_ID = "5e4230db-d7df-4bfa-8e2b-b4f4d524f0f2"

def check_campaign_exists():
    """Check if the TEST campaign exists"""
    headers = {
        "Authorization": f"Bearer {INSTANTLY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    print("Checking if TEST campaign exists...")
    print(f"Campaign ID: {TEST_CAMPAIGN_ID}")
    print("="*60)
    
    # Try to get campaign details
    response = requests.get(
        f"{INSTANTLY_BASE_URL}/campaigns/{TEST_CAMPAIGN_ID}",
        headers=headers
    )
    
    if response.status_code == 200:
        print("✓ Campaign exists!")
        data = response.json()
        print(f"\nCampaign Details:")
        print(f"- Name: {data.get('name', 'N/A')}")
        print(f"- Status: {data.get('status', 'N/A')}")
        print(f"- Created: {data.get('created_at', 'N/A')}")
        return True
    else:
        print(f"✗ Campaign not found or error: {response.status_code}")
        print(f"Response: {response.text}")
        return False

def list_all_campaigns():
    """List all campaigns to find the right one"""
    headers = {
        "Authorization": f"Bearer {INSTANTLY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    print("\n" + "="*60)
    print("Listing all campaigns...")
    print("="*60)
    
    response = requests.get(
        f"{INSTANTLY_BASE_URL}/campaigns",
        headers=headers,
        params={"limit": 100, "offset": 0}
    )
    
    if response.status_code == 200:
        campaigns = response.json()
        
        # Handle both list and dict response formats
        if isinstance(campaigns, dict):
            campaigns = campaigns.get('items', [])
        
        print(f"\nFound {len(campaigns)} campaigns:\n")
        
        test_found = False
        for camp in campaigns:
            if isinstance(camp, str):
                camp_id = camp
                print(f"Campaign ID: {camp_id}")
                if camp_id == TEST_CAMPAIGN_ID:
                    print("  ✓ THIS IS THE TEST CAMPAIGN")
                    test_found = True
            elif isinstance(camp, dict):
                camp_id = camp.get('id')
                camp_name = camp.get('name', 'Unknown')
                print(f"ID: {camp_id}")
                print(f"  Name: {camp_name}")
                if camp_id == TEST_CAMPAIGN_ID:
                    print("  ✓ THIS IS THE TEST CAMPAIGN")
                    test_found = True
            print("-" * 40)
        
        if not test_found:
            print(f"\n⚠️  TEST campaign ID {TEST_CAMPAIGN_ID} not found!")
            print("You may need to update the campaign ID in your scripts.")
    else:
        print(f"Error: {response.status_code} - {response.text}")

def check_existing_lead():
    """Check where paschal@3rdbrain.co exists"""
    headers = {
        "Authorization": f"Bearer {INSTANTLY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    print("\n" + "="*60)
    print("Checking existing lead: paschal@3rdbrain.co")
    print("="*60)
    
    # Search in the other campaign
    other_campaign = "ccbd7662-bbed-46ee-bd8f-1bc374646472"
    
    payload = {
        "campaign": other_campaign,
        "search": "paschal@3rdbrain.co",
        "limit": 1
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
            lead = leads[0]
            print(f"\n✓ Found lead in campaign: {other_campaign}")
            print(f"Lead details:")
            print(f"- Email: {lead.get('email')}")
            print(f"- Status: {lead.get('status')}")
            print(f"- Reply count: {lead.get('email_reply_count')}")
            print(f"- Last contacted: {lead.get('timestamp_last_contact')}")
            print(f"- Company: {lead.get('company_name')}")
            print("\nThis is why your lead goes to this campaign!")
            print("Instantly updates existing leads rather than creating duplicates.")

def main():
    print("Instantly Campaign Verification")
    print("="*60)
    
    if not INSTANTLY_API_KEY:
        print("ERROR: INSTANTLY_API_KEY not found")
        return
    
    # Check if TEST campaign exists
    check_campaign_exists()
    
    # List all campaigns
    list_all_campaigns()
    
    # Check existing lead
    check_existing_lead()
    
    print("\n" + "="*60)
    print("Recommendation:")
    print("Use a fresh email address to test sending to the TEST campaign.")
    print("The updated test_instantly_direct.py script now offers this option.")
    print("="*60)

if __name__ == "__main__":
    main()