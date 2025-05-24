# podcast_outreach/api/routers/ai_usage.py

from fastapi import APIRouter, HTTPException, Depends, status, Query, Response, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates # For HTML dashboard
from typing import Optional, Dict, Any, List
from datetime import datetime, date

# Import the AI usage tracker
from podcast_outreach.services.ai.tracker import tracker as ai_tracker

# Import dependencies for authentication
from api.dependencies import get_admin_user

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai-usage", tags=["AI Usage & Cost"])

# Initialize Jinja2Templates for HTML rendering (if this router serves HTML)
# Assuming templates are relative to the project root, or configured in main.py and passed.
# For simplicity, let's assume templates are accessible from the main app's context.
# If this router is mounted, it might need its own templates instance or access to the main one.
# For now, I'll assume the main app's templates object is passed or accessible.
# If not, this would need: templates = Jinja2Templates(directory="podcast_outreach/templates")
# And the main app would need to pass it or this router would need to be initialized with it.
# For this example, I'll assume it's available via the main app's context or a global.
templates = Jinja2Templates(directory="podcast_outreach/templates")

# Register custom filters for templates (copied from main.py)
def format_number(value):
    return f"{value:,}"

def format_datetime(timestamp):
    if isinstance(timestamp, str):
        try:
            dt = datetime.fromisoformat(timestamp)
        except ValueError:
            return timestamp
    elif isinstance(timestamp, datetime):
        dt = timestamp
    else:
        return str(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

templates.env.filters["format_number"] = format_number
templates.env.filters["format_datetime"] = format_datetime


@router.get("/", response_model=Dict[str, Any], summary="Get AI Usage Statistics")
async def get_ai_usage_api(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    group_by: str = Query("model", description="Field to group by: 'model', 'workflow', 'endpoint', 'related_pitch_gen_id', 'related_campaign_id', or 'related_media_id'"),
    format: str = Query("json", description="Output format: 'json', 'text', or 'csv'"),
    user: dict = Depends(get_admin_user)
):
    """
    Retrieves AI usage statistics, optionally filtered by date range and grouped by a specified field.
    Admin access required.
    """
    try:
        report = await ai_tracker.generate_report(
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )
        
        # Format as text or CSV if requested (logic from generate_reports.py)
        if format.lower() == 'text':
            from podcast_outreach.scripts.generate_reports import format_as_text # Import helper
            content = format_as_text(report)
            return Response(content=content, media_type="text/plain")
        
        elif format.lower() == 'csv':
            from podcast_outreach.scripts.generate_reports import format_as_csv # Import helper
            content = format_as_csv(report)
            return Response(content=content, media_type="text/csv", 
                          headers={"Content-Disposition": "attachment; filename=ai_usage_report.csv"})
        
        else:  # Default to json
            return JSONResponse(content=report)
            
    except Exception as e:
        logger.exception(f"Error generating AI usage report: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate AI usage report: {str(e)}"
        )

@router.get("/cost/{pitch_gen_id}", response_model=Dict[str, Any], summary="Get AI Cost for Pitch Generation")
async def get_pitch_generation_cost_api(pitch_gen_id: int, user: dict = Depends(get_admin_user)):
    """
    Retrieves detailed AI usage and cost statistics for a specific pitch generation ID.
    Admin access required.
    """
    try:
        report = await ai_tracker.get_record_cost_report(pitch_gen_id)
        if report.get("status") == "not_found":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=report.get("message"))
        return JSONResponse(content=report)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error generating AI cost report for pitch_gen_id {pitch_gen_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate AI cost report: {str(e)}"
        )

@router.get("/cost-dashboard/{pitch_gen_id}", response_class=HTMLResponse, summary="View AI Cost Dashboard for Pitch Generation")
async def get_pitch_generation_cost_dashboard_api(
    request: Request, 
    pitch_gen_id: int, 
    user: dict = Depends(get_admin_user)
):
    """
    Renders an HTML dashboard with detailed AI usage statistics for a specific pitch generation.
    Admin access required.
    """
    try:
        report = await ai_tracker.get_record_cost_report(pitch_gen_id)
        
        if report.get("status") == "not_found":
            return HTMLResponse(
                content=f"""
                <html>
                    <head>
                        <title>No Data Found</title>
                        <link rel="stylesheet" href="/static/dashboard.css">
                    </head>
                    <body>
                        <div class="container">
                            <div class="section">
                                <h2>No Data Found</h2>
                                <p>{report["message"]}</p>
                                <a href="/" class="back-button">Back to Dashboard</a>
                            </div>
                        </div>
                    </body>
                </html>
                """,
                status_code=status.HTTP_404_NOT_FOUND
            )
        
        return templates.TemplateResponse("podcast_cost.html", {
            "request": request,
            "username": user["username"],
            "role": user["role"],
            **report
        })
    
    except Exception as e:
        logger.exception(f"Error generating AI cost dashboard for pitch_gen_id {pitch_gen_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during dashboard generation: {str(e)}"
        )

@router.get("/storage-status", response_model=Dict[str, Any], summary="Get AI Usage Storage Status")
async def get_storage_status_api(user: dict = Depends(get_admin_user)):
    """
    Retrieves detailed information about the AI usage storage system.
    Admin access required.
    """
    try:
        storage_info = ai_tracker.get_storage_info()
        storage_info.update({
            'timestamp': datetime.now().isoformat()
        })
        return JSONResponse(content=storage_info)
    except Exception as e:
        logger.exception(f"Error getting storage status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get storage status: {str(e)}"
        )
