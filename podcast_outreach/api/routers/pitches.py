# podcast_outreach/api/routers/pitches.py

import uuid
from fastapi import APIRouter, HTTPException, Depends, status, Query
from typing import List, Optional, Dict, Any
from datetime import datetime

# Import schemas
from ..schemas.pitch_schemas import PitchGenerationRequest, PitchGenerationResponse, PitchInDB, PitchGenerationInDB, PitchGenerationContentUpdate

# Import services
from podcast_outreach.services.pitches.generator import PitchGeneratorService
from podcast_outreach.services.pitches.sender import PitchSenderService
from podcast_outreach.services.pitches.sender_v2 import PitchSenderServiceV2

# Import modular queries
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import pitch_generations as pitch_gen_queries
from podcast_outreach.database.queries import campaigns as campaign_queries # For validation
from podcast_outreach.database.queries import media as media_queries # For validation
from podcast_outreach.database.queries import people as people_queries # For enrichment

# Import dependencies for authentication
from ..dependencies import get_current_user, get_admin_user

import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pitches", tags=["Pitches"])

@router.get("/metrics", summary="Get Pitch Metrics for Current User")
async def get_pitch_metrics(
    campaign_id: Optional[uuid.UUID] = Query(None, description="Filter by specific campaign"),
    days: int = Query(30, ge=1, le=365, description="Number of days to look back"),
    user: dict = Depends(get_current_user)
):
    """
    Get pitch performance metrics for the current user.
    Returns statistics on pitch states, open rates, reply rates, etc.
    Can be filtered by campaign and time period.
    """
    from datetime import timedelta
    from podcast_outreach.database.connection import get_db_pool
    
    try:
        person_id = user.get("person_id")
        if not person_id:
            raise HTTPException(status_code=400, detail="User not properly authenticated")
        
        pool = await get_db_pool()
        
        # Build the base query with user filtering
        base_conditions = ["c.person_id = $1"]
        params = [person_id]
        
        # Add campaign filter if provided
        if campaign_id:
            base_conditions.append(f"p.campaign_id = ${len(params) + 1}")
            params.append(campaign_id)
        
        # Add date filter
        if days:
            base_conditions.append(f"p.created_at >= NOW() - INTERVAL '{days} days'")
        
        where_clause = " AND ".join(base_conditions)
        
        async with pool.acquire() as conn:
            # Get overall pitch metrics
            metrics_query = f"""
            SELECT 
                COUNT(*) as total_pitches,
                COUNT(CASE WHEN p.pitch_state = 'generated' THEN 1 END) as generated,
                COUNT(CASE WHEN p.pitch_state = 'sent' THEN 1 END) as sent,
                COUNT(CASE WHEN p.pitch_state = 'opened' THEN 1 END) as opened,
                COUNT(CASE WHEN p.pitch_state = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN p.pitch_state IN ('replied', 'replied_interested') THEN 1 END) as replied,
                COUNT(CASE WHEN p.pitch_state = 'bounced' THEN 1 END) as bounced,
                COUNT(CASE WHEN p.pitch_state IN ('live', 'paid') THEN 1 END) as converted,
                COUNT(CASE WHEN p.open_count > 0 THEN 1 END) as total_opened,
                COUNT(CASE WHEN p.click_count > 0 THEN 1 END) as total_clicked,
                AVG(p.open_count) as avg_opens_per_pitch,
                AVG(p.click_count) as avg_clicks_per_pitch
            FROM pitches p
            JOIN campaigns c ON p.campaign_id = c.campaign_id
            WHERE {where_clause}
            """
            
            metrics = await conn.fetchrow(metrics_query, *params)
            
            # Get campaign breakdown if not filtering by specific campaign
            campaign_breakdown = []
            if not campaign_id:
                campaign_query = f"""
                SELECT 
                    c.campaign_id,
                    c.campaign_name,
                    COUNT(p.pitch_id) as total_pitches,
                    COUNT(CASE WHEN p.pitch_state = 'sent' THEN 1 END) as sent,
                    COUNT(CASE WHEN p.pitch_state = 'opened' THEN 1 END) as opened,
                    COUNT(CASE WHEN p.pitch_state IN ('replied', 'replied_interested') THEN 1 END) as replied
                FROM campaigns c
                LEFT JOIN pitches p ON c.campaign_id = p.campaign_id
                WHERE c.person_id = $1
                GROUP BY c.campaign_id, c.campaign_name
                ORDER BY COUNT(p.pitch_id) DESC
                LIMIT 10
                """
                
                campaign_rows = await conn.fetch(campaign_query, person_id)
                campaign_breakdown = [dict(row) for row in campaign_rows]
            
            # Get recent pitch activity
            recent_query = f"""
            SELECT 
                p.pitch_id,
                p.pitch_state,
                p.created_at,
                p.send_ts as sent_at,
                c.campaign_name,
                m.name as media_name
            FROM pitches p
            JOIN campaigns c ON p.campaign_id = c.campaign_id
            LEFT JOIN media m ON p.media_id = m.media_id
            WHERE {where_clause}
            ORDER BY p.created_at DESC
            LIMIT 10
            """
            
            recent_pitches = await conn.fetch(recent_query, *params)
            
        # Calculate rates
        total = metrics['total_pitches'] or 0
        sent = metrics['sent'] or 0
        opened = metrics['total_opened'] or 0
        clicked = metrics['total_clicked'] or 0
        replied = metrics['replied'] or 0
        converted = metrics['converted'] or 0
        
        return {
            "period_days": days,
            "campaign_id": str(campaign_id) if campaign_id else None,
            "totals": {
                "total_pitches": total,
                "generated": metrics['generated'] or 0,
                "sent": sent,
                "opened": metrics['opened'] or 0,
                "clicked": metrics['clicked'] or 0,
                "replied": replied,
                "bounced": metrics['bounced'] or 0,
                "converted": converted
            },
            "rates": {
                "send_rate": round((sent / total * 100) if total > 0 else 0, 2),
                "open_rate": round((opened / sent * 100) if sent > 0 else 0, 2),
                "click_rate": round((clicked / sent * 100) if sent > 0 else 0, 2),
                "reply_rate": round((replied / sent * 100) if sent > 0 else 0, 2),
                "conversion_rate": round((converted / sent * 100) if sent > 0 else 0, 2)
            },
            "engagement": {
                "avg_opens_per_pitch": round(float(metrics['avg_opens_per_pitch'] or 0), 2),
                "avg_clicks_per_pitch": round(float(metrics['avg_clicks_per_pitch'] or 0), 2),
                "total_opens": metrics['total_opened'] or 0,
                "total_clicks": metrics['total_clicked'] or 0
            },
            "campaign_breakdown": campaign_breakdown,
            "recent_activity": [
                {
                    "pitch_id": p['pitch_id'],
                    "state": p['pitch_state'],
                    "created_at": p['created_at'].isoformat() if p['created_at'] else None,
                    "sent_at": p['sent_at'].isoformat() if p['sent_at'] else None,
                    "campaign_name": p['campaign_name'],
                    "media_name": p['media_name']
                }
                for p in recent_pitches
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching pitch metrics: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch pitch metrics: {str(e)}"
        )

@router.post("/generate-batch", status_code=status.HTTP_202_ACCEPTED, summary="Generate Pitches for Multiple Matches")
async def generate_pitches_batch_api(
    requests: List[PitchGenerationRequest],
    user: dict = Depends(get_current_user)
):
    """
    Generate pitches for multiple approved matches with different templates.
    Each request can specify a different template for each match.
    
    Example request body:
    [
        {"match_id": 1, "pitch_template_id": "template_1"},
        {"match_id": 2, "pitch_template_id": "template_2"},
        {"match_id": 3, "pitch_template_id": "template_1"}
    ]
    """
    if user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to generate pitches.")
    
    generator_service = PitchGeneratorService()
    results = {"successful": [], "failed": []}
    
    for request in requests:
        try:
            result = await generator_service.generate_pitch_for_match(
                match_id=request.match_id,
                pitch_template_id=request.pitch_template_id
            )
            
            if result.get("status") == "success":
                results["successful"].append({
                    "match_id": request.match_id,
                    "pitch_gen_id": result.get("pitch_gen_id"),
                    "message": result.get("message")
                })
            else:
                results["failed"].append({
                    "match_id": request.match_id,
                    "error": result.get("message")
                })
                
        except Exception as e:
            logger.exception(f"Error generating pitch for match {request.match_id}: {e}")
            results["failed"].append({
                "match_id": request.match_id,
                "error": str(e)
            })
    
    return {
        "status": "completed",
        "message": f"Batch generation completed. Success: {len(results['successful'])}, Failed: {len(results['failed'])}",
        "results": results
    }

@router.post("/generate", response_model=PitchGenerationResponse, status_code=status.HTTP_202_ACCEPTED, summary="Generate Pitch for Approved Match")
async def generate_pitch_for_match_api(
    request_data: PitchGenerationRequest,
    user: dict = Depends(get_current_user)
):
    """
    Triggers the AI-powered generation of a pitch email for an approved match suggestion.
    Staff or Admin access required.
    """
    generator_service = PitchGeneratorService()
    try:
        result = await generator_service.generate_pitch_for_match(
            match_id=request_data.match_id,
            pitch_template_id=request_data.pitch_template_id
        )
        
        if result.get("status") == "failed":
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.get("message"))
        
        return PitchGenerationResponse(**result)
    except HTTPException:
        raise # Re-raise FastAPI HTTPExceptions
    except Exception as e:
        logger.exception(f"Error generating pitch for match {request_data.match_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred during pitch generation: {str(e)}")

