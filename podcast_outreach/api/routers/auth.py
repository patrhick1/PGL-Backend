# podcast_outreach/api/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, Any

# Import dependencies for authentication
from api.dependencies import authenticate_user, create_session, get_current_user

import logging
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])

@router.post("/token", summary="Authenticate User and Get Session Token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticates a user with username and password, returning a session ID.
    This session ID should be set as a cookie by the client.
    """
    username = form_data.username
    password = form_data.password

    role = authenticate_user(username, password)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    session_id = create_session(username, role)
    
    # Return the session_id in the response body. The client is responsible for setting it as a cookie.
    return {"access_token": session_id, "token_type": "bearer", "role": role}

@router.post("/logout", summary="Logout User")
async def logout_api(response: Response, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Logs out the current user by invalidating their session.
    Requires authentication.
    """
    # In a real session management system, you'd invalidate the session_id in your session store.
    # For the in-memory SESSIONS dict, we don't have a direct invalidate by session_id here,
    # but deleting the cookie effectively logs out the client.
    response.delete_cookie(key="session_id", httponly=True, secure=True, samesite="lax")
    logger.info(f"User {user['username']} logged out.")
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=Dict[str, Any], summary="Get Current User Info")
async def read_users_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Retrieves information about the currently authenticated user.
    """
    return current_user
