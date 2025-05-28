# podcast_outreach/api/dependencies.py

import logging
from typing import Dict, Optional, Any
from fastapi import Request, HTTPException, Depends
from passlib.context import CryptContext

# Database imports
from podcast_outreach.database.queries import people as people_queries
# from podcast_outreach.database.connection import get_db_pool # Only if not using lifespan for DB init

logger = logging.getLogger(__name__)

# Password Hashing Utility
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# --- Authentication Logic ---
async def authenticate_user_details(email: str, password: str) -> Optional[Dict[str, Any]]:
    """
    Authenticate a user against the 'people' table using email and dashboard_password_hash.
    Returns user details (email, role, person_id, full_name) if successful.
    """
    if not email or not password:
        return None

    person_record = await people_queries.get_person_by_email_from_db(email)

    if not person_record:
        logger.debug(f"Authentication failed: User with email '{email}' not found.")
        return None

    stored_password_hash = person_record.get("dashboard_password_hash")
    if not stored_password_hash:
        logger.warning(f"Authentication failed: User with email '{email}' does not have a password hash set.")
        return None

    if not verify_password(password, stored_password_hash):
        logger.debug(f"Authentication failed: Invalid password for user with email '{email}'.")
        return None

    logger.info(f"User with email '{email}' authenticated successfully.")
    return {
        "username": person_record["email"], # Using email as the session's username identifier
        "role": person_record.get("role"),
        "person_id": person_record["person_id"],
        "full_name": person_record.get("full_name")
    }

# --- Session Data Preparation ---
def prepare_session_data(user_details: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prepares the data dictionary to be stored in the session by SessionMiddleware.
    """
    return {
        "username": user_details["username"], # This will be the email
        "role": user_details.get("role"),
        "person_id": user_details.get("person_id"),
        "full_name": user_details.get("full_name")
    }

# The SESSIONS dictionary and create_session/validate_session that directly manipulated it
# are no longer needed here if SessionMiddleware is handling session storage.
# SESSIONS = {} # REMOVED
# def create_session(user_details: Dict[str, Any]) -> str: # REMOVED (or repurposed if SessionMiddleware needs it differently)
# def validate_session(session_id: str) -> Optional[Dict[str, Any]]: # REMOVED

# --- FastAPI Dependency Functions ---

def get_current_user(request: Request) -> Dict[str, Any]:
    """
    Dependency function to get the current user from the session
    populated by Starlette's SessionMiddleware.
    """
    # SessionMiddleware populates request.session
    if not request.session or "username" not in request.session:
        logger.warning("Attempt to get current user without active session or username in session.")
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Extract all stored user details from the session
    user_data = {
        "username": request.session.get("username"), # This is the email
        "role": request.session.get("role"),
        "person_id": request.session.get("person_id"),
        "full_name": request.session.get("full_name")
    }
    logger.debug(f"Current user retrieved from session: {user_data.get('username')}, Role: {user_data.get('role')}")
    return user_data

def get_admin_user(request: Request) -> Dict[str, Any]:
    """
    Dependency function to ensure the current user has 'admin' role.
    """
    user = get_current_user(request) # This now gets data from request.session
    if user.get("role") != "admin":
        logger.warning(f"User '{user.get('username')}' with role '{user.get('role')}' attempted admin-only access.")
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

def get_staff_user(request: Request) -> Dict[str, Any]:
    """
    Dependency function to ensure the current user has 'staff' or 'admin' role.
    """
    user = get_current_user(request) # This now gets data from request.session
    if user.get("role") not in ["staff", "admin"]:
        logger.warning(f"User '{user.get('username')}' with role '{user.get('role')}' attempted staff/admin access.")
        raise HTTPException(status_code=403, detail="Staff or Admin privileges required")
    return user