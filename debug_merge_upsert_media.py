#!/usr/bin/env python3
"""
Debug script to test the merge_and_upsert_media function and identify the failure cause.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from podcast_outreach.services.media.podcast_fetcher import MediaFetcher
from podcast_outreach.database.connection import get_db_pool, close_db_pool

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_merge_and_upsert_media():
    """Test the merge_and_upsert_media function with sample data."""
    
    # Initialize database pool
    await get_db_pool()
    
    # Create MediaFetcher instance
    media_fetcher = MediaFetcher()
    
    # Sample podcast data (minimal required fields)
    sample_podcast_data = {
        'name': 'Test Podcast Debug',
        'api_id': f'test_debug_{datetime.now().timestamp()}',
        'source_api': 'ListenNotes',
        'rss_url': 'https://feeds.example.com/test-podcast-debug',
        'website': 'https://example.com/test-podcast',
        'contact_email': 'test@example.com',
        'description': 'A test podcast for debugging merge_and_upsert_media function',
        'language': 'English',
        'total_episodes': 50,
        'last_posted_at': datetime.now(timezone.utc),
        'image_url': 'https://example.com/image.jpg'
    }
    
    # Test campaign UUID
    test_campaign_uuid = uuid.uuid4()
    test_keyword = 'debug_test'
    
    try:
        logger.info("Testing merge_and_upsert_media function...")
        logger.info(f"Sample data: {sample_podcast_data}")
        
        # Call the function
        result = await media_fetcher.merge_and_upsert_media(
            sample_podcast_data, 
            'ListenNotes', 
            test_campaign_uuid, 
            test_keyword
        )
        
        if result:
            logger.info(f"SUCCESS: merge_and_upsert_media returned media_id: {result}")
        else:
            logger.error("FAILURE: merge_and_upsert_media returned None")
            
    except Exception as e:
        logger.error(f"EXCEPTION in merge_and_upsert_media: {e}", exc_info=True)
    
    finally:
        # Cleanup
        media_fetcher.cleanup()
        await close_db_pool()

async def test_database_connection():
    """Test basic database connectivity."""
    try:
        logger.info("Testing database connection...")
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            # Test simple query
            result = await conn.fetchval("SELECT 1 as test")
            logger.info(f"Database connection test: {result}")
            
            # Test media table access
            media_count = await conn.fetchval("SELECT COUNT(*) FROM media")
            logger.info(f"Current media table count: {media_count}")
            
    except Exception as e:
        logger.error(f"Database connection test failed: {e}", exc_info=True)
    
    finally:
        await close_db_pool()

async def test_media_upsert_query():
    """Test the upsert query directly."""
    try:
        logger.info("Testing media upsert query directly...")
        pool = await get_db_pool()
        
        # Test data
        test_data = {
            'api_id': f'direct_test_{datetime.now().timestamp()}',
            'source_api': 'DirectTest',
            'name': 'Direct Test Podcast',
            'rss_url': 'https://feeds.example.com/direct-test',
            'website': 'https://example.com/direct-test',
            'contact_email': 'direct@example.com',
            'description': 'Direct upsert test',
            'language': 'English'
        }
        
        async with pool.acquire() as conn:
            # Try a simple INSERT to test the basic structure
            query = """
            INSERT INTO media (api_id, source_api, name, rss_url, website, contact_email, description, language)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (api_id) DO UPDATE SET
                name = EXCLUDED.name,
                updated_at = NOW()
            RETURNING media_id, name;
            """
            
            result = await conn.fetchrow(
                query,
                test_data['api_id'],
                test_data['source_api'],
                test_data['name'],
                test_data['rss_url'],
                test_data['website'],
                test_data['contact_email'],
                test_data['description'],
                test_data['language']
            )
            
            if result:
                logger.info(f"Direct upsert SUCCESS: media_id={result['media_id']}, name={result['name']}")
            else:
                logger.error("Direct upsert returned no result")
                
    except Exception as e:
        logger.error(f"Direct upsert test failed: {e}", exc_info=True)
    
    finally:
        await close_db_pool()

async def main():
    """Run all debug tests."""
    logger.info("Starting merge_and_upsert_media debug tests...")
    
    # Test 1: Database connection
    await test_database_connection()
    
    # Test 2: Direct upsert query
    await test_media_upsert_query()
    
    # Test 3: Full merge_and_upsert_media function
    await test_merge_and_upsert_media()
    
    logger.info("Debug tests completed.")

if __name__ == "__main__":
    asyncio.run(main())