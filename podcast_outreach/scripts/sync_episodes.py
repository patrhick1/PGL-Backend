import asyncio
import logging

from podcast_outreach.services.media.episode_sync import MediaFetcher
import db_service_pg

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SYNC_INTERVAL_HOURS = 24

async def main():
    await db_service_pg.init_db_pool()
    fetcher = MediaFetcher()
    try:
        media_to_sync = await db_service_pg.get_media_to_sync_episodes(interval_hours=SYNC_INTERVAL_HOURS)
        if not media_to_sync:
            logger.info("No media records require episode sync.")
            return
        for media in media_to_sync:
            try:
                await fetcher.sync_episodes_for_media(media["media_id"])
            except Exception as e:
                logger.exception("Error syncing episodes for media %s: %s", media.get("name"), e)
    finally:
        await db_service_pg.close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())
