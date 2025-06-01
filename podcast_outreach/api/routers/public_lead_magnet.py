# podcast_outreach/api/routers/public_lead_magnet.py
import logging
import uuid
from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any

from podcast_outreach.api.schemas import lead_magnet_schemas as schemas
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.services.media_kits.generator import MediaKitService
# Assuming this helper function exists or can be created, e.g., in questionnaire_processor or a utils file
from podcast_outreach.services.campaigns.questionnaire_processor import _construct_mock_interview_from_questionnaire 

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
    logger.info(f"Received lead magnet submission from email: {submission_data.email}")

    # Check for Existing Person by Email
    existing_person = await people_queries.get_person_by_email_from_db(submission_data.email)
    if existing_person:
        # For now, we prevent submission if email exists to keep it simple.
        # Future: Could allow them to proceed and link to existing non-client, or merge later.
        logger.info(f"Lead magnet submission for existing email: {submission_data.email}. Informing user.")
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
    new_person = await people_queries.create_person_in_db(prospect_person_data)
    if not new_person or not new_person.get("person_id"):
        logger.error(f"Failed to create prospect person record for email: {submission_data.email}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing your request (P). Please try again later.")
    new_person_id = new_person["person_id"]
    logger.info(f"Created prospect person record: {new_person_id} for email: {submission_data.email}")

    # Create a Default "Prospect" Campaign
    campaign_name = f"{submission_data.full_name}'s Media Kit Preview"
    mock_interview_text = ""
    if submission_data.questionnaire_data:
        mock_interview_text = _construct_mock_interview_from_questionnaire(submission_data.questionnaire_data)
    
    prospect_campaign_data = {
        "campaign_id": uuid.uuid4(), # Generate a new UUID for the campaign
        "person_id": new_person_id,
        "campaign_name": campaign_name,
        "campaign_type": "lead_magnet_prospect",
        "questionnaire_responses": submission_data.questionnaire_data,
        "mock_interview_trancript": mock_interview_text # Corrected typo from schema 'trancript'
    }
    prospect_campaign = await campaign_queries.create_campaign_in_db(prospect_campaign_data)
    if not prospect_campaign or not prospect_campaign.get("campaign_id"):
        logger.error(f"Failed to create prospect campaign for person_id: {new_person_id}")
        # Consider cleanup for the created person record if campaign creation fails.
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing your request (C). Please try again later.")
    prospect_campaign_id = prospect_campaign["campaign_id"]
    logger.info(f"Created prospect campaign: {prospect_campaign_id} for person_id: {new_person_id}")

    # Trigger Basic Media Kit Generation
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
        created_media_kit = await media_kit_service.create_or_update_media_kit(
            campaign_id=prospect_campaign_id, 
            editable_content=media_kit_editable_content,
            # Add a flag to skip social stats for lead magnets if MediaKitService is updated
            # skip_social_stats_fetch=True 
        )
        if not created_media_kit or not created_media_kit.get("slug"):
            logger.error(f"Failed to create/generate slug for media kit for campaign: {prospect_campaign_id}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error generating your media kit preview (MK). Please try again later.")
        
        media_kit_slug = created_media_kit["slug"]
        logger.info(f"Successfully created media kit with slug '{media_kit_slug}' for campaign {prospect_campaign_id}")
        
        return schemas.LeadMagnetResponse(
            message="Your media kit preview has been generated successfully!",
            person_id=new_person_id,
            campaign_id=prospect_campaign_id,
            media_kit_slug=media_kit_slug
        )

    except Exception as e_mk:
        logger.exception(f"Error during media kit generation for lead magnet (campaign: {prospect_campaign_id}): {e_mk}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error generating your media kit preview. Please try again later.") 