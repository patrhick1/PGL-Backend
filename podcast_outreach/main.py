# podcast_outreach/main.py

"""
Unified FastAPI Application

Author: Paschal Okonkwor
Date: 2025-01-06
"""

import os
import uuid
import logging
from datetime import datetime
from contextlib import asynccontextmanager
import sys
import threading
import asyncio # Explicitly import asyncio for loop management

# Project-specific imports from the new structure
from podcast_outreach.config import ENABLE_LLM_TEST_DASHBOARD, PORT
from podcast_outreach.logging_config import setup_logging, get_logger
from podcast_outreach.api.dependencies import (
    authenticate_user, 
    create_session, 
    get_current_user,
    get_admin_user
)
from podcast_outreach.api.middleware import AuthMiddleware # Assuming AuthMiddleware is here
from podcast_outreach.database.connection import init_db_pool, close_db_pool  # <--

# Import the AI usage tracker from its new location
from podcast_outreach.services.ai.tracker import tracker as ai_tracker

# Import the task manager (assuming it's still at src/task_manager.py for now)
# In a fully migrated system, this might move to services/tasks/manager.py
from src.task_manager import task_manager

# Import FastAPI and Jinja2Templates
from fastapi import FastAPI, Request, Query, Response, status, Form, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Import the new API routers
from podcast_outreach.api.routers import campaigns, matches, media, pitches, tasks, auth, webhooks # Added webhooks router

# --- Legacy Script Imports (to be phased out) ---
# These imports are kept to maintain the functionality of the /trigger_automation endpoint
# as it existed in the original main.py. In a fully refactored system, these would
# be replaced by calls to services within the podcast_outreach package.
from webhook_handler import poll_airtable_and_process, poll_podcast_search_database # Airtable-dependent
from summary_guest_identification_optimized import PodcastProcessor # Now async
from determine_fit_optimized import determine_fit # Now async
from pitch_episode_selection_optimized import pitch_episode_selection # Still legacy, not yet moved to services/pitches/
from pitch_writer_optimized import pitch_writer # Now async
from send_pitch_to_instantly import send_pitch_to_instantly # Now async
from instantly_email_sent import update_airtable_when_email_sent # Airtable-dependent
from instantly_response import update_correspondent_on_airtable # Airtable-dependent
from fetch_episodes import get_podcast_episodes # Airtable-dependent
from podcast_note_transcriber import get_podcast_audio_transcription # Now async
from free_tier_episode_transcriber import get_podcast_audio_transcription_free_tier # Now async
from webhook_handler import enrich_host_name # Now async (from src/webhook_handler.py, but logic is in src/enrichment/enrichment_orchestrator.py)
# --- End Legacy Script Imports ---


setup_logging()
logger = get_logger(__name__)

# Conditionally import and register routes from test_runner.py
ENABLE_LLM_TEST_DASHBOARD = os.getenv("ENABLE_LLM_TEST_DASHBOARD", "false").lower() == "true"

# Define lifespan context manager before app initialization
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Application starting up...")
    
    # Initialize DB pool
    await init_db_pool()
    logger.info("Database connection pool initialized.")

    if ENABLE_LLM_TEST_DASHBOARD:
        logger.info("ENABLE_LLM_TEST_DASHBOARD is true. Attempting to load test runner routes.")
        # Get the absolute path to the project root (PGL/)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # Get the absolute path to the tests directory
        tests_dir = os.path.join(project_root, "tests")

        if not os.path.isdir(tests_dir):
            logger.warning(f"Tests directory not found at {tests_dir}. Cannot load LLM Test Dashboard.")
        else:
            original_sys_path = list(sys.path)
            # Add tests directory to sys.path to allow importing test_runner
            # and also the project root to allow test_runner to import src modules like auth_middleware
            if tests_dir not in sys.path:
                sys.path.insert(0, tests_dir)
            if project_root not in sys.path: # test_runner itself might try to import from src
                sys.path.insert(0, project_root)
            
            try:
                from test_runner import register_routes as register_test_routes # type: ignore
                logger.info("Successfully imported register_routes from test_runner.")
                register_test_routes(app) # Call the registration here
                logger.info("LLM Test Dashboard routes registered.")
            except ImportError as e:
                logger.error(f"Failed to import test_runner. LLM Test Dashboard will not be available. Error: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred while trying to import test_runner: {e}")
            finally:
                # Restore original sys.path
                sys.path = original_sys_path
    else:
        logger.info("ENABLE_LLM_TEST_DASHBOARD is false. LLM Test Dashboard routes will not be loaded.")
    
    yield  # This is where FastAPI serves requests
    
    # Shutdown logic
    try:
        logger.info("Application shutting down, cleaning up resources...")
        
        # Clean up any running tasks or processes
        if hasattr(task_manager, 'cleanup'):
            task_manager.cleanup()
        
        # Close any open database connections or services
        await close_db_pool()  # Close DB pool
        logger.info("Database connection pool closed.")
        
        # Allow some time for graceful cleanup
        await asyncio.sleep(0.5)
        
        logger.info("Cleanup completed")
    except Exception as e:
        logger.error(f"Error during application shutdown: {e}", exc_info=True)

