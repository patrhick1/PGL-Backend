# podcast_outreach/services/business_logic/enrichment_processing.py

import logging
from podcast_outreach.services.database_service import DatabaseService
from podcast_outreach.services.enrichment.enrichment_orchestrator import EnrichmentOrchestrator
from podcast_outreach.services.matches.enhanced_vetting_orchestrator import EnhancedVettingOrchestrator
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.services.enrichment.data_merger import DataMergerService
from podcast_outreach.services.enrichment.quality_score import QualityService
from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService
from podcast_outreach.services.enrichment.enrichment_agent import EnrichmentAgent

logger = logging.getLogger(__name__)

async def run_enrichment_pipeline(db_service: DatabaseService, media_id: int = None) -> bool:
    """
    Pure business logic function for enrichment pipeline.
    Assumes database resources are available via db_service.
    Can run for all media or a specific media_id.
    """
    # Temporarily set the global pool for this event loop
    from podcast_outreach.database import connection
    original_pool = connection.DB_POOL
    connection.DB_POOL = db_service.pool
    
    try:
        if media_id:
            logger.info(f"Running enrichment pipeline for media_id: {media_id}")
            return await run_single_media_enrichment(db_service, media_id)
        else:
            logger.info("Running full enrichment pipeline")
            
            # Initialize services (these should eventually use dependency injection)
            gemini_service = GeminiService()
            social_discovery_service = SocialDiscoveryService()
            data_merger = DataMergerService()
            enrichment_agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger)
            quality_service = QualityService()
            orchestrator = EnrichmentOrchestrator(enrichment_agent, quality_service, social_discovery_service)
            
            await orchestrator.run_pipeline_once()
            logger.info("Full enrichment pipeline completed")
            return True
    except Exception as e:
        logger.error(f"Error during enrichment pipeline: {e}", exc_info=True)
        return False
    finally:
        # Restore original pool
        connection.DB_POOL = original_pool

async def run_single_media_enrichment(db_service: DatabaseService, media_id: int) -> bool:
    """
    Pure business logic function for enriching a single media item.
    Moved from discovery.py to properly separate concerns.
    """
    from pydantic import HttpUrl
    from podcast_outreach.database.queries import media as media_queries
    
    logger.info(f"Starting enrichment for media_id: {media_id}")
    try:
        # Initialize all the necessary services for the orchestrator
        gemini_service = GeminiService()
        social_discovery_service = SocialDiscoveryService()
        data_merger = DataMergerService()
        enrichment_agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger)
        quality_service = QualityService()
        orchestrator = EnrichmentOrchestrator(enrichment_agent, quality_service, social_discovery_service)

        # 1. Enrich media profile (social links, emails, etc.)
        media_data = await media_queries.get_media_by_id_from_db(media_id)
        if not media_data:
            logger.error(f"Enrichment failed: Media with id {media_id} not found.")
            return False
        
        # Debug: Log media data structure  
        logger.info(f"Media data for {media_id}: name='{media_data.get('name')}', api_id='{media_data.get('api_id')}'")

        enriched_profile = await orchestrator.enrichment_agent.enrich_podcast_profile(media_data)
        if enriched_profile:
            # Convert the Pydantic model to a dictionary
            update_data = enriched_profile.model_dump(exclude_none=True)
            
            # Convert all HttpUrl objects to strings
            for key, value in update_data.items():
                if isinstance(value, HttpUrl):
                    update_data[key] = str(value)

            fields_to_remove = ['unified_profile_id', 'recent_episodes', 'quality_score']
            for field in fields_to_remove:
                if field in update_data: del update_data[field]
            if 'primary_email' in update_data:
                update_data['contact_email'] = update_data.pop('primary_email')
            if 'rss_feed_url' in update_data:
                update_data['rss_url'] = update_data.pop('rss_feed_url')

            await media_queries.update_media_enrichment_data(media_id, update_data)
            logger.info(f"Successfully ran enrichment agent for media_id: {media_id}")
        else:
            logger.warning(f"Enrichment agent returned no profile for media_id: {media_id}.")

        # 2. Update quality score
        # Refetch data after enrichment to get the most current profile for scoring
        refetched_media_data = await media_queries.get_media_by_id_from_db(media_id)
        if refetched_media_data:
            await orchestrator._update_quality_score_for_media(refetched_media_data)
        
        logger.info(f"Completed enrichment for media_id: {media_id}")
        
        # 3. Trigger vetting pipeline for any pending matches involving this media
        try:
            await trigger_vetting_for_media(db_service, media_id)
        except Exception as vetting_error:
            # Don't fail enrichment if vetting trigger fails
            logger.error(f"Error triggering vetting for media_id {media_id}: {vetting_error}", exc_info=True)
        
        return True

    except Exception as e:
        logger.error(f"Error in enrichment for media_id {media_id}: {e}", exc_info=True)
        return False

async def trigger_vetting_for_media(db_service: DatabaseService, media_id: int) -> bool:
    """
    Trigger vetting pipeline for all pending vetting tasks related to a specific media.
    Called automatically after enrichment completes.
    """
    from podcast_outreach.database.queries import review_tasks as review_task_queries
    from podcast_outreach.services.matches.enhanced_vetting_orchestrator import EnhancedVettingOrchestrator
    
    try:
        logger.info(f"Triggering vetting for enriched media_id: {media_id}")
        
        # Find pending vetting tasks for matches involving this media
        # This requires a custom query to join review_tasks -> match_suggestions -> media
        
        orchestrator = EnhancedVettingOrchestrator()
        
        # For now, run a limited vetting pipeline focused on this media
        # A more targeted approach would be to create a specific method in EnhancedVettingOrchestrator
        # that only processes vetting tasks for a specific media_id
        
        # Run the general vetting pipeline but with a small batch to avoid overprocessing
        await orchestrator.run_vetting_pipeline(batch_size=5)
        
        # Publish enrichment completed event
        try:
            from podcast_outreach.services.events.event_bus import get_event_bus, Event, EventType
            event_bus = get_event_bus()
            event = Event(
                event_type=EventType.ENRICHMENT_COMPLETED,
                entity_id=str(media_id),
                entity_type="media",
                data={
                    "vetting_triggered": True,
                    "quality_score_updated": True
                },
                source="enrichment_processing"
            )
            await event_bus.publish(event)
            logger.info(f"Published ENRICHMENT_COMPLETED event for media {media_id}")
        except Exception as e:
            logger.error(f"Error publishing enrichment completed event: {e}")
        
        logger.info(f"Successfully triggered vetting pipeline for media_id: {media_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error triggering vetting for media_id {media_id}: {e}", exc_info=True)
        return False

async def run_vetting_pipeline(db_service: DatabaseService) -> bool:
    """
    Pure business logic function for vetting pipeline.
    Assumes database resources are available via db_service.
    """
    # Temporarily set the global pool for this event loop
    from podcast_outreach.database import connection
    original_pool = connection.DB_POOL
    connection.DB_POOL = db_service.pool
    
    try:
        logger.info("Running Enhanced Vetting Orchestrator pipeline")
        orchestrator = EnhancedVettingOrchestrator()
        await orchestrator.run_vetting_pipeline()
        logger.info("Enhanced Vetting Orchestrator pipeline completed")
        return True
    except Exception as e:
        logger.error(f"Error during vetting pipeline: {e}", exc_info=True)
        return False
    finally:
        # Restore original pool
        connection.DB_POOL = original_pool