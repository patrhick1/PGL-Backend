# podcast_outreach/scripts/refresh_social_stats.py
import asyncio
import logging
import os
import sys
from typing import List
import uuid

# Add project root to sys.path to allow importing project modules
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    # Add the parent of podcast_outreach, which is the project root
    sys.path.insert(0, os.path.dirname(project_root)) 

from dotenv import load_dotenv
# Load .env from the directory containing the podcast_outreach package
load_dotenv(os.path.join(project_root, '.env'))

from podcast_outreach.database.connection import init_db_pool, close_db_pool
from podcast_outreach.database.queries import media_kits as media_kit_queries
from podcast_outreach.services.media_kits.generator import MediaKitService
from podcast_outreach.logging_config import setup_logging, get_logger

setup_logging() # Initialize logging configuration
logger = get_logger(__name__)

# Configuration for the job
BATCH_SIZE = 5  # Number of media kits to process in one go
DELAY_BETWEEN_BATCHES_SEC = 10  # Delay to avoid overwhelming APIs
PROCESS_LIMIT = 50 # Max number of kits to process in one run to avoid long-running jobs

async def main_refresh_social_stats():
    logger.info("Starting scheduled job: Refresh Social Media Stats for Media Kits.")
    await init_db_pool()
    media_kit_service = MediaKitService()
    updated_count = 0
    failed_count = 0

    try:
        media_kit_ids_to_refresh: List[uuid.UUID] = await media_kit_queries.get_active_public_media_kit_ids(limit=PROCESS_LIMIT)
        
        if not media_kit_ids_to_refresh:
            logger.info("No active/public media kits found needing social stats refresh at this time.")
            return

        logger.info(f"Found {len(media_kit_ids_to_refresh)} media kits to potentially refresh social stats for.")

        for i in range(0, len(media_kit_ids_to_refresh), BATCH_SIZE):
            batch_ids = media_kit_ids_to_refresh[i:i + BATCH_SIZE]
            logger.info(f"Processing batch of {len(batch_ids)} media kits for social stats refresh...")
            
            tasks = []
            for media_kit_id in batch_ids:
                tasks.append(media_kit_service.update_social_stats_for_media_kit(media_kit_id))
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result, media_kit_id in zip(results, batch_ids):
                if isinstance(result, Exception):
                    logger.error(f"Failed to update social stats for media_kit_id {media_kit_id}: {result}", exc_info=False) # exc_info=False as gather might wrap it
                    failed_count += 1
                elif result is None:
                    logger.warning(f"Social stats update for media_kit_id {media_kit_id} returned None (e.g., kit not found or no person). Skipping.")
                    # failed_count +=1 # Or count as skipped
                else:
                    logger.info(f"Successfully updated/checked social stats for media_kit_id {media_kit_id}.")
                    updated_count += 1
            
            if i + BATCH_SIZE < len(media_kit_ids_to_refresh):
                logger.info(f"Waiting for {DELAY_BETWEEN_BATCHES_SEC} seconds before next batch...")
                await asyncio.sleep(DELAY_BETWEEN_BATCHES_SEC)

    except Exception as e:
        logger.exception("An unexpected error occurred during the social stats refresh job.")
    finally:
        await close_db_pool()
        logger.info(f"Finished social stats refresh job. Updated: {updated_count}, Failed/Skipped: {failed_count}.")

if __name__ == "__main__":
    # Ensure the .env file is loaded relative to the script's location if run directly
    # The load_dotenv at the top should handle it if the script is in the correct project structure.
    asyncio.run(main_refresh_social_stats())