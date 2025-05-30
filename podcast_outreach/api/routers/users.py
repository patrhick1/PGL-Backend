# podcast_outreach/api/routers/users.py (or people.py)
import logging
import asyncio
import threading
import json
import uuid
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks, Query, Form
from typing import Dict, Any, Optional, List
from pydantic import EmailStr, BaseModel, Field

from ..schemas.person_schemas import PersonInDB, PersonCreate, PersonUpdate
from ..schemas.settings_schemas import (
    UserDataExportResponse, 
    AccountDeletionRequest, 
    AccountDeletionResponse,
    AccountDeletionConfirm,
    NotificationSettingsUpdate,
    PrivacySettingsUpdate
)
from ..schemas import client_profile_schemas
from podcast_outreach.database.queries import people as people_queries
from ..dependencies import get_current_user, get_admin_user, hash_password, verify_password
from podcast_outreach.logging_config import get_logger

from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import placements as placement_queries
from podcast_outreach.database.queries import client_profiles as client_profile_queries
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.config import ( # For default allowances
    FREE_PLAN_DAILY_DISCOVERY_LIMIT, FREE_PLAN_WEEKLY_DISCOVERY_LIMIT
)
from podcast_outreach.services.tasks.manager import task_manager

logger = get_logger(__name__)

# Placeholder for Email Service - This needs to be implemented or imported from an email service module
class EmailService: # Replace with your actual email service
    async def send_email(self, to_email: str, subject: str, body_html: str):
        logger.info(f"SIMULATING EMAIL to {to_email} | Subject: {subject} | Body: {body_html[:100]}...")
        await asyncio.sleep(0.1) # Simulate async operation
        return True 
email_service = EmailService() # Instantiate your email service or a mock

router = APIRouter(prefix="/users", tags=["Users & People"])

