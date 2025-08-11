#!/usr/bin/env python3
"""
Scheduled task to send match notification emails
Run this periodically (e.g., every hour or twice daily) via cron or scheduler
"""

import asyncio
import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podcast_outreach.services.match_notification_service import MatchNotificationService
from podcast_outreach.database.connection import get_db_pool

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Main task runner"""
    logger.info("Starting match notification task...")
    
    try:
        # Initialize the notification service
        notification_service = MatchNotificationService()
        
        # Check and send notifications
        await notification_service.check_and_send_match_notifications()
        
        logger.info("Match notification task completed successfully")
        
    except Exception as e:
        logger.error(f"Error in match notification task: {e}", exc_info=True)
        return 1
    
    finally:
        # Clean up database connection pool
        pool = await get_db_pool()
        if pool:
            await pool.close()
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)