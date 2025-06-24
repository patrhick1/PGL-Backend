#!/usr/bin/env python3
"""Trigger vetting for a single discovery to test the enhanced storage."""

import asyncio
import logging
import json
from datetime import datetime

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
from podcast_outreach.services.matches.enhanced_vetting_orchestrator import EnhancedVettingOrchestrator

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def trigger_single_vetting():
    """Trigger vetting for a single pending discovery."""
    pool = await get_db_pool()
    orchestrator = EnhancedVettingOrchestrator()
    
    # Find one discovery that needs vetting
    query = """
    SELECT cmd.*, m.name as media_name
    FROM campaign_media_discoveries cmd
    JOIN media m ON cmd.media_id = m.media_id
    WHERE cmd.campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    AND cmd.enrichment_status = 'completed'
    AND cmd.vetting_status = 'pending'
    AND m.ai_description IS NOT NULL
    LIMIT 1
    """
    
    async with pool.acquire() as conn:
        discovery = await conn.fetchrow(query)
    
    if not discovery:
        logger.info("No discoveries pending vetting")
        return
    
    logger.info(f"\n=== Triggering Vetting for Discovery ===")
    logger.info(f"ID: {discovery['id']}")
    logger.info(f"Media: {discovery['media_name']}")
    
    # Get campaign data
    campaign_data = await campaign_queries.get_campaign_by_id(discovery['campaign_id'])
    
    # Run vetting through orchestrator
    logger.info("\nRunning vetting...")
    
    # Process just this one discovery
    discoveries_to_vet = [dict(discovery)]
    
    for disc in discoveries_to_vet:
        discovery_id = disc['id']
        campaign_id = disc['campaign_id']
        media_id = disc['media_id']
        
        try:
            # Update status
            await cmd_queries.update_vetting_status(discovery_id, "in_progress")
            
            # Run vetting
            from podcast_outreach.services.matches.enhanced_vetting_agent import EnhancedVettingAgent
            agent = EnhancedVettingAgent()
            vetting_results = await agent.vet_match(campaign_data, media_id)
            
            if vetting_results:
                logger.info(f"\n✅ Vetting completed successfully!")
                logger.info(f"Score: {vetting_results['vetting_score']}")
                logger.info(f"Topic analysis length: {len(vetting_results.get('topic_match_analysis', ''))}")
                logger.info(f"Criteria scores: {len(vetting_results.get('vetting_criteria_scores', []))}")
                logger.info(f"Expertise matched: {len(vetting_results.get('client_expertise_matched', []))}")
                
                # Prepare data for storage
                vetting_criteria_met = {
                    'vetting_checklist': vetting_results.get('vetting_checklist', {}),
                    'topic_match_analysis': vetting_results.get('topic_match_analysis', ''),
                    'vetting_criteria_scores': vetting_results.get('vetting_criteria_scores', []),
                    'client_expertise_matched': vetting_results.get('client_expertise_matched', [])
                }
                
                # Try enhanced update
                logger.info("\nAttempting enhanced update...")
                try:
                    success = await cmd_queries.update_vetting_results_enhanced(
                        discovery_id,
                        vetting_results['vetting_score'],
                        vetting_results.get('vetting_reasoning', ''),
                        vetting_criteria_met,
                        vetting_results.get('topic_match_analysis', ''),
                        vetting_results.get('vetting_criteria_scores', []),
                        vetting_results.get('client_expertise_matched', []),
                        'completed'
                    )
                    logger.info(f"Enhanced update success: {success}")
                except Exception as e:
                    logger.error(f"Enhanced update failed: {e}")
                    # Fall back to regular update
                    logger.info("Falling back to regular update...")
                    await cmd_queries.update_vetting_results(
                        discovery_id,
                        vetting_results['vetting_score'],
                        vetting_results.get('vetting_reasoning', ''),
                        vetting_criteria_met,
                        'completed'
                    )
            else:
                logger.error("Vetting returned no results")
                await cmd_queries.update_vetting_status(discovery_id, "failed", "No results from vetting agent")
                
        except Exception as e:
            logger.error(f"Error during vetting: {e}", exc_info=True)
            await cmd_queries.update_vetting_status(discovery_id, "failed", str(e))
    
    # Check what was stored
    logger.info("\n=== Checking Stored Data ===")
    
    check_query = """
    SELECT 
        id,
        vetting_score,
        vetting_status,
        topic_match_analysis,
        vetting_criteria_scores,
        client_expertise_matched,
        vetting_criteria_met,
        vetted_at
    FROM campaign_media_discoveries
    WHERE id = $1
    """
    
    async with pool.acquire() as conn:
        result = await conn.fetchrow(check_query, discovery['id'])
    
    if result:
        logger.info(f"\nStored vetting data:")
        logger.info(f"Score: {result['vetting_score']}")
        logger.info(f"Status: {result['vetting_status']}")
        logger.info(f"topic_match_analysis: {'YES' if result['topic_match_analysis'] else 'NO'} ({len(result['topic_match_analysis']) if result['topic_match_analysis'] else 0} chars)")
        logger.info(f"vetting_criteria_scores: {'YES' if result['vetting_criteria_scores'] else 'NO'}")
        logger.info(f"client_expertise_matched: {'YES' if result['client_expertise_matched'] else 'NO'} ({len(result['client_expertise_matched']) if result['client_expertise_matched'] else 0} items)")
        
        # Check JSONB content
        if result['vetting_criteria_met']:
            vcm = result['vetting_criteria_met']
            logger.info(f"\nvetting_criteria_met contains:")
            for key in ['vetting_checklist', 'topic_match_analysis', 'vetting_criteria_scores', 'client_expertise_matched']:
                if key in vcm:
                    logger.info(f"  - {key}: YES")

async def main():
    """Main function."""
    await trigger_single_vetting()

if __name__ == "__main__":
    asyncio.run(main())