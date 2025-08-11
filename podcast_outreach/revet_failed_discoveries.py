#!/usr/bin/env python3
"""
Revet failed discoveries for campaigns with updated ideal_podcast_descriptions.
This script carefully revets podcasts that scored below 50 and moves them through
the pipeline if they pass with the new description.
"""

import asyncio
import logging
import sys
import os
from typing import Dict, Any, List
from datetime import datetime, timezone
import uuid

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import review_tasks as review_task_queries
from podcast_outreach.services.matches.enhanced_vetting_agent import EnhancedVettingAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DiscoveryRevetter:
    """Safely revet failed discoveries and move them through the pipeline."""
    
    def __init__(self):
        self.vetting_agent = EnhancedVettingAgent()
        self.pool = None
        self.stats = {
            'total_reviewed': 0,
            'revetting_attempted': 0,
            'revetting_succeeded': 0,
            'new_passes': 0,
            'matches_created': 0,
            'review_tasks_created': 0,
            'errors': []
        }
    
    async def initialize(self):
        """Initialize database connection pool."""
        self.pool = await get_db_pool()
    
    async def get_failed_discoveries(self, campaign_id: str) -> List[Dict[str, Any]]:
        """Get all discoveries with vetting_score < 50 for a campaign."""
        query = """
        SELECT 
            cmd.id,
            cmd.campaign_id,
            cmd.media_id,
            cmd.discovery_keyword,
            cmd.vetting_score,
            cmd.vetting_status,
            cmd.match_created,
            m.name as media_name,
            m.ai_description
        FROM campaign_media_discoveries cmd
        JOIN media m ON cmd.media_id = m.media_id
        WHERE cmd.campaign_id = $1
        AND cmd.vetting_score < 50
        AND cmd.vetting_status = 'completed'
        AND cmd.match_created = false
        AND m.ai_description IS NOT NULL
        ORDER BY cmd.vetting_score DESC
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, uuid.UUID(campaign_id))
            return [dict(row) for row in rows]
    
    async def revet_discovery(self, discovery: Dict[str, Any], campaign: Dict[str, Any]) -> Dict[str, Any]:
        """Revet a single discovery with the updated campaign description."""
        result = {
            'status': 'success',
            'discovery_id': discovery['id'],
            'media_id': discovery['media_id'],
            'media_name': discovery['media_name'],
            'old_score': discovery['vetting_score'],
            'new_score': None,
            'passed': False,
            'match_created': False,
            'review_task_created': False,
            'error': None
        }
        
        try:
            # Run vetting with the updated ideal_podcast_description
            logger.info(f"Revetting media {discovery['media_id']} ({discovery['media_name']})")
            
            vetting_result = await self.vetting_agent.vet_match(
                campaign, 
                discovery['media_id']
            )
            
            if not vetting_result:
                result['status'] = 'error'
                result['error'] = 'Vetting failed to produce results'
                return result
            
            result['new_score'] = vetting_result['vetting_score']
            
            # Update the discovery with new vetting results
            await cmd_queries.update_vetting_results(
                discovery['id'],
                vetting_result['vetting_score'],
                vetting_result.get('vetting_reasoning', ''),
                vetting_result.get('vetting_checklist', {}),
                'completed'
            )
            
            # Check if it now passes
            if vetting_result['vetting_score'] >= 50:
                result['passed'] = True
                
                # Create match suggestion
                match_created = await self.create_match_suggestion(
                    discovery, 
                    vetting_result['vetting_score'],
                    vetting_result.get('vetting_reasoning', '')
                )
                
                if match_created:
                    result['match_created'] = True
                    result['match_id'] = match_created['match_id']
                    
                    # Create review task
                    review_task_created = await self.create_review_task(
                        discovery,
                        match_created['match_id'],
                        vetting_result['vetting_score']
                    )
                    
                    if review_task_created:
                        result['review_task_created'] = True
                        result['review_task_id'] = review_task_created['review_task_id']
            
        except Exception as e:
            logger.error(f"Error revetting discovery {discovery['id']}: {e}", exc_info=True)
            result['status'] = 'error'
            result['error'] = str(e)
        
        return result
    
    async def create_match_suggestion(self, discovery: Dict[str, Any], vetting_score: float, vetting_reasoning: str) -> Dict[str, Any]:
        """Create a match suggestion for a passing discovery."""
        try:
            match_data = {
                "campaign_id": discovery["campaign_id"],
                "media_id": discovery["media_id"],
                "status": "pending_client_review",
                "match_score": vetting_score,
                "matched_keywords": [discovery["discovery_keyword"]],
                "ai_reasoning": vetting_reasoning,
                "vetting_score": vetting_score,
                "vetting_reasoning": vetting_reasoning,
                "created_by_client": False  # This is a system revet
            }
            
            match = await match_queries.create_match_suggestion_in_db(match_data)
            
            if match:
                # Update discovery record to mark match as created
                await cmd_queries.mark_match_created(discovery["id"], match["match_id"])
                logger.info(f"Created match suggestion {match['match_id']} for media {discovery['media_id']}")
                return match
            
        except Exception as e:
            logger.error(f"Error creating match suggestion: {e}")
            return None
    
    async def create_review_task(self, discovery: Dict[str, Any], match_id: int, vetting_score: float) -> Dict[str, Any]:
        """Create a review task for the match suggestion."""
        try:
            review_task_data = {
                "task_type": "match_suggestion",
                "related_id": match_id,
                "campaign_id": discovery["campaign_id"],
                "status": "pending",
                "notes": f"Re-vetted match after ideal_podcast_description update. New score: {vetting_score:.1f}/100"
            }
            
            review_task = await review_task_queries.create_review_task_in_db(review_task_data)
            
            if review_task:
                await cmd_queries.mark_review_task_created(
                    discovery["id"], 
                    review_task["review_task_id"]
                )
                logger.info(f"Created review task {review_task['review_task_id']} for match {match_id}")
                return review_task
                
        except Exception as e:
            logger.error(f"Error creating review task: {e}")
            return None
    
    async def process_campaign(self, campaign_id: str, dry_run: bool = True, limit: int = None):
        """Process all failed discoveries for a campaign."""
        # Get campaign data
        campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found")
            return self.stats
        
        if not campaign.get('ideal_podcast_description'):
            logger.error(f"Campaign {campaign_id} has no ideal_podcast_description")
            return self.stats
        
        print(f"\n=== CAMPAIGN: {campaign['campaign_name']} ===")
        print(f"Ideal Description: {campaign['ideal_podcast_description'][:150]}...")
        
        # Get failed discoveries
        failed_discoveries = await self.get_failed_discoveries(campaign_id)
        
        if limit:
            failed_discoveries = failed_discoveries[:limit]
        
        print(f"\nFound {len(failed_discoveries)} discoveries with scores < 50")
        
        if dry_run:
            print("\nDRY RUN MODE - No changes will be made")
            print("\nPreviewing discoveries that would be revetted:")
            print("-" * 80)
            for disc in failed_discoveries[:10]:  # Show first 10 in dry run
                print(f"Media: {disc['media_name']}")
                print(f"Current Score: {disc['vetting_score']:.1f}")
                print(f"Discovery Keyword: {disc['discovery_keyword']}")
                print("-" * 40)
        else:
            print("\nLIVE MODE - Revetting discoveries...")
            
            for i, discovery in enumerate(failed_discoveries, 1):
                print(f"\n[{i}/{len(failed_discoveries)}] Processing: {discovery['media_name']}")
                print(f"  Old score: {discovery['vetting_score']:.1f}")
                
                result = await self.revet_discovery(discovery, campaign)
                
                self.stats['total_reviewed'] += 1
                self.stats['revetting_attempted'] += 1
                
                if result['status'] == 'success':
                    self.stats['revetting_succeeded'] += 1
                    print(f"  New score: {result['new_score']:.1f}")
                    
                    if result['passed']:
                        self.stats['new_passes'] += 1
                        print(f"  PASSED - Now meets threshold!")
                        
                        if result['match_created']:
                            self.stats['matches_created'] += 1
                            print(f"  Match created (ID: {result['match_id']})")
                        
                        if result['review_task_created']:
                            self.stats['review_tasks_created'] += 1
                            print(f"  Review task created")
                    else:
                        print(f"  Still below threshold")
                else:
                    print(f"  Error: {result['error']}")
                    self.stats['errors'].append({
                        'discovery_id': discovery['id'],
                        'media_name': discovery['media_name'],
                        'error': result['error']
                    })
                
                # Small delay to avoid overwhelming the system
                await asyncio.sleep(0.5)
        
        return self.stats
    
    async def print_summary(self):
        """Print a summary of the revetting results."""
        print("\n" + "=" * 80)
        print("REVETTING SUMMARY")
        print("=" * 80)
        print(f"Total Reviewed: {self.stats['total_reviewed']}")
        print(f"Revetting Attempted: {self.stats['revetting_attempted']}")
        print(f"Revetting Succeeded: {self.stats['revetting_succeeded']}")
        print(f"New Passes (>50): {self.stats['new_passes']}")
        print(f"Matches Created: {self.stats['matches_created']}")
        print(f"Review Tasks Created: {self.stats['review_tasks_created']}")
        
        if self.stats['new_passes'] > 0:
            improvement_rate = (self.stats['new_passes'] / self.stats['revetting_attempted']) * 100
            print(f"\nSuccess Rate: {improvement_rate:.1f}% of revetted podcasts now pass!")
        
        if self.stats['errors']:
            print(f"\nErrors encountered: {len(self.stats['errors'])}")
            for err in self.stats['errors'][:5]:  # Show first 5 errors
                print(f"  - {err['media_name']}: {err['error']}")

async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Revet failed discoveries for updated campaigns')
    parser.add_argument('campaign_id', help='Campaign ID to process')
    parser.add_argument('--live', action='store_true', help='Run in live mode (actually make changes)')
    parser.add_argument('--limit', type=int, help='Limit number of discoveries to process')
    
    args = parser.parse_args()
    
    dry_run = not args.live
    
    if not dry_run:
        confirm = input("LIVE MODE WARNING: This will revet discoveries and create matches. Continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Aborted.")
            return
    
    revetter = DiscoveryRevetter()
    await revetter.initialize()
    
    try:
        await revetter.process_campaign(args.campaign_id, dry_run=dry_run, limit=args.limit)
        await revetter.print_summary()
    finally:
        if revetter.pool:
            await revetter.pool.close()

if __name__ == "__main__":
    print("Discovery Revetting Tool")
    print("========================")
    print("This tool revets failed discoveries with updated ideal_podcast_descriptions")
    print()
    
    asyncio.run(main())