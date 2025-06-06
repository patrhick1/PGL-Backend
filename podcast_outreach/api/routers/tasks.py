# podcast_outreach/api/routers/tasks.py

import uuid
import logging
import threading
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Depends, status, Query

# Import the task manager and all the task wrapper functions from the manager module
from podcast_outreach.services.tasks.manager import (
    task_manager,
    _run_angles_bio_generation_task,
    _run_episode_sync_task,
    _run_transcription_task,
    _run_enrichment_orchestrator_task,
    _run_pitch_writer_task,
    _run_send_pitch_task,
    _run_process_campaign_content_task,
    _run_qualitative_match_assessment_task,
    _run_score_potential_matches_task,
    _run_vetting_orchestrator_task
)

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
    
    # Map action strings to their corresponding wrapper functions
    task_map = {
        "generate_bio_angles": _run_angles_bio_generation_task,
        "fetch_podcast_episodes": _run_episode_sync_task,
        "transcribe_podcast": _run_transcription_task,
        "enrichment_pipeline": _run_enrichment_orchestrator_task,
        "pitch_writer": _run_pitch_writer_task,
        "send_pitch": _run_send_pitch_task,
        "process_campaign_content": _run_process_campaign_content_task,
        "qualitative_match_assessment": _run_qualitative_match_assessment_task,
        "score_potential_matches": _run_score_potential_matches_task,
        "run_vetting_pipeline": _run_vetting_orchestrator_task,
    }

    if action not in task_map:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid automation action: {action}")

    task_manager.start_task(task_id, action)
    
    # Prepare arguments for the task thread
    args = (task_manager.get_stop_flag(task_id),)
    if action in ["generate_bio_angles", "process_campaign_content"]:
        if not campaign_id:
            task_manager.cleanup_task(task_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"'campaign_id' is required for '{action}' action.")
        args = (str(campaign_id), task_manager.get_stop_flag(task_id))
    elif action == "score_potential_matches":
        if not campaign_id and media_id is None:
            task_manager.cleanup_task(task_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Either 'campaign_id' or 'media_id' is required for 'score_potential_matches' action.")
        args = (task_manager.get_stop_flag(task_id), str(campaign_id) if campaign_id else None, media_id)
    
    # Start the task in a separate thread
    thread = threading.Thread(target=task_map[action], args=args)
    thread.start()
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