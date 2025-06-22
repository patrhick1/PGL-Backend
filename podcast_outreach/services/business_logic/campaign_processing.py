# podcast_outreach/services/business_logic/campaign_processing.py

import uuid
import logging
from typing import Optional, Dict, Any
from podcast_outreach.services.database_service import DatabaseService
from podcast_outreach.services.campaigns.content_processor import ClientContentProcessor
from podcast_outreach.services.campaigns.angles_generator import AnglesProcessorPG
from podcast_outreach.database.queries import campaigns as campaign_queries

logger = logging.getLogger(__name__)

async def process_campaign_content(
    campaign_id: uuid.UUID, 
    db_service: DatabaseService,
    max_retries: int = 3, 
    retry_delay: float = 60.0
) -> bool:
    """
    Pure business logic function for processing campaign content.
    Assumes database resources are available via db_service.
    """
    processor = ClientContentProcessor()
    
    try:
        logger.info(f"Processing content for campaign {campaign_id}")
        
        # Update campaign status
        try:
            await campaign_queries.update_campaign_status(
                campaign_id, 
                "processing_content", 
                "Content processing started"
            )
        except Exception as status_error:
            logger.warning(f"Could not update campaign status for {campaign_id}: {status_error}")
        
        # Process campaign data
        success = await processor.process_and_embed_campaign_data(campaign_id)
        
        if success:
            logger.info(f"Content processing for {campaign_id} completed successfully")
            try:
                await campaign_queries.update_campaign_status(
                    campaign_id, 
                    "content_processed", 
                    "Content processing completed successfully with media kit generation"
                )
            except Exception as status_error:
                logger.warning(f"Could not update final campaign status for {campaign_id}: {status_error}")
            return True
        else:
            error_msg = f"Content processing for {campaign_id} did not complete successfully"
            logger.warning(error_msg)
            return False
            
    except Exception as e:
        logger.error(f"Error processing content for {campaign_id}: {e}", exc_info=True)
        try:
            await campaign_queries.update_campaign_status(
                campaign_id, 
                "processing_error", 
                f"Error: {str(e)[:200]}..."
            )
        except Exception as status_error:
            logger.warning(f"Could not update error campaign status for {campaign_id}: {status_error}")
        return False

async def generate_angles_and_bio(
    campaign_id_str: str,
    db_service: DatabaseService
) -> bool:
    """
    Pure business logic function for generating angles and bio.
    Assumes database resources are available via db_service.
    """
    processor = AnglesProcessorPG()
    
    try:
        logger.info(f"Generating angles/bio for campaign {campaign_id_str}")
        await processor.process_campaign(campaign_id_str)
        logger.info(f"Angles/bio generation for {campaign_id_str} completed")
        return True
    except Exception as e:
        logger.error(f"Error generating angles/bio for {campaign_id_str}: {e}", exc_info=True)
        return False
    finally:
        processor.cleanup()