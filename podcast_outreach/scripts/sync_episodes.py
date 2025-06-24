# podcast_outreach/scripts/sync_episodes.py

import asyncio
import logging
 
from podcast_outreach.services.media.episode_sync import MediaFetcher, main_episode_sync_orchestrator # Import main orchestrator
from podcast_outreach.database.queries import media as media_queries # Use modular query
from podcast_outreach.database.connection import init_db_pool, close_db_pool # Use modular connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
 
SYNC_INTERVAL_HOURS = 24
 
async def main():
    # The main_episode_sync_orchestrator already handles DB pool init/close.
    # So, this script just needs to call that.
    await main_episode_sync_orchestrator()
 
if __name__ == "__main__":
    asyncio.run(main())
