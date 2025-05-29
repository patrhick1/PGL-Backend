# podcast_outreach/api/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request # Added Request
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, Any

# Import dependencies for authentication
from podcast_outreach.api.dependencies import authenticate_user_details, prepare_session_data, get_current_user # Ensured full path for clarity
from pydantic import BaseModel, EmailStr, Field
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.api.dependencies import hash_password # For hashing

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserRegistration(BaseModel):
    full_name: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=8)
    # company_name: Optional[str] = None # Add other fields as needed

@router.post("/register", status_code=status.HTTP_201_CREATED, summary="Register New Client User")
async def register_user(registration_data: UserRegistration):
    existing_user = await people_queries.get_person_by_email_from_db(registration_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists."
        )

    hashed_password = hash_password(registration_data.password)
    
    new_person_data = {
        "full_name": registration_data.full_name,
        "email": registration_data.email,
        "dashboard_username": registration_data.email, # Use email as dashboard username
        "dashboard_password_hash": hashed_password,
        "role": "client", # Automatically assign 'client' role
        # "company_name": registration_data.company_name, # If you add company_name to UserRegistration
    }
    
    created_person = await people_queries.create_person_in_db(new_person_data)
    if not created_person:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create user account."
        )
    
    logger.info(f"New client registered: {created_person['email']}")
    # Optionally, log the user in immediately by creating a session
    # Or, require them to log in after registration.
    # For now, let's return a success message.
    return {"message": "User registered successfully. Please log in.", "user_id": created_person["person_id"]}

@router.post("/token", summary="Authenticate User and Get Session Token")
async def login_for_access_token(
    request: Request, # Inject request to access request.session
    response: Response, # Keep for potential direct cookie manipulation if needed, though SessionMiddleware handles it
    form_data: OAuth2PasswordRequestForm = Depends()
):
    email = form_data.username
    password = form_data.password

    user_details = await authenticate_user_details(email, password) 
    
    if not user_details:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Prepare data and set it in the session
    session_data = prepare_session_data(user_details)
    request.session.update(session_data) # This sets the data for SessionMiddleware to save

    logger.info(f"User with email '{user_details['username']}' authenticated via /token. Session data set for middleware.")
    
    return {
        # "access_token": session_id_val, # If you were managing a separate token
        "message": "Login successful. Session initiated.",
        "role": user_details["role"],
        "person_id": user_details.get("person_id"),
        "full_name": user_details.get("full_name"),
        "email": user_details["username"]
    }

@router.post("/logout", summary="Logout User")
async def logout_api(request: Request, response: Response):
    """
    Logs out the current user by invalidating their session cookie.
    Requires authentication.
    """
    username = request.session.get("username", "Unknown user")
    request.session.clear()
    logger.info(f"User {username} logged out via /auth/logout. Session cleared.")
    # response.delete_cookie(key="session") # Middleware handles this
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=Dict[str, Any], summary="Get Current User Info")
async def read_users_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """
    Retrieves information about the currently authenticated user.
    """
    return current_user