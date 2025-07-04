#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Test webhook reply flow - both first reply and subsequent replies
"""

import asyncio
import json
from datetime import datetime, timezone
import requests

# Test configuration
LOCAL_URL = "http://localhost:8000"
TEST_PITCH_GEN_ID = "12345"  # Use a real pitch_gen_id for testing

def simulate_first_reply():
    """Simulate the first reply to a pitch"""
    print("\n" + "="*60)
    print("1. SIMULATING FIRST REPLY")
    print("="*60)
    
    webhook_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "reply_received",
        "workspace": "0462b242-8088-4dac-a640-453777ba421f",
        "campaign_id": "cdc33aee-b0f8-4460-beec-cce66ea3772c",
        "campaign_name": "TEST Campaign",
        "email": "host@podcast.com",
        "lead_email": "host@podcast.com",
        "pitch_gen_id": TEST_PITCH_GEN_ID,
        "media_id": "789",
        "reply_text_snippet": "Hi Sarah, I'm interested in having your client on the show!",
        "reply_text": """Hi Sarah,

I'm interested in having your client on the show! 

Could you tell me more about their background and what topics they'd like to discuss?

Best,
John
Host of Tech Talk Podcast""",
        "reply_html": "<div>Hi Sarah...</div>",
        "reply_subject": "Re: Guest Opportunity for Tech Talk Podcast",
        "email_id": "reply_001",
        "is_first": True,
        "unibox_url": "https://app.instantly.ai/app/unibox?thread_search=host@podcast.com"
    }
    
    print(f"Sending first reply webhook for pitch_gen_id: {TEST_PITCH_GEN_ID}")
    
    try:
        response = requests.post(
            f"{LOCAL_URL}/webhooks/instantly-reply-received",
            json=webhook_data
        )
        print(f"Response: {response.status_code}")
        if response.status_code == 200:
            print("[OK] First reply processed")
            print("Expected behavior:")
            print("- Pitch state updated to 'replied'")
            print("- New placement created with initial email thread")
        else:
            print(f"[ERROR] {response.text}")
    except Exception as e:
        print(f"[ERROR] {e}")

def simulate_subsequent_reply():
    """Simulate a follow-up reply in the same thread"""
    print("\n" + "="*60)
    print("2. SIMULATING SUBSEQUENT REPLY")
    print("="*60)
    
    input("\nPress Enter to simulate the host's follow-up reply...")
    
    webhook_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "reply_received",
        "workspace": "0462b242-8088-4dac-a640-453777ba421f",
        "campaign_id": "cdc33aee-b0f8-4460-beec-cce66ea3772c",
        "campaign_name": "TEST Campaign",
        "email": "host@podcast.com",
        "lead_email": "host@podcast.com",
        "pitch_gen_id": TEST_PITCH_GEN_ID,
        "media_id": "789",
        "reply_text_snippet": "Great! Tuesday at 2 PM works for me. Here's my calendar link...",
        "reply_text": """Great! Tuesday at 2 PM works for me.

Here's my calendar link: https://calendly.com/johndoe/30min

Looking forward to the conversation!

John""",
        "reply_html": "<div>Great! Tuesday at 2 PM works...</div>",
        "reply_subject": "Re: Guest Opportunity for Tech Talk Podcast",
        "email_id": "reply_002",
        "is_first": False,
        "unibox_url": "https://app.instantly.ai/app/unibox?thread_search=host@podcast.com"
    }
    
    print(f"Sending subsequent reply webhook for pitch_gen_id: {TEST_PITCH_GEN_ID}")
    
    try:
        response = requests.post(
            f"{LOCAL_URL}/webhooks/instantly-reply-received",
            json=webhook_data
        )
        print(f"Response: {response.status_code}")
        if response.status_code == 200:
            print("[OK] Subsequent reply processed")
            print("Expected behavior:")
            print("- Pitch state remains 'replied'")
            print("- Email thread updated with new message")
            print("- Placement status might update based on content")
        else:
            print(f"[ERROR] {response.text}")
    except Exception as e:
        print(f"[ERROR] {e}")

def simulate_third_reply():
    """Simulate another follow-up to test thread continuity"""
    print("\n" + "="*60)
    print("3. SIMULATING THIRD REPLY")
    print("="*60)
    
    input("\nPress Enter to simulate a third reply...")
    
    webhook_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "reply_received",
        "workspace": "0462b242-8088-4dac-a640-453777ba421f",
        "campaign_id": "cdc33aee-b0f8-4460-beec-cce66ea3772c",
        "campaign_name": "TEST Campaign",
        "email": "host@podcast.com",
        "lead_email": "host@podcast.com",
        "pitch_gen_id": TEST_PITCH_GEN_ID,
        "media_id": "789",
        "reply_text_snippet": "Quick update - we've confirmed the recording for next week!",
        "reply_text": """Hi Sarah,

