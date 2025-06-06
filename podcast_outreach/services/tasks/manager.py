# podcast_outreach/services/tasks/manager.py

import threading
import uuid
from typing import Dict, Optional, Any, List
import logging
import time
import asyncio

# --- ADD ALL NECESSARY IMPORTS HERE ---
from podcast_outreach.database.connection import init_db_pool, close_db_pool
from podcast_outreach.services.campaigns.angles_generator import AnglesProcessorPG
from podcast_outreach.services.media.episode_sync import main_episode_sync_orchestrator
from podcast_outreach.scripts.transcribe_episodes import main as transcribe_main_script
from podcast_outreach.services.enrichment.enrichment_orchestrator import EnrichmentOrchestrator
from podcast_outreach.services.pitches.generator import PitchGeneratorService
from podcast_outreach.services.pitches.sender import PitchSenderService
from podcast_outreach.services.campaigns.content_processor import ClientContentProcessor
from podcast_outreach.services.matches.scorer import DetermineFitProcessor
from podcast_outreach.services.matches.match_creation import MatchCreationService
from podcast_outreach.services.matches.vetting_orchestrator import VettingOrchestrator
from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService
from podcast_outreach.services.media.podcast_fetcher import MediaFetcher
from podcast_outreach.services.media.transcriber import MediaTranscriber
from podcast_outreach.services.enrichment.enrichment_agent import EnrichmentAgent
from podcast_outreach.database.queries import people as people_queries, media as media_queries, campaigns as campaign_queries
# --- END OF ADDED IMPORTS ---

logger = logging.getLogger(__name__)

# --- Task Wrapper Functions ---

