#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Check which Instantly campaign the lead was added to
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

INSTANTLY_API_KEY = os.getenv('INSTANTLY_API_KEY')
INSTANTLY_BASE_URL = "https://api.instantly.ai/api/v2"

def list_campaigns():
    """List all campaigns to find the right one"""
    headers = {
        "Authorization": f"Bearer {INSTANTLY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    print("Fetching all campaigns...")
    response = requests.get(
        f"{INSTANTLY_BASE_URL}/campaigns",
        headers=headers,
        params={"limit": 100}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nResponse type: {type(data)}")
        print(f"Response data: {data}")
        
        # Handle different response formats
        if isinstance(data, list):
            campaigns = data
            print(f"\nFound {len(campaigns)} campaigns:\n")
            
            for camp in campaigns:
                if isinstance(camp, str):
                    print(f"Campaign ID: {camp}")
                elif isinstance(camp, dict):
                    print(f"ID: {camp.get('id')}")
                    print(f"Name: {camp.get('name')}")
                    print(f"Status: {camp.get('status')}")
                print("-" * 50)
                
                # Check if this is the campaign ID you specified
                if camp == '5e4230db-d7df-4bfa-8e2b-b4f4d524f0f2' or (isinstance(camp, dict) and camp.get('id') == '5e4230db-d7df-4bfa-8e2b-b4f4d524f0f2'):
                    print("✓ THIS IS YOUR SPECIFIED CAMPAIGN!")
                    print("-" * 50)
                    
                # Check if this is where the lead went
                if camp == 'ccbd7662-bbed-46ee-bd8f-1bc374646472' or (isinstance(camp, dict) and camp.get('id') == 'ccbd7662-bbed-46ee-bd8f-1bc374646472'):
                    print("⚠️  THIS IS WHERE YOUR LEAD WAS ADDED!")
                    print("-" * 50)
        else:
            print(f"Unexpected response format: {data}")
    else:
        print(f"Error: {response.status_code} - {response.text}")

def check_lead_in_campaign(campaign_id, email):
    """Check if a lead exists in a specific campaign"""
    headers = {
        "Authorization": f"Bearer {INSTANTLY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    print(f"\nChecking for {email} in campaign {campaign_id}...")
    
    payload = {
        "campaign": campaign_id,
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
            print(f"✓ Found lead in campaign!")
            for lead in leads:
                print(f"\nLead ID: {lead.get('id')}")
                print(f"Email: {lead.get('email')}")
                print(f"Status: {lead.get('status')}")
                print(f"Reply count: {lead.get('email_reply_count')}")
                print(f"Last contacted: {lead.get('timestamp_last_contact')}")
        else:
            print(f"✗ Lead not found in this campaign")
    else:
        print(f"Error: {response.status_code} - {response.text}")

def main():
    print("Instantly Campaign & Lead Checker")
    print("="*60)
    
    # List all campaigns
    list_campaigns()
    
    # Check the lead in both campaigns
    print("\n" + "="*60)
    print("Checking lead location...")
    print("="*60)
    
    # Check in the campaign we tried to use
    check_lead_in_campaign('5e4230db-d7df-4bfa-8e2b-b4f4d524f0f2', 'paschal@3rdbrain.co')
    
    # Check in the campaign it actually went to
    check_lead_in_campaign('ccbd7662-bbed-46ee-bd8f-1bc374646472', 'paschal@3rdbrain.co')

if __name__ == "__main__":
    main()