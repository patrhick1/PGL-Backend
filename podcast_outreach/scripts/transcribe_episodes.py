# podcast_outreach/scripts/transcribe_episodes.py

import asyncio
import logging
 
from podcast_outreach.services.media.transcriber import MediaTranscriber
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.connection import init_db_pool, close_db_pool # Use modular connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
 
BATCH_SIZE = 20
 
async def main():
    await init_db_pool() # Ensure DB pool is initialized for this script's run
    transcriber = MediaTranscriber()
    try:
        to_process = await episode_queries.fetch_episodes_for_transcription(BATCH_SIZE)
        if not to_process:
            logger.info("No episodes require transcription.")
            return
        for ep in to_process:
            try:
                # Assuming MediaTranscriber.download_audio and .transcribe_audio are async
                audio_path = await transcriber.download_audio(ep["episode_url"])
                transcript = await transcriber.transcribe_audio(audio_path, ep.get("title"))
                summary = await transcriber.summarize_transcript(transcript)
                await episode_queries.update_episode_transcription(
                    ep["episode_id"], transcript, summary
                )
            except Exception as e:
                logger.exception("Error processing episode %s: %s", ep["episode_id"], e)
    finally:
        await close_db_pool() # Close DB pool after script finishes
 
if __name__ == "__main__":
    asyncio.run(main())
