#!/usr/bin/env python3
"""
Script to send approved pitches to Instantly.ai
Processes pitches that are in 'ready_to_send' state and sends them via Instantly API.
"""

import asyncio
import logging
import sys
from typing import Optional
from datetime import datetime

from podcast_outreach.services.pitches.sender import PitchSenderService
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.database.queries import pitch_generations as pitch_gen_queries
from podcast_outreach.logging_config import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


async def send_ready_pitches(stop_flag: Optional[asyncio.Event] = None, limit: int = 50):
    """
    Send all pitches that are approved and ready to send to Instantly.
    
    Args:
        stop_flag: Optional event flag to stop processing
        limit: Maximum number of pitches to process in one run
    """
    logger.info("Starting pitch sending automation to Instantly.ai")
    
    # Initialize the pitch sender service
    sender_service = PitchSenderService()
    
    # Test Instantly connection first
    logger.info("Testing Instantly API connection...")
    if not sender_service.instantly_client.test_connection():
        logger.critical("Failed to connect to Instantly API. Please check API key.")
        sys.exit(1)
    
    logger.info("Instantly API connection successful. Proceeding...")
    
    try:
        # Fetch pitches that are ready to send
        logger.info("Fetching pitches ready to send...")
        ready_pitches = await pitch_queries.get_pitches_by_state('ready_to_send', limit=limit)
        
        if not ready_pitches:
            logger.info("No pitches found in 'ready_to_send' state.")
            return
        
        logger.info(f"Found {len(ready_pitches)} pitches ready to send")
        
        success_count = 0
        error_count = 0
        
        for pitch in ready_pitches:
            # Check stop flag
            if stop_flag and stop_flag.is_set():
                logger.info("Stop flag set, halting pitch sending.")
                break
            
            pitch_id = pitch['pitch_id']
            pitch_gen_id = pitch.get('pitch_gen_id')
            
            if not pitch_gen_id:
                logger.warning(f"Pitch {pitch_id} has no associated pitch_gen_id. Skipping.")
                error_count += 1
                continue
            
            logger.info(f"Processing pitch {pitch_id} (pitch_gen_id: {pitch_gen_id})...")
            
            try:
                # Send the pitch via the sender service
                result = await sender_service.send_pitch_to_instantly(pitch_gen_id)
                
                if result['success']:
                    success_count += 1
                    logger.info(f"Successfully sent pitch {pitch_id}: {result['message']}")
                else:
                    error_count += 1
                    logger.error(f"Failed to send pitch {pitch_id}: {result['message']}")
                    
                    # Update pitch state to indicate send failure
                    await pitch_queries.update_pitch_in_db(
                        pitch_id,
                        {"pitch_state": "send_failed", "notes": result['message']}
                    )
                
                # Small delay between sends to avoid rate limiting
                await asyncio.sleep(1)
                
            except Exception as e:
                error_count += 1
                logger.exception(f"Error processing pitch {pitch_id}: {e}")
                
                # Update pitch state to indicate error
                await pitch_queries.update_pitch_in_db(
                    pitch_id,
                    {"pitch_state": "send_error", "notes": str(e)}
                )
        
        logger.info(f"Pitch sending completed. Success: {success_count}, Errors: {error_count}")
        
    except Exception as e:
        logger.exception(f"Fatal error in send_ready_pitches: {e}")
        raise


async def send_specific_pitch(pitch_id: int):
    """
    Send a specific pitch by its ID.
    
    Args:
        pitch_id: The ID of the pitch to send
    """
    logger.info(f"Attempting to send specific pitch {pitch_id}")
    
    sender_service = PitchSenderService()
    
    # Test Instantly connection
    if not sender_service.instantly_client.test_connection():
        logger.error("Failed to connect to Instantly API")
        return False
    
    try:
        # Get the pitch
        pitch = await pitch_queries.get_pitch_by_id(pitch_id)
        if not pitch:
            logger.error(f"Pitch {pitch_id} not found")
            return False
        
        pitch_gen_id = pitch.get('pitch_gen_id')
        if not pitch_gen_id:
            logger.error(f"Pitch {pitch_id} has no associated pitch_gen_id")
            return False
        
        # Send the pitch
        result = await sender_service.send_pitch_to_instantly(pitch_gen_id)
        
        if result['success']:
            logger.info(f"Successfully sent pitch {pitch_id}: {result['message']}")
            return True
        else:
            logger.error(f"Failed to send pitch {pitch_id}: {result['message']}")
            return False
            
    except Exception as e:
        logger.exception(f"Error sending pitch {pitch_id}: {e}")
        return False


async def main():
    """Main function for command line execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Send approved pitches to Instantly.ai")
    parser.add_argument(
        "--pitch-id",
        type=int,
        help="Send a specific pitch by ID"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of pitches to process (default: 50)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be sent without actually sending"
    )
    
    args = parser.parse_args()
    
    if args.dry_run:
        logger.info("DRY RUN MODE - No pitches will actually be sent")
        # TODO: Implement dry run logic
        logger.warning("Dry run not yet implemented")
        return
    
    if args.pitch_id:
        # Send specific pitch
        success = await send_specific_pitch(args.pitch_id)
        sys.exit(0 if success else 1)
    else:
        # Send all ready pitches
        await send_ready_pitches(limit=args.limit)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("Script execution started")
    try:
        asyncio.run(main())
        logger.info("Script execution completed successfully")
    except KeyboardInterrupt:
        logger.info("Script interrupted by user")
    except Exception as e:
        logger.exception(f"Script failed with error: {e}")
        sys.exit(1)