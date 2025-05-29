# podcast_outreach/api/middleware.py

import logging
from typing import Dict, Optional, List, Callable # Keep Callable if used elsewhere, not directly here
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

# Paths that don't require authentication
PUBLIC_PATHS = [
    "/login",
    "/static",
    "/favicon.ico",
    "/api-status",
    "/webhooks", # This will match /webhooks/* as well due to startswith
    "/docs",
    "/redoc",
    "/openapi.json",
    "/campaigns/test",  # Test endpoint for debugging
    "/auth/token",  # Login endpoint (with prefix)
    "/token",  # Login endpoint (without prefix - what middleware sees)
    "/auth/register",  # Registration endpoint (with prefix)
    "/register",  # Registration endpoint (without prefix - what middleware sees)
]

# Paths that only admins can access
ADMIN_ONLY_PATHS = [
    "/admin",
    "/ai-usage", # This will match /ai-usage/*
    # "/ai-usage/cost", # Covered by /ai-usage
    # "/ai-usage/cost-dashboard", # Covered by /ai-usage
    # "/ai-usage/storage-status", # Covered by /ai-usage
]

def is_path_public(path: str) -> bool:
    logger.info(f"--- ENTERING is_path_public with path: '{path}' (type: {type(path)}) ---")
    print(f"--- ENTERING is_path_public (print) with path: '{path}' (type: {type(path)}) ---")
    try:
        if not isinstance(path, str): # Defensive check
            logger.error(f"is_path_public: path is not a string, it's {type(path)}")
            return False

        for i, public_path in enumerate(PUBLIC_PATHS):
            logger.debug(f"is_path_public: Checking '{path}' against PUBLIC_PATHS[{i}]: '{public_path}'")
            print(f"is_path_public (print): Checking '{path}' against PUBLIC_PATHS[{i}]: '{public_path}'")
            if not isinstance(public_path, str): # Defensive check
                logger.error(f"is_path_public: PUBLIC_PATHS[{i}] is not a string, it's {type(public_path)}")
                continue

            # The actual comparison
            if path == public_path or path.startswith(public_path + "/"):
                logger.info(f"--- EXITING is_path_public (True for {path}) ---")
                print(f"--- EXITING is_path_public (print) (True for {path}) ---")
                return True
        
        logger.info(f"--- EXITING is_path_public (False for {path}) ---")
        print(f"--- EXITING is_path_public (print) (False for {path}) ---")
        return False
    except Exception as e_isp:
        logger.error(f"--- ERROR INSIDE is_path_public ---: {e_isp}", exc_info=True)
        print(f"--- ERROR INSIDE is_path_public (print) ---: {e_isp}")
        raise

def requires_admin(path: str) -> bool:
    """
    Check if a path requires admin privileges at the middleware level.
    """
    logger.debug(f"Checking if path '{path}' requires admin...") # Added debug
    for admin_path in ADMIN_ONLY_PATHS:
        if path == admin_path or path.startswith(admin_path + "/"):
            logger.debug(f"Path '{path}' matched admin path '{admin_path}'. Requires admin.")
            return True
    logger.debug(f"Path '{path}' does not require admin at middleware level.")
    return False

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that handles authentication and authorization for the FastAPI application,
    relying on SessionMiddleware to populate request.session.
    """

    async def dispatch(self, request: Request, call_next):
        logger.info("--- ENTERING AuthMiddleware.dispatch ---")
        print("--- ENTERING AuthMiddleware.dispatch (print) ---")

        path_for_log = "ERROR_PATH_NOT_SET_IN_DISPATCH"
        is_public_result_for_log = "ERROR_IS_PUBLIC_NOT_CHECKED_IN_DISPATCH"

        try:
            path_for_log = request.url.path
            logger.info(f"AuthMiddleware: Processing path: {path_for_log} (type: {type(path_for_log)})")
            print(f"AuthMiddleware: Processing path (print): {path_for_log} (type: {type(path_for_log)})")

            logger.info("AuthMiddleware: About to call is_path_public.")
            print("AuthMiddleware: About to call is_path_public. (print)")
            
            is_public_result_for_log = is_path_public(path_for_log) 
            
            # Try-except block specifically for logging the result of is_path_public
            try:
                logger.info(f"AuthMiddleware: is_path_public returned: {is_public_result_for_log}")
                print(f"AuthMiddleware: is_path_public returned (print): {is_public_result_for_log}")
            except Exception as e_log_after_is_public:
                print(f"CRITICAL ERROR (print): Failed to log result of is_path_public. Error: {e_log_after_is_public}")
                logger.error(f"CRITICAL ERROR: Failed to log result of is_path_public. Error: {e_log_after_is_public}", exc_info=True)
                # Allow to fall through to the main exception handler for this specific case,
                # but the print/log above will give us a clue if this specific spot is the issue.

            if is_public_result_for_log:
                logger.info(f"AuthMiddleware: Path {path_for_log} is public. Skipping auth checks.")
                print(f"AuthMiddleware: Path {path_for_log} is public. Skipping auth checks. (print)")
                return await call_next(request)
            
        except Exception as e_path_check:
            # This catches errors from request.url.path, or from within is_path_public if it re-raises
            logger.error(f"AuthMiddleware: Error during path processing or is_path_public. Path was '{path_for_log}'. is_path_public_result was '{is_public_result_for_log}'. Error: {e_path_check}", exc_info=True)
            print(f"AuthMiddleware: Error during path processing or is_path_public (print). Path was '{path_for_log}'. is_path_public_result was '{is_public_result_for_log}'. Error: {e_path_check}")
            return Response(f"Internal Server Error: Error determining path public status. {str(e_path_check)}", status_code=500)

        # If path is not public, just continue - let dependencies handle session authentication
        logger.info(f"AuthMiddleware: Path {path_for_log} is NOT public. Letting dependencies handle authentication.")
        print(f"AuthMiddleware: Path {path_for_log} is NOT public. Letting dependencies handle authentication. (print)")

        # Note: We don't access request.session here because AuthMiddleware runs before SessionMiddleware
        # Session-based authentication will be handled by dependencies like get_current_user()
        
        logger.info(f"--- EXITING AuthMiddleware.dispatch (calling next for path {path_for_log}) ---")
        print(f"--- EXITING AuthMiddleware.dispatch (calling next for path {path_for_log}) (print) ---")
        return await call_next(request)