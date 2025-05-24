# podcast_outreach/api/routers/tasks.py

import uuid
import logging
import asyncio
import threading
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, status, Query

# Import the task manager
from podcast_outreach.services.tasks.manager import task_manager

# Import dependencies for authentication
from ..dependencies import get_current_user, get_admin_user

# Import services/scripts that can be triggered (these should be async-ready)
from podcast_outreach.services.campaigns.angles_generator import AnglesProcessorPG
from podcast_outreach.services.media.episode_sync import MediaFetcher
from podcast_outreach.services.media.transcriber import MediaTranscriber
from podcast_outreach.services.enrichment.enrichment_orchestrator import EnrichmentOrchestrator
from podcast_outreach.services.pitches.generator import PitchGeneratorService
from podcast_outreach.services.pitches.sender import PitchSenderService

# Import modular DB connection for background tasks
from podcast_outreach.database.connection import init_db_pool, close_db_pool 

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Background Tasks"])

# Helper to run async functions in a new thread (for synchronous API calls that trigger async background tasks)
def _run_async_task_in_new_loop(coro):
    """Runs an async coroutine in a new asyncio event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Define wrappers for background tasks that need to run in a separate thread
def _run_angles_bio_generation_task(campaign_id_str: str, stop_flag: threading.Event):
    async def _task():
        await init_db_pool() # Ensure DB pool is available in this thread
        processor = AnglesProcessorPG() # Re-initialize per thread/task
        try:
            logger.info(f"Background task: Generating angles/bio for campaign {campaign_id_str}")
            await processor.process_campaign(campaign_id_str)
            logger.info(f"Background task: Angles/bio generation for {campaign_id_str} completed.")
        except Exception as e:
            logger.error(f"Background task: Error generating angles/bio for {campaign_id_str}: {e}", exc_info=True)
        finally:
            processor.cleanup()
            await close_db_pool() # Close DB pool for this thread
    _run_async_task_in_new_loop(_task())

def _run_episode_sync_task(stop_flag: threading.Event):
    async def _task():
        await init_db_pool()
        fetcher = MediaFetcher()
        try:
            logger.info("Background task: Running episode sync.")
            # This should call the main orchestrator from episode_sync.py
            # which itself manages DB pool, but we ensure it's initialized for this thread.
            from podcast_outreach.services.media.episode_sync import main_episode_sync_orchestrator
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
        transcriber = MediaTranscriber()
        try:
            logger.info("Background task: Running episode transcription.")
            # This should call the main orchestrator from transcribe_episodes.py
            # which itself manages DB pool, but we ensure it's initialized for this thread.
            from podcast_outreach.scripts.transcribe_episodes import main as transcribe_main_script
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
        # The orchestrator itself takes services as args, so we need to initialize them here.
        # This is a simplified initialization for a background task.
        from podcast_outreach.services.ai.gemini_client import GeminiService # Assuming this is the new path
        from podcast_outreach.services.enrichment.discovery import DiscoveryService
        from podcast_outreach.services.enrichment.data_merger import DataMerger
        from podcast_outreach.services.enrichment.enrichment_agent import EnrichmentAgent
        from podcast_outreach.services.enrichment.quality_score import QualityScoreService

        try:
            gemini_service = GeminiService()
            social_discovery_service = DiscoveryService()
            data_merger = DataMerger()
            enrichment_agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger)
            quality_service = QualityScoreService()
            orchestrator = EnrichmentOrchestrator(enrichment_agent, quality_service)

            logger.info("Background task: Running full enrichment pipeline.")
            await orchestrator.run_pipeline_once() # This runs all enrichment steps
            logger.info("Background task: Full enrichment pipeline completed.")
        except Exception as e:
            logger.error(f"Background task: Error during full enrichment pipeline: {e}", exc_info=True)
        finally:
            await close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_pitch_writer_task(stop_flag: threading.Event):
    async def _task():
        await init_db_pool()
        generator = PitchGeneratorService()
        try:
            logger.info("Background task: Running pitch writer (generating pitches for pending matches).")
            # This needs a method in PitchGeneratorService to find and process all pending matches
            # For now, this is a placeholder.
            # Example: await generator.generate_pitches_for_all_pending_matches(stop_flag=stop_flag)
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
            # This needs a method in PitchSenderService to find and send all ready pitches
            # Example: await sender.send_all_ready_pitches(stop_flag=stop_flag)
            logger.warning("Send pitch background task is a placeholder. Needs a method to find and send ready pitches.")
            logger.info("Background task: Send pitch completed (placeholder).")
        except Exception as e:
            logger.error(f"Background task: Error during send pitch: {e}", exc_info=True)
        finally:
            await close_db_pool()
    _run_async_task_in_new_loop(_task())


@router.post("/run/{action}", status_code=status.HTTP_202_ACCEPTED, summary="Trigger Background Automation Task")
async def trigger_automation_api(
    action: str,
    campaign_id: Optional[uuid.UUID] = Query(None, description="Campaign ID for campaign-specific tasks"),
    user: dict = Depends(get_current_user) # Require authentication to trigger tasks
):
    """
    Triggers a specific background automation task.
    Staff or Admin access required.
    """
    task_id = str(uuid.uuid4())
    task_manager.start_task(task_id, action)
    
    task_map = {
        "generate_bio_angles": _run_angles_bio_generation_task,
        "fetch_podcast_episodes": _run_episode_sync_task,
        "transcribe_podcast": _run_transcription_task,
        "enrichment_pipeline": _run_enrichment_orchestrator_task, # New action for full enrichment
        "pitch_writer": _run_pitch_writer_task,
        "send_pitch": _run_send_pitch_task,
        # Removed: summary_host_guest, determine_fit, enrich_host_name as they are part of enrichment_pipeline
        # Removed: mipr_podcast_search as it's legacy/replaced by discovery service
    }

    if action not in task_map:
        task_manager.cleanup_task(task_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid automation action: {action}")

    # Start the task in a separate thread
    # Pass necessary arguments to the task wrapper
    args = (task_manager.get_stop_flag(task_id),)
    if action == "generate_bio_angles":
        if not campaign_id:
            task_manager.cleanup_task(task_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'campaign_id' is required for 'generate_bio_angles' action.")
        args = (str(campaign_id), task_manager.get_stop_flag(task_id))

    thread = threading.Thread(target=task_map[action], args=args)
    thread.start()
    logger.info(f"Started task {task_id} for action {action}")
    
    return {
        "message": f"Automation '{action}' started",
        "task_id": task_id,
        "status": "running"
    }

@router.post("/{task_id}/stop", status_code=status.HTTP_200_OK, summary="Stop a Running Task")
async def stop_task_api(task_id: str, user: dict = Depends(get_current_user)):
    """
    Signals a running background task to stop.
    Staff or Admin access required.
    """
    if task_manager.stop_task(task_id):
        logger.info(f"Task {task_id} is being stopped by user {user['username']}")
        return {"message": f"Task {task_id} is being stopped", "status": "stopping"}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found.")

@router.get("/{task_id}/status", response_model=Dict[str, Any], summary="Get Task Status")
async def get_task_status_api(task_id: str, user: dict = Depends(get_current_user)):
    """
    Retrieves the current status of a specific background task.
    Staff or Admin access required.
    """
    status_info = task_manager.get_task_status(task_id)
    if status_info:
        return status_info
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found.")

@router.get("/", response_model=List[Dict[str, Any]], summary="List All Running Tasks")
async def list_tasks_api(user: dict = Depends(get_current_user)):
    """
    Lists all currently running background tasks.
    Staff or Admin access required.
    """
    return list(task_manager.list_tasks().values())
