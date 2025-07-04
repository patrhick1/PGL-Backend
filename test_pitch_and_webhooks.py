#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Test script to:
1. Send a pitch to your email using the campaign
2. Simulate Instantly webhook responses
"""

import asyncio
import requests
import json
from datetime import datetime
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "http://localhost:8000"  # Your FastAPI localhost
NGROK_URL = "YOUR_NGROK_URL_HERE"  # Replace with your actual ngrok URL after running ngrok

# Test data
CAMPAIGN_ID = "cdc33aee-b0f8-4460-beec-cce66ea3772c"
TEST_EMAIL = "paschal@3rdbrain.co"

# You'll need a valid auth token - get this from your login
AUTH_TOKEN = "YOUR_AUTH_TOKEN_HERE"  # Replace with actual token

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {AUTH_TOKEN}"
}

async def find_or_create_test_match():
    """Find an existing match for the campaign or provide instructions to create one"""
    logger.info("Checking for matches in the campaign...")
    
    # First, let's check if there are any matches for this campaign
    response = requests.get(
        f"{BASE_URL}/api/match-suggestions",
        params={"campaign_id": CAMPAIGN_ID},
        headers=headers
    )
    
    if response.status_code == 200:
        matches = response.json()
        if matches:
            # Find an approved match
            approved_matches = [m for m in matches if m.get("status") == "approved"]
            if approved_matches:
                match_id = approved_matches[0]["match_id"]
                logger.info(f"Found approved match: {match_id}")
                return match_id
            else:
                logger.info("Found matches but none are approved. First match needs to be approved.")
                if matches:
                    logger.info(f"Available match IDs: {[m['match_id'] for m in matches]}")
                    logger.info("Please approve a match first using the admin interface.")
                return None
        else:
            logger.info("No matches found for this campaign.")
            logger.info("You need to create matches first by running the discovery and vetting pipeline.")
            return None
    else:
        logger.error(f"Failed to fetch matches: {response.status_code} - {response.text}")
        return None

async def generate_pitch(match_id):
    """Generate a pitch for the match"""
    logger.info(f"Generating pitch for match {match_id}...")
    
    # First, get available pitch templates
    templates_response = requests.get(
        f"{BASE_URL}/api/pitch-templates",
        headers=headers
    )
    
    if templates_response.status_code != 200:
        logger.error("Failed to fetch pitch templates")
        return None
    
    templates = templates_response.json()
    if not templates:
        logger.error("No pitch templates available")
        return None
    
    # Use the first template
    template_id = templates[0]["pitch_template_id"]
    logger.info(f"Using template: {template_id}")
    
    # Generate the pitch
    payload = {
        "match_id": match_id,
        "pitch_template_id": template_id
    }
    
    response = requests.post(
        f"{BASE_URL}/api/pitches/generate",
        json=payload,
        headers=headers
    )
    
    if response.status_code in [200, 202]:
        result = response.json()
        logger.info(f"Pitch generated successfully: {result}")
        return result.get("pitch_gen_id")
    else:
        logger.error(f"Failed to generate pitch: {response.status_code} - {response.text}")
        return None

async def approve_pitch(pitch_gen_id):
    """Approve the generated pitch"""
    logger.info(f"Approving pitch generation {pitch_gen_id}...")
    
    response = requests.patch(
        f"{BASE_URL}/api/pitches/generations/{pitch_gen_id}/approve",
        headers=headers
    )
    
    if response.status_code == 200:
        logger.info("Pitch approved successfully")
        return True
    else:
        logger.error(f"Failed to approve pitch: {response.status_code} - {response.text}")
        return False

async def get_pitch_id_from_generation(pitch_gen_id):
    """Get the pitch ID from the generation ID"""
    response = requests.get(
        f"{BASE_URL}/api/pitches",
        params={"limit": 100},
        headers=headers
    )
    
    if response.status_code == 200:
        pitches = response.json()
        for pitch in pitches:
            if pitch.get("pitch_gen_id") == pitch_gen_id:
                return pitch.get("pitch_id")
    return None

async def send_pitch(pitch_id):
    """Send the pitch via Instantly"""
    logger.info(f"Sending pitch {pitch_id}...")
    
    # Override the recipient email for testing
    # Note: You might need to modify the pitch record to use your test email
    # This depends on how your system handles email addresses
    
    response = requests.post(
        f"{BASE_URL}/api/pitches/{pitch_id}/send",
        headers=headers
    )
    
    if response.status_code in [200, 202]:
        logger.info("Pitch sent successfully!")
        return True
    else:
        logger.error(f"Failed to send pitch: {response.status_code} - {response.text}")
        return False

def simulate_instantly_email_sent_webhook(lead_email, campaign_name="Test Campaign"):
    """Simulate Instantly 'email sent' webhook"""
    logger.info("\n" + "="*60)
    logger.info("Simulating Instantly 'Email Sent' Webhook")
    logger.info("="*60)
    
    webhook_data = {
        "event": "email_sent",
        "timestamp": datetime.utcnow().isoformat(),
        "lead_id": "lead_123456",
        "campaign_id": CAMPAIGN_ID,
        "lead": {
            "email": lead_email,
            "first_name": "Paschal",
            "last_name": "Test",
            "company": "3rd Brain"
        },
        "email_details": {
            "subject": "Your podcast would be perfect for our client",
            "sent_at": datetime.utcnow().isoformat(),
            "template_id": "template_1"
        },
        # Attio integration expects these fields
        "airID": "attio_record_123",  # This would be the actual Attio record ID
        "personalization": "Hi Paschal, I noticed your work at 3rd Brain..."
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/webhooks/instantly-email-sent",
            json=webhook_data,
            headers={"Content-Type": "application/json"}
        )
        
        logger.info(f"Webhook response: {response.status_code} - {response.text}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send webhook: {e}")
        return False

def simulate_instantly_reply_webhook(lead_email, reply_text):
    """Simulate Instantly 'reply received' webhook"""
    logger.info("\n" + "="*60)
    logger.info("Simulating Instantly 'Reply Received' Webhook")
    logger.info("="*60)
    
    webhook_data = {
        "event": "reply_received",
        "timestamp": datetime.utcnow().isoformat(),
        "lead_id": "lead_123456",
        "campaign_id": CAMPAIGN_ID,
        "lead": {
            "email": lead_email,
            "first_name": "Paschal",
            "last_name": "Test"
        },
        "reply": {
            "subject": "Re: Your podcast would be perfect for our client",
            "body": reply_text,
            "received_at": datetime.utcnow().isoformat(),
            "snippet": reply_text[:100]  # First 100 chars
        },
        # Attio integration expects these
        "airID": "attio_record_123",
        "reply_text_snippet": reply_text[:100]
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/webhooks/instantly-reply-received",
            json=webhook_data,
            headers={"Content-Type": "application/json"}
        )
        
        logger.info(f"Webhook response: {response.status_code} - {response.text}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send webhook: {e}")
        return False

async def main():
    """Main test flow"""
    logger.info("Starting Pitch and Webhook Test")
    logger.info(f"Campaign ID: {CAMPAIGN_ID}")
    logger.info(f"Test Email: {TEST_EMAIL}")
    
    print("\n" + "="*60)
    print("IMPORTANT: Before running this test:")
    print("1. Make sure your FastAPI app is running: pgl_env/Scripts/python.exe -m uvicorn podcast_outreach.main:app --reload")
    print("2. Run ngrok in another terminal: ngrok http 8000")
    print("3. Update NGROK_URL in this script with the URL from ngrok")
    print("4. Get your AUTH_TOKEN by logging into the system")
    print("5. Update AUTH_TOKEN in this script")
    print("="*60)
    
    input("\nPress Enter when ready to continue...")
    
    # Step 1: Find or create a match
    match_id = await find_or_create_test_match()
    if not match_id:
        logger.error("No match available. Please create and approve a match first.")
        return
    
    # Step 2: Generate a pitch
    pitch_gen_id = await generate_pitch(match_id)
    if not pitch_gen_id:
        logger.error("Failed to generate pitch")
        return
    
    # Wait a bit for generation to complete
    logger.info("Waiting for pitch generation to complete...")
    await asyncio.sleep(5)
    
    # Step 3: Approve the pitch
    if not await approve_pitch(pitch_gen_id):
        logger.error("Failed to approve pitch")
        return
    
    # Step 4: Get the pitch ID
    pitch_id = await get_pitch_id_from_generation(pitch_gen_id)
    if not pitch_id:
        logger.error("Failed to find pitch ID")
        return
    
    logger.info(f"Pitch ID: {pitch_id}")
    
    # Step 5: Send the pitch
    logger.warning("\nNOTE: The pitch will be sent to the email configured in the system.")
    logger.warning("To test with your email, you may need to update the recipient in the database.")
    input("\nPress Enter to send the pitch...")
    
    if not await send_pitch(pitch_id):
        logger.error("Failed to send pitch")
        return
    
    # Step 6: Simulate webhooks
    logger.info("\nWaiting 5 seconds before simulating webhooks...")
    await asyncio.sleep(5)
    
    # Simulate email sent webhook
    simulate_instantly_email_sent_webhook(TEST_EMAIL)
    
    # Wait before simulating reply
    logger.info("\nWaiting 5 seconds before simulating reply...")
    await asyncio.sleep(5)
    
    # Simulate reply webhook
    reply_text = """
    Hi there!
    
    Thanks for reaching out. I'm definitely interested in learning more about your client.
    
    Could you tell me:
    1. What's the client's area of expertise?
    2. What topics would they want to discuss?
    3. Are they available for a 30-minute interview next week?
    
    Best regards,
    Paschal
    """
    
    simulate_instantly_reply_webhook(TEST_EMAIL, reply_text)
    
    logger.info("\n" + "="*60)
    logger.info("Test completed!")
    logger.info("Check your FastAPI logs to see how the webhooks were processed")
    logger.info("="*60)

if __name__ == "__main__":
    asyncio.run(main())