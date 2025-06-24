"""
Test script for enrichment enhancements

This script tests:
1. Host name confidence verification
2. Batch transcription
3. Failed URL handling
"""

import asyncio
import logging
from datetime import datetime, timezone
from podcast_outreach.database.connection import init_db_pool, close_db_pool
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.services.enrichment.host_confidence_verifier import HostConfidenceVerifier
from podcast_outreach.services.media.batch_transcriber import BatchTranscriptionService
from podcast_outreach.logging_config import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

async def test_host_verification():
    """Test host name confidence verification"""
    print("\n" + "="*60)
    print("Testing Host Name Confidence Verification")
    print("="*60)
    
    try:
        verifier = HostConfidenceVerifier()
        
        # Get a sample media with host names
        sample_media = await media_queries.get_media_for_enrichment(limit=1, only_new=False)
        
        if not sample_media:
            print("No media found for testing")
            return
        
        media_id = sample_media[0]['media_id']
        media_name = sample_media[0].get('name', 'Unknown')
        
        print(f"\nTesting with media: {media_name} (ID: {media_id})")
        
        # Run verification
        result = await verifier.verify_host_names(media_id)
        
        if result:
            print(f"\nVerification Results:")
            print(f"- Total hosts found: {result['total_hosts_found']}")
            print(f"- Discovery sources: {', '.join(result['discovery_sources'])}")
            
            print(f"\nVerified Hosts:")
            for host in result['verified_hosts']:
                print(f"  - {host['name']}: confidence={host['confidence']}, sources={host['sources']}")
            
            if result['low_confidence_hosts']:
                print(f"\nLow Confidence Hosts (need review):")
                for host in result['low_confidence_hosts']:
                    print(f"  - {host['name']}: confidence={host['confidence']}")
        else:
            print("Verification failed or returned no results")
            
    except Exception as e:
        print(f"Error in host verification test: {e}")
        logger.error(f"Host verification test error: {e}", exc_info=True)

async def test_batch_transcription():
    """Test batch transcription with failed URL handling"""
    print("\n" + "="*60)
    print("Testing Batch Transcription")
    print("="*60)
    
    try:
        batch_service = BatchTranscriptionService()
        
        # Get episodes without transcripts
        episodes = await episode_queries.get_episodes_for_transcription(limit=5)
        
        if not episodes:
            print("No episodes found that need transcription")
            return
        
        episode_ids = [ep['episode_id'] for ep in episodes[:3]]  # Test with up to 3 episodes
        
        print(f"\nCreating batch for {len(episode_ids)} episodes")
        
        # Create batch
        batch_info = await batch_service.create_transcription_batch(episode_ids)
        
        print(f"\nBatch created:")
        print(f"- Batch ID: {batch_info['batch_id']}")
        print(f"- Total batches: {batch_info.get('total_batches', 0)}")
        print(f"- Total episodes: {batch_info.get('total_episodes', 0)}")
        print(f"- Estimated duration: {batch_info.get('estimated_duration_minutes', 0):.1f} minutes")
        
        # Note: Not actually processing the batch to avoid costs
        print("\nNote: Batch created but not processed (to avoid transcription costs)")
        print("To process, call: await batch_service.process_batch(batch_info['batch_id'])")
        
    except Exception as e:
        print(f"Error in batch transcription test: {e}")
        logger.error(f"Batch transcription test error: {e}", exc_info=True)

async def test_failed_url_tracking():
    """Test failed URL tracking"""
    print("\n" + "="*60)
    print("Testing Failed URL Tracking")
    print("="*60)
    
    try:
        # Check for episodes with failed URLs
        from podcast_outreach.database.connection import get_db_pool
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            # Get episodes with various URL statuses
            failed_episodes = await conn.fetch("""
                SELECT 
                    episode_id,
                    title,
                    audio_url_status,
                    audio_url_failure_count,
                    audio_url_last_error,
                    audio_url_last_checked
                FROM episodes
                WHERE audio_url_status != 'available'
                ORDER BY audio_url_last_checked DESC NULLS LAST
                LIMIT 10
            """)
            
            if failed_episodes:
                print(f"\nFound {len(failed_episodes)} episodes with non-available URLs:")
                for ep in failed_episodes:
                    print(f"\n- Episode: {ep['title'][:50]}...")
                    print(f"  Status: {ep['audio_url_status']}")
                    print(f"  Failures: {ep['audio_url_failure_count'] or 0}")
                    if ep['audio_url_last_error']:
                        print(f"  Last error: {ep['audio_url_last_error'][:100]}...")
                    if ep['audio_url_last_checked']:
                        print(f"  Last checked: {ep['audio_url_last_checked']}")
            else:
                print("\nNo episodes with failed URLs found (this is good!)")
                
            # Check URL status distribution
            status_counts = await conn.fetch("""
                SELECT 
                    audio_url_status,
                    COUNT(*) as count
                FROM episodes
                WHERE direct_audio_url IS NOT NULL
                GROUP BY audio_url_status
                ORDER BY count DESC
            """)
            
            print(f"\nURL Status Distribution:")
            for row in status_counts:
                status = row['audio_url_status'] or 'null'
                count = row['count']
                print(f"  - {status}: {count} episodes")
                
    except Exception as e:
        print(f"Error in failed URL tracking test: {e}")
        logger.error(f"Failed URL tracking test error: {e}", exc_info=True)

async def test_enrichment_integration():
    """Test the full enhanced discovery workflow"""
    print("\n" + "="*60)
    print("Testing Enhanced Discovery Workflow Integration")
    print("="*60)
    
    try:
        from podcast_outreach.services.business_logic.enhanced_discovery_workflow import EnhancedDiscoveryWorkflow
        
        workflow = EnhancedDiscoveryWorkflow()
        
        # Get a recent discovery
        from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
        
        recent_discoveries = await cmd_queries.get_discoveries_needing_enrichment(limit=1)
        
        if recent_discoveries:
            discovery = recent_discoveries[0]
            print(f"\nProcessing discovery:")
            print(f"- Campaign ID: {discovery['campaign_id']}")
            print(f"- Media ID: {discovery['media_id']}")
            print(f"- Keyword: {discovery['discovery_keyword']}")
            
            # Note: Not actually processing to avoid costs
            print("\nNote: Discovery found but not processed (to avoid costs)")
            print("The enhanced workflow would:")
            print("1. Run enrichment with social data collection")
            print("2. Batch transcribe episodes")
            print("3. Verify host names with confidence scoring")
            print("4. Handle failed URLs with exponential backoff")
            print("5. Run vetting and create matches")
        else:
            print("\nNo discoveries pending enrichment")
            
    except Exception as e:
        print(f"Error in integration test: {e}")
        logger.error(f"Integration test error: {e}", exc_info=True)

async def main():
    """Run all tests"""
    print("\nEnrichment Enhancements Test Suite")
    print("=" * 60)
    
    # Initialize database
    await init_db_pool()
    
    try:
        # Run tests
        await test_host_verification()
        await test_batch_transcription()
        await test_failed_url_tracking()
        await test_enrichment_integration()
        
        print("\n" + "="*60)
        print("All tests completed!")
        print("="*60)
        
    except Exception as e:
        print(f"\nTest suite error: {e}")
        logger.error(f"Test suite error: {e}", exc_info=True)
    finally:
        await close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())