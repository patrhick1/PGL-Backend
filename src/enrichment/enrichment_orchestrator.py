import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

# Assuming services and models are in paths like src.services, src.enrichment, src.models
# Adjust these relative imports based on your final project structure.
import db_service_pg # For direct DB calls
from .enrichment_agent import EnrichmentAgent
from .quality_service import QualityService
from ..models.podcast_profile_models import EnrichedPodcastProfile # For constructing profile for QualityService

logger = logging.getLogger(__name__)

# Configuration for the orchestrator
ORCHESTRATOR_CONFIG = {
    "media_enrichment_batch_size": 10,
    "media_enrichment_interval_hours": 24 * 7,  # Re-enrich media older than 1 week
    "quality_score_min_transcribed_episodes": 3,
    "quality_score_update_interval_days": 7, # Re-calculate quality scores for media if last score is older than this
    "max_transcription_flags_per_media": 4, # Max episodes to flag for transcription per media item
    "main_loop_sleep_seconds": 300 # Sleep duration for the main orchestrator loop if run continuously
}

class EnrichmentOrchestrator:
    """Orchestrates the end-to-end podcast data enrichment and quality scoring pipeline."""

    def __init__(self,
                 enrichment_agent: EnrichmentAgent,
                 quality_service: QualityService):
        self.enrichment_agent = enrichment_agent
        self.quality_service = quality_service
        # DB pool should be managed externally or by individual functions in db_service_pg
        logger.info("EnrichmentOrchestrator initialized with EnrichmentAgent and QualityService.")

    async def _enrich_media_batch(self):
        """Fetches a batch of media, enriches them, and updates the database."""
        logger.info("Starting media enrichment batch...")
        media_to_enrich = await db_service_pg.get_media_for_enrichment(
            batch_size=ORCHESTRATOR_CONFIG["media_enrichment_batch_size"],
            enriched_before_hours=ORCHESTRATOR_CONFIG["media_enrichment_interval_hours"]
        )

        if not media_to_enrich:
            logger.info("No media items found needing metadata enrichment in this batch.")
            return

        logger.info(f"Found {len(media_to_enrich)} media items for enrichment.")
        enriched_count = 0
        failed_count = 0

        for media_data_dict in media_to_enrich:
            media_id = media_data_dict.get('media_id')
            try:
                enriched_profile = await self.enrichment_agent.enrich_podcast_profile(media_data_dict)
                if enriched_profile:
                    # Convert EnrichedPodcastProfile to a dict for DB update
                    # Ensure all fields in the dict match columns in the 'media' table
                    update_data = enriched_profile.model_dump(exclude_none=False) # include_none=False to only update provided fields
                    
                    # Remove fields that are not directly on media table or managed by DB
                    fields_to_remove_before_db_update = ['unified_profile_id', 'recent_episodes', 'quality_score']
                    for field in fields_to_remove_before_db_update:
                        if field in update_data: del update_data[field]
                    
                    # Ensure primary_email is mapped to contact_email if that's the DB column
                    if 'primary_email' in update_data and 'contact_email' not in update_data:
                        update_data['contact_email'] = update_data.pop('primary_email')
                    elif 'primary_email' in update_data and 'contact_email' in update_data and not update_data['contact_email']:
                        update_data['contact_email'] = update_data.pop('primary_email')
                    elif 'primary_email' in update_data: # Both exist, primary_email might have been consolidated
                        update_data['contact_email'] = update_data.pop('primary_email')

                    # last_enriched_timestamp is crucial
                    update_data['last_enriched_timestamp'] = datetime.utcnow()

                    updated_media = await db_service_pg.update_media_enrichment_data(media_id, update_data)
                    if updated_media:
                        logger.info(f"Successfully enriched and updated media_id: {media_id}")
                        enriched_count += 1
                    else:
                        logger.error(f"Enrichment successful for media_id: {media_id}, but DB update failed.")
                        failed_count += 1
                else:
                    logger.warning(f"Enrichment agent returned no profile for media_id: {media_id}. Skipping update.")
                    failed_count += 1 # Count as failed if agent returns None
            except Exception as e:
                logger.error(f"Error during enrichment process for media_id {media_id}: {e}", exc_info=True)
                failed_count += 1
            await asyncio.sleep(0.5) # Small delay between processing each item
        logger.info(f"Media enrichment batch finished. Enriched: {enriched_count}, Failed: {failed_count}")

    async def _manage_transcription_flags(self):
        """Identifies media that might need new episodes flagged for transcription."""
        logger.info("Checking for media items to flag new episodes for transcription...")
        # Strategy: Fetch media that have been enriched recently but might have new episodes.
        # Or, fetch all media periodically and let flag_episodes_for_transcription handle the logic.
        # For simplicity, let's assume we call this periodically for active media.
        # We could fetch media updated in last N days, or all media that are "active".
        
        # Example: Fetch all media that have a quality score or were enriched recently
        # This is a placeholder for a more targeted query if needed.
        media_to_check = await db_service_pg.get_media_for_enrichment(
            batch_size=100, # Check a larger batch for flagging
            enriched_before_hours=24 * 30 # Check media enriched in the last 30 days, or never scored
        )
        if not media_to_check:
            logger.info("No media items found for transcription flagging check.")
            return

        logger.info(f"Found {len(media_to_check)} media items to check for transcription flagging.")
        flagged_episode_counts = 0
        for media_item in media_to_check:
            media_id = media_item['media_id']
            try:
                newly_flagged_count = await db_service_pg.flag_episodes_for_transcription(
                    media_id, ORCHESTRATOR_CONFIG["max_transcription_flags_per_media"]
                )
                if newly_flagged_count > 0:
                    logger.info(f"Newly flagged {newly_flagged_count} episodes for media_id: {media_id}")
                    flagged_episode_counts += newly_flagged_count
            except Exception as e:
                logger.error(f"Error flagging episodes for media_id {media_id}: {e}", exc_info=True)
            await asyncio.sleep(0.1) # Small delay
        logger.info(f"Transcription flagging check finished. Total new episodes flagged: {flagged_episode_counts}")

    async def _update_quality_scores_batch(self):
        """Fetches media, checks transcribed episode counts, and updates quality scores."""
        logger.info("Starting quality score update batch...")
        
        # Fetch media that might need quality score calculation/update
        # e.g., quality_score IS NULL OR updated_at < now() - interval X days
        # Using get_media_for_enrichment as a proxy to get candidates for now.
        # A more specific query in db_service_pg might be `get_media_for_quality_scoring`.
        media_for_scoring = await db_service_pg.get_media_for_enrichment(
            batch_size=ORCHESTRATOR_CONFIG["media_enrichment_batch_size"], # Reuse batch size
            enriched_before_hours=ORCHESTRATOR_CONFIG["quality_score_update_interval_days"] * 24
        )

        if not media_for_scoring:
            logger.info("No media items found needing quality score update in this batch.")
            return
        
        logger.info(f"Found {len(media_for_scoring)} media items for potential quality score update.")
        updated_scores_count = 0
        skipped_count = 0

        for media_data_dict in media_for_scoring:
            media_id = media_data_dict.get('media_id')
            try:
                transcribed_count = await db_service_pg.count_transcribed_episodes_for_media(media_id)
                
                if transcribed_count >= ORCHESTRATOR_CONFIG["quality_score_min_transcribed_episodes"]:
                    # Construct EnrichedPodcastProfile from the DB data for QualityService
                    # This requires all relevant fields to be present in media_data_dict
                    # get_media_for_enrichment should return most of these.
                    try:
                        profile_for_scoring = EnrichedPodcastProfile(**media_data_dict)
                    except Exception as val_err:
                        logger.error(f"Could not construct EnrichedPodcastProfile for media_id {media_id} from DB data for quality scoring: {val_err}")
                        skipped_count +=1
                        continue

                    quality_score_val, _ = self.quality_service.calculate_podcast_quality_score(profile_for_scoring)
                    
                    if quality_score_val is not None:
                        success = await db_service_pg.update_media_quality_score(media_id, quality_score_val)
                        if success:
                            logger.info(f"Successfully updated quality score for media_id: {media_id} to {quality_score_val}")
                            updated_scores_count += 1
                        else:
                            logger.error(f"Failed to update quality score in DB for media_id: {media_id}")
                    else:
                        logger.warning(f"Quality score calculation returned None for media_id: {media_id}")
                else:
                    logger.debug(f"Skipping quality score for media_id: {media_id}, transcribed episodes: {transcribed_count} (need {ORCHESTRATOR_CONFIG['quality_score_min_transcribed_episodes']}).")
                    skipped_count += 1
            except Exception as e:
                logger.error(f"Error during quality score update for media_id {media_id}: {e}", exc_info=True)
            await asyncio.sleep(0.2) # Small delay
        logger.info(f"Quality score update batch finished. Scores updated: {updated_scores_count}, Skipped: {skipped_count}")

    async def run_pipeline_once(self):
        """Runs one full cycle of the enrichment pipeline."""
        logger.info("=== Starting Single Enrichment Pipeline Run ===")
        start_time = datetime.utcnow()

        # 1. Enrich Media Metadata
        await self._enrich_media_batch()
        
        # 2. Manage Transcription Flags (queue up episodes for the transcriber script)
        await self._manage_transcription_flags()
        
        # 3. Update Quality Scores (for media that have enough transcriptions)
        await self._update_quality_scores_batch()
        
        end_time = datetime.utcnow()
        logger.info(f"=== Single Enrichment Pipeline Run Finished. Duration: {end_time - start_time} ===")

    async def run_continuously(self, stop_event: Optional[asyncio.Event] = None):
        """Runs the enrichment pipeline continuously until stop_event is set."""
        logger.info("=== Starting Continuous Enrichment Pipeline ===")
        while not (stop_event and stop_event.is_set()):
            await self.run_pipeline_once()
            logger.info(f"Main orchestrator loop sleeping for {ORCHESTRATOR_CONFIG['main_loop_sleep_seconds']} seconds...")
            try:
                # Sleep in chunks to check stop_event more frequently
                for _ in range(ORCHESTRATOR_CONFIG['main_loop_sleep_seconds'] // 10):
                    if stop_event and stop_event.is_set(): break
                    await asyncio.sleep(10)
                if stop_event and stop_event.is_set(): break # Check again after loop
            except asyncio.CancelledError:
                logger.info("Continuous pipeline run cancelled during sleep.")
                break
        logger.info("=== Continuous Enrichment Pipeline Stopped ===")

# Main execution block for standalone running of the orchestrator
if __name__ == '__main__':
    # This requires all services to be initializable
    # You would typically run this from a main application script or a scheduled task manager
    
    # Setup basic logging for standalone run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')

    async def main():
        # Initialize DB Pool (must be done in async context)
        # Ensure .env is loaded if services depend on it for their init (e.g. API keys)
        from dotenv import load_dotenv
        load_dotenv()
        
        await db_service_pg.init_db_pool()

        # Initialize services (in a real app, these might be injected or use a DI framework)
        try:
            from ..services.gemini_service import GeminiService
            from ..services.social_discovery_service import SocialDiscoveryService
            # from .data_merger_service import DataMergerService # Already imported

            gemini_service = GeminiService() 
            social_discovery_service = SocialDiscoveryService()
            data_merger = DataMergerService()
            
            enrichment_agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger)
            quality_service = QualityService()
            
            orchestrator = EnrichmentOrchestrator(enrichment_agent, quality_service)
            
            # Run the pipeline once for testing
            await orchestrator.run_pipeline_once()
            
            # To run continuously (example, you'd manage the stop_event elsewhere):
            # stop_signal = asyncio.Event()
            # logger.info("Starting orchestrator continuously. Press Ctrl+C to attempt stop (may take time).")
            # try:
            #     await orchestrator.run_continuously(stop_signal)
            # except KeyboardInterrupt:
            #     logger.info("Ctrl+C received, setting stop signal for orchestrator...")
            #     stop_signal.set()
            #     # Give it a moment to stop gracefully, then re-raise or exit
            #     await asyncio.sleep(5) # Wait for cleanup within run_continuously

        except ValueError as e:
            logger.error(f"Failed to initialize services for orchestrator: {e}", exc_info=True)
        except Exception as e_main:
            logger.error(f"Error in orchestrator main execution: {e_main}", exc_info=True)
        finally:
            await db_service_pg.close_db_pool()
            logger.info("Orchestrator finished and DB pool closed.")

    asyncio.run(main()) 