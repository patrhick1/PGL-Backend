# podcast_outreach/api/routers/scheduler.py

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel

from podcast_outreach.services.scheduler.task_scheduler import get_scheduler
from podcast_outreach.api.dependencies import get_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])

class TaskControlRequest(BaseModel):
    task_name: str
    action: str  # "enable" or "disable"

@router.get("/status", response_model=Dict[str, Any], summary="Get Scheduler Status")
async def get_scheduler_status(user: dict = Depends(get_admin_user)):
    """Get the status of the task scheduler and all scheduled tasks."""
    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Scheduler not initialized")
    
    return scheduler.get_task_status()

@router.post("/control", summary="Control Scheduled Tasks")
async def control_scheduled_task(
    request: TaskControlRequest,
    user: dict = Depends(get_admin_user)
):
    """Enable or disable a specific scheduled task."""
    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Scheduler not initialized")
    
    if request.action == "enable":
        scheduler.enable_task(request.task_name)
        return {"message": f"Task '{request.task_name}' enabled", "status": "success"}
    elif request.action == "disable":
        scheduler.disable_task(request.task_name)
        return {"message": f"Task '{request.task_name}' disabled", "status": "success"}
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Action must be 'enable' or 'disable'")

@router.post("/start", summary="Start Task Scheduler")
async def start_scheduler(user: dict = Depends(get_admin_user)):
    """Start the task scheduler if it's not running."""
    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Scheduler not initialized")
    
    if scheduler.running:
        return {"message": "Scheduler is already running", "status": "already_running"}
    
    await scheduler.start()
    return {"message": "Scheduler started", "status": "started"}

@router.post("/stop", summary="Stop Task Scheduler")
async def stop_scheduler(user: dict = Depends(get_admin_user)):
    """Stop the task scheduler."""
    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Scheduler not initialized")
    
    if not scheduler.running:
        return {"message": "Scheduler is already stopped", "status": "already_stopped"}
    
    await scheduler.stop()
    return {"message": "Scheduler stopped", "status": "stopped"}