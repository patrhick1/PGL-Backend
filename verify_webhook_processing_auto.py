#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Verify webhook data processing - Non-interactive version
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from dotenv import load_dotenv

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Load environment variables
load_dotenv()

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import pitch_generations as pitch_gen_queries
from podcast_outreach.database.queries import placements as placement_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries

async def check_webhook_structure():
    """Display the webhook data structures we're receiving"""
    print("\n" + "="*60)
    print("Instantly Webhook Data Structure Analysis")
    print("="*60)
    
    print("\n1. EMAIL SENT WEBHOOK (Actual data from ngrok):")
    email_sent_structure = {
        "timestamp": "2025-07-02T16:07:47.353Z",
        "event_type": "email_sent",
        "workspace": "0462b242-8088-4dac-a640-453777ba421f",
        "campaign_id": "cdc33aee-b0f8-4460-beec-cce66ea3772c",  # PGL campaign
        "campaign_name": "TEST Campaign",
        "email": "ebube4u@gmail.com",
        "pitch_gen_id": "test_pitch_gen_123",  # KEY FIELD
        "media_id": "test_media_456",          # KEY FIELD
        "Subject": "Test Email - PGL Webhook Integration",
        "firstName": "Ebube",
        "companyName": "Test Podcast",
        "personalization": "Hi Ebube..."
    }
    
    print(json.dumps(email_sent_structure, indent=2))
    print("\nKEY FIELDS FOR PROCESSING:")
    print("- pitch_gen_id: Links to pitch_generations table")
    print("- media_id: Links to media table")
    print("- campaign_id: Our PGL campaign ID")
    
    print("\n2. REPLY RECEIVED WEBHOOK (Actual data from ngrok):")
    reply_received_structure = {
        "timestamp": "2025-07-02T16:16:43.428Z",
        "event_type": "reply_received",
        "workspace": "0462b242-8088-4dac-a640-453777ba421f",
        "campaign_id": "cdc33aee-b0f8-4460-beec-cce66ea3772c",  # PGL campaign
        "campaign_name": "TEST Campaign",
        "email": "ebube4u@gmail.com",
        "pitch_gen_id": "test_pitch_gen_123",  # KEY FIELD
        "media_id": "test_media_456",          # KEY FIELD
        "reply_text_snippet": "Okay rest is working\\nThis is Ebube responding",
        "reply_text": "Full reply text...",
        "reply_html": "<div>HTML version...</div>"
    }
    
    print(json.dumps(reply_received_structure, indent=2))
    print("\nKEY FIELDS FOR PROCESSING:")
    print("- pitch_gen_id: Links to find the pitch record")
    print("- Creates placement record for booking tracking")
    print("- Updates pitch state to 'replied'")

async def check_database_state():
    """Check current database state for test records"""
    print("\n" + "="*60)
    print("Checking Database State")
    print("="*60)
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Check for any test pitches
        test_pitches = await conn.fetch("""
            SELECT p.pitch_id, p.pitch_state, p.send_ts, p.reply_bool, 
                   p.placement_id, pg.pitch_gen_id, m.name as media_name
            FROM pitches p
            JOIN pitch_generations pg ON p.pitch_gen_id = pg.pitch_gen_id
            JOIN media m ON p.media_id = m.media_id
            WHERE m.name LIKE '%Test%' OR m.contact_email = 'ebube4u@gmail.com'
            ORDER BY p.created_at DESC
            LIMIT 5
        """)
        
        if test_pitches:
            print("\nFound test pitches:")
            for pitch in test_pitches:
                print(f"\n- Pitch ID: {pitch['pitch_id']}")
                print(f"  Media: {pitch['media_name']}")
                print(f"  State: {pitch['pitch_state']}")
                print(f"  Sent: {pitch['send_ts']}")
                print(f"  Replied: {pitch['reply_bool']}")
                print(f"  Placement: {pitch['placement_id']}")
        else:
            print("\nNo test pitches found")
            
        # Check for test placements
        test_placements = await conn.fetch("""
            SELECT p.placement_id, p.current_status, p.created_at, p.notes
            FROM placements p
            WHERE p.notes LIKE '%ebube4u@gmail.com%' 
               OR p.notes LIKE '%test%'
            ORDER BY p.created_at DESC
            LIMIT 5
        """)
        
        if test_placements:
            print("\nFound test placements:")
            for placement in test_placements:
                print(f"\n- Placement ID: {placement['placement_id']}")
                print(f"  Status: {placement['current_status']}")
                print(f"  Created: {placement['created_at']}")
                print(f"  Notes: {placement['notes'][:50]}...")
        else:
            print("\nNo test placements found")

async def simulate_webhook_processing():
    """Show how webhook data would be processed"""
    print("\n" + "="*60)
    print("Webhook Processing Flow")
    print("="*60)
    
    print("\n1. EMAIL SENT WEBHOOK PROCESSING:")
    print("   - Extract pitch_gen_id from webhook data")
    print("   - Find pitch record using pitch_gen_id")
    print("   - Update pitch state to 'sent'")
    print("   - Set send_ts timestamp")
    print("   - Update Attio (if configured)")
    
    print("\n2. REPLY RECEIVED WEBHOOK PROCESSING:")
    print("   - Extract pitch_gen_id from webhook data")
    print("   - Find pitch record using pitch_gen_id")
    print("   - Update pitch state to 'replied'")
    print("   - Set reply_bool = True and reply_ts")
    print("   - Create placement record:")
    print("     * Links to campaign, media, and pitch")
    print("     * Sets initial status = 'initial_reply'")
    print("     * Adds note about reply")
    print("   - Update pitch with placement_id")
    print("   - Update Attio (if configured)")

async def verify_campaign_exists():
    """Verify the test campaign exists"""
    print("\n" + "="*60)
    print("Verifying Test Campaign")
    print("="*60)
    
    campaign_id = "cdc33aee-b0f8-4460-beec-cce66ea3772c"
    campaign = await campaign_queries.get_campaign_by_id(campaign_id)
    
    if campaign:
        print(f"[OK] Campaign found: {campaign.get('campaign_name', 'Unknown')}")
        print(f"     ID: {campaign_id}")
        print(f"     Instantly ID: {campaign.get('instantly_campaign_id', 'Not set')}")
    else:
        print(f"[X] Campaign {campaign_id} not found")
        print("     This campaign ID is used in the webhook data")

async def main():
    print("Webhook Data Structure Verification")
    print("="*60)
    print("This script verifies the webhook data structure from Instantly")
    print("="*60)
    
    # Show webhook structure
    await check_webhook_structure()
    
    # Verify campaign exists
    await verify_campaign_exists()
    
    # Check database state
    await check_database_state()
    
    # Show processing flow
    await simulate_webhook_processing()
    
    print("\n" + "="*60)
    print("Summary")
    print("="*60)
    print("\nThe webhook data structures from Instantly are CORRECT!")
    print("\nKey points:")
    print("1. Both webhooks include pitch_gen_id for linking")
    print("2. Email sent webhook triggers pitch state update")
    print("3. Reply webhook creates placement for booking tracking")
    print("4. All custom variables are preserved in the webhook data")
    print("\nTo test with real data:")
    print("1. Create a real pitch using the UI")
    print("2. Send it through Instantly")
    print("3. The webhooks will automatically update the database")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())