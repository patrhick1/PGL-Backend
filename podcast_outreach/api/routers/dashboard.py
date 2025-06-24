# podcast_outreach/api/routers/dashboard.py
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional

# Import schemas
from ..schemas.dashboard_schemas import DashboardStatsOverview, RecentPlacementItem, RecommendedPodcastItem

# Import modular queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import placements as placement_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import review_tasks as review_task_queries
from podcast_outreach.database.queries import people as people_queries # For client name

# Import dependencies for authentication
from ..dependencies import get_current_user # Clients and internal team can see their dashboard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/stats", response_model=DashboardStatsOverview, summary="Get Dashboard Statistics")
async def get_dashboard_stats(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Aggregates key statistics for the dashboard.
    Filters by user's person_id if the user is a 'client'.
    """
    person_id_filter = None
    if user.get("role") == "client":
        person_id_filter = user.get("person_id")
        if not person_id_filter:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client user not properly identified.")

    try:
        # Active Campaigns
        # Assuming an "active" campaign is one without an end_date or end_date is in the future
        # This logic might need to be more sophisticated in campaign_queries
        active_campaigns_count = await campaign_queries.count_active_campaigns(person_id=person_id_filter)

        # Approved Placements
        # Assuming 'live' or 'paid' status means approved and successful
        approved_placements_count = await placement_queries.count_placements_by_status(
            statuses=["live", "paid", "recorded", "recording_booked"], # Define what "approved" means
            person_id=person_id_filter
        )

        # Pending Reviews (e.g., match_suggestions or pitch_reviews)
        pending_review_tasks_count = await review_task_queries.count_review_tasks_by_status(
            status="pending",
            person_id=person_id_filter # This assumes review_tasks can be linked to a person via campaign
        )
        
        # Success Rate (Placements / Total Pitches Sent)
        # This is a simplified example. You might need more specific pitch states.
        total_pitches_sent = await pitch_queries.count_pitches_by_state(
            pitch_states=["sent", "opened", "replied", "clicked", "replied_interested", "live", "paid"], # All states after 'generated'
            person_id=person_id_filter
        )
        success_rate = (approved_placements_count / total_pitches_sent * 100) if total_pitches_sent > 0 else 0.0

        return DashboardStatsOverview(
            active_campaigns=active_campaigns_count,
            approved_placements=approved_placements_count,
            pending_reviews=pending_review_tasks_count,
            success_rate_placements=round(success_rate, 2)
        )
    except Exception as e:
        logger.exception(f"Error fetching dashboard stats for user {user.get('person_id')}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not fetch dashboard statistics.")


@router.get("/recent-placements", response_model=List[RecentPlacementItem], summary="Get Recent Placements")
async def get_recent_placements_api(limit: int = 3, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Fetches recent placement records, enriched with media and campaign names.
    Filters by user's person_id if the user is a 'client'.
    """
    person_id_filter = None
    if user.get("role") == "client":
        person_id_filter = user.get("person_id")
        if not person_id_filter:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client user not properly identified.")
    
    try:
        # The query function needs to handle person_id_filter
        recent_placements_db, _ = await placement_queries.get_placements_paginated(
            person_id_for_campaign_filter=person_id_filter, # New param for query
            page=1, 
            size=limit,
            sort_by="created_at", # or status_ts, or go_live_date
            sort_order="DESC"
        )
        
        enriched_placements = []
        for placement_dict in recent_placements_db:
            enriched_item = {
                "placement_id": placement_dict["placement_id"],
                "status": placement_dict.get("current_status"),
                "created_at": placement_dict["created_at"].isoformat(),
            }
            # Enrich with campaign and media details
            if placement_dict.get("campaign_id"):
                campaign = await campaign_queries.get_campaign_by_id(placement_dict["campaign_id"])
                if campaign:
                    enriched_item["campaign_name"] = campaign.get("campaign_name")
                    if campaign.get("person_id"):
                        person = await people_queries.get_person_by_id_from_db(campaign["person_id"])
                        if person:
                            enriched_item["client_name"] = person.get("full_name")
            
            if placement_dict.get("media_id"):
                media = await media_queries.get_media_by_id_from_db(placement_dict["media_id"])
                if media:
                    enriched_item["podcast_name"] = media.get("name")
                    enriched_item["podcast_category"] = media.get("category")
                    enriched_item["podcast_cover_image_url"] = media.get("image_url")
            
            enriched_placements.append(RecentPlacementItem(**enriched_item))
            
        return enriched_placements
    except Exception as e:
        logger.exception(f"Error fetching recent placements for user {user.get('person_id')}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not fetch recent placements.")


@router.get("/recommended-podcasts", response_model=List[RecommendedPodcastItem], summary="Get Recommended Podcasts")
async def get_recommended_podcasts_api(limit: int = 3, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Fetches recommended podcasts.
    Current logic: recently added or high quality score.
    TODO: Implement more sophisticated recommendation logic based on user/campaign.
    """
    try:
        # Simple recommendation: recently added media with a decent quality score
        # This query function needs to be created or adapted.
        recommended_media_db = await media_queries.get_media_for_recommendation(
            limit=limit,
            min_quality_score=60 # Example threshold
        )
        
        recommendations = []
        for media_dict in recommended_media_db:
            recommendations.append(RecommendedPodcastItem(
                media_id=media_dict["media_id"],
                name=media_dict.get("name"),
                host_names=media_dict.get("host_names"),
                category=media_dict.get("category"),
                audience_size=media_dict.get("audience_size"),
                description=media_dict.get("description"),
                image_url=media_dict.get("image_url"),
                quality_score=media_dict.get("quality_score"),
                website=media_dict.get("website")
            ))
        return recommendations
    except Exception as e:
        logger.exception(f"Error fetching recommended podcasts: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not fetch recommended podcasts.")