# Initialize FastAPI app with lifespan context manager
app = FastAPI(lifespan=lifespan)

# Add authentication middleware
app.add_middleware(AuthMiddleware)

# Initialize Jinja2Templates for HTML rendering
templates = Jinja2Templates(directory="templates")

# Register custom filters for templates
def format_number(value):
    """Format a number with comma separators"""
    return f"{value:,}"

def format_datetime(timestamp):
    """Convert ISO timestamp or datetime object to readable format"""
    if isinstance(timestamp, str):
        try:
            dt = datetime.fromisoformat(timestamp)
        except ValueError:
            return timestamp # Return original if cannot parse
    elif isinstance(timestamp, datetime):
        dt = timestamp
    else:
        return str(timestamp) # Fallback for unexpected types

    return dt.strftime("%Y-%m-%d %H:%M:%S")

templates.env.filters["format_number"] = format_number
templates.env.filters["format_datetime"] = format_datetime

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include API routers
app.include_router(campaigns.router)
app.include_router(matches.router)
app.include_router(media.router)
app.include_router(pitches.router)
app.include_router(tasks.router)
app.include_router(auth.router)
app.include_router(webhooks.router) # For Instantly.ai webhooks

@app.get("/login")
def login_page(request: Request):
    """Render the login page"""
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    """Handle login form submission"""
    role = authenticate_user(username, password)
    
    if not role:
        return templates.TemplateResponse(
            "login.html", 
            {
                "request": request, 
                "error": "Invalid username or password"
            }
        )
    
    session_id = create_session(username, role)
    
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=3600
    )
    
    return response


@app.get("/logout")
def logout(request: Request):
    """Log out the user by clearing the session cookie"""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session_id")
    return response


@app.get("/")
def index(request: Request, user: dict = Depends(get_current_user)):
    """
    Root endpoint that renders the main dashboard HTML.
    Requires authentication.
    """
    # In a fully migrated system, this would render a dashboard using data from PostgreSQL
    # For now, it might be a placeholder or a simple dashboard.html
    return templates.TemplateResponse(
        "dashboard.html", # Assuming dashboard.html is the main entry point now
        {
            "request": request,
            "username": user["username"],
            "role": user["role"]
        }
    )


@app.get("/api-status")
def api_status():
    """
    API status endpoint that returns a simple JSON message.
    This endpoint is public.
    """
    return {"message": "PGL Automation API is running (FastAPI version)!"}


