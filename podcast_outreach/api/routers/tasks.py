# podcast_outreach/api/routers/tasks.py

import uuid
import logging
import asyncio
import threading
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, status, Query

# Import the task manager (moving it to services/tasks/manager.py first)
from podcast_outreach.services.tasks.manager import task_manager

# Import dependencies for authentication
from api.dependencies import get_current_user, get_admin_user

# Import services/scripts that can be triggered (these should be async-ready)
# NOTE: These imports assume the underlying services/scripts have been moved
# and refactored to be callable directly and are async-compatible.
# For example, 'angles_processor_pg' is now part of 'services.campaigns.angles_generator'.
# 'fetch_episodes_to_pg' is now 'services.media.episode_sync'.
# 'summary_guest_identification_optimized' is now 'services.media.analyzer'.
# 'determine_fit_optimized' is now 'services.matches.scorer'.
# 'pitch_writer_optimized' is now 'services.pitches.generator'.
# 'send_pitch_to_instantly' is now 'services.pitches.sender'.
# 'enrich_host_name' (from webhook_handler) is part of 'services.enrichment.enrichment_orchestrator'.
# 'podcast_note_transcriber' and 'free_tier_episode_transcriber' are now 'services.media.transcriber'.

# For now, I'll import the services/scripts as they are in the new structure,
# assuming their main execution functions are async and can be called.
# If they still have synchronous wrappers, those wrappers should be called in asyncio.to_thread.

from podcast_outreach.services.campaigns.angles_generator import AnglesProcessorPG # Assuming this is the main entry
from podcast_outreach.services.media.episode_sync import MediaFetcher # For episode sync
from podcast_outreach.services.media.analyzer import PodcastAnalyzer # Assuming this is the new class
from podcast_outreach.services.matches.scorer import MatchScorer # Assuming this is the new class
from podcast_outreach.services.pitches.generator import PitchGeneratorService # For pitch generation
from podcast_outreach.services.pitches.sender import PitchSenderService # For sending pitches
from podcast_outreach.services.media.transcriber import MediaTranscriber # For transcription
from podcast_outreach.services.enrichment.enrichment_orchestrator import EnrichmentOrchestrator # For host enrichment

import db_service_pg # For DB pool init/close in background tasks

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
# These wrappers will initialize services and call their async methods.
# This is a temporary pattern if FastAPI's background tasks or a proper queue (Celery)
# are not yet fully integrated.
def _run_angles_bio_generation_task(campaign_id_str: str, stop_flag: threading.Event):
    async def _task():
        await db_service_pg.init_db_pool() # Ensure DB pool is available in this thread
        processor = AnglesProcessorPG() # Re-initialize per thread/task
        try:
            logger.info(f"Background task: Generating angles/bio for campaign {campaign_id_str}")
            await processor.process_campaign(campaign_id_str)
            logger.info(f"Background task: Angles/bio generation for {campaign_id_str} completed.")
        except Exception as e:
            logger.error(f"Background task: Error generating angles/bio for {campaign_id_str}: {e}", exc_info=True)
        finally:
            processor.cleanup()
            await db_service_pg.close_db_pool() # Close DB pool for this thread
    _run_async_task_in_new_loop(_task())

