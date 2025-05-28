# podcast_outreach/scripts/transcribe_episodes.py

import asyncio
import logging
 
from podcast_outreach.services.media.transcriber import MediaTranscriber
from podcast_outreach.services.media.analyzer import MediaAnalyzerService # NEW IMPORT
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.connection import init_db_pool, close_db_pool # Use modular connection
 
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
 
BATCH_SIZE = 20
 
async def main():
    await init_db_pool() # Ensure DB pool is initialized for this script's run
    transcriber = MediaTranscriber()
    analyzer = MediaAnalyzerService() # NEW: Initialize MediaAnalyzerService
    try:
        to_process = await episode_queries.fetch_episodes_for_transcription(BATCH_SIZE)
        if not to_process:
            logger.info("No episodes require transcription.")
            return
        
        logger.info(f"Found {len(to_process)} episodes to transcribe and analyze.")

        for ep in to_process:
            episode_id = ep["episode_id"]
            try:
                logger.info(f"Processing episode {episode_id}: '{ep.get('title')}'")
                
                # 1. Transcribe and Summarize
                audio_path = await transcriber.download_audio(ep["episode_url"])
                transcript = await transcriber.transcribe_audio(audio_path, ep.get("title"))
                summary = await transcriber.summarize_transcript(transcript)
                
                # Update episode with transcript and summary
                await episode_queries.update_episode_transcription(
                    episode_id, transcript, summary
                )
                logger.info(f"Episode {episode_id} transcribed and summarized.")

                # 2. Analyze the episode content
                analysis_result = await analyzer.analyze_episode(episode_id)
                if analysis_result["status"] == "success":
                    logger.info(f"Episode {episode_id} analysis successful.")
                else:
                    logger.warning(f"Episode {episode_id} analysis failed: {analysis_result['message']}")

            except Exception as e:
                logger.exception("Error processing episode %s: %s", episode_id, e)
    finally:
        await close_db_pool() # Close DB pool after script finishes
 
if __name__ == "__main__":
    asyncio.run(main())