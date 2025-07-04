#!/usr/bin/env python3
"""
Test script to verify bio generation is triggered after chatbot completion
"""

import asyncio
import json
from uuid import UUID
from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import chatbot_conversations as conv_queries

logger = get_logger(__name__)

async def test_bio_generation_trigger():
    """Test that bio generation is triggered after chatbot completion"""
    
    # Test campaign ID (you can update this with a real campaign ID)
    campaign_id = "57591092-58b7-4884-9bee-9df959869696"
    
    print(f"\nTesting bio generation trigger for campaign: {campaign_id}")
    print("="*60)
    
    # Check campaign data before
    campaign = await campaign_queries.get_campaign_by_id(UUID(campaign_id))
    if not campaign:
        print("[ERROR] Campaign not found")
        return
    
    print("\nBEFORE:")
    print(f"  - Has mock interview transcript: {'Yes' if campaign.get('mock_interview_transcript') else 'No'}")
    print(f"  - Has campaign bio: {'Yes' if campaign.get('campaign_bio') else 'No'}")
    print(f"  - Has campaign angles: {'Yes' if campaign.get('campaign_angles') else 'No'}")
    
    # Simulate what happens after chatbot completion
    print("\n[INFO] Simulating chatbot completion flow...")
    
    # Check if the mock interview transcript exists
    if campaign.get('mock_interview_transcript'):
        print("[OK] Mock interview transcript exists - bio generation would be triggered")
        
        # Check the actual bio generation endpoint
        try:
            from podcast_outreach.services.campaigns.angles_generator import AnglesProcessorPG
            angles_processor = AnglesProcessorPG()
            
            print("\n[INFO] Testing bio generation directly...")
            result = await angles_processor.process_campaign(campaign_id)
            
            if result.get("status") == "success":
                print("[SUCCESS] Bio generation completed successfully!")
                
                # Check campaign data after
                updated_campaign = await campaign_queries.get_campaign_by_id(UUID(campaign_id))
                print("\nAFTER:")
                print(f"  - Has campaign bio: {'Yes' if updated_campaign.get('campaign_bio') else 'No'}")
                print(f"  - Has campaign angles: {'Yes' if updated_campaign.get('campaign_angles') else 'No'}")
            else:
                print(f"[ERROR] Bio generation failed: {result.get('reason', 'Unknown error')}")
            
            angles_processor.cleanup()
            
        except Exception as e:
            print(f"[ERROR] Failed to test bio generation: {e}")
    else:
        print("[WARNING] No mock interview transcript found - bio generation would not be triggered")
        print("          The chatbot should generate this before completion")
    
    print("\n[INFO] Test complete!")

if __name__ == "__main__":
    asyncio.run(test_bio_generation_trigger())