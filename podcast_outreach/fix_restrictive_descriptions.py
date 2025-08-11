#!/usr/bin/env python3
"""
Fix overly restrictive ideal_podcast_descriptions for existing campaigns.
This script identifies campaigns with restrictive descriptions and regenerates them.
"""

import asyncio
import logging
import sys
import os
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.services.ai.openai_client import OpenAIService
from podcast_outreach.generate_ideal_podcast_descriptions import generate_ideal_description

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def is_restrictive_description(description: str) -> bool:
    """Check if a description is likely too restrictive."""
    if not description:
        return False
    
    # Indicators of overly restrictive descriptions
    restrictive_indicators = [
        # Multiple ANDs or commas suggesting ALL requirements
        description.count(',') >= 3,
        # Contains words suggesting ALL criteria must be met
        all(word in description.lower() for word in ['sales', 'web', 'customer', 'leadership']),
        # Very long descriptions trying to cover everything
        len(description) > 300,
        # Missing flexible language
        not any(phrase in description.lower() for phrase in ['or', 'particularly', 'especially']),
        # Contains "with audiences interested in" which is often too specific
        'with audiences interested in' in description.lower()
    ]
    
    # If 2 or more indicators are present, it's likely restrictive
    return sum(restrictive_indicators) >= 2

async def analyze_and_fix_campaigns(dry_run: bool = True):
    """Analyze campaigns and fix restrictive descriptions."""
    pool = await get_db_pool()
    openai_service = OpenAIService()
    
    # Get all campaigns with descriptions
    query = """
    SELECT campaign_id, campaign_name, ideal_podcast_description, questionnaire_responses
    FROM campaigns
    WHERE ideal_podcast_description IS NOT NULL 
    AND ideal_podcast_description != ''
    AND questionnaire_responses IS NOT NULL
    ORDER BY campaign_name
    """
    
    async with pool.acquire() as conn:
        campaigns = await conn.fetch(query)
    
    logger.info(f"Found {len(campaigns)} campaigns with descriptions")
    
    restrictive_campaigns = []
    for campaign in campaigns:
        description = campaign['ideal_podcast_description']
        if is_restrictive_description(description):
            restrictive_campaigns.append(campaign)
    
    logger.info(f"Found {len(restrictive_campaigns)} campaigns with potentially restrictive descriptions")
    
    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        print("\n=== CAMPAIGNS WITH RESTRICTIVE DESCRIPTIONS ===\n")
        for campaign in restrictive_campaigns:
            print(f"Campaign: {campaign['campaign_name']}")
            print(f"Current Description: {campaign['ideal_podcast_description'][:200]}...")
            print("-" * 60)
    else:
        logger.info("LIVE MODE - Updating restrictive descriptions")
        updated_count = 0
        
        for campaign in restrictive_campaigns:
            campaign_id = campaign['campaign_id']
            campaign_name = campaign['campaign_name']
            old_description = campaign['ideal_podcast_description']
            
            logger.info(f"Processing: {campaign_name}")
            print(f"\nCampaign: {campaign_name}")
            print(f"Old: {old_description[:150]}...")
            
            # Generate new description
            new_description = await generate_ideal_description(dict(campaign), openai_service)
            
            if new_description and new_description != old_description:
                # Update the campaign
                update_query = """
                UPDATE campaigns
                SET ideal_podcast_description = $1
                WHERE campaign_id = $2
                """
                
                async with pool.acquire() as conn:
                    await conn.execute(update_query, new_description, campaign_id)
                
                print(f"New: {new_description}")
                print("✓ Updated successfully")
                updated_count += 1
            else:
                print("✗ Could not generate better description")
            
            print("-" * 60)
            
            # Small delay to avoid rate limits
            await asyncio.sleep(1)
        
        logger.info(f"Updated {updated_count}/{len(restrictive_campaigns)} campaigns")
    
    # Show statistics
    print("\n=== ANALYSIS SUMMARY ===")
    print(f"Total campaigns analyzed: {len(campaigns)}")
    print(f"Restrictive descriptions found: {len(restrictive_campaigns)} ({len(restrictive_campaigns)/len(campaigns)*100:.1f}%)")
    
    if restrictive_campaigns:
        print("\nCommon patterns in restrictive descriptions:")
        patterns = {
            'Multiple requirements (AND logic)': 0,
            'Too many commas': 0,
            'Very long (>300 chars)': 0,
            'Missing flexible language': 0,
            'Overly specific audience': 0
        }
        
        for campaign in restrictive_campaigns:
            desc = campaign['ideal_podcast_description']
            if desc.count(',') >= 3:
                patterns['Too many commas'] += 1
            if len(desc) > 300:
                patterns['Very long (>300 chars)'] += 1
            if not any(word in desc.lower() for word in ['or', 'particularly', 'especially']):
                patterns['Missing flexible language'] += 1
            if 'with audiences interested in' in desc.lower():
                patterns['Overly specific audience'] += 1
            if all(word in desc.lower() for word in ['and', ',']):
                patterns['Multiple requirements (AND logic)'] += 1
        
        for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                print(f"  - {pattern}: {count} campaigns")

async def main():
    """Main entry point."""
    import sys
    
    # Check for --live flag
    dry_run = '--live' not in sys.argv
    
    if not dry_run:
        confirm = input("⚠️  LIVE MODE: This will update campaign descriptions. Continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            return
    
    await analyze_and_fix_campaigns(dry_run=dry_run)

if __name__ == "__main__":
    print("Campaign Description Analyzer & Fixer")
    print("=====================================")
    print("Usage: python fix_restrictive_descriptions.py [--live]")
    print("  Without --live: Dry run mode (analysis only)")
    print("  With --live: Actually update the descriptions")
    print()
    
    asyncio.run(main())