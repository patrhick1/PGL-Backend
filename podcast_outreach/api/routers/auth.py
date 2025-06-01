# podcast_outreach/api/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request # Added Request
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, Any, Optional
import uuid

# Import dependencies for authentication
from podcast_outreach.api.dependencies import authenticate_user_details, prepare_session_data, get_current_user # Ensured full path for clarity
from pydantic import BaseModel, EmailStr, Field
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.api.dependencies import hash_password # For hashing
from podcast_outreach.database.queries import campaigns as campaign_queries

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserRegistration(BaseModel):
    full_name: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=8)
    # company_name: Optional[str] = None # Add other fields as needed
    prospect_person_id: Optional[int] = Field(None, description="ID of an existing prospect person to convert.")
    prospect_campaign_id: Optional[uuid.UUID] = Field(None, description="ID of an existing prospect campaign to convert.")

@router.post("/register", status_code=status.HTTP_201_CREATED, summary="Register New User or Convert Prospect")
async def register_user(registration_data: UserRegistration):
    hashed_password = hash_password(registration_data.password)

    if registration_data.prospect_person_id:
        # --- Convert Prospect to Client --- 
        logger.info(f"Attempting to convert prospect_person_id: {registration_data.prospect_person_id} for email: {registration_data.email}")
        prospect_person = await people_queries.get_person_by_id_from_db(registration_data.prospect_person_id)

        if not prospect_person:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prospect ID not found.")
        
        if prospect_person.get('email') != registration_data.email:
            logger.error(f"Email mismatch for prospect conversion. Prospect email: {prospect_person.get('email')}, Submitted email: {registration_data.email}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email does not match prospect record.")

        if prospect_person.get('role') != 'prospect':
            logger.warning(f"Attempt to convert non-prospect person (role: {prospect_person.get('role')}) with ID: {registration_data.prospect_person_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User record cannot be converted in this way.")

        person_update_data = {
            "full_name": registration_data.full_name, # Allow name update
            "dashboard_password_hash": hashed_password,
            "role": "client", # Upgrade role
            "dashboard_username": registration_data.email # Ensure username is email
        }
        updated_person = await people_queries.update_person_in_db(registration_data.prospect_person_id, person_update_data)
        if not updated_person:
            logger.error(f"Failed to update prospect person {registration_data.prospect_person_id} to client.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update user account.")

        # Optionally, update the associated campaign's type
        if registration_data.prospect_campaign_id:
            campaign_update_data = {"campaign_type": "converted_client"} # Or some other standard type
            updated_campaign = await campaign_queries.update_campaign(registration_data.prospect_campaign_id, campaign_update_data)
            if updated_campaign:
                logger.info(f"Prospect campaign {registration_data.prospect_campaign_id} type updated for converted client {updated_person['email']}.")
            else:
                logger.warning(f"Could not update prospect campaign type for {registration_data.prospect_campaign_id} during conversion.")
        
        logger.info(f"Prospect {updated_person['email']} (ID: {updated_person['person_id']}) converted to client.")
        return {"message": "Account activated successfully. Please log in.", "user_id": updated_person["person_id"]}

    else:
        # --- Standard New User Registration ---
        logger.info(f"Attempting standard new user registration for email: {registration_data.email}")
        existing_user = await people_queries.get_person_by_email_from_db(registration_data.email)
        if existing_user:
            # This case should ideally be caught by frontend or the lead-magnet flow if email already exists.
            # But good to have a safeguard here.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists. If you started with a media kit preview, please ensure you use the correct sign-up link or contact support."
            )

        new_person_data = {
            "full_name": registration_data.full_name,
            "email": registration_data.email,
            "dashboard_username": registration_data.email,
            "dashboard_password_hash": hashed_password,
            "role": "client",
        }
        
        created_person = await people_queries.create_person_in_db(new_person_data)
        if not created_person:
            logger.error(f"Failed to create new client person record for email: {registration_data.email}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not create user account."
            )
        
        # Optionally, create a default blank campaign for a brand new client
        default_campaign_data = {
            "campaign_id": uuid.uuid4(),
            "person_id": created_person['person_id'],
            "campaign_name": f"{created_person['full_name']}'s First Campaign",
            "campaign_type": "general" # or a default type
        }
        await campaign_queries.create_campaign_in_db(default_campaign_data)
        logger.info(f"Default campaign created for new client {created_person['email']}.")
        
        logger.info(f"New client registered: {created_person['email']} (ID: {created_person['person_id']})")
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