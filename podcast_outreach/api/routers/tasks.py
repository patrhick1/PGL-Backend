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
# Import ClientContentProcessor for the new task
from podcast_outreach.services.campaigns.content_processor import ClientContentProcessor
# Import DetermineFitProcessor for the new qualitative assessment task
from podcast_outreach.services.matches.scorer import DetermineFitProcessor
# Import MatchCreationService for the new scoring task
from podcast_outreach.services.matches.match_creation import MatchCreationService
# Import queries for the new scoring task
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries

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

def _run_process_campaign_content_task(campaign_id_str: str, stop_flag: threading.Event, max_retries: int = 3, retry_delay: float = 60.0):
    """
    Enhanced background task for processing campaign content with robust error handling and retry mechanisms.
    
    Args:
        campaign_id_str: Campaign ID as string
        stop_flag: Threading event to signal task stopping
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Delay in seconds between retries (default: 60.0)
    """
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
                
                # Mark processing start in database if it's the first attempt
                if retry_count == 0:
                    try:
                        from podcast_outreach.database.queries import campaigns as campaign_queries
                        await campaign_queries.update_campaign_status(
                            campaign_id, 
                            "processing_content", 
                            f"Content processing started at attempt {retry_count + 1}"
                        )
                    except Exception as status_error:
                        logger.warning(f"Could not update campaign status for {campaign_id_str}: {status_error}")
                
                # Execute the enhanced processing that includes podcast transcription and media kit generation
                success = await processor.process_and_embed_campaign_data(campaign_id)
                
                if success:
                    logger.info(f"Background task: Content processing for {campaign_id_str} completed successfully on attempt {retry_count + 1}.")
                    
                    # Update campaign status to indicate successful processing
                    try:
                        from podcast_outreach.database.queries import campaigns as campaign_queries
                        await campaign_queries.update_campaign_status(
                            campaign_id, 
                            "content_processed", 
                            f"Content processing completed successfully with media kit generation on attempt {retry_count + 1}"
                        )
                    except Exception as status_error:
                        logger.warning(f"Could not update final campaign status for {campaign_id_str}: {status_error}")
                    
                    return  # Success - exit the retry loop
                else:
                    error_msg = f"Content processing for {campaign_id_str} did not complete successfully or found no data on attempt {retry_count + 1}"
                    logger.warning(f"Background task: {error_msg}")
                    last_error = Exception(error_msg)
                    
            except Exception as e:
                last_error = e
                logger.error(f"Background task: Error processing content for {campaign_id_str} on attempt {retry_count + 1}: {e}", exc_info=True)
                
                # Update campaign status with error information
                try:
                    from podcast_outreach.database.queries import campaigns as campaign_queries
                    await campaign_queries.update_campaign_status(
                        campaign_id, 
                        "processing_error", 
                        f"Error on attempt {retry_count + 1}: {str(e)[:200]}..."  # Truncate long error messages
                    )
                except Exception as status_error:
                    logger.warning(f"Could not update error campaign status for {campaign_id_str}: {status_error}")
            
            retry_count += 1
            
            # If we haven't reached max retries and haven't been signaled to stop, wait before retrying
            if retry_count <= max_retries and not stop_flag.is_set():
                logger.info(f"Background task: Retrying campaign content processing for {campaign_id_str} in {retry_delay} seconds...")
                
                # Wait with stop_flag checking (break wait early if stop is signaled)
                wait_time = 0
                while wait_time < retry_delay and not stop_flag.is_set():
                    await asyncio.sleep(min(5.0, retry_delay - wait_time))  # Check every 5 seconds
                    wait_time += 5.0
                
                if stop_flag.is_set():
                    logger.info(f"Background task: Campaign content processing for {campaign_id_str} stopped during retry wait.")
                    break
        
        # If we've exhausted all retries, log final failure and update status
        if retry_count > max_retries:
            final_error_msg = f"Campaign content processing for {campaign_id_str} failed after {max_retries + 1} attempts. Last error: {str(last_error)}"
            logger.error(f"Background task: {final_error_msg}")
            
            try:
                from podcast_outreach.database.queries import campaigns as campaign_queries
                await campaign_queries.update_campaign_status(
                    campaign_id, 
                    "processing_failed", 
                    f"Processing failed after {max_retries + 1} attempts. Last error: {str(last_error)[:150]}..."
                )
                
                # Optionally, you could queue this campaign for manual review or re-queue for later processing
                logger.info(f"Campaign {campaign_id_str} marked as 'processing_failed' and may need manual intervention.")
                
            except Exception as status_error:
                logger.warning(f"Could not update final failure status for campaign {campaign_id_str}: {status_error}")
        
        # Clean up database pool
        try:
            await close_db_pool()
        except Exception as pool_error:
            logger.warning(f"Error closing database pool for campaign processing task {campaign_id_str}: {pool_error}")
    
    _run_async_task_in_new_loop(_task())

