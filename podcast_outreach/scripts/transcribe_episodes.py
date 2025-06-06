# podcast_outreach/scripts/transcribe_episodes.py

import asyncio
import logging
import os

from podcast_outreach.services.media.transcriber import MediaTranscriber
from podcast_outreach.services.media.analyzer import MediaAnalyzerService
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.connection import init_db_pool, close_db_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 20

async def main():
    """
    Main orchestration function for the transcription script.
    It fetches episodes flagged for transcription and processes them one by one,
    chaining transcription with content analysis for immediate processing.
    """
    await init_db_pool()
    transcriber = MediaTranscriber()
    analyzer = MediaAnalyzerService()
    try:
        to_process = await episode_queries.fetch_episodes_for_transcription(BATCH_SIZE)
        if not to_process:
            logger.info("No episodes require transcription at this time.")
            return
        
        logger.info(f"Found {len(to_process)} episodes to transcribe and analyze.")

        for ep in to_process:
            episode_id = ep["episode_id"]
            local_audio_path = None
            try:
                logger.info(f"--- Processing episode {episode_id}: '{ep.get('title')}' ---")
                
                # 1. Download Audio
                local_audio_path = await transcriber.download_audio(ep["episode_url"])
                if not local_audio_path:
                    logger.error(f"Failed to download audio for episode {episode_id}. Skipping.")
                    continue

                # 2. Transcribe and Summarize
                transcript, summary, embedding = await transcriber.transcribe_audio(
                    local_audio_path, 
                    episode_id=episode_id, 
                    episode_title=ep.get("title")
                )
                
                if not transcript or "ERROR in chunk" in transcript:
                    logger.error(f"Transcription failed or had errors for episode {episode_id}. Skipping further processing.")
                    # Update DB to mark it as failed/processed to avoid retrying
                    await episode_queries.update_episode_transcription(episode_id, transcript or "[TRANSCRIPTION FAILED]", summary)
                    continue

                # 3. Update DB with transcript, summary, and embedding
                await episode_queries.update_episode_transcription(
                    episode_id, transcript, summary, embedding
                )
                logger.info(f"Episode {episode_id} transcribed and updated in DB.")

                # 4. Immediately Analyze the new transcript
                analysis_result = await analyzer.analyze_episode(episode_id)
                if analysis_result.get("status") == "success":
                    logger.info(f"Episode {episode_id} analysis successful.")
                else:
                    logger.warning(f"Episode {episode_id} analysis failed: {analysis_result.get('message')}")

            except Exception as e:
                logger.exception(f"An unexpected error occurred while processing episode {episode_id}: {e}")
            finally:
                # 5. Clean up downloaded audio file
                if local_audio_path and os.path.exists(local_audio_path):
                    try:
                        os.remove(local_audio_path)
                        logger.info(f"Cleaned up temporary audio file: {local_audio_path}")
                    except OSError as e:
                        logger.error(f"Error removing temporary audio file {local_audio_path}: {e}")
                logger.info(f"--- Finished processing episode {episode_id} ---")

    finally:
        await close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())