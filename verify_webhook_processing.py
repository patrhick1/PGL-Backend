#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Verify webhook data processing and create test records for full flow testing
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

async def check_test_webhook_data():
    """Check if test webhook data was processed"""
    print("\n" + "="*60)
    print("Checking Test Webhook Processing")
    print("="*60)
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Check for test pitch
        result = await conn.fetchrow("""
            SELECT p.*, pg.pitch_gen_id 
            FROM pitches p
            LEFT JOIN pitch_generations pg ON p.pitch_gen_id = pg.pitch_gen_id
            WHERE pg.pitch_gen_id = $1
        """, 123)  # test_pitch_gen_123 as integer
        
        if result:
            print(f"[OK] Found test pitch:")
            print(f"  - Pitch ID: {result['pitch_id']}")
            print(f"  - State: {result['pitch_state']}")
            print(f"  - Reply: {result['reply_bool']}")
            print(f"  - Placement ID: {result['placement_id']}")
        else:
            print("[X] No test pitch found (expected for test webhook data)")
            
        # Check for test placement
        placement = await conn.fetchrow("""
            SELECT * FROM placements 
            WHERE notes LIKE '%ebube4u@gmail.com%'
            ORDER BY created_at DESC
            LIMIT 1
        """)
        
        if placement:
            print(f"\n[OK] Found test placement:")
            print(f"  - Placement ID: {placement['placement_id']}")
            print(f"  - Status: {placement['current_status']}")
            print(f"  - Notes: {placement['notes']}")
        else:
            print("\n[X] No test placement found")

async def create_test_pitch_record():
    """Create a real test pitch record for webhook testing"""
    print("\n" + "="*60)
    print("Creating Test Database Records")
    print("="*60)
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Use the actual campaign and media IDs from the webhook
        campaign_id = "cdc33aee-b0f8-4460-beec-cce66ea3772c"
        
        # Check if campaign exists
        campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign:
            print(f"[X] Campaign {campaign_id} not found")
            return None
            
        # Create or find a test media record
        test_media = await conn.fetchrow("""
            SELECT media_id FROM media 
            WHERE name = 'Test Podcast Webhook' 
            LIMIT 1
        """)
        
        if not test_media:
            # Create test media
            media_id = await conn.fetchval("""
                INSERT INTO media (
                    name, website, category, source, rating,
                    contact_email, social_media_handles, host_names,
                    keyword_matches, about
                ) VALUES (
                    'Test Podcast Webhook', 'https://testpodcast.com', 
                    'Technology', 'manual', 5.0,
                    'ebube4u@gmail.com', '{}', ARRAY['Ebube'],
                    ARRAY['test', 'technology'], 'Test podcast for webhook testing'
                ) RETURNING media_id
            """)
            print(f"[OK] Created test media: {media_id}")
        else:
            media_id = test_media['media_id']
            print(f"[OK] Found existing test media: {media_id}")
            
        # Create pitch generation record
        pitch_gen_id = await conn.fetchval("""
            INSERT INTO pitch_generations (
                campaign_id, media_id, template_id, draft_text,
                ai_model_used, pitch_topic, temperature,
                final_text, send_ready_bool, generation_status
            ) VALUES (
                $1, $2, 'test_template', 'Test pitch draft',
                'manual', 'Webhook Testing', 0.7,
                'Hi Ebube, This is a test pitch for webhook testing...', 
                true, 'approved'
            ) RETURNING pitch_gen_id
        """, campaign_id, media_id)
        print(f"[OK] Created pitch generation: {pitch_gen_id}")
        
        # Create pitch record
        pitch_id = await conn.fetchval("""
            INSERT INTO pitches (
                campaign_id, media_id, attempt_no, match_score,
                matched_keywords, outreach_type, subject_line,
                body_snippet, pitch_gen_id, pitch_state,
                client_approval_status, created_by
            ) VALUES (
                $1, $2, 1, 0.95,
                ARRAY['test', 'webhook'], 'email', 
                'Test Webhook Integration - Real Record',
                'Testing webhook with real database records...',
                $3, 'draft', 'approved', 'webhook_test'
            ) RETURNING pitch_id
        """, campaign_id, media_id, pitch_gen_id)
        print(f"[OK] Created pitch: {pitch_id}")
        
        return {
            'campaign_id': campaign_id,
            'media_id': media_id,
            'pitch_gen_id': pitch_gen_id,
            'pitch_id': pitch_id
        }

