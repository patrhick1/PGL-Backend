# podcast_outreach/api/routers/public_lead_magnet.py
import logging
import uuid
import json
from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any

from podcast_outreach.api.schemas import lead_magnet_schemas as schemas
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.services.media_kits.generator import MediaKitService
# Assuming this helper function exists or can be created, e.g., in questionnaire_processor or a utils file
from podcast_outreach.services.campaigns.questionnaire_processor import construct_mock_interview_from_questionnaire

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/public/lead-magnet",
    tags=["Lead Magnet (Public)"]
)

@router.post("/submit", response_model=schemas.LeadMagnetResponse, status_code=status.HTTP_201_CREATED)
async def submit_lead_magnet_questionnaire(submission_data: schemas.LeadMagnetSubmission):
    """
    Accepts simplified questionnaire data from a public lead magnet form,
    creates a prospect person, a basic campaign, and a basic media kit.
    """
    print("--- [PUBLIC LEAD MAGNET] --- Entering submit_lead_magnet_questionnaire ---") # DEBUG PRINT
    logger.info(f"Received lead magnet submission from email: {submission_data.email}")
    print(f"--- [PUBLIC LEAD MAGNET] --- Submission data email: {submission_data.email}") # DEBUG PRINT

    # Check for Existing Person by Email
    print("--- [PUBLIC LEAD MAGNET] --- Checking for existing person by email ---") # DEBUG PRINT
    existing_person = await people_queries.get_person_by_email_from_db(submission_data.email)
    if existing_person:
        # For now, we prevent submission if email exists to keep it simple.
        # Future: Could allow them to proceed and link to existing non-client, or merge later.
        logger.info(f"Lead magnet submission for existing email: {submission_data.email}. Informing user.")
        print(f"--- [PUBLIC LEAD MAGNET] --- Existing person found for email: {submission_data.email}. Returning early.") # DEBUG PRINT
        # Returning a 200 with a specific message, or a 409 Conflict.
        # For lead magnet, a clear message with 200 might be better UX than a raw 409.
        return schemas.LeadMagnetResponse(
            message="An account with this email already exists. Please log in or use a different email for the media kit preview."
        )
        # raise HTTPException(
        #     status_code=status.HTTP_409_CONFLICT,
        #     detail="Account with this email already exists. Please log in or use a different email."
        # )

    # Create "Prospect" Person Record
    prospect_person_data = {
        "full_name": submission_data.full_name,
        "email": submission_data.email,
        "dashboard_username": submission_data.email, # Using email as username
        "role": "prospect",
        "dashboard_password_hash": None # No password yet
    }
    print(f"--- [PUBLIC LEAD MAGNET] --- Creating prospect person with data: {prospect_person_data}") # DEBUG PRINT
    new_person = await people_queries.create_person_in_db(prospect_person_data)
    if not new_person or not new_person.get("person_id"):
        logger.error(f"Failed to create prospect person record for email: {submission_data.email}")
        print(f"--- [PUBLIC LEAD MAGNET] --- ERROR: Failed to create prospect person for email: {submission_data.email}") # DEBUG PRINT
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing your request (P). Please try again later.")
    new_person_id = new_person["person_id"]
    logger.info(f"Created prospect person record: {new_person_id} for email: {submission_data.email}")
    print(f"--- [PUBLIC LEAD MAGNET] --- Successfully created prospect person ID: {new_person_id}") # DEBUG PRINT

    # Create a Default "Prospect" Campaign
    campaign_name = f"{submission_data.full_name}'s Media Kit Preview"
    mock_interview_text = ""
    if submission_data.questionnaire_data:
        print(f"--- [PUBLIC LEAD MAGNET] --- Constructing mock interview from questionnaire data: {submission_data.questionnaire_data}") # DEBUG PRINT
        mock_interview_text = construct_mock_interview_from_questionnaire(submission_data.questionnaire_data)
    
    prospect_campaign_data = {
        "campaign_id": uuid.uuid4(), # Generate a new UUID for the campaign
        "person_id": new_person_id,
        "campaign_name": campaign_name,
        "campaign_type": "lead_magnet_prospect",
        "questionnaire_responses": submission_data.questionnaire_data, # Pass the dict directly
        "mock_interview_transcript": mock_interview_text 
    }
    print(f"--- [PUBLIC LEAD MAGNET] --- Creating prospect campaign with data: {prospect_campaign_data}") # DEBUG PRINT
    prospect_campaign = await campaign_queries.create_campaign_in_db(prospect_campaign_data)
    if not prospect_campaign or not prospect_campaign.get("campaign_id"):
        logger.error(f"Failed to create prospect campaign for person_id: {new_person_id}")
        print(f"--- [PUBLIC LEAD MAGNET] --- ERROR: Failed to create prospect campaign for person ID: {new_person_id}") # DEBUG PRINT
        # Consider cleanup for the created person record if campaign creation fails.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing your request (C). Please try again later.")
    prospect_campaign_id = prospect_campaign["campaign_id"]
    logger.info(f"Created prospect campaign: {prospect_campaign_id} for person_id: {new_person_id}")
    print(f"--- [PUBLIC LEAD MAGNET] --- Successfully created prospect campaign ID: {prospect_campaign_id}") # DEBUG PRINT

    # Trigger Basic Media Kit Generation
    print("--- [PUBLIC LEAD MAGNET] --- Initializing MediaKitService ---") # DEBUG PRINT
    media_kit_service = MediaKitService()
    try:
        # For lead magnets, we might want to pass specific editable_content or ensure defaults are suitable.
        # is_public should be True by default for these.
        media_kit_editable_content = {
            "title": f"{submission_data.full_name} - Media Kit Preview",
            "is_public": True,
            # Skip social stats explicitly for lead magnet for now by not calling update_social_stats separately
            # The service needs to be aware of this context for `update_social_stats_for_media_kit` part.
        }
        print(f"--- [PUBLIC LEAD MAGNET] --- Calling create_or_update_media_kit for campaign ID: {prospect_campaign_id} with content: {media_kit_editable_content}") # DEBUG PRINT
        created_media_kit = await media_kit_service.create_or_update_media_kit(
            campaign_id=prospect_campaign_id, 
            editable_content=media_kit_editable_content,
            # Add a flag to skip social stats for lead magnets if MediaKitService is updated
            # skip_social_stats_fetch=True 
        )
        print(f"--- [PUBLIC LEAD MAGNET] --- Media kit creation/update result: {created_media_kit}") # DEBUG PRINT
        if not created_media_kit or not created_media_kit.get("slug"):
            logger.error(f"Failed to create/generate slug for media kit for campaign: {prospect_campaign_id}")
            print(f"--- [PUBLIC LEAD MAGNET] --- ERROR: Failed to create media kit or get slug for campaign ID: {prospect_campaign_id}") # DEBUG PRINT
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error generating your media kit preview (MK). Please try again later.")
        
        media_kit_slug = created_media_kit["slug"]
        logger.info(f"Successfully created media kit with slug '{media_kit_slug}' for campaign {prospect_campaign_id}")
        print(f"--- [PUBLIC LEAD MAGNET] --- Successfully created media kit with slug: {media_kit_slug}. Returning response.") # DEBUG PRINT
        
        return schemas.LeadMagnetResponse(
            message="Your media kit preview has been generated successfully!",
            person_id=new_person_id,
            campaign_id=prospect_campaign_id,
            media_kit_slug=media_kit_slug
        )

    except Exception as e_mk:
        logger.exception(f"Error during media kit generation for lead magnet (campaign: {prospect_campaign_id}): {e_mk}")
        print(f"--- [PUBLIC LEAD MAGNET] --- EXCEPTION during media kit generation: {e_mk}") # DEBUG PRINT
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error generating your media kit preview. Please try again later.") 