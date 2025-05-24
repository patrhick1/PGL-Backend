# podcast_outreach/api/middleware.py

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Callable
from fastapi import Request, Response, HTTPException, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse

# Import core authentication functions and session store from dependencies
from podcast_outreach.api.dependencies import (
    validate_session,
    SESSIONS # Although SESSIONS is a mock, middleware needs to know about it for cleanup
)
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

# Session expiration time in minutes
SESSION_EXPIRY_MINUTES = 60

# Paths that don't require authentication
PUBLIC_PATHS = [
    "/login",
    "/static",
    "/favicon.ico",
    "/api-status",
    "/webhooks", # Webhooks should be public for external services to hit them
    "/docs", # Allow access to Swagger UI documentation
    "/redoc", # Allow access to ReDoc documentation
    "/openapi.json", # Allow access to the OpenAPI specification file
]

# Paths that only admins can access
ADMIN_ONLY_PATHS = [
    "/admin", # The admin dashboard itself
    "/ai-usage",
    "/ai-usage/cost",
    "/ai-usage/cost-dashboard",
    "/ai-usage/storage-status",
    # Add any API routes that are strictly admin-only
    "/people/", # CRUD for people
    "/media/", # CRUD for media
    "/campaigns/", # CRUD for campaigns
    # Note: Specific POST/PUT/DELETE operations on other routers might also be admin-only
    # This is handled by Depends(get_admin_user) in the routers themselves.
    # This list is for paths that are *always* admin-only at the middleware level.
]

# Paths that staff (and admins) can access
STAFF_ACCESSIBLE_PATHS = [
    "/", # Main dashboard
    "/tasks", # Task management
    "/campaigns", # Read-only access to campaigns (if not covered by admin_only)
    "/matches", # Match review
    "/pitches", # Pitch review
    # Add any other API routes that staff can access
]

def is_path_public(path: str) -> bool:
    """
    Check if a path is public (doesn't require authentication)
    """
    for public_path in PUBLIC_PATHS:
        if path == public_path or path.startswith(public_path + "/"):
            return True
    return False

def requires_admin(path: str) -> bool:
    """
    Check if a path requires admin privileges
    """
    for admin_path in ADMIN_ONLY_PATHS:
        if path == admin_path or path.startswith(admin_path + "/"):
            return True
    return False

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that handles authentication and authorization for the FastAPI application.
    """

    async def dispatch(self, request: Request, call_next):
        # Get the request path
        path = request.url.path

        # Check if the path is public (no authentication required)
        if is_path_public(path):
            return await call_next(request)

        # Get session cookie
        session_id = request.cookies.get("session_id")
        session = validate_session(session_id) if session_id else None

        # If no valid session, redirect to login
        if not session:
            logger.info(f"Unauthenticated access to {path}. Redirecting to /login.")
            return RedirectResponse(url="/login", status_code=303)

        # Set session in request state for access in route handlers
        request.state.session = session
        request.state.username = session["username"]
        request.state.role = session["role"]

        # Check authorization for admin-only paths
        if requires_admin(path) and session["role"] != "admin":
            logger.warning(f"User {session['username']} (role: {session['role']}) attempted unauthorized access to admin path: {path}")
            return Response(
                content="Access denied: Admin privileges required",
                status_code=403
            )
        
        # For other paths, if authenticated, allow access (assuming STAFF_ACCESSIBLE_PATHS are covered by default)
        # The specific API routers will handle finer-grained authorization using Depends(get_admin_user) etc.

        # Continue with the request
        return await call_next(request)