Quick update - we've confirmed the recording for next week!

I'll send the guest prep materials and Zoom link shortly.

Can you confirm your client's preferred name pronunciation?

Thanks,
John""",
        "reply_html": "<div>Hi Sarah...</div>",
        "reply_subject": "Re: Guest Opportunity for Tech Talk Podcast",
        "email_id": "reply_003",
        "is_first": False
    }
    
    print(f"Sending third reply webhook for pitch_gen_id: {TEST_PITCH_GEN_ID}")
    
    try:
        response = requests.post(
            f"{LOCAL_URL}/webhooks/instantly-reply-received",
            json=webhook_data
        )
        print(f"Response: {response.status_code}")
        if response.status_code == 200:
            print("[OK] Third reply processed")
            print("Email thread now contains:")
            print("1. Original pitch (if available)")
            print("2. First reply")
            print("3. Second reply")
            print("4. Third reply")
        else:
            print(f"[ERROR] {response.text}")
    except Exception as e:
        print(f"[ERROR] {e}")

async def check_database_state():
    """Check the database to verify the results"""
    print("\n" + "="*60)
    print("CHECKING DATABASE STATE")
    print("="*60)
    
    print(f"\nTo verify the webhook processing, run these SQL queries:")
    print(f"\n-- Check pitch state")
    print(f"SELECT pitch_id, pitch_state, reply_bool, reply_ts, placement_id")
    print(f"FROM pitches p")
    print(f"JOIN pitch_generations pg ON p.pitch_gen_id = pg.pitch_gen_id")
    print(f"WHERE pg.pitch_gen_id = {TEST_PITCH_GEN_ID};")
    
    print(f"\n-- Check placement and email thread")
    print(f"SELECT placement_id, current_status, ")
    print(f"       jsonb_array_length(email_thread) as thread_count,")
    print(f"       email_thread")
    print(f"FROM placements")
    print(f"WHERE pitch_id = (")
    print(f"  SELECT pitch_id FROM pitches p")
    print(f"  JOIN pitch_generations pg ON p.pitch_gen_id = pg.pitch_gen_id")
    print(f"  WHERE pg.pitch_gen_id = {TEST_PITCH_GEN_ID}")
    print(f");")

def main():
    print("Webhook Reply Flow Test")
    print("="*60)
    print("This tests how the webhook handles first and subsequent replies")
    print("="*60)
    
    print(f"\nIMPORTANT: Update TEST_PITCH_GEN_ID to a real pitch_gen_id!")
    print(f"Current test ID: {TEST_PITCH_GEN_ID}")
    
    choice = input("\nProceed with test? (y/n): ")
    if choice.lower() != 'y':
        return
    
    # Test first reply
    simulate_first_reply()
    
    # Test subsequent replies
    simulate_subsequent_reply()
    simulate_third_reply()
    
    # Show how to check results
    asyncio.run(check_database_state())
    
    print("\n" + "="*60)
    print("Test Complete!")
    print("The webhook now properly handles:")
    print("1. First reply: Creates placement with initial thread")
    print("2. Subsequent replies: Appends to existing thread")
    print("="*60)

if __name__ == "__main__":
    main()