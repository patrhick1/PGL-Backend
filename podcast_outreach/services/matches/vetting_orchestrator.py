# podcast_outreach/services/matches/vetting_orchestrator.py
import logging
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timezone

from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import review_tasks as review_task_queries # Import review_tasks
from .vetting_agent import VettingAgent

logger = logging.getLogger(__name__)

class VettingOrchestrator:
    """Orchestrates the vetting process for match suggestions."""

    def __init__(self):
        self.vetting_agent = VettingAgent()
        logger.info("VettingOrchestrator initialized.")

    async def run_vetting_pipeline(self, batch_size: int = 10):
        """Finds and processes 'match_suggestion_vetting' tasks."""
        logger.info("Starting vetting pipeline run...")
        
        # 1. Find tasks of type 'match_suggestion_vetting' that are pending
        tasks_to_process, total = await review_task_queries.get_all_review_tasks_paginated(
            task_type='match_suggestion_vetting',
            status='pending',
            size=batch_size
        )
        
        if not tasks_to_process:
            logger.info("No match suggestions found requiring vetting at this time.")
            return

        logger.info(f"Found {len(tasks_to_process)} match suggestions to vet.")
        
        for task in tasks_to_process:
            task_id = task['review_task_id']
            match_id = task['related_id']
            campaign_id = task['campaign_id']
            
            logger.info(f"Vetting match_id: {match_id} (via task_id: {task_id})")
            
            campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
            if not campaign_data:
                logger.error(f"Could not find campaign {campaign_id} for match {match_id}. Skipping.")
                await review_task_queries.update_review_task_status_in_db(task_id, "failed", "Campaign data not found.")
                continue
            
            match_suggestion = await match_queries.get_match_suggestion_by_id(match_id)
            if not match_suggestion:
                logger.error(f"Could not find match_suggestion {match_id}. Skipping.")
                await review_task_queries.update_review_task_status_in_db(task_id, "failed", "Match suggestion data not found.")
                continue

            # 2. Run the Vetting Agent
            vetting_results = await self.vetting_agent.vet_match(campaign_data, match_suggestion['media_id'])

            # 3. Update the match suggestion with the results
            if vetting_results:
                # Also update the match status to 'pending_human_review'
                vetting_results['status'] = 'pending_human_review'
                await match_queries.update_match_suggestion_in_db(match_id, vetting_results)
                
                # Mark the vetting task as completed
                await review_task_queries.update_review_task_status_in_db(task_id, "completed", f"Vetting successful. Score: {vetting_results['vetting_score']}")
                
                # Create the final human review task
                await review_task_queries.create_review_task_in_db({
                    "task_type": "match_suggestion",
                    "related_id": match_id,
                    "campaign_id": campaign_id,
                    "status": "pending",
                    "notes": f"Final human review for AI-vetted match. Score: {vetting_results['vetting_score']}"
                })
                logger.info(f"Successfully vetted match_id: {match_id}. Score: {vetting_results['vetting_score']}. Ready for human review.")
            else:
                # Mark vetting task as failed
                await review_task_queries.update_review_task_status_in_db(task_id, "failed", "Vetting agent failed to produce a result.")
                # Mark match as failed
                await match_queries.update_match_suggestion_in_db(match_id, {
                    "status": "vetting_failed",
                    "vetting_reasoning": "The vetting agent failed to produce a result.",
                    "last_vetted_at": datetime.now(timezone.utc)
                })
                logger.error(f"Vetting failed for match_id: {match_id}.")
            
            await asyncio.sleep(1)

        logger.info("Vetting pipeline run finished.")