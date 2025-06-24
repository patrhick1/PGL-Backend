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

    def _clean_media_data_for_validation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Clean media data to fix common validation issues (same logic as data_merger)."""
        cleaned_data = data.copy()
        
        # Fix emails being stored in URL fields
        url_fields = [
            'podcast_twitter_url', 'podcast_linkedin_url', 'podcast_instagram_url',
            'podcast_facebook_url', 'podcast_youtube_url', 'podcast_tiktok_url',
            'podcast_other_social_url', 'website', 'image_url', 'rss_feed_url'
        ]
        
        for field in url_fields:
            if field in cleaned_data and cleaned_data[field]:
                value = str(cleaned_data[field]).strip()
                # Check if it's an email (contains @ but not a valid URL)
                if '@' in value and not value.startswith(('http://', 'https://')):
                    logger.warning(f"Found email '{value}' in URL field '{field}' during quality scoring, cleaning...")
                    # Clear the URL field (don't move to email since we don't want to overwrite)
                    cleaned_data[field] = None
        
        return cleaned_data

    async def run_social_stats_refresh(self, batch_size: int = 20):
        """Refreshes only social media follower counts for stale records."""
        logger.info("Starting social stats refresh batch...")
        refresh_interval = ORCHESTRATOR_CONFIG["social_stats_refresh_interval_hours"]
        media_to_refresh = await media_queries.get_media_for_social_refresh(batch_size, refresh_interval)
        
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
                    await media_queries.update_media_enrichment_data(media_id, update_payload)
                    logger.info(f"Successfully updated social stats for media_id: {media_id}. Payload: {update_payload}")
                    
                    # Trigger quality score update since social stats affect quality calculation
                    try:
                        # Get updated media data for quality score calculation
                        updated_media_data = await media_queries.get_media_by_id_from_db(media_id)
                        if updated_media_data:
                            await self._update_quality_score_for_media(updated_media_data)
                            logger.info(f"Triggered quality score update after social refresh for media_id: {media_id}")
                    except Exception as quality_e:
                        logger.error(f"Error updating quality score after social refresh for media_id {media_id}: {quality_e}")
                        
                else: # Otherwise, just update the timestamp
                    await media_queries.update_media_enrichment_data(media_id, {"social_stats_last_fetched_at": datetime.now(timezone.utc)})

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
                    
                    # Convert HttpUrl objects to strings
                    from pydantic import HttpUrl
                    for key, value in update_data.items():
                        if isinstance(value, HttpUrl):
                            update_data[key] = str(value)
                    
                    fields_to_remove = ['unified_profile_id', 'recent_episodes', 'quality_score']
                    for field in fields_to_remove:
                        if field in update_data: del update_data[field]
                    
                    if 'primary_email' in update_data: update_data['contact_email'] = update_data.pop('primary_email')
                    if 'rss_feed_url' in update_data: update_data['rss_url'] = update_data.pop('rss_feed_url')

                    # Use confidence-aware update for core enrichment (API source, medium confidence)
                    await media_queries.update_media_with_confidence_check(
                        media_id, update_data, source="api", confidence=0.85
                    )
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
        update_interval = ORCHESTRATOR_CONFIG["quality_score_update_interval_hours"]
        media_to_score = await media_queries.get_media_for_quality_score_update(batch_size, update_interval)
        
        if not media_to_score:
            logger.info("No media items found for quality score update in this batch.")
            return

        for media_data in media_to_score:
            media_id = media_data['media_id']
            try:
                # Clean the data before validation (same logic as in data_merger)
                cleaned_media_data = self._clean_media_data_for_validation(media_data)
                profile = EnrichedPodcastProfile(**cleaned_media_data)
                
                quality_score_val, score_components = self.quality_service.calculate_podcast_quality_score(profile)
                
                if quality_score_val is not None:
                    # Use update_media_quality_score which also compiles episode summaries
                    success = await media_queries.update_media_quality_score(media_id, quality_score_val)
                    if success:
                        logger.info(f"Updated quality score and compiled episode summaries for media_id: {media_id}")
                    else:
                        logger.error(f"Failed to update quality score for media_id: {media_id}")
                else:
                    logger.warning(f"Quality score calculation returned None for media_id: {media_id}")

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
                    # Clean the data before validation (same as in data_merger)
                    cleaned_media_data = self._clean_media_data_for_validation(media_data_dict)
                    profile_for_scoring = EnrichedPodcastProfile(**cleaned_media_data)
                except Exception as val_err:
                    logger.error(f"Could not construct EnrichedPodcastProfile for media_id {media_id} from DB data for quality scoring: {val_err}")
                    return

                quality_score_val, score_components = self.quality_service.calculate_podcast_quality_score(profile_for_scoring)
                
                if quality_score_val is not None:
                    # Use update_media_quality_score which also compiles episode summaries
                    success = await media_queries.update_media_quality_score(media_id, quality_score_val)
                    if success:
                        logger.info(f"Successfully updated quality score and compiled episode summaries for media_id: {media_id} to {quality_score_val}")
                    else:
                        logger.error(f"Failed to update quality score in DB for media_id: {media_id}")
                else:
                    logger.warning(f"Quality score calculation returned None for media_id: {media_id}")
            else:
                logger.info(f"Skipping quality score for media_id: {media_id}, transcribed episodes: {transcribed_count} (need {ORCHESTRATOR_CONFIG['quality_score_min_transcribed_episodes']}).")
        except Exception as e:
            logger.error(f"Error during quality score update for single media_id {media_id}: {e}", exc_info=True)

    async def _trigger_match_creation_for_ready_media(self):
        """
        Check for media that have completed enrichment and episode analysis,
        and trigger match creation for them.
        """
        try:
            from podcast_outreach.services.business_logic.match_processing import create_matches_for_enriched_media
            from podcast_outreach.services.database_service import DatabaseService
            from podcast_outreach.database.connection import get_db_pool
            
            # Create a temporary database service for this operation
            pool = await get_db_pool()
            db_service = DatabaseService(pool)
            
            logger.info("Checking for enriched media ready for match creation")
            success = await create_matches_for_enriched_media(db_service)
            
            if success:
                logger.info("Match creation for enriched media completed successfully")
            else:
                logger.warning("Match creation for enriched media completed with some issues")
                
        except Exception as e:
            logger.error(f"Error during match creation trigger: {e}", exc_info=True)

    async def enrich_media(self, media_id: int) -> bool:
        """
        Enrich a single media item completely.
        This is the main method called by discovery_processing.py
        
        Returns:
            bool: True if enrichment was successful, False otherwise
        """
        try:
            logger.info(f"Starting enrichment for media_id: {media_id}")
            
            # Get current media data
            media_data = await media_queries.get_media_by_id_from_db(media_id)
            if not media_data:
                logger.error(f"Media {media_id} not found")
                return False
            
            # 1. Run core enrichment (social data, contact info, etc.)
            enriched_profile = await self.enrichment_agent.enrich_podcast_profile(media_data)
            if enriched_profile:
                update_data = enriched_profile.model_dump(exclude_none=True)
                
                # Convert HttpUrl objects to strings
                from pydantic import HttpUrl
                for key, value in update_data.items():
                    if isinstance(value, HttpUrl):
                        update_data[key] = str(value)
                
                # Clean up data
                fields_to_remove = ['unified_profile_id', 'recent_episodes', 'quality_score']
                for field in fields_to_remove:
                    if field in update_data:
                        del update_data[field]
                
                if 'primary_email' in update_data:
                    update_data['contact_email'] = update_data.pop('primary_email')
                if 'rss_feed_url' in update_data:
                    update_data['rss_url'] = update_data.pop('rss_feed_url')
                
                # Update media with enriched data
                await media_queries.update_media_enrichment_data(media_id, update_data)
                logger.info(f"Core enrichment completed for media_id: {media_id}")
            
            # 2. Generate AI description if missing
            media_data = await media_queries.get_media_by_id_from_db(media_id)
            if not media_data.get('ai_description'):
                # Check if we have enough episode data for AI description
                from podcast_outreach.database.queries import episodes as episode_queries
                episodes = await episode_queries.get_episodes_for_media_with_content(media_id, limit=3)
                
                if episodes:
                    # Use episode summaries to generate AI description
                    from podcast_outreach.services.media.analyzer import MediaAnalyzerService
                    analyzer = MediaAnalyzerService()
                    podcast_analysis = await analyzer.analyze_podcast_from_episodes(media_id)
                    
                    if podcast_analysis.get("status") == "success" and podcast_analysis.get("ai_description"):
                        await media_queries.update_media_ai_description(media_id, podcast_analysis["ai_description"])
                        logger.info(f"AI description generated for media_id: {media_id}")
            
            # 3. Update quality score and compile episode summaries
            # Refetch media data to get latest updates
            media_data = await media_queries.get_media_by_id_from_db(media_id)
            transcribed_count = await media_queries.count_transcribed_episodes_for_media(media_id)
            
            if transcribed_count >= ORCHESTRATOR_CONFIG.get("quality_score_min_transcribed_episodes", 3):
                try:
                    # Clean data and calculate quality score
                    cleaned_media_data = self._clean_media_data_for_validation(media_data)
                    profile = EnrichedPodcastProfile(**cleaned_media_data)
                    quality_score_val, _ = self.quality_service.calculate_podcast_quality_score(profile)
                    
                    if quality_score_val is not None:
                        # Use update_media_quality_score which also compiles episode summaries
                        await media_queries.update_media_quality_score(media_id, quality_score_val)
                        logger.info(f"Quality score updated and episode summaries compiled for media_id: {media_id}")
                except Exception as e:
                    logger.error(f"Error updating quality score for media {media_id}: {e}")
            
            logger.info(f"Enrichment completed successfully for media_id: {media_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error enriching media {media_id}: {e}", exc_info=True)
            return False

    async def run_pipeline_once(self):
        """Runs all selective tasks in sequence."""
        logger.info("=== Starting Single Enrichment Pipeline Run ===")
        start_time = datetime.now(timezone.utc)

        await self.run_core_details_enrichment()
        await self.run_social_stats_refresh()
        await self.run_quality_score_updates()
        await self._manage_transcription_flags()
        await self._trigger_match_creation_for_ready_media()
        
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