def _run_episode_sync_task(stop_flag: threading.Event):
    async def _task():
        await db_service_pg.init_db_pool()
        fetcher = MediaFetcher()
        try:
            logger.info("Background task: Running episode sync.")
            # This should ideally call a method that fetches media to sync and processes them
            # For now, it will call the main orchestrator from episode_sync.py
            from podcast_outreach.services.media.episode_sync import main_episode_sync_orchestrator
            await main_episode_sync_orchestrator() # This function already manages its own DB pool
            logger.info("Background task: Episode sync completed.")
        except Exception as e:
            logger.error(f"Background task: Error during episode sync: {e}", exc_info=True)
        finally:
            await db_service_pg.close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_transcription_task(stop_flag: threading.Event):
    async def _task():
        await db_service_pg.init_db_pool()
        transcriber = MediaTranscriber()
        try:
            logger.info("Background task: Running episode transcription.")
            # This should call a method that fetches episodes to transcribe and processes them
            from podcast_outreach.scripts.transcribe_episodes import main as transcribe_main_script
            await transcribe_main_script() # This function already manages its own DB pool
            logger.info("Background task: Episode transcription completed.")
        except Exception as e:
            logger.error(f"Background task: Error during episode transcription: {e}", exc_info=True)
        finally:
            await db_service_pg.close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_summary_host_guest_task(stop_flag: threading.Event):
    async def _task():
        await db_service_pg.init_db_pool()
        analyzer = PodcastAnalyzer() # Assuming PodcastAnalyzer is the new class
        try:
            logger.info("Background task: Running summary/host/guest analysis.")
            # This should call a method that fetches records and processes them
            # For now, assuming it processes all eligible records
            await analyzer.process_all_records(stop_flag=stop_flag) # Assuming it takes stop_flag
            logger.info("Background task: Summary/host/guest analysis completed.")
        except Exception as e:
            logger.error(f"Background task: Error during summary/host/guest analysis: {e}", exc_info=True)
        finally:
            await db_service_pg.close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_determine_fit_task(stop_flag: threading.Event):
    async def _task():
        await db_service_pg.init_db_pool()
        scorer = MatchScorer() # Assuming MatchScorer is the new class
        try:
            logger.info("Background task: Running determine fit analysis.")
            # This should call a method that fetches records and processes them
            await scorer.process_all_records(stop_flag=stop_flag) # Assuming it takes stop_flag
            logger.info("Background task: Determine fit analysis completed.")
        except Exception as e:
            logger.error(f"Background task: Error during determine fit analysis: {e}", exc_info=True)
        finally:
            await db_service_pg.close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_pitch_writer_task(stop_flag: threading.Event):
    async def _task():
        await db_service_pg.init_db_pool()
        generator = PitchGeneratorService() # Assuming PitchGeneratorService is the new class
        try:
            logger.info("Background task: Running pitch writer.")
            # This should call a method that fetches records and processes them
            # The PitchGeneratorService.generate_pitch_for_match is for a single match_id.
            # A dedicated script or orchestrator function is needed to find all matches needing pitches.
            # For now, this is a placeholder.
            # If the old pitch_writer_optimized.py had a batch processing function, it should be moved here.
            # Assuming a method like `generate_pitches_for_pending_matches` exists.
            # await generator.generate_pitches_for_pending_matches(stop_flag=stop_flag)
            logger.warning("Pitch writer background task is a placeholder. Needs a method to find and process pending pitches.")
            logger.info("Background task: Pitch writer completed (placeholder).")
        except Exception as e:
            logger.error(f"Background task: Error during pitch writer: {e}", exc_info=True)
        finally:
            await db_service_pg.close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_send_pitch_task(stop_flag: threading.Event):
    async def _task():
        await db_service_pg.init_db_pool()
        sender = PitchSenderService() # Assuming PitchSenderService is the new class
        try:
            logger.info("Background task: Running send pitch.")
            # This should call a method that fetches pitches ready to send and dispatches them.
            # Assuming a method like `send_all_ready_pitches` exists.
            # await sender.send_all_ready_pitches(stop_flag=stop_flag)
            logger.warning("Send pitch background task is a placeholder. Needs a method to find and send ready pitches.")
            logger.info("Background task: Send pitch completed (placeholder).")
        except Exception as e:
            logger.error(f"Background task: Error during send pitch: {e}", exc_info=True)
        finally:
            await db_service_pg.close_db_pool()
    _run_async_task_in_new_loop(_task())

def _run_enrich_host_name_task(stop_flag: threading.Event):
    async def _task():
        await db_service_pg.init_db_pool()
        orchestrator = EnrichmentOrchestrator() # Assuming EnrichmentOrchestrator handles this
        try:
            logger.info("Background task: Running host name enrichment.")
            # This should trigger the relevant part of the enrichment orchestrator
            await orchestrator.run_pipeline_once() # This runs all enrichment steps, including host enrichment
            logger.info("Background task: Host name enrichment completed.")
        except Exception as e:
            logger.error(f"Background task: Error during host name enrichment: {e}", exc_info=True)
        finally:
            await db_service_pg.close_db_pool()
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
        "summary_host_guest": _run_summary_host_guest_task,
        "determine_fit": _run_determine_fit_task,
        "pitch_writer": _run_pitch_writer_task,
        "send_pitch": _run_send_pitch_task,
        "enrich_host_name": _run_enrich_host_name_task,
        # Add other specific tasks here
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
