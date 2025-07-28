# podcast_outreach/services/business_logic/media_processing.py

import logging
from podcast_outreach.services.database_service import DatabaseService
from podcast_outreach.services.media.episode_sync import main_episode_sync_orchestrator

logger = logging.getLogger(__name__)

async def sync_episodes(db_service: DatabaseService) -> bool:
    """
    Pure business logic function for episode synchronization.
    Assumes database resources are available via db_service.
    """
    # Temporarily set the global pool for this event loop
    from podcast_outreach.database import connection
    original_pool = connection.DB_POOL
    connection.DB_POOL = db_service.pool
    
    try:
        logger.info("Running episode sync")
        await main_episode_sync_orchestrator()
        logger.info("Episode sync completed")
        return True
    except Exception as e:
        logger.error(f"Error during episode sync: {e}", exc_info=True)
        return False
    finally:
        # Restore original pool
        connection.DB_POOL = original_pool

async def transcribe_episodes(db_service: DatabaseService) -> bool:
    """
    Pure business logic function for episode transcription.
    Assumes database resources are available via db_service.
    """
    try:
        logger.info("Running episode transcription")
        # Import here to avoid circular imports
        from podcast_outreach.scripts.transcribe_episodes import run_transcription_logic
        await run_transcription_logic(db_service)
        logger.info("Episode transcription completed")
        return True
    except Exception as e:
        logger.error(f"Error during episode transcription: {e}", exc_info=True)
        return False