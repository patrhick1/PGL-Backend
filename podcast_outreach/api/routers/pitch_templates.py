# podcast_outreach/api/routers/pitch_templates.py
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status, Path, Body
import uuid
from datetime import datetime

from podcast_outreach.api.schemas import pitch_template_schemas as schemas # Import new schemas
from podcast_outreach.database.queries import pitch_templates as queries # Import new queries
from podcast_outreach.api.dependencies import get_current_user, get_admin_user, get_staff_user # Assuming these exist

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pitch-templates",
    tags=["Pitch Templates"],
    dependencies=[Depends(get_staff_user)] # Require at least staff user for all template operations
)

@router.post("/", response_model=schemas.PitchTemplateInDB, status_code=status.HTTP_201_CREATED)
async def create_pitch_template(
    template_in: schemas.PitchTemplateCreate,
    current_user: Dict[str, Any] = Depends(get_current_user) # get_staff_user already applied at router level
):
    """Create a new pitch template."""
    existing_template = await queries.get_template_by_id(template_in.template_id)
    if existing_template:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Pitch template with ID '{template_in.template_id}' already exists."
        )
    
    template_data = template_in.model_dump()
    if not template_data.get('created_by'): # Set created_by if not provided
        template_data['created_by'] = current_user.get('username') or current_user.get('email') # or user_id

    created_template = await queries.create_template(template_data)
    if not created_template:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create pitch template '{template_in.template_id}'."
        )
    return schemas.PitchTemplateInDB(**created_template)

@router.get("/", response_model=List[schemas.PitchTemplateInDB])
async def list_pitch_templates(skip: int = 0, limit: int = 100):
    """List all pitch templates."""
    templates_db = await queries.list_templates(skip=skip, limit=limit)
    return [schemas.PitchTemplateInDB(**t) for t in templates_db]

@router.get("/{template_id_str}", response_model=schemas.PitchTemplateInDB)
async def get_pitch_template(
    template_id_str: str = Path(..., description="The ID of the pitch template to retrieve", min_length=3, max_length=100, regex=r"^[a-zA-Z0-9_-]+$")
):
    """Retrieve a specific pitch template by its ID."""
    template_db = await queries.get_template_by_id(template_id_str)
    if not template_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pitch template with ID '{template_id_str}' not found."
        )
    return schemas.PitchTemplateInDB(**template_db)

@router.put("/{template_id_str}", response_model=schemas.PitchTemplateInDB)
async def update_pitch_template(
    template_id_str: str = Path(..., description="The ID of the pitch template to update", min_length=3, max_length=100, regex=r"^[a-zA-Z0-9_-]+$"),
    template_update: schemas.PitchTemplateUpdate = Body(...),
    current_user: Dict[str, Any] = Depends(get_current_user) # For logging who updated, if needed
):
    """Update an existing pitch template."""
    existing_template = await queries.get_template_by_id(template_id_str)
    if not existing_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pitch template with ID '{template_id_str}' not found for update."
        )
    
    update_data = template_update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update data provided."
        )

    # Optionally set/update a modified_by field if you add one to your table/schemas
    # update_data['modified_by'] = current_user.get('username')

    updated_template = await queries.update_template(template_id_str, update_data)
    if not updated_template:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update pitch template '{template_id_str}'."
        )
    return schemas.PitchTemplateInDB(**updated_template)

@router.delete("/{template_id_str}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pitch_template(
    template_id_str: str = Path(..., description="The ID of the pitch template to delete", min_length=3, max_length=100, regex=r"^[a-zA-Z0-9_-]+$"),
    # current_user: Dict[str, Any] = Depends(get_admin_user) # Example: Only admins can delete
):
    """Delete a pitch template by its ID. (Requires admin privileges if get_admin_user is used)."""
    # Router-level dependency is get_staff_user. If stricter access is needed for DELETE:
    # You'd add `Depends(get_admin_user)` here and remove it from router if other endpoints are staff-ok.
    
    deleted = await queries.delete_template(template_id_str)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, # Or 500 if deletion failed for other reasons
            detail=f"Pitch template with ID '{template_id_str}' not found or could not be deleted."
        )
    return # No content response 