@router.patch("/generations/{pitch_gen_id}/approve", response_model=PitchGenerationInDB, summary="Approve a Generated Pitch")
async def approve_pitch_generation_api(
    pitch_gen_id: int,
    user: dict = Depends(get_current_user)
):
    """
    Approves a generated pitch, marking it as ready to send.
    Staff or Admin access required.
    """
    try:
        approved_pitch_gen = await pitch_gen_queries.approve_pitch_generation(
            pitch_gen_id=pitch_gen_id,
            reviewer_id=user["username"]
        )
        if not approved_pitch_gen:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch generation with ID {pitch_gen_id} not found or could not be approved.")
        
        return PitchGenerationInDB(**approved_pitch_gen)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error approving pitch generation {pitch_gen_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred during pitch approval: {str(e)}")

@router.post("/{pitch_id}/send", status_code=status.HTTP_202_ACCEPTED, summary="Send Pitch via Instantly.ai")
async def send_pitch_api(
    pitch_id: int,
    user: dict = Depends(get_current_user)
):
    """
    Sends an approved pitch via Instantly.ai.
    Staff or Admin access required.
    """
    sender_service = PitchSenderService()
    try:
        pitch_record = await pitch_queries.get_pitch_by_id(pitch_id)
        if not pitch_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch record with ID {pitch_id} not found.")
        
        pitch_gen_id = pitch_record.get('pitch_gen_id')
        if not pitch_gen_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Pitch record {pitch_id} is not linked to a pitch generation.")

        pitch_gen_record = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
        if not pitch_gen_record or not pitch_gen_record.get('send_ready_bool'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Pitch generation {pitch_gen_id} is not marked as send-ready.")

        result = await sender_service.send_pitch_to_instantly(pitch_gen_id=pitch_gen_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.get("message"))
        
        return {"message": result.get("message"), "status": "accepted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error sending pitch {pitch_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred during pitch sending: {str(e)}")

@router.post("/send-nylas/{pitch_gen_id}", status_code=status.HTTP_202_ACCEPTED, summary="Send Pitch via Nylas")
async def send_pitch_via_nylas(
    pitch_gen_id: int,
    user: dict = Depends(get_current_user)
):
    """
    Sends an approved pitch via Nylas email service.
    Requires the campaign to have a configured Nylas grant ID.
    Staff or Admin access required.
    """
    if user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to send pitches.")
    
    sender_service_v2 = PitchSenderServiceV2()
    
    try:
        # Verify pitch generation exists and is ready to send
        pitch_gen_record = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
        if not pitch_gen_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch generation {pitch_gen_id} not found.")
        
        if not pitch_gen_record.get('send_ready_bool'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Pitch generation {pitch_gen_id} is not marked as send-ready.")
        
        # Get campaign and verify it has Nylas configured
        campaign_id = pitch_gen_record.get('campaign_id')
        campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
        
        if not campaign_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found.")
        
        if not campaign_data.get('nylas_grant_id'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Campaign {campaign_id} does not have a Nylas grant ID configured.")
        
        # Force the email provider to Nylas for this send
        campaign_data['email_provider'] = 'nylas'
        
        # Send the pitch using the V2 service (which will use Nylas)
        result = await sender_service_v2.send_pitch(pitch_gen_id=pitch_gen_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.get("message"))
        
        return {
            "message": result.get("message"),
            "status": "accepted",
            "provider": "nylas",
            "nylas_message_id": result.get("nylas_message_id")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error sending pitch {pitch_gen_id} via Nylas: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

@router.post("/send-instantly/{pitch_gen_id}", status_code=status.HTTP_202_ACCEPTED, summary="Send Pitch via Instantly")
async def send_pitch_via_instantly(
    pitch_gen_id: int,
    user: dict = Depends(get_current_user)
):
    """
    Sends an approved pitch via Instantly.ai email service.
    Requires the campaign to have a configured Instantly campaign ID.
    Staff or Admin access required.
    """
    if user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to send pitches.")
    
    sender_service_v2 = PitchSenderServiceV2()
    
    try:
        # Verify pitch generation exists and is ready to send
        pitch_gen_record = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
        if not pitch_gen_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch generation {pitch_gen_id} not found.")
        
        if not pitch_gen_record.get('send_ready_bool'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Pitch generation {pitch_gen_id} is not marked as send-ready.")
        
        # Get campaign and verify it has Instantly configured
        campaign_id = pitch_gen_record.get('campaign_id')
        campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
        
        if not campaign_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign {campaign_id} not found.")
        
        if not campaign_data.get('instantly_campaign_id'):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Campaign {campaign_id} does not have an Instantly campaign ID configured.")
        
        # Force the email provider to Instantly for this send
        campaign_data['email_provider'] = 'instantly'
        
        # Send the pitch using the V2 service (which will use Instantly)
        result = await sender_service_v2.send_pitch(pitch_gen_id=pitch_gen_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.get("message"))
        
        return {
            "message": result.get("message"),
            "status": "accepted",
            "provider": "instantly",
            "instantly_lead_id": result.get("instantly_lead_id")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error sending pitch {pitch_gen_id} via Instantly: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

@router.post("/send-batch-nylas", status_code=status.HTTP_202_ACCEPTED, summary="Send Multiple Pitches via Nylas")
async def send_pitches_batch_nylas(
    pitch_gen_ids: List[int],
    user: dict = Depends(get_current_user)
):
    """
    Sends multiple approved pitches via Nylas email service.
    Each pitch generation must be from a campaign with a configured Nylas grant ID.
    Staff or Admin access required.
    
    Example request body:
    [1, 2, 3, 4, 5]
    """
    if user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to send pitches.")
    
    sender_service_v2 = PitchSenderServiceV2()
    results = {"successful": [], "failed": []}
    
    for pitch_gen_id in pitch_gen_ids:
        try:
            # Verify pitch generation exists and is ready to send
            pitch_gen_record = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
            if not pitch_gen_record:
                results["failed"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "error": f"Pitch generation {pitch_gen_id} not found."
                })
                continue
            
            if not pitch_gen_record.get('send_ready_bool'):
                results["failed"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "error": f"Pitch generation {pitch_gen_id} is not marked as send-ready."
                })
                continue
            
            # Get campaign and verify it has Nylas configured
            campaign_id = pitch_gen_record.get('campaign_id')
            campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
            
            if not campaign_data:
                results["failed"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "error": f"Campaign {campaign_id} not found."
                })
                continue
            
            if not campaign_data.get('nylas_grant_id'):
                results["failed"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "error": f"Campaign {campaign_id} does not have a Nylas grant ID configured."
                })
                continue
            
            # Force the email provider to Nylas for this send
            campaign_data['email_provider'] = 'nylas'
            
            # Send the pitch using the V2 service
            result = await sender_service_v2.send_pitch(pitch_gen_id=pitch_gen_id)
            
            if result.get("success"):
                results["successful"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "message": result.get("message"),
                    "nylas_message_id": result.get("nylas_message_id")
                })
            else:
                results["failed"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "error": result.get("message")
                })
                
        except Exception as e:
            logger.exception(f"Error sending pitch {pitch_gen_id} via Nylas: {e}")
            results["failed"].append({
                "pitch_gen_id": pitch_gen_id,
                "error": str(e)
            })
    
    return {
        "status": "completed",
        "message": f"Batch send completed. Success: {len(results['successful'])}, Failed: {len(results['failed'])}",
        "provider": "nylas",
        "results": results
    }

@router.post("/send-batch-instantly", status_code=status.HTTP_202_ACCEPTED, summary="Send Multiple Pitches via Instantly")
async def send_pitches_batch_instantly(
    pitch_gen_ids: List[int],
    user: dict = Depends(get_current_user)
):
    """
    Sends multiple approved pitches via Instantly.ai email service.
    Each pitch generation must be from a campaign with a configured Instantly campaign ID.
    Staff or Admin access required.
    
    Example request body:
    [1, 2, 3, 4, 5]
    """
    if user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to send pitches.")
    
    sender_service_v2 = PitchSenderServiceV2()
    results = {"successful": [], "failed": []}
    
    for pitch_gen_id in pitch_gen_ids:
        try:
            # Verify pitch generation exists and is ready to send
            pitch_gen_record = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
            if not pitch_gen_record:
                results["failed"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "error": f"Pitch generation {pitch_gen_id} not found."
                })
                continue
            
            if not pitch_gen_record.get('send_ready_bool'):
                results["failed"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "error": f"Pitch generation {pitch_gen_id} is not marked as send-ready."
                })
                continue
            
            # Get campaign and verify it has Instantly configured
            campaign_id = pitch_gen_record.get('campaign_id')
            campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
            
            if not campaign_data:
                results["failed"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "error": f"Campaign {campaign_id} not found."
                })
                continue
            
            if not campaign_data.get('instantly_campaign_id'):
                results["failed"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "error": f"Campaign {campaign_id} does not have an Instantly campaign ID configured."
                })
                continue
            
            # Force the email provider to Instantly for this send
            campaign_data['email_provider'] = 'instantly'
            
            # Send the pitch using the V2 service
            result = await sender_service_v2.send_pitch(pitch_gen_id=pitch_gen_id)
            
            if result.get("success"):
                results["successful"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "message": result.get("message"),
                    "instantly_lead_id": result.get("instantly_lead_id")
                })
            else:
                results["failed"].append({
                    "pitch_gen_id": pitch_gen_id,
                    "error": result.get("message")
                })
                
        except Exception as e:
            logger.exception(f"Error sending pitch {pitch_gen_id} via Instantly: {e}")
            results["failed"].append({
                "pitch_gen_id": pitch_gen_id,
                "error": str(e)
            })
    
    return {
        "status": "completed",
        "message": f"Batch send completed. Success: {len(results['successful'])}, Failed: {len(results['failed'])}",
        "provider": "instantly",
        "results": results
    }

