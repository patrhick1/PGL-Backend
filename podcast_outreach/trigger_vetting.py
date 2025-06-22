#!/usr/bin/env python3
"""
Trigger vetting pipeline manually for discovery 21
"""

import asyncio
import logging
from podcast_outreach.database.connection import init_db_pool, close_db_pool
from podcast_outreach.services.matches.enhanced_vetting_orchestrator import EnhancedVettingOrchestrator

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


async def trigger_vetting():
    """Trigger vetting pipeline"""
    try:
        logger.info("Triggering vetting pipeline...")
        orchestrator = EnhancedVettingOrchestrator()
        await orchestrator.run_vetting_pipeline(batch_size=10)
        logger.info("Vetting pipeline completed")
    except Exception as e:
        logger.error(f"Error running vetting pipeline: {e}", exc_info=True)


async def main():
    """Main function"""
    await init_db_pool()
    
    try:
        await trigger_vetting()
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        await close_db_pool()


if __name__ == "__main__":
    asyncio.run(main())