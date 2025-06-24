# podcast_outreach/api/routers/tasks.py

import uuid
import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, status, Query

# Import the task manager
from podcast_outreach.services.tasks.manager import task_manager

# Import dependencies for authentication
from ..dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Background Tasks"])


@router.post("/run/{action}", status_code=status.HTTP_202_ACCEPTED, summary="Trigger Background Automation Task")
async def trigger_automation_api(
    action: str,
    campaign_id: Optional[uuid.UUID] = Query(None, description="Campaign ID for campaign-specific tasks"),
    media_id: Optional[int] = Query(None, description="Media ID for media-specific tasks"),
    user: dict = Depends(get_current_user)
):
    """
    Triggers a specific background automation task.
    Staff or Admin access required.
    """
    task_id = str(uuid.uuid4())
    
    # Map action strings to their corresponding task manager methods
    valid_actions = {
        "generate_bio_angles",
        "fetch_podcast_episodes", 
        "transcribe_podcast",
        "enrichment_pipeline",
        "pitch_writer",
        "send_pitch",
        "process_campaign_content",
        "qualitative_match_assessment",
        "score_potential_matches",
        "run_vetting_pipeline",
        "create_matches_for_enriched_media",
        "workflow_health_check",
    }

    if action not in valid_actions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid automation action: {action}")

    task_manager.start_task(task_id, action)
    
    # Route to appropriate task manager method
    try:
        if action == "generate_bio_angles":
            if not campaign_id:
                task_manager.cleanup_task(task_id)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'campaign_id' is required for 'generate_bio_angles' action.")
            task_manager.run_angles_bio_generation(task_id, str(campaign_id))
        
        elif action == "fetch_podcast_episodes":
            task_manager.run_episode_sync(task_id)
        
        elif action == "transcribe_podcast":
            task_manager.run_transcription(task_id)
        
        elif action == "enrichment_pipeline":
            task_manager.run_enrichment_pipeline(task_id)
        
        elif action == "pitch_writer":
            task_manager.run_pitch_generation(task_id)
        
        elif action == "send_pitch":
            task_manager.run_pitch_sending(task_id)
        
        elif action == "process_campaign_content":
            if not campaign_id:
                task_manager.cleanup_task(task_id)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="'campaign_id' is required for 'process_campaign_content' action.")
            task_manager.run_campaign_content_processing(task_id, str(campaign_id))
        
        elif action == "qualitative_match_assessment":
            task_manager.run_qualitative_match_assessment(task_id)
        
        elif action == "score_potential_matches":
            if not campaign_id and media_id is None:
                task_manager.cleanup_task(task_id)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either 'campaign_id' or 'media_id' is required for 'score_potential_matches' action.")
            task_manager.run_score_potential_matches(task_id, str(campaign_id) if campaign_id else None, media_id)
        
        elif action == "run_vetting_pipeline":
            task_manager.run_vetting_pipeline(task_id)
        
        elif action == "create_matches_for_enriched_media":
            task_manager.run_create_matches_for_enriched_media(task_id)
        
        elif action == "workflow_health_check":
            task_manager.run_workflow_health_check(task_id)
    
    except Exception as e:
        task_manager.cleanup_task(task_id)
        logger.error(f"Error starting task {task_id} for action '{action}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to start task: {str(e)}")
    logger.info(f"Started task {task_id} for action '{action}'")
    
    return {
        "message": f"Automation '{action}' started",
        "task_id": task_id,
        "status": "running"
    }

@router.post("/{task_id}/stop", status_code=status.HTTP_200_OK, summary="Stop a Running Task")
async def stop_task_api(task_id: str, user: dict = Depends(get_current_user)):
    """Signals a running background task to stop."""
    if task_manager.stop_task(task_id):
        logger.info(f"Task {task_id} is being stopped by user {user['username']}")
        return {"message": f"Task {task_id} is being stopped", "status": "stopping"}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found.")

@router.get("/{task_id}/status", response_model=Dict[str, Any], summary="Get Task Status")
async def get_task_status_api(task_id: str, user: dict = Depends(get_current_user)):
    """Retrieves the current status of a specific background task."""
    status_info = task_manager.get_task_status(task_id)
    if status_info:
        return status_info
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Task {task_id} not found.")

@router.get("/", response_model=List[Dict[str, Any]], summary="List All Running Tasks")
async def list_tasks_api(user: dict = Depends(get_current_user)):
    """Lists all currently running background tasks."""
    return list(task_manager.list_tasks().values())