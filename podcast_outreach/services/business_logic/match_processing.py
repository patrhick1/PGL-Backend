# podcast_outreach/services/business_logic/match_processing.py

import uuid
import logging
from typing import Optional
from podcast_outreach.services.database_service import DatabaseService
from podcast_outreach.services.matches.scorer import DetermineFitProcessor
from podcast_outreach.services.matches.match_creation import MatchCreationService
from podcast_outreach.database.queries import review_tasks as rt_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import campaigns as campaign_queries

logger = logging.getLogger(__name__)

async def run_qualitative_match_assessment(db_service: DatabaseService) -> bool:
    """
    Pure business logic function for qualitative match assessment.
    Assumes database resources are available via db_service.
    """
    # Temporarily set the global pool for this event loop
    from podcast_outreach.database import connection
    original_pool = connection.DB_POOL
    connection.DB_POOL = db_service.pool
    
    try:
        processor = DetermineFitProcessor()
        
        logger.info("Running Qualitative Match Assessment for pending review tasks")
        pending_qual_reviews, total_pending = await rt_queries.get_all_review_tasks_paginated(
            task_type='match_suggestion_qualitative_review',
            status='pending',
            size=50
        )
        
        if not pending_qual_reviews:
            logger.info("No pending qualitative review tasks found")
            return True

        logger.info(f"Found {len(pending_qual_reviews)} tasks for qualitative assessment")
        
        for review_task_record in pending_qual_reviews:
            logger.info(f"Processing qualitative review for task_id: {review_task_record.get('review_task_id')}, match_suggestion_id: {review_task_record.get('related_id')}")
            await processor.process_single_record(review_task_record)
        
        logger.info("Qualitative Match Assessment cycle completed")
        return True
    except Exception as e:
        logger.error(f"Error during qualitative match assessment: {e}", exc_info=True)
        return False
    finally:
        # Restore original pool
        connection.DB_POOL = original_pool

async def create_matches_for_enriched_media(db_service: DatabaseService) -> bool:
    """
    Create match suggestions for media that have completed enrichment and episode analysis.
    This runs as part of the new workflow: Discovery → Enrichment → Match Creation → Vetting
    """
    # Temporarily set the global pool for this event loop
    from podcast_outreach.database import connection
    original_pool = connection.DB_POOL
    connection.DB_POOL = db_service.pool
    
    try:
        # Get media that are ready for match creation
        ready_media = await media_queries.get_enriched_media_for_campaigns()
        
        if not ready_media:
            logger.info("No enriched media ready for match creation")
            return True
        
        logger.info(f"Found {len(ready_media)} enriched media ready for match creation")
        
        match_creator = MatchCreationService()
        created_count = 0
        
        for item in ready_media:
            campaign_id = item['campaign_id']
            media_id = item['media_id']
            keyword = item['discovery_keyword']
            media_name = item['media_name']
            
            try:
                logger.info(f"Creating match suggestion for media '{media_name}' (ID: {media_id}) and campaign {campaign_id}")
                
                # NEW WORKFLOW: Vet first, then create match suggestion if approved
                from podcast_outreach.services.matches.enhanced_vetting_agent import EnhancedVettingAgent
                from podcast_outreach.database.queries import campaigns as campaign_queries
                
                # Get campaign details for vetting
                campaign_data = await campaign_queries.get_campaign_by_id(campaign_id)
                if not campaign_data:
                    logger.error(f"Campaign {campaign_id} not found for vetting")
                    continue
                
                # Run AI vetting before creating match
                vetting_agent = EnhancedVettingAgent()
                vetting_result = await vetting_agent.vet_media_for_campaign(media_id, campaign_data)
                
                if vetting_result.get('status') == 'success':
                    vetting_score = vetting_result.get('vetting_score', 0)
                    min_vetting_score = 60  # Only create matches for well-vetted podcasts
                    
                    if vetting_score >= min_vetting_score:
                        # Create match suggestion only if vetting passes
                        from podcast_outreach.services.media.podcast_fetcher import MediaFetcher
                        fetcher = MediaFetcher()
                        success = await fetcher.create_match_suggestions(media_id, campaign_id, keyword)
                        
                        if success:
                            logger.info(f"Created match suggestion for well-vetted media {media_id} (score: {vetting_score}) and campaign {campaign_id}")
                        else:
                            logger.warning(f"Failed to create match suggestion despite good vetting score for media {media_id}")
                    else:
                        logger.info(f"Media {media_id} did not pass vetting for campaign {campaign_id} (score: {vetting_score} < {min_vetting_score})")
                        success = False
                else:
                    logger.warning(f"Vetting failed for media {media_id} and campaign {campaign_id}: {vetting_result.get('message')}")
                    success = False
                
                if success:
                    created_count += 1
                    logger.info(f"Successfully created match suggestion for media {media_id} and campaign {campaign_id}")
                else:
                    logger.warning(f"Failed to create match suggestion for media {media_id} and campaign {campaign_id}")
                    
            except Exception as e:
                logger.error(f"Error creating match for media {media_id} and campaign {campaign_id}: {e}", exc_info=True)
        
        logger.info(f"Match creation completed. Created {created_count} new match suggestions from {len(ready_media)} ready media")
        return True
        
    except Exception as e:
        logger.error(f"Error during enriched media match creation: {e}", exc_info=True)
        return False
    finally:
        # Restore original pool
        connection.DB_POOL = original_pool

async def score_potential_matches(
    db_service: DatabaseService,
    campaign_id_str: Optional[str] = None, 
    media_id_int: Optional[int] = None
) -> bool:
    """
    Pure business logic function for scoring potential matches.
    Assumes database resources are available via db_service.
    """
    match_creator = MatchCreationService()
    
    try:
        if campaign_id_str:
            campaign_uuid = uuid.UUID(campaign_id_str)
            logger.info(f"Scoring potential matches for campaign {campaign_uuid}")
            all_media = await media_queries.get_all_media_from_db(limit=10000)
            if all_media:
                await match_creator.create_and_score_match_suggestions_for_campaign(campaign_uuid, all_media)
                logger.info(f"Completed scoring for campaign {campaign_uuid}")
            else:
                logger.info(f"No media found to score against campaign {campaign_uuid}")
        
        elif media_id_int is not None:
            logger.info(f"Scoring potential matches for media {media_id_int}")
            all_campaigns, total_campaigns = await campaign_queries.get_campaigns_with_embeddings(limit=10000)
            if all_campaigns:
                await match_creator.create_and_score_match_suggestions_for_media(media_id_int, all_campaigns)
                logger.info(f"Completed scoring for media {media_id_int}")
            else:
                logger.info(f"No campaigns with embeddings found to score against media {media_id_int}")
        else:
            logger.warning("score_potential_matches called without campaign_id or media_id")
            return False

        return True
    except Exception as e:
        logger.error(f"Error scoring potential matches (campaign: {campaign_id_str}, media: {media_id_int}): {e}", exc_info=True)
        return False