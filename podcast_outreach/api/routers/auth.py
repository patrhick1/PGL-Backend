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
from podcast_outreach.database.queries import client_profiles as client_profile_queries
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
    Register a new user or convert an existing prospect to a client.
    
    Three scenarios:
    1. Auto-convert prospect (if existing user with role 'prospect' found)
    2. Manual prospect conversion (if prospect_person_id provided)
    3. New user registration (if no existing user found)
    """
    
    # Hash the password first
    hashed_password = hash_password(registration_data.password)
    
    # Check if user already exists
    existing_user = await people_queries.get_person_by_email_from_db(registration_data.email)
    
    if existing_user:
        # If user exists with non-prospect role - conflict
        if existing_user.get('role') != 'prospect':
            logger.warning(f"Registration attempt for existing {existing_user.get('role')} account: {registration_data.email}")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already exists with this email address.")
        
        # If user exists and is a prospect - convert them to client
        elif existing_user.get('role') == 'prospect':
            logger.info(f"Auto-converting existing prospect {existing_user['person_id']} to client for email: {registration_data.email}")
            
            person_update_data = {
                "full_name": registration_data.full_name,
                "dashboard_password_hash": hashed_password,
                "role": "client",
                "dashboard_username": registration_data.email
            }
            updated_person = await people_queries.update_person_in_db(existing_user['person_id'], person_update_data)
            if not updated_person:
                logger.error(f"Failed to update prospect person {existing_user['person_id']} to client.")
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update user account.")

            # Find and update any associated prospect campaigns
            prospect_campaigns = await campaign_queries.get_all_campaigns_from_db(person_id=existing_user['person_id'])
            for campaign in prospect_campaigns:
                if campaign.get('campaign_type') == 'lead_magnet_prospect':
                    campaign_update_data = {"campaign_type": "targetted media campaign"}
                    updated_campaign = await campaign_queries.update_campaign(campaign['campaign_id'], campaign_update_data)
                    if updated_campaign:
                        logger.info(f"Updated campaign {campaign['campaign_id']} type to targetted media campaign")
            
            # Create client profile for auto-converted prospect
            await _ensure_client_profile_exists(updated_person['person_id'], updated_person['full_name'])
            
            logger.info(f"Prospect {updated_person['email']} (ID: {updated_person['person_id']}) auto-converted to client.")
            return {"message": "Account activated successfully. Please log in.", "user_id": updated_person["person_id"]}

    if registration_data.prospect_person_id:
        # --- Manual Prospect Conversion (with explicit IDs) --- 
        logger.info(f"Manual prospect conversion for prospect_person_id: {registration_data.prospect_person_id} for email: {registration_data.email}")
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
            campaign_update_data = {"campaign_type": "targetted media campaign"}
            updated_campaign = await campaign_queries.update_campaign(registration_data.prospect_campaign_id, campaign_update_data)
            if updated_campaign:
                logger.info(f"Prospect campaign {registration_data.prospect_campaign_id} type updated for converted client {updated_person['email']}.")
            else:
                logger.warning(f"Could not update prospect campaign type for {registration_data.prospect_campaign_id} during conversion.")
        
        # Create client profile for manually converted prospect
        await _ensure_client_profile_exists(updated_person['person_id'], updated_person['full_name'])
        
        logger.info(f"Prospect {updated_person['email']} (ID: {updated_person['person_id']}) manually converted to client.")
        return {"message": "Account activated successfully. Please log in.", "user_id": updated_person["person_id"]}

    else:
        # --- Standard New User Registration ---
        logger.info(f"Creating new user account for email: {registration_data.email}")

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
            "campaign_type": "targetted media campaign"
        }
        await campaign_queries.create_campaign_in_db(default_campaign_data)
        logger.info(f"Default campaign created for new client {created_person['email']}.")
        
        # Create client profile for new user
        await _ensure_client_profile_exists(created_person['person_id'], created_person['full_name'])
        
        logger.info(f"New client registered: {created_person['email']} (ID: {created_person['person_id']})")
        return {"message": "User registered successfully. Please log in.", "user_id": created_person["person_id"]}

async def _ensure_client_profile_exists(person_id: int, full_name: str):
    """
    Helper function to ensure a client profile exists for a person.
    Creates one with default settings if it doesn't exist.
    """
    try:
        # Check if profile already exists
        existing_profile = await client_profile_queries.get_client_profile_by_person_id(person_id)
        
        if not existing_profile:
            # Create default client profile
            profile_data = {
                "plan_type": "free",
                "daily_discovery_allowance": 10,  # Default free plan limit
                "weekly_discovery_allowance": 50,  # Default free plan limit
            }
            
            created_profile = await client_profile_queries.create_client_profile(person_id, profile_data)
            
            if created_profile:
                logger.info(f"Created client profile for {full_name} (person_id: {person_id})")
            else:
                logger.error(f"Failed to create client profile for {full_name} (person_id: {person_id})")
        else:
            logger.debug(f"Client profile already exists for {full_name} (person_id: {person_id})")
            
    except Exception as e:
        logger.error(f"Error ensuring client profile for person_id {person_id}: {e}")
        # Don't raise exception - client profile creation is not critical for registration

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
    """Get information about the currently authenticated user including profile and banner images."""
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=401, detail="User not authenticated.")
    
    # Fetch full user profile from database to get image URLs
    person = await people_queries.get_person_by_id_from_db(person_id)
    if not person:
        raise HTTPException(status_code=404, detail="User profile not found.")
    
    # Combine session data with profile data
    user_info = {
        **current_user,  # Include session data (username, role, person_id, full_name)
        "profile_image_url": person.get("profile_image_url"),
        "profile_banner_url": person.get("profile_banner_url"),
        "bio": person.get("bio"),
        "website": person.get("website"),
        "location": person.get("location"),
        "timezone": person.get("timezone"),
        "linkedin_profile_url": person.get("linkedin_profile_url"),
        "twitter_profile_url": person.get("twitter_profile_url"),
        "instagram_profile_url": person.get("instagram_profile_url"),
        "tiktok_profile_url": person.get("tiktok_profile_url"),
        "notification_settings": person.get("notification_settings"),
        "privacy_settings": person.get("privacy_settings")
    }
    
    return user_info