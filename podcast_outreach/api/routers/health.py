# podcast_outreach/api/routers/health.py

from fastapi import APIRouter

router = APIRouter(tags=["General"])

@router.get("/health", summary="Health Check")
async def health_check():
    """Checks if the API is running."""
    return {"status": "healthy", "message": "API is up and running!"}