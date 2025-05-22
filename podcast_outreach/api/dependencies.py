# podcast_outreach/api/dependencies.py

import logging
from typing import Dict, Optional
from fastapi import Request, HTTPException, Depends
from passlib.context import CryptContext

# Assuming auth_middleware.py is now part of the new structure,
# or its core logic is moved here. For now, we'll assume the
# get_current_user and get_admin_user logic is here.
# In a real app, you might have a dedicated auth_service.py.

logger = logging.getLogger(__name__)

# Password Hashing Utility
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# --- Mock Session/User Management (Replace with real DB/Auth system) ---
# In a real application, these would interact with your database
# and a proper session management system (e.g., Redis, JWT).
# For now, we'll use the in-memory SESSIONS from the original auth_middleware.py.
SESSIONS = {} # This should be replaced by a proper session store

# Admin and Staff credentials (from original auth_middleware.py)
ADMIN_USERS = {
    "admin": "pgl_admin_password",  # CHANGE THIS IN PRODUCTION!
}
STAFF_USERS = {
    "staff": "pgl_staff_password",  # CHANGE THIS IN PRODUCTION!
}

def authenticate_user(username: str, password: str) -> Optional[str]:
    """
    Authenticate a user and return their role if successful
    """
    if username in ADMIN_USERS and ADMIN_USERS[username] == password:
        return "admin"
    if username in STAFF_USERS and STAFF_USERS[username] == password:
        return "staff"
    return None

def create_session(username: str, role: str) -> str:
    """
    Create a new session ID (simplified, no expiry logic here for brevity)
    """
    import secrets
    session_id = secrets.token_urlsafe(32)
    SESSIONS[session_id] = {"username": username, "role": role}
    return session_id

def validate_session(session_id: str) -> Optional[Dict]:
    """
    Validate a session ID and return the session data if valid (simplified)
    """
    return SESSIONS.get(session_id)

# --- FastAPI Dependency Functions ---

def get_current_user(request: Request) -> Dict:
    """
    Dependency function to get the current user from the session.
    Assumes AuthMiddleware has populated request.state.session.
    """
    if not hasattr(request.state, "session") or not request.state.session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    return {
        "username": request.state.session["username"],
        "role": request.state.session["role"]
    }

def get_admin_user(request: Request) -> Dict:
    """
    Dependency function to get an admin user.
    """
    user = get_current_user(request)
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

# --- Database Dependency (if needed for routers) ---
# If db_service_pg.py is moved to database/queries/db_service_pg.py,
# and its pool is managed by lifespan, you might inject it like this:
# from database.queries import db_service_pg
# async def get_db_pool():
#     return await db_service_pg.get_db_pool()