@router.patch("/me/notification-settings", response_model=PersonInDB, summary="Update My Notification Settings")
async def update_my_notification_settings(
    settings_data: NotificationSettingsUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated for settings update.")

    updated_person = await people_queries.update_person_in_db(
        person_id, 
        {"notification_settings": settings_data.model_dump(exclude_unset=True)}
    )
    if not updated_person:
        logger.error(f"Failed to update notification_settings for person_id: {person_id}")
        raise HTTPException(status_code=500, detail="Failed to update notification settings.")
    return PersonInDB(**updated_person)

@router.patch("/me/privacy-settings", response_model=PersonInDB, summary="Update My Privacy Settings")
async def update_my_privacy_settings(
    settings_data: PrivacySettingsUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated for settings update.")
    
    updated_person = await people_queries.update_person_in_db(
        person_id, 
        {"privacy_settings": settings_data.model_dump(exclude_unset=True)}
    )
    if not updated_person:
        logger.error(f"Failed to update privacy_settings for person_id: {person_id}")
        raise HTTPException(status_code=500, detail="Failed to update privacy settings.")
    return PersonInDB(**updated_person)

# CRUD for People (Admin only)
@router.post("/", response_model=PersonInDB, status_code=status.HTTP_201_CREATED, summary="Admin: Create Person")
async def create_person(
    person_data: PersonCreate, 
    admin_user: Dict[str, Any] = Depends(get_admin_user)
):
    # Hash password if provided
    if person_data.dashboard_password:
        person_data.dashboard_password_hash = hash_password(person_data.dashboard_password)
    
    person_dict = person_data.model_dump(exclude_unset=True)
    # Remove plain password if hash was created, to avoid storing it if not handled by schema
    if 'dashboard_password' in person_dict: 
        del person_dict['dashboard_password']

    created_person = await people_queries.create_person_in_db(person_dict)
    if not created_person:
        logger.error(f"Admin: Failed to create person with email: {person_data.email}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create person.")
    return PersonInDB(**created_person)

@router.get("/", response_model=List[PersonInDB], summary="Admin: List People")
async def list_people(
    skip: int = 0, limit: int = 100, 
    admin_user: Dict[str, Any] = Depends(get_admin_user)
):
    people_list = await people_queries.get_all_people_from_db(skip=skip, limit=limit)
    return [PersonInDB(**p) for p in people_list]

@router.get("/{person_id}", response_model=PersonInDB, summary="Admin: Get Person by ID")
async def get_person(
    person_id: int, 
    admin_user: Dict[str, Any] = Depends(get_admin_user)
):
    person = await people_queries.get_person_by_id_from_db(person_id)
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found")
    return PersonInDB(**person)

@router.put("/{person_id}", response_model=PersonInDB, summary="Admin: Update Person")
async def update_person(
    person_id: int, 
    person_update_data: PersonUpdate, 
    admin_user: Dict[str, Any] = Depends(get_admin_user)
):
    update_data = person_update_data.model_dump(exclude_unset=True)
    if person_update_data.dashboard_password:
        update_data["dashboard_password_hash"] = hash_password(person_update_data.dashboard_password)
        if 'dashboard_password' in update_data: # Ensure plain password isn't passed to DB query
            del update_data['dashboard_password']
    
    updated_person = await people_queries.update_person_in_db(person_id, update_data)
    if not updated_person:
        logger.error(f"Admin: Failed to update person_id: {person_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found or update failed")
    return PersonInDB(**updated_person)

@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Admin: Delete Person")
async def delete_person(
    person_id: int, 
    admin_user: Dict[str, Any] = Depends(get_admin_user)
):
    success = await people_queries.delete_person_from_db(person_id)
    if not success:
        logger.warning(f"Admin: Failed to delete person_id: {person_id} (not found or error).")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found or delete failed")
    return

# Placeholder for email sending task - adjust as per your actual implementation
async def send_verification_email_task(email_to: str, token: str):
    await asyncio.sleep(1) # Simulate email sending
    logger.info(f"Simulated sending verification email to {email_to} with token {token}")

@router.post("/request-email-verification", status_code=status.HTTP_202_ACCEPTED, summary="Request Email Verification")
async def request_email_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    user_email = current_user.get("username") # Assuming username in session is the email
    person_id = current_user.get("person_id")

    if not user_email or not person_id:
        logger.warning("Attempt to request email verification for unauthenticated or unidentified user.")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not properly identified for email verification.")

    # Check if email is already verified (you'll need a field in your people table, e.g., 'email_verified_at')
    # For now, let's assume we always send a new one or this logic is elsewhere.
    # person_record = await people_queries.get_person_by_id_from_db(person_id)
    # if person_record.get("email_verified_at"):
    #     return {"message": "Email is already verified."}

    verification_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    # Store token and expiry (e.g., in people table or a separate verification_tokens table)
    # Example: await people_queries.store_email_verification_token(person_id, verification_token, expires_at)
    logger.info(f"Generated email verification token for {user_email} (person_id: {person_id}): {verification_token}, expires: {expires_at.isoformat()}")
    
    # Use background task to send email
    # background_tasks.add_task(send_verification_email_task, user_email, verification_token)
    # Temporarily call it directly for testing since the actual email task is a placeholder
    await send_verification_email_task(user_email, verification_token)

    return {"message": "Verification email sent. Please check your inbox."}

@router.post("/verify-email", summary="Verify Email with Token")
async def verify_email_with_token(token: str = Query(..., min_length=32)):
    # Logic to find user by token, check expiry, mark email as verified
    # Example: verified_user = await people_queries.verify_email_with_token(token)
    # if not verified_user:
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification token.")
    logger.info(f"Received request to verify email with token: {token}")
    # Placeholder response
    return {"message": f"Email verification for token {token} would be processed here. User would be marked as verified."}

# Example structure for a password reset request
# You would need similar token generation, storage, and email sending logic
@router.post("/request-password-reset", status_code=status.HTTP_202_ACCEPTED, summary="Request Password Reset")
async def request_password_reset(email: EmailStr = Form(...)):
    person = await people_queries.get_person_by_email_from_db(email)
    if not person:
        # Even if user not found, return a generic message for security
        logger.info(f"Password reset requested for non-existent email: {email}")
        return {"message": "If an account with this email exists, a password reset link has been sent."}

    reset_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    # Store reset_token and expires_at for the user (e.g., in people table or a dedicated table)
    # await people_queries.store_password_reset_token(person['person_id'], reset_token, expires_at)
    logger.info(f"Generated password reset token for {email} (person_id: {person['person_id']}): {reset_token}, expires: {expires_at.isoformat()}")

    # Send email with reset_token (use background task)
    # background_tasks.add_task(send_password_reset_email, email, reset_token)
    await send_verification_email_task(email, f"Password Reset Token: {reset_token}") # Reusing for simulation

    return {"message": "If an account with this email exists, a password reset link has been sent."}

@router.post("/reset-password", summary="Reset Password with Token")
async def reset_password_with_token(
    token: str = Form(...),
    new_password: str = Form(..., min_length=8)
):
    # Validate token, find user, check expiry
    # Example: user_id = await people_queries.get_user_id_from_reset_token(token)
    # if not user_id:
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired password reset token.")

    logger.info(f"Attempting to reset password with token: {token}")
    # For this placeholder, we'll assume token is valid and we have a user_id (e.g., 1)
    placeholder_user_id = 1 
    
    new_password_hash = hash_password(new_password)
    success = await people_queries.update_person_password_hash(placeholder_user_id, new_password_hash)

    if not success:
        # This might happen if user_id was invalid or DB error
        logger.error(f"Failed to update password for user (placeholder_id: {placeholder_user_id}) using reset token.")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not reset password.")
    
    # Optionally, invalidate the reset token after successful use
    # await people_queries.invalidate_reset_token(token)

    return {"message": "Password has been reset successfully. You can now log in with your new password."}

# --- Data Export Endpoint ---
async def perform_data_export_task(user_id: int, user_email: str, stop_flag: threading.Event):
    """
    Asynchronous task to gather user data and email it.
    This function will be run by the task_manager in a separate thread.
    """
    try:
        logger.info(f"[DataExportTask user_id={user_id}] Starting data export...")
        if stop_flag.is_set(): logger.info(f"[DataExportTask user_id={user_id}] Task cancelled before start."); return

        # 1. Fetch all related data
        # IMPORTANT: Ensure these query functions are async and properly handle DB connections if called from a thread
        # You might need to initialize/close DB pool within this task if task_manager runs it in a new thread context
        # For simplicity, assuming queries can be called.
        
        # await init_db_pool() # If needed within the task thread

        person_data = await people_queries.get_person_by_id_from_db(user_id)
        if not person_data:
            logger.error(f"[DataExportTask user_id={user_id}] User not found.")
            await email_service.send_email(user_email, "Data Export Failed", "We could not find your user account to export data.")
            return

        campaigns_data = await campaign_queries.get_campaigns_by_person_id_for_export(user_id) # Needs new query
        placements_data = await placement_queries.get_placements_for_person_for_export(user_id) # Needs new query
        pitches_data = await pitch_queries.get_pitches_for_person_for_export(user_id) # Needs new query
        # media_kits_data = await media_kit_queries.get_media_kits_for_person(user_id) # When implemented

        if stop_flag.is_set(): logger.info(f"[DataExportTask user_id={user_id}] Task cancelled after data fetch."); return


        # 2. Compile data into a structured format (e.g., JSON)
        export_data = {
            "profile": person_data,
            "campaigns": campaigns_data,
            "placements": placements_data,
            "pitches": pitches_data,
            # "media_kits": media_kits_data,
            "export_timestamp": datetime.utcnow().isoformat()
        }
        
        # Convert to JSON string (or create CSVs and zip them)
        export_content_json = json.dumps(export_data, indent=2, default=str) # default=str for datetime/UUID

        if stop_flag.is_set(): logger.info(f"[DataExportTask user_id={user_id}] Task cancelled before email send."); return

        # 3. Email the data (or a link to it)
        # For large data, upload to secure storage (e.g., S3 presigned URL) and email the link.
        # For smaller data, can attach directly or include in email body (if very small).
        email_subject = "Your PGL System Data Export"
        email_body = f"""
        <p>Hello {person_data.get('full_name', 'User')},</p>
        <p>Your data export from the PGL System is ready. Please find your data attached (or download from the link below).</p>
        <p><strong>Note:</strong> For security, if this is a download link, it may expire.</p>
        <pre>{export_content_json[:2000]}...</pre> 
        <p>If the data is too large to display here, it would be attached or linked.</p>
        <p>Regards,<br>The PGL System Team</p>
        """ # In a real scenario, attach as a file.

        await email_service.send_email(user_email, email_subject, email_body)
        logger.info(f"[DataExportTask user_id={user_id}] Data export email sent to {user_email}.")

    except Exception as e:
        logger.error(f"[DataExportTask user_id={user_id}] Error during data export: {e}", exc_info=True)
        try:
            await email_service.send_email(user_email, "Data Export Failed", f"An error occurred while processing your data export request: {str(e)}")
        except Exception as email_err:
            logger.error(f"[DataExportTask user_id={user_id}] Failed to send error email for data export: {email_err}")
    finally:
        # await close_db_pool() # If DB pool was initialized in this task
        logger.info(f"[DataExportTask user_id={user_id}] Data export task finished.")
        # task_manager.cleanup_task(task_id_from_manager) # If task_manager needs explicit cleanup signal


@router.post("/export-data", response_model=UserDataExportResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_data_export(
    background_tasks: BackgroundTasks,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    person_id = current_user.get("person_id")
    user_email = current_user.get("username") # Assuming username is email

    if not person_id or not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not properly identified.")

    # Using FastAPI's BackgroundTasks for simplicity here.
    # If using your custom task_manager, adapt this part.
    task_id_for_response = str(uuid.uuid4()) # Generate a simple ID for response
    
    logger.info(f"User {person_id} ({user_email}) requested data export. Task ID for response: {task_id_for_response}")

    # If your perform_data_export_task is truly async and handles its own DB connections:
    background_tasks.add_task(perform_data_export_task, person_id, user_email, threading.Event()) # Pass a dummy event if not using task_manager's stop_flag

    # If using your existing TaskManager:
    # task_manager_id = str(uuid.uuid4())
    # task_manager.start_task(task_manager_id, "data_export")
    # thread = threading.Thread(target=asyncio.run, args=(perform_data_export_task(person_id, user_email, task_manager.get_stop_flag(task_manager_id)),))
    # thread.start()
    # task_id_for_response = task_manager_id


    return UserDataExportResponse(
        message="Data export process initiated. You will receive an email with your data shortly.",
        task_id=task_id_for_response # Optional: return a task ID if you want frontend to poll status
    )


# --- Account Deletion Endpoints ---
# Temporary storage for deletion tokens (IN PRODUCTION, USE A DATABASE OR REDIS)
DELETION_TOKENS_DB: Dict[str, Dict[str, Any]] = {} 

@router.post("/delete-account-request", response_model=AccountDeletionResponse)
async def request_account_deletion(
    request_data: AccountDeletionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    person_id = current_user.get("person_id")
    user_email = current_user.get("username")

    if not person_id or not user_email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated.")

    user_record = await people_queries.get_person_by_id_from_db(person_id)
    if not user_record or not user_record.get("dashboard_password_hash"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password not set or user record issue.")

    if not verify_password(request_data.password, user_record["dashboard_password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password.")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=1) # Token valid for 1 hour
    
    DELETION_TOKENS_DB[token] = {"person_id": person_id, "email": user_email, "expires_at": expires_at}
    logger.info(f"Account deletion token generated for user {person_id} ({user_email}). Token: {token[:8]}...")


    # TODO: Construct a proper confirmation URL for your frontend
    # Example: frontend_url = "https://your-frontend.com/confirm-delete?token=" + token
    # For now, just sending the token in the email body for manual use or simple link.
    confirmation_link = f"Please confirm account deletion by using this token: {token} (or clicking a link if implemented)"

    email_subject = "Confirm Account Deletion for PGL System"
    email_body = f"""
    <p>Hello {user_record.get('full_name', 'User')},</p>
    <p>We received a request to delete your account for the PGL System.</p>
    <p>To confirm this action, please use the following token or link within the next hour:</p>
    <p><strong>Token:</strong> {token}</p>
    <p>If you did not request this, please ignore this email or contact support.</p>
    <p>Regards,<br>The PGL System Team</p>
    """
    await email_service.send_email(user_email, email_subject, email_body)

    return AccountDeletionResponse(message="Account deletion confirmation email sent. Please check your inbox.")


@router.post("/delete-account-confirm", response_model=AccountDeletionResponse)
async def confirm_account_deletion(
    confirmation_data: AccountDeletionConfirm,
    request: Request # To clear session after deletion
):
    token_info = DELETION_TOKENS_DB.get(confirmation_data.token)

    if not token_info or token_info["expires_at"] < datetime.utcnow():
        if token_info: # Token expired, remove it
            del DELETION_TOKENS_DB[confirmation_data.token]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired deletion token.")

    person_id_to_delete = token_info["person_id"]
    user_email_deleted = token_info["email"]
    
    logger.info(f"Attempting to delete account for person_id: {person_id_to_delete}")

    # --- Perform Deletion Logic ---
    # This is a critical part. Decide on soft vs. hard delete.
    # Soft delete: Mark as inactive, anonymize PII.
    # Hard delete: Remove records (ensure cascading deletes or manual cleanup of related data).
    
    # Example: Soft Delete (marking as inactive and anonymizing some fields)
    try:
        anonymized_email = f"deleted_{person_id_to_delete}_{secrets.token_hex(4)}@example.com"
        anonymized_name = f"Deleted User {person_id_to_delete}"
        
        update_payload = {
            "email": anonymized_email,
            "full_name": anonymized_name,
            "dashboard_username": f"deleted_{person_id_to_delete}",
            "dashboard_password_hash": None, # Clear password hash
            "role": "deleted", # Or a specific inactive role
            "linkedin_profile_url": None,
            "twitter_profile_url": None,
            # Clear other PII as per your policy
            "notification_settings": {}, # Clear settings
            "privacy_settings": {},
            # Consider what to do with campaigns, placements etc.
            # Option 1: Cascade delete (if DB constraints allow and it's desired)
            # Option 2: Disassociate or anonymize links in related tables
        }
        success = await people_queries.update_person_in_db(person_id_to_delete, update_payload)
        
        if not success:
            raise Exception("Failed to update person record during soft delete.")

        # Clean up the token
        del DELETION_TOKENS_DB[confirmation_data.token]
        
        # Log out the user by clearing their current session if this endpoint is called by an active session
        # This assumes the confirm link might be opened in a browser where the user is still logged in.
        if request.session: # Check if session exists on the request
            request.session.clear()
            logger.info(f"Session cleared for user {user_email_deleted} after account deletion.")

        logger.info(f"Account soft-deleted successfully for person_id: {person_id_to_delete} (formerly {user_email_deleted}).")
        return AccountDeletionResponse(message="Account deleted successfully.")

    except Exception as e:
        logger.error(f"Error during account deletion for person_id {person_id_to_delete}: {e}", exc_info=True)
        # Don't delete token on failure, user might retry with same token if it's still valid
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process account deletion.")
    
# --- Client Profile Management by Admin ---
@router.post("/{person_id}/client-profile", response_model=client_profile_schemas.ClientProfileInDB, summary="Admin: Create or Link Client Profile")
async def admin_create_client_profile(
    person_id: int,
    profile_data_in: client_profile_schemas.ClientProfileCreate, # Use ClientProfileCreate which includes person_id
    admin_user: dict = Depends(get_admin_user)
):
    person = await people_queries.get_person_by_id_from_db(person_id)
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found.")
    if person.get("role") != "client":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This person is not a client.")

    existing_profile = await client_profile_queries.get_client_profile_by_person_id(person_id)
    if existing_profile:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client profile already exists for this person.")

    # Use profile_data_in directly as it should match the structure needed by create_client_profile
    # The query function will handle default allowances based on plan_type.
    created_profile = await client_profile_queries.create_client_profile(person_id, profile_data_in.model_dump())
    if not created_profile:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create client profile.")
    return client_profile_schemas.ClientProfileInDB(**created_profile)


@router.put("/{person_id}/client-profile", response_model=client_profile_schemas.ClientProfileInDB, summary="Admin: Update Client Profile")
async def admin_update_client_profile(
    person_id: int,
    profile_update_data: client_profile_schemas.ClientProfileUpdate,
    admin_user: dict = Depends(get_admin_user)
):
    person = await people_queries.get_person_by_id_from_db(person_id)
    if not person or person.get("role") != "client":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client person not found.")

    update_data_dict = profile_update_data.model_dump(exclude_unset=True)
    if not update_data_dict:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided.")

    updated_profile = await client_profile_queries.update_client_profile(person_id, update_data_dict)
    if not updated_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client profile not found or update failed.")
    return client_profile_schemas.ClientProfileInDB(**updated_profile)

@router.get("/{person_id}/client-profile", response_model=client_profile_schemas.ClientProfileInDB, summary="Admin: Get Client Profile")
async def admin_get_client_profile(person_id: int, admin_user: dict = Depends(get_admin_user)):
    profile = await client_profile_queries.get_client_profile_by_person_id(person_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client profile not found for this person.")
    return client_profile_schemas.ClientProfileInDB(**profile)