# podcast_outreach/api/routers/health.py

from fastapi import APIRouter
from podcast_outreach.database.connection import DB_POOL, BACKGROUND_TASK_POOL

router = APIRouter(tags=["General"])

@router.get("/health", summary="Health Check")
async def health_check():
    """Checks if the API is running."""
    response = {"status": "healthy", "message": "API is up and running!"}
    
    # Add pool statistics for monitoring
    if DB_POOL and not DB_POOL._closed:
        response["frontend_pool"] = {
            "size": DB_POOL.get_size(),
            "min_size": DB_POOL.get_min_size(),
            "max_size": DB_POOL.get_max_size(),
            "idle_connections": DB_POOL.get_idle_size(),
        }
    
    if BACKGROUND_TASK_POOL and not BACKGROUND_TASK_POOL._closed:
        response["background_pool"] = {
            "size": BACKGROUND_TASK_POOL.get_size(),
            "min_size": BACKGROUND_TASK_POOL.get_min_size(), 
            "max_size": BACKGROUND_TASK_POOL.get_max_size(),
            "idle_connections": BACKGROUND_TASK_POOL.get_idle_size(),
        }
    
    return response