@router.get("/generations", response_model=List[PitchGenerationInDB], summary="List All Pitch Generations")
async def list_pitch_generations_api(skip: int = 0, limit: int = 100, user: dict = Depends(get_current_user)):
    """
    Lists all pitch generation records with pagination. Staff or Admin access required.
    """
    try:
        generations_from_db = await pitch_gen_queries.get_all_pitch_generations_from_db(skip=skip, limit=limit)
        return [PitchGenerationInDB(**pg) for pg in generations_from_db]
    except Exception as e:
        logger.exception(f"Error in list_pitch_generations_api: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/generations/{pitch_gen_id}", response_model=PitchGenerationInDB, summary="Get Specific Pitch Generation by ID")
async def get_pitch_generation_api(pitch_gen_id: int, user: dict = Depends(get_current_user)):
    logger.info(f"API: Attempting to fetch pitch generation with ID: {pitch_gen_id}")
    try:
        generation_from_db = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)

        if not generation_from_db:
            logger.warning(f"API: Pitch generation with ID {pitch_gen_id} not found in DB.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch generation with ID {pitch_gen_id} not found.")

        logger.debug(f"API: Raw data from DB for pitch_gen_id {pitch_gen_id}: {generation_from_db}") # Log raw data

        # Attempt Pydantic validation and catch potential errors
        try:
            validated_data = PitchGenerationInDB(**generation_from_db)
            logger.info(f"API: Successfully validated data for pitch_gen_id {pitch_gen_id}.")
            return validated_data
        except Exception as pydantic_exc: # Catch Pydantic validation errors specifically
            logger.error(f"API: Pydantic validation error for pitch_gen_id {pitch_gen_id}. Data: {generation_from_db}. Error: {pydantic_exc}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Data validation error for pitch generation: {pydantic_exc}")

    except HTTPException: # Re-raise known HTTPExceptions
        raise
    except Exception as e: # Catch other unexpected errors
        logger.exception(f"API: Unexpected error in get_pitch_generation_api for ID {pitch_gen_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")

