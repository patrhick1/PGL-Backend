#!/usr/bin/env python3
"""
Test script for the campaign generate-angles-bio API endpoint.
This script assumes that the questionnaire has already been submitted
for the campaign, populating the mock_interview_trancript.
"""

import requests
import json

# Configuration
BASE_URL = "http://localhost:8000"
CAMPAIGN_ID = "cdc33aee-b0f8-4460-beec-cce66ea3772c" # Same campaign ID as test_questionnaire_api.py
ENDPOINT_URL = f"{BASE_URL}/campaigns/{CAMPAIGN_ID}/generate-angles-bio"

# Headers with session cookie (same as test_questionnaire_api.py)
# Replace with a valid session cookie if needed
HEADERS = {
    'Content-Type': 'application/json',
    'Cookie': 'session=eyJ1c2VybmFtZSI6ICJlYnViZTR1QGdtYWlsLmNvbSIsICJyb2xlIjogImNsaWVudCIsICJwZXJzb25faWQiOiA0MiwgImZ1bGxfbmFtZSI6ICJNYXJ5IFV3YSJ9.aD5H4g.yYStr97RJDarwAnvNLPF0eZlAqE'
}

def test_trigger_generate_angles_bio():
    """
    Tests the generate-angles-bio endpoint for a campaign.
    """
    print(f"🔄 Testing Generate Angles & Bio API for campaign: {CAMPAIGN_ID}...")
    print(f"URL: {ENDPOINT_URL}")
    
    try:
        # Make the API request (POST request, no body needed for this endpoint)
        response = requests.post(ENDPOINT_URL, headers=HEADERS)
        
        print(f"\n📊 Response Status: {response.status_code}")
        response_headers = dict(response.headers)
        print(f"📝 Response Headers: {json.dumps(response_headers, indent=2)}")
        
        try:
            response_json = response.json()
            print(f"💬 Response JSON: {json.dumps(response_json, indent=2)}")
            
            if response.status_code == 200 or response.status_code == 202: # 202 Accepted is also common for async tasks
                print(f"✅ SUCCESS: Trigger for Bio & Angles generation for campaign {CAMPAIGN_ID} was successful (or accepted).")
                if "details" in response_json and response_json["details"]:
                    print("   Details from response:")
                    if response_json["details"].get("bio_doc_link"):
                         print(f"   Bio GDoc Link: {response_json['details']['bio_doc_link']}")
                    if response_json["details"].get("angles_doc_link"):
                         print(f"   Angles GDoc Link: {response_json['details']['angles_doc_link']}")
                    if response_json["details"].get("keywords"):
                         print(f"   Generated Keywords: {response_json['details']['keywords']}")
            elif response.status_code == 400 and "does not have a mock interview transcript" in response.text:
                print(f"❌ FAILED (400): The campaign {CAMPAIGN_ID} does not have a mock interview transcript. Please ensure the questionnaire was submitted successfully first via test_questionnaire_api.py.")
            else:
                print(f"❌ FAILED: API returned status {response.status_code}")
                
        except json.JSONDecodeError:
            print("⚠️ Response is not valid JSON.")
            print(f"💬 Response Text: {response.text}")
            if response.status_code == 200 or response.status_code == 202:
                 print(f"✅ SUCCESS (Status {response.status_code}): Trigger for Bio & Angles generation for campaign {CAMPAIGN_ID} was successful (or accepted), but response was not JSON.")
            else:
                print(f"❌ FAILED: API returned status {response.status_code} with non-JSON response.")

    except requests.exceptions.ConnectionError:
        print(f"❌ FAILED: Could not connect to the server at {BASE_URL}. Is it running?")
    except Exception as e:
        print(f"❌ FAILED: An unexpected error occurred: {e}")

if __name__ == "__main__":
    test_trigger_generate_angles_bio() 