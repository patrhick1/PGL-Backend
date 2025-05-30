# podcast_outreach/api/routers/client.py
import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone # ENSURED THIS IS PRESENT
import asyncio # For concurrent API calls

from fastapi import APIRouter, Depends, HTTPException, status

from podcast_outreach.api.dependencies import get_current_user
from podcast_outreach.api.schemas import client_profile_schemas as schemas # Ensure this import is correct
from podcast_outreach.database.queries import client_profiles as client_profile_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import match_suggestions as match_suggestion_queries
from podcast_outreach.database.queries import review_tasks as review_task_queries

# Import actual API clients and MediaFetcher for discovery logic
from podcast_outreach.integrations.listen_notes import ListenNotesAPIClient
from podcast_outreach.integrations.podscan import PodscanAPIClient
from podcast_outreach.services.media.podcast_fetcher import MediaFetcher # MediaFetcher handles enrichment and upsert

from podcast_outreach.config import (
    FREE_PLAN_DAILY_DISCOVERY_LIMIT, FREE_PLAN_WEEKLY_DISCOVERY_LIMIT,
    PAID_PLAN_DAILY_DISCOVERY_LIMIT, PAID_PLAN_WEEKLY_DISCOVERY_LIMIT,
    LISTENNOTES_PAGE_SIZE, # Assuming these are defined in config or use defaults
    PODSCAN_PAGE_SIZE,
    API_CALL_DELAY
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/client", tags=["Client Portal"])

# --- Helper to get plan limits (already provided, ensure it's here) ---
def _get_plan_limits(plan_type: str) -> tuple[int, int]:
    if plan_type == 'free':
        return FREE_PLAN_DAILY_DISCOVERY_LIMIT, FREE_PLAN_WEEKLY_DISCOVERY_LIMIT
    elif plan_type == 'paid_basic': # Example, add more plans as needed
        return PAID_PLAN_DAILY_DISCOVERY_LIMIT, PAID_PLAN_WEEKLY_DISCOVERY_LIMIT
    else:
        logger.warning(f"Unknown plan_type '{plan_type}', defaulting to free plan limits.")
        return FREE_PLAN_DAILY_DISCOVERY_LIMIT, FREE_PLAN_WEEKLY_DISCOVERY_LIMIT

# --- GET /client/discovery-status (already provided, ensure it's here) ---
@router.get("/discovery-status", response_model=schemas.ClientDiscoveryStatusSchema)
async def get_client_discovery_status(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "client" or not current_user.get("person_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized or client ID missing.")
    
    person_id = current_user["person_id"]
    profile = await client_profile_queries.reset_discovery_counts_if_needed(person_id) # Resets counts if day/week changed
    if not profile:
        default_daily, default_weekly = _get_plan_limits('free')
        profile_data_to_create = {
            "plan_type": "free",
            "daily_discovery_allowance": default_daily,
            "weekly_discovery_allowance": default_weekly,
        }
        profile = await client_profile_queries.create_client_profile(person_id, profile_data_to_create)
        if not profile:
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not retrieve or create client profile.")

    daily_allowance = profile.get('daily_discovery_allowance', FREE_PLAN_DAILY_DISCOVERY_LIMIT)
    weekly_allowance = profile.get('weekly_discovery_allowance', FREE_PLAN_WEEKLY_DISCOVERY_LIMIT)
    daily_used = profile.get('current_daily_discoveries', 0)
    weekly_used = profile.get('current_weekly_discoveries', 0)

    return schemas.ClientDiscoveryStatusSchema(
        person_id=person_id,
        plan_type=profile.get('plan_type', 'free'),
        daily_discoveries_used=daily_used,
        daily_discovery_allowance=daily_allowance,
        weekly_discoveries_used=weekly_used,
        weekly_discovery_allowance=weekly_allowance,
        can_discover_today=(daily_used < daily_allowance),
        can_discover_this_week=(weekly_used < weekly_allowance)
    )

# --- POST /client/campaigns/{campaign_id}/discover-preview (Refined) ---
@router.post("/client/campaigns/{campaign_id}/discover-preview", response_model=List[schemas.PodcastPreviewSchema])
async def client_discover_podcast_previews(campaign_id: uuid.UUID, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "client" or not current_user.get("person_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    
    person_id = current_user["person_id"]
    
    campaign = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign or campaign.get("person_id") != person_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found or access denied.")

    profile = await client_profile_queries.reset_discovery_counts_if_needed(person_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Client profile error.")

    daily_allowance = profile.get('daily_discovery_allowance', FREE_PLAN_DAILY_DISCOVERY_LIMIT)
    weekly_allowance = profile.get('weekly_discovery_allowance', FREE_PLAN_WEEKLY_DISCOVERY_LIMIT)

    if profile.get('current_daily_discoveries', 0) >= daily_allowance:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Daily discovery limit of {daily_allowance} reached.")
    if profile.get('current_weekly_discoveries', 0) >= weekly_allowance:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"Weekly discovery limit of {weekly_allowance} reached.")

    keywords = campaign.get('campaign_keywords', [])
    if not keywords:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign has no keywords for discovery.")

    # Initialize MediaFetcher (it contains the API clients)
    # MediaFetcher's methods are async, so we can await them.
    media_fetcher = MediaFetcher()
    discovered_media_records: List[Dict[str, Any]] = []
    processed_ids_for_this_run: set = set() # To avoid processing same podcast from multiple keywords in one client call

    # Limit the number of keywords to process for a client preview to manage API costs/time
    keywords_to_process = keywords[:2] # Example: Use first 2 keywords for client preview
    max_results_per_keyword_per_source = 3 # Fetch fewer results for client preview

    try:
        for kw in keywords_to_process:
            kw = kw.strip()
            if not kw: continue

            logger.info(f"Client Discovery: Processing keyword '{kw}' for campaign {campaign_id}")

            # ListenNotes Search (Simplified from MediaFetcher's internal logic)
            try:
                # Genre IDs are optional for client preview, or use a simpler method
                # For simplicity, we might skip genre_id generation for client previews or use a fixed set
                ln_response = await media_fetcher._run_in_executor(
                    media_fetcher.listennotes_client.search_podcasts,
                    kw,
                    page_size=max_results_per_keyword_per_source 
                )
                ln_results = ln_response.get('results', []) if isinstance(ln_response, dict) else []
                for item in ln_results:
                    unique_id = item.get('rss') or item.get('id')
                    if unique_id and unique_id not in processed_ids_for_this_run:
                        enriched = await media_fetcher._enrich_podcast_data(item, "ListenNotes")
                        # Upsert to media table (this is where it gets stored)
                        media_db_id = await media_fetcher.merge_and_upsert_media(enriched, "ListenNotes", campaign_id, kw)
                        if media_db_id:
                            media_record = await media_queries.get_media_by_id_from_db(media_db_id)
                            if media_record: discovered_media_records.append(media_record)
                        processed_ids_for_this_run.add(unique_id)
                await asyncio.sleep(API_CALL_DELAY)
            except Exception as e_ln:
                logger.error(f"Client Discovery: ListenNotes error for '{kw}': {e_ln}")

            # Podscan Search (Simplified)
            try:
                ps_response = await media_fetcher._run_in_executor(
                    media_fetcher.podscan_client.search_podcasts,
                    kw,
                    per_page=max_results_per_keyword_per_source
                )
                ps_results = ps_response.get('podcasts', []) if isinstance(ps_response, dict) else []
                for item in ps_results:
                    unique_id = item.get('rss_url') or item.get('podcast_id')
                    if unique_id and unique_id not in processed_ids_for_this_run:
                        enriched = await media_fetcher._enrich_podcast_data(item, "PodscanFM")
                        media_db_id = await media_fetcher.merge_and_upsert_media(enriched, "PodscanFM", campaign_id, kw)
                        if media_db_id:
                            media_record = await media_queries.get_media_by_id_from_db(media_db_id)
                            if media_record: discovered_media_records.append(media_record)
                        processed_ids_for_this_run.add(unique_id)
                await asyncio.sleep(API_CALL_DELAY)
            except Exception as e_ps:
                logger.error(f"Client Discovery: Podscan error for '{kw}': {e_ps}")
        
        # Deduplicate based on media_id (in case a podcast was found by multiple keywords/sources)
        final_unique_media_records: Dict[int, Dict[str, Any]] = {}
        for record in discovered_media_records:
            if record['media_id'] not in final_unique_media_records:
                final_unique_media_records[record['media_id']] = record
        
        preview_results = [
            schemas.PodcastPreviewSchema(
                media_id=m['media_id'],
                name=m.get('name'),
                image_url=m.get('image_url'),
                short_description=(m.get('description') or "")[:150] + "..." if m.get('description') else None,
                website=m.get('website')
            ) for m in final_unique_media_records.values()
        ]
        # Limit the number of previews returned to the client, e.g., 10-15
        preview_results = preview_results[:15]

        # Increment discovery count (Option 1: count when preview is generated)
        if preview_results: # Only count if we actually found something to show
            await client_profile_queries.increment_discovery_counts(person_id, discoveries_made=1)
        
        return preview_results

    finally:
        media_fetcher.cleanup() # Important if ThreadPoolExecutor is used in MediaFetcher

# --- POST /client/request-match-review (already provided, ensure it's here) ---
@router.post("/request-match-review", status_code=status.HTTP_201_CREATED)
async def client_request_match_review(
    payload: schemas.ClientRequestMatchReviewSchema,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "client" or not current_user.get("person_id"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized.")
    
    person_id = current_user["person_id"]
    campaign_id = payload.campaign_id

    campaign = await campaign_queries.get_campaign_by_id(campaign_id)
    if not campaign or campaign.get("person_id") != person_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found or access denied.")

    # If using Option 2 for discovery count (incrementing here):
    # profile = await client_profile_queries.reset_discovery_counts_if_needed(person_id)
    # if not profile: raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Client profile error.")
    # daily_allowance = profile.get('daily_discovery_allowance', FREE_PLAN_DAILY_DISCOVERY_LIMIT)
    # weekly_allowance = profile.get('weekly_discovery_allowance', FREE_PLAN_WEEKLY_DISCOVERY_LIMIT)
    #
    # if profile.get('current_daily_discoveries', 0) + len(payload.media_ids) > daily_allowance:
    #     raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Requesting these reviews would exceed your daily discovery limit.")
    # if profile.get('current_weekly_discoveries', 0) + len(payload.media_ids) > weekly_allowance:
    #     raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Requesting these reviews would exceed your weekly discovery limit.")
    #
    # await client_profile_queries.increment_discovery_counts(person_id, discoveries_made=len(payload.media_ids))

    created_matches_count = 0
    for media_id_to_match in payload.media_ids:
        media_exists = await media_queries.get_media_by_id_from_db(media_id_to_match)
        if not media_exists:
            logger.warning(f"Client {person_id} requested review for non-existent media_id {media_id_to_match}. Skipping.")
            continue

        existing_match = await match_suggestion_queries.get_match_suggestion_by_campaign_and_media_ids(campaign_id, media_id_to_match)
        if existing_match:
            logger.info(f"Match suggestion already exists for campaign {campaign_id} and media {media_id_to_match}. Status: {existing_match.get('status')}")
            # Optionally, if it was 'rejected_by_client', maybe allow re-requesting by changing status.
            # For now, just skip if any match exists.
            continue

        match_suggestion_data = {
            "campaign_id": campaign_id,
            "media_id": media_id_to_match,
            "status": "pending_internal_review", # This status indicates it came from client and needs team vetting
            "client_approved": True, # Client initiated this
            "approved_at": datetime.now(timezone.utc),
            "ai_reasoning": f"Client (Person ID: {person_id}) requested review for this podcast."
        }
        created_match = await match_suggestion_queries.create_match_suggestion_in_db(match_suggestion_data)
        
        if created_match and created_match.get('match_id'):
            review_task_data = {
                "task_type": "match_suggestion_internal_vetting", # Specific task for team
                "related_id": created_match['match_id'],
                "campaign_id": campaign_id,
                "status": "pending",
                "notes": f"Client (Person ID: {person_id}) requested review for media: {media_exists.get('name', media_id_to_match)}."
            }
            await review_task_queries.create_review_task_in_db(review_task_data)
            created_matches_count += 1
        else:
            logger.error(f"Failed to create match suggestion for media {media_id_to_match} requested by client {person_id}.")
            
    if created_matches_count == 0 and len(payload.media_ids) > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No new match suggestions were created. They may already exist or media IDs were invalid.")

    return {"message": f"Successfully requested internal review for {created_matches_count} podcast(s)."}