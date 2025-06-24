# podcast_outreach/api/routers/people.py

import uuid
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional, Dict, Any
import logging
import asyncpg # For specific asyncpg exceptions

# Import schemas
from ..schemas.person_schemas import PersonCreate, PersonUpdate, PersonInDB, PersonSetPassword, UserProfileUpdate

# Import modular queries
from podcast_outreach.database.queries import people as people_queries

# Import dependencies (for password hashing and user auth)
from ..dependencies import get_current_user, get_admin_user, hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/people", tags=["People"])

@router.post("/", response_model=PersonInDB, status_code=status.HTTP_201_CREATED, summary="Create New Person")
async def create_person_api(person_data: PersonCreate, user: dict = Depends(get_admin_user)):
    """
    Creates a new person record. Admin access required.
    """
    person_dict = person_data.model_dump()
    try:
        # Check if email already exists, as it's unique
        existing_person_by_email = await people_queries.get_person_by_email_from_db(person_data.email)
        if existing_person_by_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Person with email {person_data.email} already exists.")
        
        created_db_person = await people_queries.create_person_in_db(person_dict)
        if not created_db_person:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create person in database.")
        return PersonInDB(**created_db_person)
    except asyncpg.exceptions.UniqueViolationError: # Catch UniqueViolation specifically if not caught in db_service
         raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Person with email {person_data.email} already exists (unique constraint).")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in create_person_api for email {person_data.email}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/", response_model=List[PersonInDB], summary="List All People")
async def list_people_api(skip: int = 0, limit: int = 100, user: dict = Depends(get_current_user)):
    """
    Lists all person records with pagination. Staff or Admin access required.
    """
    try:
        people_from_db = await people_queries.get_all_people_from_db(skip=skip, limit=limit)
        return [PersonInDB(**p) for p in people_from_db]
    except Exception as e:
        logger.exception(f"Error in list_people_api: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/{person_id}", response_model=PersonInDB, summary="Get Specific Person by ID")
async def get_person_api(person_id: int, user: dict = Depends(get_current_user)):
    """
    Retrieves a specific person record by ID. Staff or Admin access required.
    """
    try:
        person_from_db = await people_queries.get_person_by_id_from_db(person_id)
        if not person_from_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Person with ID {person_id} not found.")
        return PersonInDB(**person_from_db)
    except Exception as e:
        logger.exception(f"Error in get_person_api for ID {person_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/email/{email}", response_model=PersonInDB, summary="Get Specific Person by Email")
async def get_person_by_email_api(email: str, user: dict = Depends(get_current_user)):
    """
    Retrieves a specific person record by email. Staff or Admin access required.
    """
    try:
        person_from_db = await people_queries.get_person_by_email_from_db(email)
        if not person_from_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Person with email {email} not found.")
        return PersonInDB(**person_from_db)
    except Exception as e:
        logger.exception(f"Error in get_person_by_email_api for email {email}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put("/{person_id}", response_model=PersonInDB, summary="Update Person")
async def update_person_api(person_id: int, person_update_data: PersonUpdate, user: dict = Depends(get_admin_user)):
    """
    Updates an existing person record. Admin access required.
    """
    update_data = person_update_data.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided.")
    try:
        # If email is being updated, check if the new email already exists for another person
        if "email" in update_data and update_data['email'] is not None:
            existing_person_with_new_email = await people_queries.get_person_by_email_from_db(update_data["email"])
            if existing_person_with_new_email and existing_person_with_new_email["person_id"] != person_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Email {update_data['email']} already in use by another person.")

        updated_db_person = await people_queries.update_person_in_db(person_id, update_data)
        if not updated_db_person:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Person with ID {person_id} not found or update failed.")
        return PersonInDB(**updated_db_person)
    except asyncpg.exceptions.UniqueViolationError: # Catch UniqueViolation specifically if not caught in db_service
         raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Update failed: email {update_data.get('email')} may already exist for another person (unique constraint). ")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in update_person_api for ID {person_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Person")
async def delete_person_api(person_id: int, user: dict = Depends(get_admin_user)):
    """
    Deletes a person record. Admin access required.
    """
    try:
        success = await people_queries.delete_person_from_db(person_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Person with ID {person_id} not found or delete failed.")
        return # Returns 204 No Content on success
    except Exception as e:
        logger.exception(f"Error in delete_person_api for ID {person_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put("/{person_id}/set-password", status_code=status.HTTP_204_NO_CONTENT, summary="Set or Change Person's Dashboard Password")
async def set_person_password_api(person_id: int, password_data: PersonSetPassword, user: dict = Depends(get_admin_user)):
    """
    Sets or changes the dashboard password for a specified person.
    The password will be hashed before being stored. Admin access required.
    """
    person_exists = await people_queries.get_person_by_id_from_db(person_id)
    if not person_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Person with ID {person_id} not found.")

    hashed_password_value = hash_password(password_data.password)

    try:
        success = await people_queries.update_person_password_hash(person_id, hashed_password_value)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Person not found or password update failed at DB level.") 
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error setting password for person ID {person_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to set password: {str(e)}")
    
    logger.info(f"Password updated successfully for person ID: {person_id}")
    return # Return 204 No Content


@router.patch("/me/profile", response_model=PersonInDB, summary="Update Current User's Profile")
async def update_current_user_profile(
    profile_data: UserProfileUpdate, 
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Allows the authenticated user to update their own profile information.
    """
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated properly.")

    update_data_dict = profile_data.model_dump(exclude_unset=True)
    
    # Prevent users from updating certain fields like role or email directly if needed
    # For example, if email change requires verification:
    # if "email" in update_data_dict and update_data_dict["email"] != current_user.get("username"):
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email change requires a separate verification process.")
    # if "role" in update_data_dict:
    #     del update_data_dict["role"] # Users cannot change their own role

    if not update_data_dict:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided.")

    try:
        # If dashboard_username is being updated, check for uniqueness against other users
        if "dashboard_username" in update_data_dict and update_data_dict["dashboard_username"]:
            existing_user_with_username = await people_queries.get_person_by_dashboard_username(update_data_dict["dashboard_username"])
            if existing_user_with_username and existing_user_with_username["person_id"] != person_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Dashboard username already taken.")
        
        # If email is being updated, check for uniqueness (if self-service email change is allowed)
        if "email" in update_data_dict and update_data_dict["email"]:
            existing_user_with_email = await people_queries.get_person_by_email_from_db(update_data_dict["email"])
            if existing_user_with_email and existing_user_with_email["person_id"] != person_id:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email address already in use.")


        updated_person = await people_queries.update_person_in_db(person_id, update_data_dict)
        if not updated_person:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User profile not found or update failed.")
        
        # IMPORTANT: If email or other critical session fields are updated,
        # you might need to update the session data here.
        # For example, if email (which is `username` in session) changes:
        # request.session["username"] = updated_person["email"]
        # This requires `request: Request` to be injected into this endpoint.
        # For simplicity, this example assumes `useAuth` will refetch `/auth/me` which will have updated data.

        return PersonInDB(**updated_person)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error updating profile for person ID {person_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))