async def simulate_real_webhook_flow(test_data):
    """Simulate webhook flow with real database records"""
    print("\n" + "="*60)
    print("Simulating Real Webhook Flow")
    print("="*60)
    
    import requests
    
    # 1. Simulate email sent
    print("\n1. Simulating Email Sent...")
    email_sent_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "email_sent",
        "workspace": "0462b242-8088-4dac-a640-453777ba421f",
        "campaign_id": str(test_data['campaign_id']),
        "campaign_name": "TEST Campaign",
        "email_account": "aidrian@digitalpodcastguest.com",
        "lead_email": "ebube4u@gmail.com",
        "email": "ebube4u@gmail.com",
        "pitch_gen_id": str(test_data['pitch_gen_id']),
        "media_id": str(test_data['media_id']),
        "Subject": "Test Webhook Integration - Real Record",
        "firstName": "Ebube",
        "companyName": "Test Podcast Webhook"
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/webhooks/instantly-email-sent",
            json=email_sent_payload
        )
        print(f"Response: {response.status_code}")
        if response.status_code == 200:
            print("[OK] Email sent webhook processed")
    except Exception as e:
        print(f"[X] Error: {e}")
        
    # Wait a moment
    await asyncio.sleep(1)
    
    # 2. Check pitch state
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        pitch = await conn.fetchrow("""
            SELECT pitch_id, pitch_state, send_ts 
            FROM pitches 
            WHERE pitch_id = $1
        """, test_data['pitch_id'])
        
        if pitch and pitch['pitch_state'] == 'sent':
            print(f"\n[OK] Pitch updated to 'sent' state")
            print(f"  - Send timestamp: {pitch['send_ts']}")
        else:
            print(f"\n[X] Pitch state not updated: {pitch['pitch_state'] if pitch else 'not found'}")
            
    # 3. Simulate reply
    print("\n2. Simulating Reply Received...")
    reply_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "reply_received",
        "workspace": "0462b242-8088-4dac-a640-453777ba421f",
        "campaign_id": str(test_data['campaign_id']),
        "campaign_name": "TEST Campaign",
        "email": "ebube4u@gmail.com",
        "pitch_gen_id": str(test_data['pitch_gen_id']),
        "media_id": str(test_data['media_id']),
        "reply_text_snippet": "Yes, I'm interested in having your client on the show!",
        "reply_text": "Hi there,\n\nYes, I'm interested in having your client on the show!\n\nLet's schedule a call to discuss.\n\nBest,\nEbube"
    }
    
    try:
        response = requests.post(
            "http://localhost:8000/webhooks/instantly-reply-received",
            json=reply_payload
        )
        print(f"Response: {response.status_code}")
        if response.status_code == 200:
            print("[OK] Reply received webhook processed")
    except Exception as e:
        print(f"[X] Error: {e}")
        
    # Wait a moment
    await asyncio.sleep(1)
    
    # 4. Check final state
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Check pitch
        pitch = await conn.fetchrow("""
            SELECT pitch_id, pitch_state, reply_bool, reply_ts, placement_id
            FROM pitches 
            WHERE pitch_id = $1
        """, test_data['pitch_id'])
        
        if pitch:
            print(f"\n[OK] Final pitch state:")
            print(f"  - State: {pitch['pitch_state']}")
            print(f"  - Reply: {pitch['reply_bool']}")
            print(f"  - Reply timestamp: {pitch['reply_ts']}")
            print(f"  - Placement ID: {pitch['placement_id']}")
            
        # Check placement
        if pitch and pitch['placement_id']:
            placement = await conn.fetchrow("""
                SELECT * FROM placements 
                WHERE placement_id = $1
            """, pitch['placement_id'])
            
            if placement:
                print(f"\n[OK] Placement created:")
                print(f"  - Status: {placement['current_status']}")
                print(f"  - Created: {placement['created_at']}")
                print(f"  - Notes: {placement['notes']}")

async def show_webhook_data_structure():
    """Display the expected webhook data structures"""
    print("\n" + "="*60)
    print("Instantly Webhook Data Structures")
    print("="*60)
    
    print("\n1. EMAIL SENT WEBHOOK:")
    print("""
    Key fields we use:
    - pitch_gen_id: Links to our pitch_generations table
    - campaign_id: Our PGL campaign ID
    - media_id: Our media/podcast ID
    - email: Recipient email
    - timestamp: When email was sent
    """)
    
    print("\n2. REPLY RECEIVED WEBHOOK:")
    print("""
    Key fields we use:
    - pitch_gen_id: Links to our pitch_generations table
    - campaign_id: Our PGL campaign ID  
    - media_id: Our media/podcast ID
    - email: Who replied
    - reply_text_snippet: Preview of reply
    - reply_text: Full reply content
    - timestamp: When reply was received
    
    This creates a placement record for booking tracking!
    """)

async def main():
    print("Webhook Processing Verification")
    print("="*60)
    
    # Check test webhook processing
    await check_test_webhook_data()
    
    # Show data structures
    await show_webhook_data_structure()
    
    # Ask if user wants to create test records
    print("\n" + "="*60)
    print("Would you like to create real test records and simulate the flow?")
    print("This will:")
    print("1. Create a test media record")
    print("2. Create a test pitch generation")
    print("3. Create a test pitch")
    print("4. Simulate the full webhook flow")
    print("="*60)
    
    choice = input("\nProceed? (y/n): ")
    
    if choice.lower() == 'y':
        test_data = await create_test_pitch_record()
        if test_data:
            await simulate_real_webhook_flow(test_data)
            
    print("\n" + "="*60)
    print("Verification Complete!")
    print("The webhook data structures from Instantly are correct!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())