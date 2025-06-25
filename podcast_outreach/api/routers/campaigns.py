# podcast_outreach/api/routers/campaigns.py

import uuid
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import logging

# Import schemas
from ..schemas.campaign_schemas import (
    CampaignCreate, CampaignUpdate, CampaignInDB, AnglesBioTriggerResponse,
    QuestionnaireSubmitData, QuestionnaireDraftData # <<< NEW IMPORT
)

# Import modular queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import people as people_queries # Needed for person_id validation if desired

# Import AnglesProcessorPG (assuming it's now at services/campaigns/bio_generator.py)
from podcast_outreach.services.campaigns.angles_generator import AnglesProcessorPG # Corrected import path

from podcast_outreach.services.campaigns.questionnaire_processor import (
    process_campaign_questionnaire_submission,
    QuestionnaireProcessor
) 

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

@router.get("/", response_model=List[CampaignInDB], summary="List Campaigns")
async def list_campaigns_api(
    person_id_query: Optional[int] = Query(None, alias="person_id", description="Filter campaigns by person ID (client ID). Admin/Staff can use this. Clients are auto-filtered."),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=10, le=500),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Lists campaign records with pagination.
    - Clients will only see their own campaigns.
    - Staff/Admins can see all or filter by person_id.
    """
    target_person_id: Optional[int] = None

    if user.get("role") == "client":
        user_person_id = user.get("person_id")
        if not user_person_id:
            logger.error(f"Client user {user.get('username')} missing person_id in token/session.")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User profile incomplete.")
        
        if person_id_query is not None and person_id_query != user_person_id:
            logger.warning(f"Client {user_person_id} attempted to access campaigns for person_id {person_id_query}.")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Clients can only access their own campaigns.")
        target_person_id = user_person_id
    elif user.get("role") in ["staff", "admin"]:
        if person_id_query is not None:
            target_person_id = person_id_query
        # If person_id_query is None, target_person_id remains None, fetching all campaigns (respecting pagination)
    else: # Should not happen if roles are well-defined and get_current_user enforces valid roles
        logger.error(f'User with unrecognized role \'{user.get("role")}\' attempted to list campaigns.')
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    try:
        campaigns_from_db = await campaign_queries.get_all_campaigns_from_db(
            skip=skip, 
            limit=limit, 
            person_id=target_person_id
        )
        return [CampaignInDB(**c) for c in campaigns_from_db]
    except Exception as e:
        logger.exception(f"Error in list_campaigns_api (target_person_id: {target_person_id}): {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/{campaign_id}", response_model=CampaignInDB, summary="Get Specific Campaign")
async def get_campaign_api(campaign_id: uuid.UUID, user: dict = Depends(get_current_user)):
    """
    Retrieves a specific campaign record by ID. 
    Clients can view their own campaigns. Staff/Admin can view any campaign.
    """
    try:
        campaign_from_db = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign_from_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign with ID {campaign_id} not found.")
        
        # Authorization: Ensure user can access this campaign
        if user.get("role") == "client":
            if campaign_from_db.get("person_id") != user.get("person_id"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only view your own campaigns.")
        # Admin/staff can view any campaign
        
        return CampaignInDB(**campaign_from_db)
    except HTTPException:
        raise
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

@router.patch("/me/{campaign_id}", response_model=CampaignInDB, summary="Update My Campaign")
async def update_my_campaign_api(
    campaign_id: uuid.UUID, 
    campaign_update: CampaignUpdate, 
    user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Updates a campaign owned by the current user. Clients can only edit their own campaigns.
    Restricted fields like person_id cannot be changed by clients.
    """
    # First check if campaign exists and user owns it
    campaign = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
    
    # Authorization: Ensure user owns this campaign (unless admin/staff)
    if user.get("role") == "client":
        if campaign.get("person_id") != user.get("person_id"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own campaigns.")
    # Admin/staff can edit any campaign via this endpoint too
    
    update_data = campaign_update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update data provided.")
    
    # Prevent clients from changing restricted fields
    if user.get("role") == "client":
        restricted_fields = ["person_id", "attio_client_id"]
        for field in restricted_fields:
            if field in update_data:
                del update_data[field]
                logger.warning(f"Client {user.get('person_id')} attempted to update restricted field '{field}' on campaign {campaign_id}")
    
    try:
        updated_db_campaign = await campaign_queries.update_campaign(campaign_id, update_data)
        if not updated_db_campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign update failed.")
        return CampaignInDB(**updated_db_campaign)
    except Exception as e:
        logger.exception(f"Error in update_my_campaign_api for ID {campaign_id}: {e}")
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

@router.post("/{campaign_id}/submit-questionnaire", 
            summary="Submit Questionnaire Data with Social Media Enrichment")
async def submit_campaign_questionnaire_api(
    campaign_id: uuid.UUID, 
    submission_data: QuestionnaireSubmitData,
    user: dict = Depends(get_current_user),
    enable_social_enrichment: bool = Query(default=True, description="Enable social media enrichment processing")
):
    """
    Enhanced questionnaire submission with automatic social media processing.
    
    Features:
    - Processes questionnaire responses
    - Extracts and validates social media handles
    - Generates AI-powered profile insights
    - Creates ideal podcast description for vetting
    - Generates mock interview transcript
    
    Set enable_social_enrichment=false to use legacy processing only.
    """
    try:
        logger.info(f"Received questionnaire submission for campaign {campaign_id} (social_enrichment={enable_social_enrichment})")
        
        campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

        # Authorization: Ensure the current user is the owner or an admin/staff
        if user.get("role") not in ["admin", "staff"] and campaign.get("person_id") != user.get("person_id"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to submit questionnaire for this campaign")

        if enable_social_enrichment:
            # Use enhanced processing with social media enrichment
            processor = QuestionnaireProcessor()
            result = await processor.process_questionnaire_with_social_enrichment(
                str(campaign_id), 
                submission_data.questionnaire_data
            )
            
            if result.get("success"):
                updated_campaign = await campaign_queries.get_campaign_by_id(campaign_id)
                if not updated_campaign:
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve campaign after update.")
                
                return {
                    "status": "success",
                    "message": "Questionnaire processed successfully with social media enrichment",
                    "campaign": CampaignInDB(**updated_campaign),
                    "social_insights": {
                        "social_handles_found": len(result.get("social_profile", {}).get("handles", [])),
                        "expertise_topics": result.get("social_profile", {}).get("expertise_topics", []),
                        "ideal_podcast_description": result.get("ideal_podcast_description", "")
                    }
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Enhanced questionnaire processing failed: {result.get('error', 'Unknown error')}"
                )
        else:
            # Use legacy processing (backward compatibility)
            success = await process_campaign_questionnaire_submission(str(campaign_id), submission_data.questionnaire_responses)
            
            if success:
                updated_campaign = await campaign_queries.get_campaign_by_id(campaign_id)
                if not updated_campaign:
                    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve campaign after update.")
                
                return {
                    "status": "success", 
                    "message": "Questionnaire processed successfully (legacy mode)",
                    "campaign": CampaignInDB(**updated_campaign)
                }
            else:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process questionnaire data.")
                
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.exception(f"Unhandled exception during questionnaire submission for campaign {campaign_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")
    

@router.post("/{campaign_id}/save-questionnaire-draft", 
            response_model=CampaignInDB, 
            summary="Save Questionnaire Draft")
async def save_campaign_questionnaire_draft_api(
    campaign_id: uuid.UUID,
    draft_data: QuestionnaireDraftData,
    user: dict = Depends(get_current_user)
):
    """
    Saves a draft of the questionnaire data for a specific campaign.
    Accessible by the client who owns the campaign or staff/admin.
    """
    campaign = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    if user.get("role") not in ["admin", "staff"] and campaign.get("person_id") != user.get("person_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to save draft for this campaign")

    update_payload = {"questionnaire_responses": draft_data.questionnaire_data}
    
    try:
        updated_campaign = await campaign_queries.update_campaign(campaign_id, update_payload)
        if not updated_campaign:
            # This case might indicate an issue with update_campaign or data itself, 
            # though get_campaign_by_id right before should have caught non-existence.
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save questionnaire draft.")
        return CampaignInDB(**updated_campaign)
    except Exception as e:
        logger.error(f"Error saving questionnaire draft for campaign {campaign_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error saving draft: {str(e)}")


@router.post("/{campaign_id}/generate-angles-bio", response_model=AnglesBioTriggerResponse, summary="Trigger Bio & Angles Generation")
async def trigger_angles_bio_generation_api(campaign_id: uuid.UUID, user: dict = Depends(get_current_user)):
    """
    Triggers the AI-powered generation of client bio and talking angles for a campaign.
    Requires the campaign to have mock_interview_trancript populated (usually from questionnaire).
    Clients can generate bio/angles for their own campaigns. Staff/Admin can generate for any campaign.
    """
    campaign_exists = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign_exists:
         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found.")
    
    # Authorization: Ensure user can access this campaign
    if user.get("role") == "client":
        if campaign_exists.get("person_id") != user.get("person_id"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only generate bio/angles for your own campaigns.")
    # Admin/staff can generate for any campaign
    
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




