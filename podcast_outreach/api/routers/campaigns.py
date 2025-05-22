# podcast_outreach/api/routers/campaigns.py

import uuid
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from datetime import datetime, date
import logging

# Import schemas
from api.schemas.campaign_schemas import CampaignCreate, CampaignUpdate, CampaignInDB, AnglesBioTriggerResponse

# Import db_service_pg (assuming it's now at database/queries/db_service_pg.py)
# Adjust this import based on its final location in your new structure
import db_service_pg # Original path, adjust if moved to database/queries/

# Import AnglesProcessorPG (assuming it's now at services/campaigns/bio_generator.py)
# Adjust this import based on its final location in your new structure
# from services.campaigns.bio_generator import AnglesProcessorPG # This is the target import
from angles_processor_pg import AnglesProcessorPG # Current path, needs to be moved as per plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

@router.post("/", response_model=CampaignInDB, status_code=201, summary="Create New Campaign")
async def create_campaign_api(campaign: CampaignCreate):
    campaign_dict = campaign.model_dump() # Use model_dump() for Pydantic v2
    try:
        created_db_campaign = await db_service_pg.create_campaign_in_db(campaign_dict)
        if not created_db_campaign:
            raise HTTPException(status_code=500, detail="Failed to create campaign in database.")
        return CampaignInDB(**created_db_campaign)
    except Exception as e:
        logger.exception(f"Error in create_campaign_api for campaign name {campaign.campaign_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[CampaignInDB], summary="List All Campaigns")
async def list_campaigns_api(skip: int = 0, limit: int = 100):
    try:
        campaigns_from_db = await db_service_pg.get_all_campaigns_from_db(skip=skip, limit=limit)
        return [CampaignInDB(**c) for c in campaigns_from_db]
    except Exception as e:
        logger.exception(f"Error in list_campaigns_api: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{campaign_id}", response_model=CampaignInDB, summary="Get Specific Campaign")
async def get_campaign_api(campaign_id: uuid.UUID):
    try:
        campaign_from_db = await db_service_pg.get_campaign_by_id(campaign_id)
        if not campaign_from_db:
            raise HTTPException(status_code=404, detail=f"Campaign with ID {campaign_id} not found.")
        return CampaignInDB(**campaign_from_db)
    except Exception as e:
        logger.exception(f"Error in get_campaign_api for ID {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{campaign_id}", response_model=CampaignInDB, summary="Update Campaign")
async def update_campaign_api(campaign_id: uuid.UUID, campaign_update: CampaignUpdate):
    update_data = campaign_update.model_dump(exclude_unset=True) # Use model_dump() for Pydantic v2
    if not update_data:
        raise HTTPException(status_code=400, detail="No update data provided.")
    try:
        updated_db_campaign = await db_service_pg.update_campaign(campaign_id, update_data)
        if not updated_db_campaign:
            raise HTTPException(status_code=404, detail=f"Campaign with ID {campaign_id} not found or update failed.")
        return CampaignInDB(**updated_db_campaign)
    except Exception as e:
        logger.exception(f"Error in update_campaign_api for ID {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{campaign_id}", status_code=204, summary="Delete Campaign")
async def delete_campaign_api(campaign_id: uuid.UUID):
    try:
        success = await db_service_pg.delete_campaign_from_db(campaign_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Campaign with ID {campaign_id} not found or delete failed.")
        return # Returns 204 No Content on success
    except Exception as e:
        logger.exception(f"Error in delete_campaign_api for ID {campaign_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{campaign_id}/generate-angles-bio", response_model=AnglesBioTriggerResponse, summary="Trigger Bio & Angles Generation")
async def trigger_angles_bio_generation_api(campaign_id: uuid.UUID):
    campaign_exists = await db_service_pg.get_campaign_by_id(campaign_id)
    if not campaign_exists:
         raise HTTPException(status_code=404, detail=f"Campaign {campaign_id} not found, cannot trigger generation.")

    # AnglesProcessorPG is currently at the root level.
    # In the new structure, it should be moved to services/campaigns/bio_generator.py
    # and imported as: from services.campaigns.bio_generator import AnglesProcessorPG
    # For now, keeping the original import path from the provided file.
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
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during generation: {str(e)}")
    finally:
        processor.cleanup()