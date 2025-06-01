# podcast_outreach/api/routers/auth.py

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from typing import Dict, Any, Optional
import uuid
import secrets
import asyncio
from datetime import datetime, timedelta, timezone
import logging
import bcrypt

logger = logging.getLogger(__name__)

# Import dependencies for authentication
from podcast_outreach.api.dependencies import authenticate_user_details, prepare_session_data, get_current_user
from pydantic import BaseModel, EmailStr, Field
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.api.dependencies import hash_password
from podcast_outreach.database.queries import campaigns as campaign_queries
from ...services.email_service import email_service
from ...database.queries import auth_queries

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserRegistration(BaseModel):
    full_name: str = Field(..., min_length=2)
    email: EmailStr
    password: str = Field(..., min_length=8)
    
    # Optional fields - ONLY needed when converting a prospect (from lead magnet signup)
    prospect_person_id: Optional[int] = Field(None, description="ONLY for lead magnet conversions: ID of existing prospect person to convert to client.")
    prospect_campaign_id: Optional[uuid.UUID] = Field(None, description="ONLY for lead magnet conversions: ID of existing prospect campaign to update.")

@router.post("/register", status_code=status.HTTP_201_CREATED, summary="Register New User or Convert Prospect")
async def register_user(registration_data: UserRegistration):
    """
    Register a new user account.
    
    For NEW USERS: Just provide full_name, email, and password.
    For PROSPECT CONVERSION (from lead magnet): Also provide prospect_person_id and prospect_campaign_id.
    """
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
            "full_name": registration_data.full_name,
            "dashboard_password_hash": hashed_password,
            "role": "client",
            "dashboard_username": registration_data.email
        }
        updated_person = await people_queries.update_person_in_db(registration_data.prospect_person_id, person_update_data)
        if not updated_person:
            logger.error(f"Failed to update prospect person {registration_data.prospect_person_id} to client.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update user account.")

        # Update associated campaign type if provided
        if registration_data.prospect_campaign_id:
            campaign_update_data = {"campaign_type": "converted_client"}
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
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists. Please log in instead, or use password reset if you forgot your password."
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
        
        # Create a default campaign for new client
        default_campaign_data = {
            "campaign_id": uuid.uuid4(),
            "person_id": created_person['person_id'],
            "campaign_name": f"{created_person['full_name']}'s First Campaign",
            "campaign_type": "general"
        }
        await campaign_queries.create_campaign_in_db(default_campaign_data)
        logger.info(f"Default campaign created for new client {created_person['email']}.")
        
        logger.info(f"New client registered: {created_person['email']} (ID: {created_person['person_id']})")
        return {"message": "User registered successfully. Please log in.", "user_id": created_person["person_id"]}

@router.post("/token", summary="Login - Get Session Token")
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """Standard login endpoint. Use email as username."""
    email = form_data.username
    password = form_data.password

    user_details = await authenticate_user_details(email, password) 
    
    if not user_details:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    session_data = prepare_session_data(user_details)
    request.session.update(session_data)

    logger.info(f"User with email '{user_details['username']}' authenticated via /token.")
    
    return {
        "message": "Login successful. Session initiated.",
        "role": user_details["role"],
        "person_id": user_details.get("person_id"),
        "full_name": user_details.get("full_name"),
        "email": user_details["username"]
    }

@router.post("/request-password-reset", status_code=status.HTTP_202_ACCEPTED, summary="Request Password Reset (Forgot Password)")
async def request_password_reset(request: Request, email: EmailStr = Form(...)):
    """Request password reset for user who forgot their password"""
    try:
        # Check if user exists
        user = await people_queries.get_person_by_email_from_db(email)
        
        if user:
            # Generate secure reset token
            reset_token = secrets.token_urlsafe(32)
            
            # Get client IP for logging
            client_ip = request.client.host if request.client else None
            
            # Store token in database
            token_created = await auth_queries.create_password_reset_token(
                person_id=user['person_id'],
                token=reset_token,
                client_ip=client_ip
            )
            
            if token_created:
                # Send password reset email
                email_sent = await email_service.send_password_reset_email(email, reset_token)
                
                if not email_sent:
                    logger.error(f"Failed to send password reset email to {email}")
                    # Don't reveal email sending failure to user for security
            else:
                logger.error(f"Failed to create password reset token for {email}")
        
        # Always return success message for security (don't reveal if email exists)
        return {
            "message": "If an account with this email exists, a password reset link has been sent to your email address."
        }
        
    except Exception as e:
        logger.error(f"Error in password reset request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request"
        )

@router.post("/reset-password", summary="Reset Password with Token")
async def reset_password_with_token(
    token: str = Form(...),
    new_password: str = Form(..., min_length=8)
):
    """Reset user password using a valid reset token"""
    try:
        # Validate token and get person_id
        person_id = await auth_queries.validate_and_use_reset_token(token)
        
        if not person_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        
        # Hash the new password
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Update user's password
        updated = await people_queries.update_person_password_hash(person_id, hashed_password)
        
        if not updated:
            logger.error(f"Failed to update password for person_id: {person_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update password"
            )
        
        logger.info(f"Password successfully reset for person_id: {person_id}")
        return {"message": "Password reset successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in password reset: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while resetting your password"
        )

@router.post("/logout", summary="Logout User")
async def logout_api(request: Request, response: Response):
    """Logout the current user by clearing their session."""
    username = request.session.get("username", "Unknown user")
    request.session.clear()
    logger.info(f"User {username} logged out via /auth/logout.")
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=Dict[str, Any], summary="Get Current User Info")
async def read_users_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get information about the currently authenticated user."""
    return current_user