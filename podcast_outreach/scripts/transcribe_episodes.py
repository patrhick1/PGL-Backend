# podcast_outreach/scripts/transcribe_episodes.py

import asyncio
import logging
import os

# Corrected imports to use the new service class and queries
from podcast_outreach.services.media.transcriber import MediaTranscriber
from podcast_outreach.services.media.analyzer import MediaAnalyzerService
from podcast_outreach.services.matches.match_creation import MatchCreationService
from podcast_outreach.database.queries import episodes as episode_queries, campaigns as campaign_queries, media as media_queries
from podcast_outreach.database.connection import init_db_pool, close_db_pool
from podcast_outreach.config import ORCHESTRATOR_CONFIG
from podcast_outreach.services.enrichment.quality_score import QualityService
from podcast_outreach.database.models.media_models import EnrichedPodcastProfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 20

async def run_transcription_logic():
    """
    Core logic for the transcription process. Assumes DB pool is initialized.
    """
    transcriber = MediaTranscriber()
    analyzer = MediaAnalyzerService()
    match_creator = MatchCreationService()
    quality_service = QualityService()

    to_process = await episode_queries.fetch_episodes_for_transcription(BATCH_SIZE)
    if not to_process:
        logger.info("No episodes require transcription at this time.")
        return

    logger.info(f"Found {len(to_process)} episodes to transcribe and analyze.")

    for ep in to_process:
        episode_id = ep["episode_id"]
        media_id = ep["media_id"]
        local_audio_path = None
        try:
            logger.info(f"--- Processing episode {episode_id}: '{ep.get('title')}' ---")
            
            local_audio_path = await transcriber.download_audio(ep["episode_url"])
            if not local_audio_path:
                logger.error(f"Failed to download audio for episode {episode_id}. Skipping.")
                continue

            transcript, summary, embedding = await transcriber.transcribe_audio(
                local_audio_path, episode_id=episode_id, episode_title=ep.get("title")
            )
            
            if not transcript or "ERROR in chunk" in transcript:
                logger.error(f"Transcription failed for episode {episode_id}. Skipping further processing.")
                await episode_queries.update_episode_transcription(episode_id, transcript or "[TRANSCRIPTION FAILED]", summary)
                continue

            updated_episode = await episode_queries.update_episode_transcription(
                episode_id, transcript, summary, embedding
            )
            logger.info(f"Episode {episode_id} transcribed and updated in DB.")

            # --- Post-Transcription Pipeline ---
            if updated_episode:
                # 1. Analyze Content
                analysis_result = await analyzer.analyze_episode(episode_id)
                if analysis_result.get("status") == "success":
                    logger.info(f"Episode {episode_id} analysis successful.")
                else:
                    logger.warning(f"Episode {episode_id} analysis failed: {analysis_result.get('message')}")

                # 2. Trigger Matching
                if updated_episode.get('embedding'):
                    logger.info(f"Triggering match creation for media_id {media_id} due to new episode {episode_id}.")
                    active_campaigns, _ = await campaign_queries.get_campaigns_with_embeddings(limit=1000)
                    if active_campaigns:
                        await match_creator.create_and_score_match_suggestions_for_media(media_id, active_campaigns)
                    else:
                        logger.info(f"No active campaigns with embeddings to match against media {media_id}.")

                # 3. Update Quality Score
                transcribed_count = await media_queries.count_transcribed_episodes_for_media(media_id)
                min_episodes_needed = ORCHESTRATOR_CONFIG.get("quality_score_min_transcribed_episodes", 3)
                if transcribed_count >= min_episodes_needed:
                    logger.info(f"Media {media_id} has enough transcripts. Updating quality score.")
                    media_data = await media_queries.get_media_by_id_from_db(media_id)
                    if media_data:
                        profile = EnrichedPodcastProfile(**media_data)
                        score, components = quality_service.calculate_podcast_quality_score(profile)
                        if score is not None:
                            await media_queries.update_media_in_db(media_id, components)
                            logger.info(f"Updated quality score for media {media_id} to {score}.")

        except Exception as e:
            logger.exception(f"An unexpected error occurred while processing episode {episode_id}: {e}")
        finally:
            if local_audio_path and os.path.exists(local_audio_path):
                try:
                    os.remove(local_audio_path)
                    logger.info(f"Cleaned up temporary audio file: {local_audio_path}")
                except OSError as e:
                    logger.error(f"Error removing temporary audio file {local_audio_path}: {e}")
            logger.info(f"--- Finished processing episode {episode_id} ---")

async def main():
    """Main entry point for running the script directly."""
    await init_db_pool()
    try:
        await run_transcription_logic()
    finally:
        await close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())