def _run_qualitative_match_assessment_task(stop_flag: threading.Event):
    async def _task():
        await init_db_pool()
        processor = DetermineFitProcessor()
        # Import review_task_queries here locally to avoid potential startup circular dependencies
        from podcast_outreach.database.queries import review_tasks as rt_queries
        try:
            logger.info("Background task: Running Qualitative Match Assessment for pending review tasks.")
            # Fetch pending 'match_suggestion_qualitative_review' tasks
            # We process them one by one in this example. A more robust system might use a queue or batching.
            pending_qual_reviews, total_pending = await rt_queries.get_all_review_tasks_paginated(
                task_type='match_suggestion_qualitative_review',
                status='pending',
                size=50 # Process up to 50 in one run of this task trigger
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
                # Fetch all media to match against this campaign
                # Consider pagination or more specific filtering for large numbers of media
                all_media, total_media = await media_queries.get_all_media_from_db(limit=10000) # Example limit
                if all_media:
                    await match_creator.create_and_score_match_suggestions_for_campaign(campaign_uuid, all_media)
                    logger.info(f"Completed scoring for campaign {campaign_uuid}.")
                else:
                    logger.info(f"No media found to score against campaign {campaign_uuid}.")
            
            elif media_id_int is not None:
                logger.info(f"Background task: Scoring potential matches for media {media_id_int}")
                # Fetch all campaigns with embeddings to match against this media
                all_campaigns, total_campaigns = await campaign_queries.get_campaigns_with_embeddings(limit=10000) # Example limit
                if all_campaigns:
                    await match_creator.create_and_score_match_suggestions_for_media(media_id_int, all_campaigns)
                    logger.info(f"Completed scoring for media {media_id_int}.")
                else:
                    logger.info(f"No campaigns with embeddings found to score against media {media_id_int}.")
            else:
                logger.warning("Background task: score_potential_matches called without campaign_id or media_id.")
                # Optionally, implement a full re-score of all campaigns vs all media, 
                # but this could be very resource-intensive.
                # For now, it requires one of the IDs.

        except Exception as e:
            logger.error(f"Background task: Error scoring potential matches (campaign: {campaign_id_str}, media: {media_id_int}): {e}", exc_info=True)
        finally:
            await close_db_pool()
    _run_async_task_in_new_loop(_task())

@router.post("/run/{action}", status_code=status.HTTP_202_ACCEPTED, summary="Trigger Background Automation Task")
async def trigger_automation_api(
    action: str,
    campaign_id: Optional[uuid.UUID] = Query(None, description="Campaign ID for campaign-specific tasks"),
    media_id: Optional[int] = Query(None, description="Media ID for media-specific tasks"), # Added media_id query param
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
        "process_campaign_content": _run_process_campaign_content_task, # New task
        "qualitative_match_assessment": _run_qualitative_match_assessment_task, # New task for scorer
        "score_potential_matches": _run_score_potential_matches_task, # New task
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
    elif action == "process_campaign_content": # Add argument handling for the new task
        if not campaign_id:
            task_manager.cleanup_task(task_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'campaign_id' is required for 'process_campaign_content' action.")
        args = (str(campaign_id), task_manager.get_stop_flag(task_id))
    elif action == "score_potential_matches":
        if not campaign_id and media_id is None:
            task_manager.cleanup_task(task_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either 'campaign_id' or 'media_id' is required for 'score_potential_matches' action.")
        # Pass both, the task wrapper will decide which one to use
        args = (task_manager.get_stop_flag(task_id), str(campaign_id) if campaign_id else None, media_id)
    # For tasks like qualitative_match_assessment, fetch_podcast_episodes etc args remains default (stop_flag,)

    thread = threading.Thread(target=task_map[action], args=args)
    thread.start()
    logger.info(f"Started task {task_id} for action '{action}' with args: {args}")
    
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
