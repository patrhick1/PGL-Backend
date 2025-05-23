# podcast_outreach/main.py

"""
Unified FastAPI Application

Author: Paschal Okonkwor
Date: 2025-05-23
"""

import os
import uuid
import logging
from datetime import datetime
from contextlib import asynccontextmanager
import sys
import threading
import asyncio 

# Project-specific imports from the new structure
from podcast_outreach.config import ENABLE_LLM_TEST_DASHBOARD, PORT
from podcast_outreach.logging_config import setup_logging, get_logger
from podcast_outreach.api.dependencies import (
    authenticate_user, 
    create_session, 
    get_current_user,
    get_admin_user
)
from podcast_outreach.api.middleware import AuthMiddleware 
from podcast_outreach.database.connection import init_db_pool, close_db_pool  
from podcast_outreach.services.tasks.manager import task_manager # New path for task_manager

# Import the AI usage tracker from its new location
from podcast_outreach.services.ai.tracker import tracker as ai_tracker

# Import FastAPI and Jinja2Templates
from fastapi import FastAPI, Request, Query, Response, status, Form, Depends, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Import the new API routers
from podcast_outreach.api.routers import campaigns, matches, media, pitches, tasks, auth, webhooks, ai_usage # Added ai_usage router

# --- Legacy Script Imports (to be phased out - REMOVED from here) ---
# All direct calls to legacy scripts like webhook_handler, summary_guest_identification_optimized,
# determine_fit_optimized, pitch_episode_selection_optimized, pitch_writer_optimized,
# send_pitch_to_instantly, instantly_email_sent, instantly_response, fetch_episodes,
# podcast_note_transcriber, free_tier_episode_transcriber are REMOVED from main.py.
# Their functionalities are now exposed via the new modular routers or background scripts.
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
templates = Jinja2Templates(directory="podcast_outreach/templates") # Explicitly set path

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
app.mount("/static", StaticFiles(directory="podcast_outreach/static"), name="static") # Explicitly set path

# Include API routers
app.include_router(campaigns.router)
app.include_router(matches.router)
app.include_router(media.router)
app.include_router(pitches.router)
app.include_router(tasks.router)
app.include_router(auth.router)
app.include_router(webhooks.router) 
app.include_router(ai_usage.router) # Include the new AI usage router


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
    return templates.TemplateResponse(
        "dashboard.html", 
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


# --- REMOVED: The /trigger_automation endpoint and its associated legacy wrappers ---
# All automation triggers are now handled by specific endpoints in podcast_outreach/api/routers/tasks.py
# or other domain-specific routers (e.g., /campaigns/{id}/generate-angles-bio).
# The direct imports from 'src/' are also removed from here.


# --- REMOVED: AI Usage & Cost Endpoints from main.py ---
# These are now in podcast_outreach/api/routers/ai_usage.py


# --- REMOVED: Webhook Endpoints from main.py ---
# These are now in podcast_outreach/api/routers/webhooks.py


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
