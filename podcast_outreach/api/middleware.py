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
    "/auth/request-password-reset",  # Password reset request (with prefix)
    "/request-password-reset",  # Password reset request (without prefix - what middleware sees)
    "/auth/reset-password",  # Password reset (with prefix)
    "/reset-password",  # Password reset (without prefix - what middleware sees)
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
    # logger.info(f"is_path_public check for: {path}") # Keep if very high-level trace needed
    if not isinstance(path, str): return False
    for public_path in PUBLIC_PATHS:
        if path == public_path or path.startswith(public_path + "/"):
            return True
    return False

def requires_admin(path: str) -> bool:
    # logger.debug(f"Checking if path '{path}' requires admin...")
    for admin_path in ADMIN_ONLY_PATHS:
        if path == admin_path or path.startswith(admin_path + "/"):
            return True
    return False

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that handles authentication and authorization for the FastAPI application,
    relying on SessionMiddleware to populate request.session.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        logger.debug(f"AuthMiddleware processing path: {path}")

        if is_path_public(path):
            logger.debug(f"Path {path} is public, skipping auth.")
            return await call_next(request)

        # For non-public paths, AuthMiddleware now defers actual session validation 
        # and user fetching to endpoint dependencies (like get_current_user).
        # It can still perform broad role checks based on request.state.role if populated by dependencies.
        # However, the primary role of this middleware (after SessionMiddleware runs) is to check path-based rules
        # that don't depend on a fully validated session (e.g. IP blocking, rate limiting - not implemented here).
        # The current logic for role checks based on request.state.role (populated by get_current_user)
        # inside an endpoint is generally preferred over doing it broadly in middleware if it involves reading session.
        
        # The previous version of this middleware tried to access request.session directly here.
        # That was problematic because middleware order dictates SessionMiddleware might not have run yet.
        # Now, we let it pass through. If an endpoint requires auth, its `Depends(get_current_user)`
        # will handle checking `request.session` (which *will* have been populated by SessionMiddleware by then)
        # and raise HTTPException if no valid session/user.

        # We *could* still check `requires_admin` here if we make `get_current_user` populate `request.state`
        # and then check `request.state.role` if it exists. But let's keep this middleware simpler for now.
        # The dependencies in routers are the primary gatekeepers for roles.

        logger.debug(f"Path {path} is not public. Proceeding to next handler/endpoint dependencies.")
        return await call_next(request)