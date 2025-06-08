# podcast_outreach/services/enrichment/enrichment_orchestrator.py

import os
import sys
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

# Import specific query functions from the modular queries packages
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries.episodes import flag_specific_episodes_for_transcription
from podcast_outreach.database.models.media_models import EnrichedPodcastProfile

# Import services
from .enrichment_agent import EnrichmentAgent
from .quality_score import QualityService
from .social_scraper import SocialDiscoveryService

# Import modular DB connection for main execution block
from podcast_outreach.database.connection import init_db_pool, close_db_pool 
from podcast_outreach.config import ORCHESTRATOR_CONFIG

logger = logging.getLogger(__name__)

class EnrichmentOrchestrator:
    """Orchestrates the end-to-end podcast data enrichment and quality scoring pipeline."""

    def __init__(self,
                 enrichment_agent: EnrichmentAgent,
                 quality_service: QualityService,
                 social_discovery_service: SocialDiscoveryService):
        self.enrichment_agent = enrichment_agent
        self.quality_service = quality_service
        self.social_discovery_service = social_discovery_service
        logger.info("EnrichmentOrchestrator initialized with EnrichmentAgent, QualityService, and SocialDiscoveryService.")

    async def run_social_stats_refresh(self, batch_size: int = 20):
        """Refreshes only social media follower counts for stale records."""
        logger.info("Starting social stats refresh batch...")
        media_to_refresh = await media_queries.get_media_for_social_refresh(batch_size)
        
        if not media_to_refresh:
            logger.info("No media items found needing social stats refresh.")
            return

        for media_data in media_to_refresh:
            media_id = media_data['media_id']
            logger.info(f"Refreshing social stats for media_id: {media_id}")
            
            try:
                social_urls_to_scrape = {
                    "twitter": media_data.get("podcast_twitter_url"),
                    "instagram": media_data.get("podcast_instagram_url"),
                    "tiktok": media_data.get("podcast_tiktok_url"),
                    "linkedin": media_data.get("podcast_linkedin_url"),
                }
                
                update_payload = {}
                
                # Twitter
                if url := social_urls_to_scrape.get("twitter"):
                    twitter_data_map = await self.social_discovery_service.get_twitter_data_for_urls([url])
                    if twitter_data_map and (twitter_data := twitter_data_map.get(url)):
                        update_payload["twitter_followers"] = twitter_data.get('followers_count')

                # Instagram
                if url := social_urls_to_scrape.get("instagram"):
                    insta_data_map = await self.social_discovery_service.get_instagram_data_for_urls([url])
                    if insta_data_map and (insta_data := insta_data_map.get(url)):
                        update_payload["instagram_followers"] = insta_data.get('followers_count')
                
                # TikTok
                if url := social_urls_to_scrape.get("tiktok"):
                    tiktok_data_map = await self.social_discovery_service.get_tiktok_data_for_urls([url])
                    if tiktok_data_map and (tiktok_data := tiktok_data_map.get(url)):
                        update_payload["tiktok_followers"] = tiktok_data.get('followers_count')

                # LinkedIn
                if url := social_urls_to_scrape.get("linkedin"):
                    linkedin_data_map = await self.social_discovery_service.get_linkedin_data_for_urls([url])
                    if linkedin_data_map and (linkedin_data := linkedin_data_map.get(url)):
                        update_payload["linkedin_connections"] = linkedin_data.get('followers_count') or linkedin_data.get('connections_count')

                # Always update the timestamp to prevent immediate re-checking
                update_payload["social_stats_last_fetched_at"] = datetime.now(timezone.utc)
                
                if len(update_payload) > 1: # Only update if new data was actually fetched
                    await media_queries.update_media_in_db(media_id, update_payload)
                    logger.info(f"Successfully updated social stats for media_id: {media_id}. Payload: {update_payload}")
                else: # Otherwise, just update the timestamp
                    await media_queries.update_media_in_db(media_id, {"social_stats_last_fetched_at": datetime.now(timezone.utc)})

            except Exception as e:
                logger.error(f"Error refreshing social stats for media_id {media_id}: {e}", exc_info=True)
            await asyncio.sleep(0.5)
        logger.info("Social stats refresh batch finished.")

    async def run_core_details_enrichment(self, batch_size: int = 10):
        """Runs the full enrichment pipeline but only for records that have never been enriched."""
        logger.info("Starting core details enrichment for new media...")
        media_to_enrich = await media_queries.get_media_for_enrichment(batch_size, only_new=True)

        if not media_to_enrich:
            logger.info("No new media items found needing core details enrichment.")
            return
        
        for media_data_dict in media_to_enrich:
            media_id = media_data_dict.get('media_id')
            try:
                enriched_profile = await self.enrichment_agent.enrich_podcast_profile(media_data_dict)
                if enriched_profile:
                    update_data = enriched_profile.model_dump(exclude_none=True)
                    
                    fields_to_remove = ['unified_profile_id', 'recent_episodes', 'quality_score']
                    for field in fields_to_remove:
                        if field in update_data: del update_data[field]
                    
                    if 'primary_email' in update_data: update_data['contact_email'] = update_data.pop('primary_email')
                    if 'rss_feed_url' in update_data: update_data['rss_url'] = update_data.pop('rss_feed_url')

                    await media_queries.update_media_in_db(media_id, update_data)
                    logger.info(f"Successfully ran core enrichment for new media_id: {media_id}")
                else:
                    logger.warning(f"Core enrichment returned no profile for media_id: {media_id}.")
            except Exception as e:
                logger.error(f"Error during core enrichment for media_id {media_id}: {e}", exc_info=True)
            await asyncio.sleep(0.5)
        logger.info("Core details enrichment batch finished.")

    async def run_quality_score_updates(self, batch_size: int = 20):
        """Refreshes quality scores for records where the score is stale."""
        logger.info("Starting quality score update batch...")
        media_to_score = await media_queries.get_media_for_quality_score_update(batch_size)
        
        if not media_to_score:
            logger.info("No media items found for quality score update in this batch.")
            return

        for media_data in media_to_score:
            media_id = media_data['media_id']
            try:
                profile = EnrichedPodcastProfile(**media_data)
                
                _, score_components = self.quality_service.calculate_podcast_quality_score(profile)
                
                if score_components:
                    await media_queries.update_media_in_db(media_id, score_components)
                    logger.info(f"Updated quality score components for media_id: {media_id}")
                else:
                    logger.warning(f"Quality score calculation returned no components for media_id: {media_id}")

            except Exception as e:
                logger.error(f"Error updating quality score for media_id {media_id}: {e}", exc_info=True)
            await asyncio.sleep(0.2)
        logger.info("Quality score update batch finished.")

    async def _manage_transcription_flags(self):
        """Identifies media that might need new episodes flagged for transcription."""
        logger.info("Checking for media items to flag new episodes for transcription...")
        
        media_to_check = await media_queries.get_media_for_enrichment(
            batch_size=100,
            enriched_before_hours=24 * 30 # Check even if not recently enriched
        )
        if not media_to_check:
            logger.info("No media items found for transcription flagging check.")
            return

        logger.info(f"Found {len(media_to_check)} media items to check for transcription flagging.")
        for media_item in media_to_check:
            media_id = media_item['media_id']
            try:
                # This logic is now in EpisodeHandlerService, called after episode sync.
                # This becomes a fallback/periodic check.
                from podcast_outreach.services.media.episode_handler import EpisodeHandlerService
                handler = EpisodeHandlerService()
                await handler.flag_episodes_to_meet_transcription_goal(
                    media_id, ORCHESTRATOR_CONFIG["max_transcription_flags_per_media"]
                )
            except Exception as e:
                logger.error(f"Error flagging episodes for media_id {media_id}: {e}", exc_info=True)
            await asyncio.sleep(0.1)
        logger.info("Transcription flagging check finished.")

    async def _update_quality_score_for_media(self, media_data_dict: Dict[str, Any]):
        """
        Calculates and updates the quality score for a single media item.
        Designed to be called from a direct, non-blocking process like the discovery service.
        """
        media_id = media_data_dict.get('media_id')
        if not media_id:
            logger.error("Cannot update quality score: media_id missing from provided data.")
            return

        logger.info(f"Starting quality score update for single media_id: {media_id}")
        try:
            transcribed_count = await media_queries.count_transcribed_episodes_for_media(media_id)
            
            if transcribed_count >= ORCHESTRATOR_CONFIG["quality_score_min_transcribed_episodes"]:
                try:
                    profile_for_scoring = EnrichedPodcastProfile(**media_data_dict)
                except Exception as val_err:
                    logger.error(f"Could not construct EnrichedPodcastProfile for media_id {media_id} from DB data for quality scoring: {val_err}")
                    return

                quality_score_val, score_components = self.quality_service.calculate_podcast_quality_score(profile_for_scoring)
                
                if score_components:
                    success = await media_queries.update_media_in_db(media_id, score_components)
                    if success:
                        logger.info(f"Successfully updated quality score for media_id: {media_id} to {quality_score_val}")
                    else:
                        logger.error(f"Failed to update quality score in DB for media_id: {media_id}")
                else:
                    logger.warning(f"Quality score calculation returned None for media_id: {media_id}")
            else:
                logger.info(f"Skipping quality score for media_id: {media_id}, transcribed episodes: {transcribed_count} (need {ORCHESTRATOR_CONFIG['quality_score_min_transcribed_episodes']}).")
        except Exception as e:
            logger.error(f"Error during quality score update for single media_id {media_id}: {e}", exc_info=True)

    async def run_pipeline_once(self):
        """Runs all selective tasks in sequence."""
        logger.info("=== Starting Single Enrichment Pipeline Run ===")
        start_time = datetime.now(timezone.utc)

        await self.run_core_details_enrichment()
        await self.run_social_stats_refresh()
        await self.run_quality_score_updates()
        await self._manage_transcription_flags()
        
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
            from podcast_outreach.services.enrichment.data_merger import DataMergerService

            gemini_service = GeminiService()
            social_discovery_service = SocialDiscoveryService()
            data_merger = DataMergerService()
            
            enrichment_agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger)
            quality_service = QualityService()
            
            orchestrator = EnrichmentOrchestrator(enrichment_agent, quality_service, social_discovery_service)
            
            await orchestrator.run_pipeline_once()
            
        except ValueError as e:
            logger.error(f"Failed to initialize services for orchestrator: {e}", exc_info=True)
        except Exception as e_main:
            logger.error(f"Error in orchestrator main execution: {e_main}", exc_info=True)
        finally:
            await close_db_pool()
            logger.info("Orchestrator finished and DB pool closed.")

    asyncio.run(main())