# --- Helper functions to run async tasks in a separate thread ---
# These are necessary because the /trigger_automation endpoint is synchronous
# but many of the underlying processing functions are now asynchronous.
def run_async_task_in_new_loop(coro):
    """Runs an async coroutine in a new asyncio event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def run_summary_host_guest_optimized_async_wrapper(stop_flag):
    """Wrapper for the async PodcastProcessor.process_all_records."""
    # Import here to avoid circular dependencies if PodcastProcessor imports main.py
    from summary_guest_identification_optimized import PodcastProcessor
    processor = PodcastProcessor()
    return run_async_task_in_new_loop(
        processor.process_all_records(max_concurrency=3, batch_size=5, stop_flag=stop_flag)
    )

def run_determine_fit_optimized_async_wrapper(stop_flag):
    """Wrapper for the async determine_fit function."""
    from determine_fit_optimized import determine_fit_async # Import the async version
    return run_async_task_in_new_loop(
        determine_fit_async(stop_flag=stop_flag, max_concurrency=3, batch_size=5)
    )

def run_pitch_writer_optimized_async_wrapper(stop_flag):
    """Wrapper for the async pitch_writer function."""
    from podcast_outreach.services.pitches.generator import PitchGeneratorService # New import path
    generator = PitchGeneratorService()
    # Note: pitch_writer_async in generator.py expects match_id, not a general trigger.
    # This wrapper needs to be adapted if it's meant to process a queue of pitches.
    # For now, it will just run the process_all_records from the old pitch_writer_optimized.py logic.
    # The new PitchGeneratorService.generate_pitch_for_match is for a single match_id.
    # This might need a dedicated script in podcast_outreach/scripts/
    # For now, assuming the old pitch_writer_optimized.py's `pitch_writer` function is still callable.
    # If `pitch_writer` itself is async, it needs `run_async_task_in_new_loop`.
    # Based on previous phase, `pitch_writer` is a sync wrapper around `pitch_writer_async`.
    return pitch_writer(stop_flag) # Call the sync wrapper

def run_send_pitch_to_instantly_async_wrapper(stop_flag):
    """Wrapper for the async send_pitch_to_instantly function."""
    from podcast_outreach.services.pitches.sender import PitchSenderService # New import path
    sender = PitchSenderService()
    # The old send_pitch_to_instantly.py had a loop. The new sender.py has send_pitch_to_instantly(pitch_gen_id).
    # This wrapper needs to fetch pitch_gen_ids that are ready to send.
    # This is a placeholder and needs a proper query for 'send_ready_bool = TRUE' pitches.
    # For now, it will call the old script's function if it's still available.
    # If `send_pitch_to_instantly` itself is async, it needs `run_async_task_in_new_loop`.
    # Based on previous phase, `send_pitch_to_instantly` is a sync wrapper.
    return send_pitch_to_instantly(stop_flag) # Call the sync wrapper

def run_enrich_host_name_async_wrapper(stop_flag):
    """Wrapper for the async enrich_host_name function."""
    # The original enrich_host_name was in webhook_handler.py, but its logic was async.
    # Assuming it's now in a service or script that can be called.
    # If it's the `webhook_handler.enrich_host_name` that calls async logic, it needs this wrapper.
    # If it's a new service, import that service and call its async method.
    # For now, assume `webhook_handler.enrich_host_name` is the entry point.
    return run_async_task_in_new_loop(enrich_host_name(stop_flag)) # Assuming enrich_host_name is async

def run_transcription_task_async_wrapper(stop_flag):
    """Wrapper for the async get_podcast_audio_transcription function."""
    # Assuming get_podcast_audio_transcription is now async
    return run_async_task_in_new_loop(get_podcast_audio_transcription(stop_flag))

def run_transcription_task_free_tier_async_wrapper(stop_flag):
    """Wrapper for the async get_podcast_audio_transcription_free_tier function."""
    # Assuming get_podcast_audio_transcription_free_tier is now async
    return run_async_task_in_new_loop(get_podcast_audio_transcription_free_tier(stop_flag))

# --- End Helper functions for async tasks ---


@app.get("/trigger_automation")
async def trigger_automation( # Made async to allow awaiting ai_tracker.log_usage if needed
        action: str = Query(...,
                            description="Name of the automation to trigger"),
        id: Optional[str] = Query(
            None, description="Record ID for the automation if needed")):
    """
    A single endpoint to trigger one of multiple automation functions.
    Returns a task ID that can be used to stop the automation if needed.
    This endpoint is publicly accessible (no auth required).
    """
    try:
        task_id = str(uuid.uuid4())
        
        task_manager.start_task(task_id, action)
        
        # Start the task in a separate thread to avoid blocking the FastAPI event loop
        # All calls to async functions within this thread must be wrapped in a new asyncio event loop
        def run_task_in_thread():
            try:
                stop_flag = task_manager.get_stop_flag(task_id)
                if not stop_flag:
                    logger.error(f"Could not get stop flag for task {task_id}")
                    return
                
                # --- Legacy Airtable-dependent calls (to be replaced) ---
                if action == 'generate_bio_angles':
                    if not id:
                        logger.warning("No record ID provided for generate_bio_angles, will process all eligible records (Airtable-dependent)")
                    poll_airtable_and_process(id, stop_flag) # Calls Airtable-dependent logic
                
                elif action == 'mipr_podcast_search':
                    if not id:
                        raise ValueError("Missing 'id' parameter for MIPR Podcast Search automation! (Airtable-dependent)")
                    poll_podcast_search_database(id, stop_flag) # Calls Airtable-dependent logic
                
                elif action == 'fetch_podcast_episodes':
                    get_podcast_episodes(stop_flag) # Calls Airtable-dependent logic
                
                elif action == 'pitch_episode_angle':
                    # This is still a legacy script, not yet migrated to new services/pitches/
                    pitch_episode_selection(stop_flag) 
                # --- End Legacy Airtable-dependent calls ---

                # --- Calls to new/migrated async services (wrapped for sync thread execution) ---
                elif action == 'summary_host_guest':
                    run_summary_host_guest_optimized_async_wrapper(stop_flag)
                
                elif action == 'determine_fit':
                    run_determine_fit_optimized_async_wrapper(stop_flag)
                
                elif action == 'pitch_writer':
                    run_pitch_writer_optimized_async_wrapper(stop_flag)
                
                elif action == 'send_pitch':
                    run_send_pitch_to_instantly_async_wrapper(stop_flag)
                
                elif action == 'enrich_host_name':
                    run_enrich_host_name_async_wrapper(stop_flag)
                
                elif action == 'transcribe_podcast':
                    run_transcription_task_async_wrapper(stop_flag)
                
                elif action == 'transcribe_podcast_free_tier':
                    run_transcription_task_free_tier_async_wrapper(stop_flag)
                
                else:
                    raise ValueError(f"Invalid action: {action}")
                
            except Exception as e:
                logger.error(f"Error in task {task_id}: {e}", exc_info=True)
            finally:
                task_manager.cleanup_task(task_id)
                logger.info(f"Task {task_id} cleaned up")
        
        thread = threading.Thread(target=run_task_in_thread)
        thread.start()
        logger.info(f"Started task {task_id} for action {action}")
        
        return JSONResponse(content={
            "message": f"Automation '{action}' started",
            "task_id": task_id,
            "status": "running"
        })

    except Exception as e:
        logger.error(f"Error triggering automation for action '{action}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error triggering automation for action '{action}': {str(e)}"
        )

@app.post("/stop_task/{task_id}")
def stop_task(task_id: str, user: dict = Depends(get_current_user)):
    """
    Stop a running automation task.
    Staff or admin access required.
    """
    try:
        if task_manager.stop_task(task_id):
            logger.info(f"Task {task_id} is being stopped by user {user['username']}")
            return JSONResponse(content={"message": f"Task {task_id} is being stopped", "status": "stopping"})
        logger.warning(f"Task {task_id} not found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    except Exception as e:
        logger.error(f"Error stopping task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error stopping task {task_id}: {str(e)}"
        )

@app.get("/task_status/{task_id}")
def get_task_status(task_id: str, user: dict = Depends(get_current_user)):
    """
    Get the status of a specific task.
    Staff or admin access required.
    """
    try:
        status = task_manager.get_task_status(task_id)
        if status:
            return JSONResponse(content=status)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found"
        )
    except Exception as e:
        logger.error(f"Error getting status for task {task_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting status for task {task_id}: {str(e)}"
        )

@app.get("/list_tasks")
def list_tasks(user: dict = Depends(get_current_user)):
    """
    List all running tasks.
    Staff or admin access required.
    """
    try:
        return JSONResponse(content=task_manager.list_tasks())
    except Exception as e:
        logger.error(f"Error listing tasks: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing tasks: {str(e)}"
        )


@app.get("/ai-usage")
async def get_ai_usage( # Made async
    request: Request,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    group_by: str = Query("model", description="Field to group by: 'model', 'workflow', 'endpoint', 'related_pitch_gen_id', 'related_campaign_id', or 'related_media_id'"), # Updated choices
    format: str = Query("json", description="Output format: 'json', 'text', or 'csv'"),
    user: dict = Depends(get_admin_user)
):
    """
    Get AI usage statistics, optionally filtered by date range.
    Admin access required.
    """
    try:
        report = await ai_tracker.generate_report( # Await the async method
            start_date=start_date,
            end_date=end_date,
            group_by=group_by
        )
        
        # Handle different output formats
        if format.lower() == 'text':
            # Import from the new location in scripts/generate_reports.py
            from podcast_outreach.scripts.generate_reports import format_as_text 
            content = format_as_text(report)
            return Response(content=content, media_type="text/plain")
        
        elif format.lower() == 'csv':
            # Import from the new location in scripts/generate_reports.py
            from podcast_outreach.scripts.generate_reports import format_as_csv 
            content = format_as_csv(report)
            return Response(content=content, media_type="text/csv", 
                          headers={"Content-Disposition": "attachment; filename=ai_usage_report.csv"})
        
        else:  # Default to json
            return JSONResponse(content=report) # Ensure JSONResponse
            
    except Exception as e:
        logger.error(f"Error generating AI usage report: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate AI usage report: {str(e)}"
        )


@app.get("/podcast-cost/{pitch_gen_id}") # Changed path parameter name
async def get_podcast_cost(pitch_gen_id: int, user: dict = Depends(get_admin_user)): # Changed parameter name and type
    """
    Get detailed AI usage statistics for a specific pitch generation ID.
    Admin access required.
    """
    try:
        report = await ai_tracker.get_record_cost_report(pitch_gen_id) # Await the async method
        return JSONResponse(content=report)
    except Exception as e:
        logger.error(f"Error generating AI usage report for pitch_gen_id {pitch_gen_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate AI usage report: {str(e)}"
        )


@app.get("/podcast-cost-dashboard/{pitch_gen_id}", response_class=HTMLResponse) # Changed path parameter name
async def get_podcast_cost_dashboard( # Made async
    request: Request, 
    pitch_gen_id: int, # Changed parameter name and type
    user: dict = Depends(get_admin_user)
):
    """
    Render a dashboard with detailed AI usage statistics for a specific pitch generation.
    Admin access required.
    """
    try:
        report = await ai_tracker.get_record_cost_report(pitch_gen_id) # Await the async method
        
        if report.get("status") == "not_found": # Check for specific not_found status
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
        logger.error(f"Error generating podcast cost dashboard for pitch_gen_id {pitch_gen_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during dashboard generation: {str(e)}"
        )


@app.get("/storage-status")
async def get_storage_status(user: dict = Depends(get_admin_user)): # Made async
    """
    Get detailed information about the AI usage storage system.
    Admin access required.
    """
    try:
        # ai_tracker.get_storage_info() is synchronous, no await needed
        storage_info = ai_tracker.get_storage_info() 
        
        storage_info.update({
            'replit_info': {
                'REPL_HOME': os.getenv('REPL_HOME', 'Not running on Replit'),
                'REPL_ID': os.getenv('REPL_ID', 'Not available'),
                'REPL_SLUG': os.getenv('REPL_SLUG', 'Not available'),
            },
            'timestamp': datetime.now().isoformat()
        })
        
        return JSONResponse(content=storage_info)
    except Exception as e:
        logger.error(f"Error getting storage status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get storage status: {str(e)}"
        )


@app.get("/admin")
def admin_dashboard(request: Request, user: dict = Depends(get_admin_user)):
    """
    Admin dashboard page that shows links to all admin-only features.
    Admin access required.
    """
    return templates.TemplateResponse(
        "admin_dashboard.html", 
        {
            "request": request,
            "username": user["username"],
            "role": user["role"]
        }
    )

if __name__ == "__main__":
    import uvicorn

    port = PORT
    logger.info(f"Starting FastAPI app on port {port}.")

    uvicorn.run(app, host='0.0.0.0', port=port)