def _run_async_task_in_new_loop(coro):
    """Runs an async coroutine in a new asyncio event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def _run_angles_bio_generation_task(campaign_id_str: str, stop_flag: threading.Event):
    async def _task():
        await init_db_pool()
        processor = AnglesProcessorPG()
        try:
            logger.info(f"Background task: Generating angles/bio for campaign {campaign_id_str}")
            await processor.process_campaign(campaign_id_str)
            logger.info(f"Background task: Angles/bio generation for {campaign_id_str} completed.")
        except Exception as e:
            logger.error(f"Background task: Error generating angles/bio for {campaign_id_str}: {e}", exc_info=True)
        finally:
            processor.cleanup()
            await close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_episode_sync_task(stop_flag: threading.Event):
    async def _task():
        await init_db_pool()
        try:
            logger.info("Background task: Running episode sync.")
            await main_episode_sync_orchestrator() 
            logger.info("Background task: Episode sync completed.")
        except Exception as e:
            logger.error(f"Background task: Error during episode sync: {e}", exc_info=True)
        finally:
            await close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_transcription_task(stop_flag: threading.Event):
    async def _task():
        await init_db_pool()
        try:
            logger.info("Background task: Running episode transcription.")
            await transcribe_main_script() 
            logger.info("Background task: Episode transcription completed.")
        except Exception as e:
            logger.error(f"Background task: Error during episode transcription: {e}", exc_info=True)
        finally:
            await close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_enrichment_orchestrator_task(stop_flag: threading.Event):
    async def _task():
        await init_db_pool()
        from podcast_outreach.services.ai.gemini_client import GeminiService
        from podcast_outreach.services.enrichment.data_merger import DataMergerService
        from podcast_outreach.services.enrichment.quality_score import QualityService
        try:
            gemini_service = GeminiService()
            social_discovery_service = SocialDiscoveryService()
            data_merger = DataMergerService()
            enrichment_agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger)
            quality_service = QualityService()
            orchestrator = EnrichmentOrchestrator(enrichment_agent, quality_service)
            logger.info("Background task: Running full enrichment pipeline.")
            await orchestrator.run_pipeline_once()
            logger.info("Background task: Full enrichment pipeline completed.")
        except Exception as e:
            logger.error(f"Background task: Error during full enrichment pipeline: {e}", exc_info=True)
        finally:
            await close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_vetting_orchestrator_task(stop_flag: threading.Event):
    """Wrapper function to run the VettingOrchestrator pipeline."""
    async def _task():
        await init_db_pool()
        orchestrator = VettingOrchestrator()
        try:
            logger.info("Background task: Running Vetting Orchestrator pipeline.")
            await orchestrator.run_vetting_pipeline()
            logger.info("Background task: Vetting Orchestrator pipeline run completed.")
        except Exception as e:
            logger.error(f"Background task: Error during vetting pipeline: {e}", exc_info=True)
        finally:
            await close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_pitch_writer_task(stop_flag: threading.Event):
    async def _task():
        await init_db_pool()
        generator = PitchGeneratorService()
        try:
            logger.info("Background task: Running pitch writer (generating pitches for pending matches).")
            logger.warning("Pitch writer background task is a placeholder. Needs a method to find and process pending pitches.")
            logger.info("Background task: Pitch writer completed (placeholder).")
        except Exception as e:
            logger.error(f"Background task: Error during pitch writer: {e}", exc_info=True)
        finally:
            await close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_send_pitch_task(stop_flag: threading.Event):
    async def _task():
        await init_db_pool()
        sender = PitchSenderService()
        try:
            logger.info("Background task: Running send pitch (sending all ready pitches).")
            logger.warning("Send pitch background task is a placeholder. Needs a method to find and send ready pitches.")
            logger.info("Background task: Send pitch completed (placeholder).")
        except Exception as e:
            logger.error(f"Background task: Error during send pitch: {e}", exc_info=True)
        finally:
            await close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_process_campaign_content_task(campaign_id_str: str, stop_flag: threading.Event, max_retries: int = 3, retry_delay: float = 60.0):
    async def _task():
        await init_db_pool()
        processor = ClientContentProcessor()
        campaign_id = uuid.UUID(campaign_id_str)
        
        retry_count = 0
        last_error = None
        
        while retry_count <= max_retries:
            if stop_flag.is_set():
                logger.info(f"Background task: Campaign content processing for {campaign_id_str} stopped by signal.")
                break
                
            try:
                logger.info(f"Background task: Processing content for campaign {campaign_id_str} (attempt {retry_count + 1}/{max_retries + 1})")
                
                if retry_count == 0:
                    try:
                        await campaign_queries.update_campaign_status(
                            campaign_id, 
                            "processing_content", 
                            f"Content processing started at attempt {retry_count + 1}"
                        )
                    except Exception as status_error:
                        logger.warning(f"Could not update campaign status for {campaign_id_str}: {status_error}")
                
                success = await processor.process_and_embed_campaign_data(campaign_id)
                
                if success:
                    logger.info(f"Background task: Content processing for {campaign_id_str} completed successfully on attempt {retry_count + 1}.")
                    try:
                        await campaign_queries.update_campaign_status(
                            campaign_id, 
                            "content_processed", 
                            f"Content processing completed successfully with media kit generation on attempt {retry_count + 1}"
                        )
                    except Exception as status_error:
                        logger.warning(f"Could not update final campaign status for {campaign_id_str}: {status_error}")
                    return
                else:
                    error_msg = f"Content processing for {campaign_id_str} did not complete successfully or found no data on attempt {retry_count + 1}"
                    logger.warning(f"Background task: {error_msg}")
                    last_error = Exception(error_msg)
                    
            except Exception as e:
                last_error = e
                logger.error(f"Background task: Error processing content for {campaign_id_str} on attempt {retry_count + 1}: {e}", exc_info=True)
                try:
                    await campaign_queries.update_campaign_status(
                        campaign_id, 
                        "processing_error", 
                        f"Error on attempt {retry_count + 1}: {str(e)[:200]}..."
                    )
                except Exception as status_error:
                    logger.warning(f"Could not update error campaign status for {campaign_id_str}: {status_error}")
            
            retry_count += 1
            
            if retry_count <= max_retries and not stop_flag.is_set():
                logger.info(f"Background task: Retrying campaign content processing for {campaign_id_str} in {retry_delay} seconds...")
                wait_time = 0
                while wait_time < retry_delay and not stop_flag.is_set():
                    await asyncio.sleep(min(5.0, retry_delay - wait_time))
                    wait_time += 5.0
                if stop_flag.is_set():
                    logger.info(f"Background task: Campaign content processing for {campaign_id_str} stopped during retry wait.")
                    break
        
        if retry_count > max_retries:
            final_error_msg = f"Campaign content processing for {campaign_id_str} failed after {max_retries + 1} attempts. Last error: {str(last_error)}"
            logger.error(f"Background task: {final_error_msg}")
            try:
                await campaign_queries.update_campaign_status(
                    campaign_id, 
                    "processing_failed", 
                    f"Processing failed after {max_retries + 1} attempts. Last error: {str(last_error)[:150]}..."
                )
                logger.info(f"Campaign {campaign_id_str} marked as 'processing_failed' and may need manual intervention.")
            except Exception as status_error:
                logger.warning(f"Could not update final failure status for campaign {campaign_id_str}: {status_error}")
        
        try:
            await close_db_pool()
        except Exception as pool_error:
            logger.warning(f"Error closing database pool for campaign processing task {campaign_id_str}: {pool_error}")
    
    _run_async_task_in_new_loop(_task())

def _run_qualitative_match_assessment_task(stop_flag: threading.Event):
    async def _task():
        await init_db_pool()
        processor = DetermineFitProcessor()
        from podcast_outreach.database.queries import review_tasks as rt_queries
        try:
            logger.info("Background task: Running Qualitative Match Assessment for pending review tasks.")
            pending_qual_reviews, total_pending = await rt_queries.get_all_review_tasks_paginated(
                task_type='match_suggestion_qualitative_review',
                status='pending',
                size=50
            )
            
            if not pending_qual_reviews:
                logger.info("Background task: No pending qualitative review tasks found.")
                return

            logger.info(f"Background task: Found {len(pending_qual_reviews)} tasks for qualitative assessment.")
            
            for review_task_record in pending_qual_reviews:
                if stop_flag.is_set():
                    logger.info("Background task: Qualitative assessment task signaled to stop.")
                    break
                logger.info(f"Processing qualitative review for task_id: {review_task_record.get('review_task_id')}, match_suggestion_id: {review_task_record.get('related_id')}")
                await processor.process_single_record(review_task_record)
            
            logger.info("Background task: Qualitative Match Assessment cycle completed.")
        except Exception as e:
            logger.error(f"Background task: Error during qualitative match assessment: {e}", exc_info=True)
        finally:
            await close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_score_potential_matches_task(
    stop_flag: threading.Event,
    campaign_id_str: Optional[str] = None, 
    media_id_int: Optional[int] = None
):
    async def _task():
        await init_db_pool()
        match_creator = MatchCreationService()
        try:
            if campaign_id_str:
                campaign_uuid = uuid.UUID(campaign_id_str)
                logger.info(f"Background task: Scoring potential matches for campaign {campaign_uuid}")
                all_media, total_media = await media_queries.get_all_media_from_db(limit=10000)
                if all_media:
                    await match_creator.create_and_score_match_suggestions_for_campaign(campaign_uuid, all_media)
                    logger.info(f"Completed scoring for campaign {campaign_uuid}.")
                else:
                    logger.info(f"No media found to score against campaign {campaign_uuid}.")
            
            elif media_id_int is not None:
                logger.info(f"Background task: Scoring potential matches for media {media_id_int}")
                all_campaigns, total_campaigns = await campaign_queries.get_campaigns_with_embeddings(limit=10000)
                if all_campaigns:
                    await match_creator.create_and_score_match_suggestions_for_media(media_id_int, all_campaigns)
                    logger.info(f"Completed scoring for media {media_id_int}.")
                else:
                    logger.info(f"No campaigns with embeddings found to score against media {media_id_int}.")
            else:
                logger.warning("Background task: score_potential_matches called without campaign_id or media_id.")

        except Exception as e:
            logger.error(f"Background task: Error scoring potential matches (campaign: {campaign_id_str}, media: {media_id_int}): {e}", exc_info=True)
        finally:
            await close_db_pool()
    _run_async_task_in_new_loop(_task())

class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        # The TaskManager itself doesn't need to instantiate services if the wrappers do it.
        # This keeps the manager lightweight.
        logger.info("TaskManager initialized.")
    
    def start_task(self, task_id: str, action: str) -> None:
        with self._lock:
            self.tasks[task_id] = {
                'action': action,
                'start_time': time.time(),
                'stop_flag': threading.Event(),
                'status': 'running'
            }
            logger.info(f"Task {task_id} for action '{action}' started.")
    
    def stop_task(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self.tasks:
                return False
            self.tasks[task_id]['stop_flag'].set()
            self.tasks[task_id]['status'] = 'stopping'
            logger.info(f"Task {task_id} for action '{self.tasks[task_id]['action']}' signaled to stop.")
            return True
    
    def get_stop_flag(self, task_id: str) -> Optional[threading.Event]:
        with self._lock:
            if task_id not in self.tasks:
                return None
            return self.tasks[task_id]['stop_flag']
    
    def cleanup_task(self, task_id: str) -> None:
        with self._lock:
            if task_id in self.tasks:
                action = self.tasks[task_id]['action']
                del self.tasks[task_id]
                logger.info(f"Task {task_id} for action '{action}' cleaned up.")
    
    def get_task_status(self, task_id: str) -> Optional[dict]:
        with self._lock:
            if task_id not in self.tasks:
                return None
            task = self.tasks[task_id]
            return {
                'task_id': task_id,
                'action': task['action'],
                'status': task['status'],
                'runtime': time.time() - task['start_time']
            }
    
    def list_tasks(self) -> Dict[str, dict]:
        with self._lock:
            return {
                task_id: {
                    'task_id': task_id,
                    'action': info['action'],
                    'status': info['status'],
                    'runtime': time.time() - info['start_time']
                }
                for task_id, info in self.tasks.items()
            }
    
    def cleanup(self) -> None:
        logger.info("Cleaning up all tasks during application shutdown.")
        with self._lock:
            task_ids = list(self.tasks.keys())
            for task_id in task_ids:
                try:
                    self.tasks[task_id]['stop_flag'].set()
                    self.tasks[task_id]['status'] = 'stopped'
                    logger.info(f"Signaled task {task_id} to stop during shutdown.")
                except Exception as e:
                    logger.error(f"Error signaling task {task_id} to stop during shutdown: {e}")
            self.tasks.clear()
            logger.info(f"All {len(task_ids)} tasks cleared from manager.")

# Global task manager instance
task_manager = TaskManager()