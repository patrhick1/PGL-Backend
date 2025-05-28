# podcast_outreach/api/middleware.py

import logging
from typing import Dict, Optional, List, Callable
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
    "/webhooks",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/campaigns/test",  # Test endpoint for debugging
]

# Paths that only admins can access
ADMIN_ONLY_PATHS = [
    "/admin",
    "/ai-usage",
    "/ai-usage/cost",
    "/ai-usage/cost-dashboard",
    "/ai-usage/storage-status",
    # These are more granular and likely handled by Depends(get_admin_user) in routers
    # "/people/",
    # "/media/",
    # "/campaigns/",
]

# STAFF_ACCESSIBLE_PATHS might also be largely handled by router dependencies
# For this middleware, the primary concern is authentication and broad admin path checks.

def is_path_public(path: str) -> bool:
    """
    Check if a path is public (doesn't require authentication)
    """
    for public_path in PUBLIC_PATHS:
        if path == public_path or path.startswith(public_path + "/"):
            # Ensure that /docs/something still matches /docs
            return True
    return False

def requires_admin(path: str) -> bool:
    """
    Check if a path requires admin privileges at the middleware level.
    """
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

        if is_path_public(path):
            return await call_next(request)

        # SessionMiddleware should populate request.session if a valid session cookie exists.
        # The keys in request.session depend on what was stored during login.
        # We expect at least 'username' and 'role' from prepare_session_data in dependencies.py
        
        session_data = request.session
        current_username = session_data.get("username")
        current_user_role = session_data.get("role")

        if not current_username: # If username is not in session, consider unauthenticated
            logger.info(f"Unauthenticated access to {path} (no username in session). Redirecting to /login.")
            return RedirectResponse(url="/login", status_code=303)

        # Populate request.state for compatibility with existing get_current_user, get_admin_user if they still use it.
        # Ideally, those dependencies would also directly use request.session.
        request.state.session = session_data # Store the whole session data
        request.state.username = current_username
        request.state.role = current_user_role
        # person_id and full_name would also be in session_data if stored during login
        request.state.person_id = session_data.get("person_id")
        request.state.full_name = session_data.get("full_name")

        # Check authorization for admin-only paths
        if requires_admin(path) and current_user_role != "admin":
            logger.warning(f"User {current_username} (role: {current_user_role}) attempted unauthorized access to admin path: {path}")
            return Response(
                content="Access denied: Admin privileges required", 
                status_code=403
            )
        
        return await call_next(request)