# podcast_outreach/services/enrichment/enrichment_orchestrator.py

import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

# Import specific query functions from the modular queries packages
from podcast_outreach.database.queries.media import (
    get_media_for_enrichment,
    update_media_enrichment_data,
    update_media_quality_score,
    count_transcribed_episodes_for_media,
)
from podcast_outreach.database.queries.episodes import (
    flag_recent_episodes_for_transcription,
)

# Import services
from .enrichment_agent import EnrichmentAgent
from .quality_score import QualityService # Corrected import path and filename

# Import modular DB connection for main execution block
from podcast_outreach.database.connection import init_db_pool, close_db_pool 

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
        logger.info("EnrichmentOrchestrator initialized with EnrichmentAgent and QualityService.")

    async def _enrich_media_batch(self):
        """Fetches a batch of media, enriches them, and updates the database."""
        logger.info("Starting media enrichment batch...")
        media_to_enrich = await get_media_for_enrichment(
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
                    update_data = enriched_profile.model_dump(exclude_none=True)
                    
                    fields_to_remove_before_db_update = ['unified_profile_id', 'recent_episodes', 'quality_score']
                    for field in fields_to_remove_before_db_update:
                        if field in update_data: del update_data[field]
                    
                    if 'primary_email' in update_data:
                        update_data['contact_email'] = update_data.pop('primary_email')
                    
                    if 'rss_feed_url' in update_data:
                        update_data['rss_url'] = update_data.pop('rss_feed_url')

                    updated_media = await update_media_enrichment_data(media_id, update_data)
                    if updated_media:
                        logger.info(f"Successfully enriched and updated media_id: {media_id}")
                        enriched_count += 1
                    else:
                        logger.error(f"Enrichment successful for media_id: {media_id}, but DB update failed.")
                        failed_count += 1
                else:
                    logger.warning(f"Enrichment agent returned no profile for media_id: {media_id}. Skipping update.")
                    failed_count += 1
            except Exception as e:
                logger.error(f"Error during enrichment process for media_id {media_id}: {e}", exc_info=True)
                failed_count += 1
            await asyncio.sleep(0.5)
        logger.info(f"Media enrichment batch finished. Enriched: {enriched_count}, Failed: {failed_count}")

    async def _manage_transcription_flags(self):
        """Identifies media that might need new episodes flagged for transcription."""
        logger.info("Checking for media items to flag new episodes for transcription...")
        
        media_to_check = await get_media_for_enrichment(
            batch_size=100,
            enriched_before_hours=24 * 30
        )
        if not media_to_check:
            logger.info("No media items found for transcription flagging check.")
            return

        logger.info(f"Found {len(media_to_check)} media items to check for transcription flagging.")
        flagged_episode_counts = 0
        for media_item in media_to_check:
            media_id = media_item['media_id']
            try:
                newly_flagged_count = await flag_recent_episodes_for_transcription(
                    media_id, ORCHESTRATOR_CONFIG["max_transcription_flags_per_media"]
                )
                if newly_flagged_count > 0:
                    logger.info(f"Newly flagged {newly_flagged_count} episodes for media_id: {media_id}")
                    flagged_episode_counts += newly_flagged_count
            except Exception as e:
                logger.error(f"Error flagging episodes for media_id {media_id}: {e}", exc_info=True)
            await asyncio.sleep(0.1)
        logger.info(f"Transcription flagging check finished. Total new episodes flagged: {flagged_episode_counts}")

    async def _update_quality_scores_batch(self):
        """Fetches media, checks transcribed episode counts, and updates quality scores."""
        logger.info("Starting quality score update batch...")
        
        media_for_scoring = await get_media_for_enrichment(
            batch_size=ORCHESTRATOR_CONFIG["media_enrichment_batch_size"],
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
                transcribed_count = await count_transcribed_episodes_for_media(media_id)
                
                if transcribed_count >= ORCHESTRATOR_CONFIG["quality_score_min_transcribed_episodes"]:
                    from podcast_outreach.database.models.media_models import EnrichedPodcastProfile
                    try:
                        profile_for_scoring = EnrichedPodcastProfile(**media_data_dict)
                    except Exception as val_err:
                        logger.error(f"Could not construct EnrichedPodcastProfile for media_id {media_id} from DB data for quality scoring: {val_err}")
                        skipped_count +=1
                        continue

                    quality_score_val, _ = self.quality_service.calculate_podcast_quality_score(profile_for_scoring)
                    
                    if quality_score_val is not None:
                        success = await update_media_quality_score(media_id, quality_score_val)
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
            await asyncio.sleep(0.2)
        logger.info(f"Quality score update batch finished. Scores updated: {updated_scores_count}, Skipped: {skipped_count}")

    async def run_pipeline_once(self):
        """Runs one full cycle of the enrichment pipeline."""
        logger.info("=== Starting Single Enrichment Pipeline Run ===")
        start_time = datetime.now(timezone.utc)

        await self._enrich_media_batch()
        await self._manage_transcription_flags()
        await self._update_quality_scores_batch()
        
        end_time = datetime.now(timezone.utc)
        logger.info(f"=== Single Enrichment Pipeline Run Finished. Duration: {end_time - start_time} ===")

    async def run_continuously(self, stop_event: Optional[asyncio.Event] = None):
        """Runs the enrichment pipeline continuously until stop_event is set."""
        logger.info("=== Starting Continuous Enrichment Pipeline ===")
        while not (stop_event and stop_event.is_set()):
            await self.run_pipeline_once()
            logger.info(f"Main orchestrator loop sleeping for {ORCHESTRATOR_CONFIG['main_loop_sleep_seconds']} seconds...")
            try:
                for _ in range(ORCHESTRATOR_CONFIG['main_loop_sleep_seconds'] // 10):
                    if stop_event and stop_event.is_set(): break
                    await asyncio.sleep(10)
                if stop_event and stop_event.is_set(): break
            except asyncio.CancelledError:
                logger.info("Continuous pipeline run cancelled during sleep.")
                break
        logger.info("=== Continuous Enrichment Pipeline Stopped ===")

# Main execution block for standalone running of the orchestrator
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')

    async def main():
        from dotenv import load_dotenv
        load_dotenv()
        
        await init_db_pool()

        try:
            from podcast_outreach.services.ai.gemini_client import GeminiService
            from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService
            from podcast_outreach.services.enrichment.data_merger import DataMergerService
            from podcast_outreach.services.enrichment.enrichment_agent import EnrichmentAgent
            from podcast_outreach.services.enrichment.quality_score import QualityService

            gemini_service = GeminiService()
            social_discovery_service = SocialDiscoveryService()
            data_merger = DataMergerService()
            
            enrichment_agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger)
            quality_service = QualityService()
            
            orchestrator = EnrichmentOrchestrator(enrichment_agent, quality_service)
            
            await orchestrator.run_pipeline_once()
            
        except ValueError as e:
            logger.error(f"Failed to initialize services for orchestrator: {e}", exc_info=True)
        except Exception as e_main:
            logger.error(f"Error in orchestrator main execution: {e_main}", exc_info=True)
        finally:
            await close_db_pool()
            logger.info("Orchestrator finished and DB pool closed.")

    asyncio.run(main())
