import asyncio
import logging

from podcast_outreach.services.media.transcriber import MediaTranscriber
from podcast_outreach.database.queries import episodes as episode_queries
import db_service_pg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 20

async def main():
    await db_service_pg.init_db_pool()
    transcriber = MediaTranscriber()
    try:
        to_process = await episode_queries.fetch_episodes_for_transcription(BATCH_SIZE)
        if not to_process:
            logger.info("No episodes require transcription.")
            return
        for ep in to_process:
            try:
                audio_path = await transcriber.download_audio(ep["episode_url"])
                transcript = await transcriber.transcribe_audio(audio_path, ep.get("title"))
                summary = await transcriber.summarize_transcript(transcript)
                await episode_queries.update_episode_transcription(
                    ep["episode_id"], transcript, summary
                )
            except Exception as e:
                logger.exception("Error processing episode %s: %s", ep["episode_id"], e)
    finally:
        await db_service_pg.close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())
