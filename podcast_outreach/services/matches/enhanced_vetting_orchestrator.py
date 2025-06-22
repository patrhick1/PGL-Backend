# podcast_outreach/services/matches/enhanced_vetting_orchestrator.py

import logging
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timezone

from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import review_tasks as review_task_queries
from .vetting_agent import VettingAgent
from .episode_matcher import EpisodeMatcher

logger = logging.getLogger(__name__)

class EnhancedVettingOrchestrator:
    """
    Enhanced vetting orchestrator that works with campaign_media_discoveries
    instead of looking for review tasks. This processes discoveries that
    are ready for vetting (enrichment completed).
    """

    def __init__(self):
        self.vetting_agent = VettingAgent()
        self.episode_matcher = EpisodeMatcher()
        logger.info("EnhancedVettingOrchestrator initialized.")

    async def run_vetting_pipeline(self, batch_size: int = 10):
        """
        Process discoveries that are ready for vetting.
        Looks for records in campaign_media_discoveries where:
        - enrichment_status = 'completed'
        - vetting_status = 'pending'
        - media has ai_description
        - campaign has ideal_podcast_description
        """
        logger.info("Starting enhanced vetting pipeline run...")
        
        # First, clean up any stale vetting locks from previous runs
        cleaned = await cmd_queries.cleanup_stale_vetting_locks(stale_minutes=60)
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} stale vetting locks")
        
        # Get discoveries ready for vetting
        # Use atomic work acquisition to prevent race conditions
        discoveries_to_vet = await cmd_queries.acquire_vetting_work_batch(limit=batch_size)
        
        if not discoveries_to_vet:
            logger.info("No discoveries ready for vetting at this time.")
            return
        
        logger.info(f"Found {len(discoveries_to_vet)} discoveries to vet.")
        
        processed = 0
        successful = 0
        
        for discovery in discoveries_to_vet:
            discovery_id = discovery['id']
            campaign_id = discovery['campaign_id']
            media_id = discovery['media_id']
            
            logger.info(f"Vetting discovery_id: {discovery_id} (campaign: {campaign_id}, media: {media_id})")
            
            try:
                # Update vetting status to in_progress (not enrichment!)
                # This was a bug - we were updating enrichment_status instead of vetting_status
                await cmd_queries.update_vetting_status(discovery_id, "in_progress")
                
                # Get full campaign data including questionnaire responses
                campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
                if not campaign_data:
                    logger.error(f"Could not find campaign {campaign_id}. Skipping.")
                    await self._mark_vetting_failed(
                        discovery_id, 
                        "Campaign data not found"
                    )
                    continue
                
                # Ensure we have ideal_podcast_description
                if not campaign_data.get('ideal_podcast_description'):
                    logger.error(f"Campaign {campaign_id} missing ideal_podcast_description. Skipping.")
                    await self._mark_vetting_failed(
                        discovery_id,
                        "Campaign missing ideal_podcast_description"
                    )
                    continue
                
                # Run the vetting agent
                vetting_results = await self.vetting_agent.vet_match(campaign_data, media_id)
                
                if vetting_results:
                    # Update discovery with vetting results
                    await cmd_queries.update_vetting_results(
                        discovery_id,
                        vetting_results['vetting_score'],
                        vetting_results.get('vetting_reasoning', ''),
                        vetting_results.get('vetting_checklist', {}),
                        'completed'
                    )
                    
                    logger.info(
                        f"Successfully vetted discovery {discovery_id}. "
                        f"Score: {vetting_results['vetting_score']}"
                    )
                    
                    successful += 1
                    
                    # If score is high enough, automatically create match suggestion
                    if vetting_results['vetting_score'] >= 5.0:
                        match_created = await self._create_match_suggestion(
                            discovery, 
                            vetting_results
                        )
                        if match_created:
                            logger.info(f"Match suggestion created for discovery {discovery_id}")
                        
                    # Publish vetting completed event
                    await self._publish_vetting_event(discovery, vetting_results)
                    
                else:
                    # Vetting failed to produce results
                    await self._mark_vetting_failed(
                        discovery_id,
                        "Vetting agent failed to produce results"
                    )
                    logger.error(f"Vetting failed for discovery {discovery_id}")
                
            except Exception as e:
                logger.error(f"Error vetting discovery {discovery_id}: {e}", exc_info=True)
                await self._mark_vetting_failed(
                    discovery_id,
                    f"Vetting error: {str(e)}"
                )
            
            processed += 1
            
            # Small delay between vettings to avoid overwhelming AI services
            if processed < len(discoveries_to_vet):
                await asyncio.sleep(1)
        
        logger.info(
            f"Vetting pipeline completed. "
            f"Processed: {processed}, Successful: {successful}"
        )
    
    async def _mark_vetting_failed(self, discovery_id: int, error_message: str):
        """Mark a discovery as having failed vetting."""
        await cmd_queries.update_vetting_results(
            discovery_id,
            0.0,  # score
            error_message,  # reasoning
            {},  # criteria_met
            'failed'  # status
        )
    
    async def _create_match_suggestion(
        self, 
        discovery: Dict[str, Any], 
        vetting_results: Dict[str, Any]
    ) -> bool:
        """Create a match suggestion for a successfully vetted discovery."""
        try:
            # Check if match already exists
            if discovery.get('match_created'):
                logger.info(f"Match already created for discovery {discovery['id']}")
                return False
            
            # Find best matching episode
            best_episode_id = await self.episode_matcher.find_best_matching_episode(
                discovery['campaign_id'],
                discovery['media_id']
            )
            
            # Create match suggestion
            match_data = {
                'campaign_id': discovery['campaign_id'],
                'media_id': discovery['media_id'],
                'status': 'pending_client_review',
                'match_score': vetting_results['vetting_score'],
                'matched_keywords': [discovery['discovery_keyword']],
                'ai_reasoning': vetting_results.get('vetting_reasoning', ''),
                'vetting_score': vetting_results['vetting_score'],
                'vetting_reasoning': vetting_results.get('vetting_reasoning', ''),
                'vetting_checklist': vetting_results.get('vetting_checklist', {}),
                'last_vetted_at': datetime.now(timezone.utc),
                'best_matching_episode_id': best_episode_id
            }
            
            created_match = await match_queries.create_match_suggestion_in_db(match_data)
            
            if created_match and created_match.get('match_id'):
                match_id = created_match['match_id']
                
                # Update discovery to mark match created
                await cmd_queries.mark_match_created(discovery['id'], match_id)
                
                # Create review task for client
                review_task_data = {
                    'task_type': 'match_suggestion',
                    'related_id': match_id,
                    'campaign_id': discovery['campaign_id'],
                    'status': 'pending',
                    'notes': f"AI-vetted match ready for client review. Score: {vetting_results['vetting_score']:.1f}/10"
                }
                
                review_task = await review_task_queries.create_review_task_in_db(review_task_data)
                if review_task and review_task.get('review_task_id'):
                    await cmd_queries.mark_review_task_created(
                        discovery['id'], 
                        review_task['review_task_id']
                    )
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error creating match suggestion: {e}", exc_info=True)
            return False
    
    async def _publish_vetting_event(
        self, 
        discovery: Dict[str, Any], 
        vetting_results: Dict[str, Any]
    ):
        """Publish vetting completed event for notifications."""
        try:
            from podcast_outreach.services.events.event_bus import get_event_bus, Event, EventType
            
            event_bus = get_event_bus()
            
            # Get media name for the event
            media_name = discovery.get('media_name', 'Unknown')
            
            event = Event(
                event_type=EventType.VETTING_COMPLETED,
                entity_id=str(discovery['media_id']),
                entity_type="media",
                data={
                    "campaign_id": str(discovery['campaign_id']),
                    "media_id": discovery['media_id'],
                    "media_name": media_name,
                    "vetting_score": vetting_results['vetting_score'],
                    "vetting_reasoning": vetting_results.get('vetting_reasoning', ''),
                    "discovery_keyword": discovery['discovery_keyword'],
                    "discovery_id": discovery['id']
                },
                source="enhanced_vetting_orchestrator"
            )
            
            await event_bus.publish(event)
            logger.info(f"Published VETTING_COMPLETED event for discovery {discovery['id']}")
            
        except Exception as e:
            logger.error(f"Error publishing vetting completed event: {e}")