@router.get("/", response_model=List[PitchInDB], summary="List All Pitches (Enriched)")
async def list_pitches_api(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    campaign_id: Optional[uuid.UUID] = Query(None),
    media_id: Optional[int] = Query(None),
    pitch_state__in: Optional[List[str]] = Query(None, alias="pitch_state__in", description="List of pitch states to filter by (e.g., ready_to_send,sent)"),
    client_approval_status: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    """
    Lists all pitch records with pagination and optional filters, now enriched.
    Supports filtering by multiple pitch_states using `pitch_state__in=state1&pitch_state__in=state2`.
    """
    # Basic role check for non-admins trying to list all pitches without campaign filter
    if user.get("role") not in ["admin", "staff"] and not campaign_id:
         # Clients should generally view pitches via their specific campaign or context
         # This endpoint without a campaign_id filter might expose too much.
         # Consider adding a person_id filter for clients, similar to other endpoints.
         pass # For now, allow but enrichment will be limited if no campaign context

    try:
        pitches_from_db = await pitch_queries.get_all_pitches_enriched(
            skip=skip, limit=limit,
            campaign_id=campaign_id,
            media_id=media_id,
            pitch_states=pitch_state__in, # Pass the list of states
            client_approval_status=client_approval_status,
            person_id=user.get("person_id") if user.get("role") == "client" else None # Auto-filter for client role
        )
        return [PitchInDB(**p) for p in pitches_from_db]
    except Exception as e:
        logger.exception(f"Error in list_pitches_api: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/{pitch_id}", response_model=PitchInDB, summary="Get Specific Pitch by ID (Enriched)")
async def get_pitch_api(pitch_id: int, user: dict = Depends(get_current_user)):
    """Retrieves a specific pitch record by ID, now enriched directly from the database."""
    try:
        enriched_pitch = await pitch_queries.get_pitch_by_id_enriched(pitch_id)

        if not enriched_pitch:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch with ID {pitch_id} not found.")
        
        # Authorization for clients (still needed)
        if user.get("role") == "client":
            # The enriched_pitch should contain campaign_id and its associated person_id (client_id)
            # We need to verify that this person_id matches the current_user's person_id
            campaign_id_of_pitch = enriched_pitch.get("campaign_id")
            if not campaign_id_of_pitch:
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Pitch is missing campaign information.")

            # The enrichment should have fetched c.person_id, so we can check that.
            # If client_name was populated, person_id for the campaign owner was found.
            # We need to make sure the DB query for enrichment correctly aliases or includes c.person_id if it's not part of p.* from pitches
            # Let's assume the JOINs in get_pitch_by_id_enriched give us c.person_id implicitly or explicitly
            # and we compare it to user.get("person_id")
            
            # To be robust, fetch campaign and check its person_id if not directly in enriched_pitch
            # This is a fallback, ideally enriched_pitch contains campaign's person_id
            campaign_owner_person_id = None
            campaign_details = await campaign_queries.get_campaign_by_id(campaign_id_of_pitch)
            if campaign_details:
                campaign_owner_person_id = campaign_details.get("person_id")

            if campaign_owner_person_id != user.get("person_id"):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this pitch.")

        return PitchInDB(**enriched_pitch)
    except HTTPException: # Re-raise FastAPI HTTPExceptions
        raise
    except Exception as e:
        logger.exception(f"Error in get_pitch_api for ID {pitch_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/bulk-send", status_code=status.HTTP_202_ACCEPTED, summary="Send Multiple Pitches via Instantly.ai")
async def send_pitches_bulk_api(
    pitch_ids: List[int],
    user: dict = Depends(get_current_user)
):
    """
    Sends multiple approved pitches via Instantly.ai.
    Staff or Admin access required.
    Returns a summary of successes and failures.
    """
    if user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to send pitches.")
    
    sender_service = PitchSenderService()
    results = {"successful": [], "failed": []}
    
    for pitch_id in pitch_ids:
        try:
            pitch_record = await pitch_queries.get_pitch_by_id(pitch_id)
            if not pitch_record:
                results["failed"].append({"pitch_id": pitch_id, "error": "Pitch not found"})
                continue
            
            pitch_gen_id = pitch_record.get('pitch_gen_id')
            if not pitch_gen_id:
                results["failed"].append({"pitch_id": pitch_id, "error": "No pitch generation linked"})
                continue
            
            pitch_gen_record = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
            if not pitch_gen_record or not pitch_gen_record.get('send_ready_bool'):
                results["failed"].append({"pitch_id": pitch_id, "error": "Pitch not ready to send"})
                continue
            
            result = await sender_service.send_pitch_to_instantly(pitch_gen_id=pitch_gen_id)
            
            if result.get("success"):
                results["successful"].append({"pitch_id": pitch_id, "message": result.get("message")})
            else:
                results["failed"].append({"pitch_id": pitch_id, "error": result.get("message")})
                
        except Exception as e:
            logger.exception(f"Error sending pitch {pitch_id} in bulk operation: {e}")
            results["failed"].append({"pitch_id": pitch_id, "error": str(e)})
    
    return {
        "message": f"Bulk send completed. Success: {len(results['successful'])}, Failed: {len(results['failed'])}",
        "results": results
    }

@router.patch("/generations/{pitch_gen_id}/content", response_model=PitchGenerationInDB, summary="Update Pitch Draft Content and Subject")
async def update_pitch_generation_content_api(
    pitch_gen_id: int,
    update_data: PitchGenerationContentUpdate, # New schema
    user: dict = Depends(get_current_user) # Staff or Admin access
):
    """
    Updates the draft_text of a pitch generation and/or the subject_line 
    of the associated pitch record.
    """
    if user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to edit pitch content.")

    updated_pitch_gen = None
    updated_pitch = None

    if update_data.draft_text is not None:
        updated_pitch_gen = await pitch_gen_queries.update_pitch_generation_in_db(
            pitch_gen_id,
            {"draft_text": update_data.draft_text}
        )
        if not updated_pitch_gen:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch generation {pitch_gen_id} not found or update failed.")

    if update_data.new_subject_line is not None:
        # Find the associated pitch record to update its subject line
        pitch_record = await pitch_queries.get_pitch_by_pitch_gen_id(pitch_gen_id)
        if not pitch_record or not pitch_record.get("pitch_id"):
            logger.warning(f"No associated pitch record found for pitch_gen_id {pitch_gen_id} to update subject line.")
            # Decide if this is an error or if pitch_gen can exist without a pitch record yet.
            # If pitch_gen always has a pitch, this is an error.
            # For now, we'll proceed if pitch_gen was updated, but log a warning.
        else:
            updated_pitch = await pitch_queries.update_pitch_in_db(
                pitch_record["pitch_id"],
                {"subject_line": update_data.new_subject_line}
            )
            if not updated_pitch:
                 logger.warning(f"Failed to update subject line for pitch_id {pitch_record['pitch_id']}.")
    
    # Return the updated pitch generation record as the primary object of this endpoint
    # If only subject was updated, fetch the pitch_gen again to return its current state
    if updated_pitch_gen:
        return PitchGenerationInDB(**updated_pitch_gen)
    elif update_data.new_subject_line and not update_data.draft_text:
        # Only subject was updated, fetch current pitch_gen to return
        current_pitch_gen = await pitch_gen_queries.get_pitch_generation_by_id(pitch_gen_id)
        if not current_pitch_gen:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pitch generation {pitch_gen_id} not found after attempting subject update.")
        return PitchGenerationInDB(**current_pitch_gen)
    else:
        # This case should ideally not be reached if at least one update was attempted and failed to find pitch_gen
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No update performed or pitch generation not found.")
