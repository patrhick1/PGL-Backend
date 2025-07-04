#!/usr/bin/env python3
"""
Check campaign data after chatbot completion
"""

import asyncio
import json
from uuid import UUID
from podcast_outreach.database.queries import campaigns as campaign_queries

async def check_campaign_data():
    campaign_id = "57591092-58b7-4884-9bee-9df959869696"
    
    print(f"\nChecking campaign data for: {campaign_id}")
    print("="*60)
    
    # Get campaign data
    campaign = await campaign_queries.get_campaign_by_id(UUID(campaign_id))
    
    if campaign:
        print("\n1. QUESTIONNAIRE DATA:")
        if campaign.get('questionnaire_data'):
            q_data = json.loads(campaign['questionnaire_data'])
            print(f"   - Name: {q_data.get('name')}")
            print(f"   - Email: {q_data.get('email')}")
            print(f"   - Success Story: {q_data.get('successStory', 'Not found')[:100]}...")
        else:
            print("   [X] No questionnaire data found")
            
        print("\n2. MOCK INTERVIEW TRANSCRIPT:")
        if campaign.get('mock_interview_transcript'):
            print(f"   [OK] Transcript generated ({len(campaign['mock_interview_transcript'])} chars)")
        else:
            print("   [X] No transcript found")
            
        print("\n3. QUESTIONNAIRE KEYWORDS:")
        if campaign.get('questionnaire_keywords'):
            keywords = campaign['questionnaire_keywords']
            if isinstance(keywords, str):
                keywords = json.loads(keywords)
            print(f"   [OK] {len(keywords)} keywords: {', '.join(keywords[:5])}...")
        else:
            print("   [X] No keywords found")
            
        print("\n4. IDEAL PODCAST DESCRIPTION:")
        if campaign.get('ideal_podcast_description'):
            print(f"   [OK] {campaign['ideal_podcast_description'][:150]}...")
        else:
            print("   [X] No ideal description found")
            
        print("\n5. CAMPAIGN STATUS:")
        print(f"   - Status: {campaign.get('status')}")
        print(f"   - Has angles/bio: {campaign.get('has_angles_bio')}")
        print(f"   - Has media kit: {campaign.get('has_media_kit')}")
        
    else:
        print("[X] Campaign not found")

if __name__ == "__main__":
    asyncio.run(check_campaign_data())