# podcast_outreach/api/routers/campaigns.py

import uuid
from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import logging

# Import schemas
from ..schemas.campaign_schemas import (
    CampaignCreate, CampaignUpdate, CampaignInDB, AnglesBioTriggerResponse,
    QuestionnaireSubmitData # <<< NEW IMPORT
)

# Import modular queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import people as people_queries # Needed for person_id validation if desired

# Import AnglesProcessorPG (assuming it's now at services/campaigns/bio_generator.py)
from podcast_outreach.services.campaigns.angles_generator import AnglesProcessorPG # Corrected import path

from podcast_outreach.services.campaigns.questionnaire_processor import process_campaign_questionnaire_submission 

# Import dependencies for authentication
from ..dependencies import get_current_user, get_admin_user, get_staff_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

# Add a simple test endpoint to debug database connectivity
@router.get("/test", summary="Test Database Connectivity")
async def test_campaigns_db():
    """
    Test endpoint to verify database connectivity without authentication.
    """
    try:
        # Try to fetch campaigns from database
        campaigns_from_db = await campaign_queries.get_all_campaigns_from_db(skip=0, limit=1)
        return {
            "status": "success", 
            "message": "Database connection working",
            "campaign_count": len(campaigns_from_db),
            "test_timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.exception(f"Error in test_campaigns_db: {e}")
        return {
            "status": "error",
            "message": f"Database error: {str(e)}",
            "test_timestamp": datetime.now().isoformat()
        }

@router.post("/", response_model=CampaignInDB, status_code=status.HTTP_201_CREATED, summary="Create New Campaign")
async def create_campaign_api(campaign: CampaignCreate, user: dict = Depends(get_admin_user)):
    """
    Creates a new campaign record. Admin access required.
    """
    campaign_dict = campaign.model_dump()
    try:
        # Optional: Validate person_id exists
        person_exists = await people_queries.get_person_by_id_from_db(campaign.person_id)
        if not person_exists:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Person with ID {campaign.person_id} does not exist.")

        created_db_campaign = await campaign_queries.create_campaign_in_db(campaign_dict)
        if not created_db_campaign:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create campaign in database.")
        return CampaignInDB(**created_db_campaign)
    except HTTPException:
        raise # Re-raise FastAPI HTTPExceptions
    except Exception as e:
        logger.exception(f"Error in create_campaign_api for campaign name {campaign.campaign_name}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/", response_model=List[CampaignInDB], summary="List All Campaigns")
async def list_campaigns_api(skip: int = 0, limit: int = 100, user: dict = Depends(get_current_user)):
    """
    Lists all campaign records with pagination. Staff or Admin access required.
    """
    try:
        campaigns_from_db = await campaign_queries.get_all_campaigns_from_db(skip=skip, limit=limit)
        return [CampaignInDB(**c) for c in campaigns_from_db]
    except Exception as e:
        logger.exception(f"Error in list_campaigns_api: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/{campaign_id}", response_model=CampaignInDB, summary="Get Specific Campaign")
async def get_campaign_api(campaign_id: uuid.UUID, user: dict = Depends(get_current_user)):
    """
    Retrieves a specific campaign record by ID. Staff or Admin access required.
    """
    try:
        campaign_from_db = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign_from_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign with ID {campaign_id} not found.")
        return CampaignInDB(**campaign_from_db)
    except Exception as e:
        logger.exception(f"Error in get_campaign_api for ID {campaign_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.put("/{campaign_id}", response_model=CampaignInDB, summary="Update Campaign")
async def update_campaign_api(campaign_id: uuid.UUID, campaign_update: CampaignUpdate, user: dict = Depends(get_admin_user)):
    """
    Updates an existing campaign record. Admin access required.
    """
    update_data = campaign_update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided.")
    try:
        # Optional: Validate person_id if it's being updated
        if 'person_id' in update_data and update_data['person_id'] is not None:
            person_exists = await people_queries.get_person_by_id_from_db(update_data['person_id'])
            if not person_exists:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Person with ID {update_data['person_id']} does not exist.")

        updated_db_campaign = await campaign_queries.update_campaign(campaign_id, update_data)
        if not updated_db_campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign with ID {campaign_id} not found or update failed.")
        return CampaignInDB(**updated_db_campaign)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in update_campaign_api for ID {campaign_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Campaign")
async def delete_campaign_api(campaign_id: uuid.UUID, user: dict = Depends(get_admin_user)):
    """
    Deletes a campaign record. Admin access required.
    """
    try:
        success = await campaign_queries.delete_campaign_from_db(campaign_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign with ID {campaign_id} not found or delete failed.")
        return # Returns 204 No Content on success
    except Exception as e:
        logger.exception(f"Error in delete_campaign_api for ID {campaign_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/{campaign_id}/generate-angles-bio", response_model=AnglesBioTriggerResponse, summary="Trigger Bio & Angles Generation")
async def trigger_angles_bio_generation_api(campaign_id: uuid.UUID, user: dict = Depends(get_current_user)):
    """
    Triggers the AI-powered generation of client bio and talking angles for a campaign.
    Staff or Admin access required.
    """
    campaign_exists = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign_exists:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found, cannot trigger generation.")

    processor = AnglesProcessorPG() 
    try:
        result = await processor.process_campaign(str(campaign_id))
        
        response_status = result.get("status", "error")
        response_message = result.get("reason") or result.get("bio_doc_link") or "Processing completed."
        if response_status == "success":
            response_message = f"Successfully generated Bio & Angles for campaign {campaign_id}."

        return AnglesBioTriggerResponse(
            campaign_id=campaign_id,
            status=response_status,
            message=response_message,
            details=result
        )
    except Exception as e:
        logger.exception(f"Unhandled exception during angles/bio generation trigger for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred during generation: {str(e)}")
    finally:
        processor.cleanup()


@router.post("/{campaign_id}/submit-questionnaire", 
            response_model=CampaignInDB, # Or a more specific response
            summary="Submit Questionnaire Data for a Campaign")
async def submit_campaign_questionnaire_api(
    campaign_id: uuid.UUID, 
    submission_data: QuestionnaireSubmitData, # Use the new Pydantic model for request body
    user: dict = Depends(get_current_user) # Client or Staff/Admin can submit
):
    """
    Submits questionnaire data for a specific campaign.
    This will update the campaign with the questionnaire responses and a
    generated mock interview transcript.
    Accessible by the client who owns the campaign or staff/admin.
    """
    campaign = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    # Authorization: Ensure the current user is the owner or an admin/staff
    if user.get("role") not in ["admin", "staff"] and campaign.get("person_id") != user.get("person_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to submit questionnaire for this campaign")

    success = await process_campaign_questionnaire_submission(campaign_id, submission_data.questionnaire_data)
    
    if success:
        updated_campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not updated_campaign: # Should not happen if update was successful
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve campaign after update.")
        return CampaignInDB(**updated_campaign)
    else:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process questionnaire data.")
    

@router.post("/{campaign_id}/generate-angles-bio", response_model=AnglesBioTriggerResponse, summary="Trigger Bio & Angles Generation")
async def trigger_angles_bio_generation_api(campaign_id: uuid.UUID, user: dict = Depends(get_staff_user)): # Changed to get_staff_user
    """
    Triggers the AI-powered generation of client bio and talking angles for a campaign.
    Requires the campaign to have mock_interview_trancript populated (usually from questionnaire).
    Staff or Admin access required.
    """
    campaign_exists = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign_exists:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found.")
    
    if not campaign_exists.get("mock_interview_trancript"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Campaign {campaign_id} does not have a mock interview transcript. Please submit the questionnaire first.")

    processor = AnglesProcessorPG() 
    try:
        # The process_campaign method in AnglesProcessorPG should use the mock_interview_trancript
        # and other fields from the campaign record.
        result = await processor.process_campaign(str(campaign_id))
        
        response_status = result.get("status", "error")
        response_message = result.get("reason") or result.get("bio_doc_link") or "Processing completed."
        if response_status == "success":
            response_message = f"Successfully generated Bio & Angles for campaign {campaign_id}."

        return AnglesBioTriggerResponse(
            campaign_id=campaign_id,
            status=response_status,
            message=response_message,
            details=result
        )
    except Exception as e:
        logger.exception(f"Unhandled exception during angles/bio generation trigger for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")
    finally:
        processor.cleanup()