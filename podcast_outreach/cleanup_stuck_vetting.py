#!/usr/bin/env python3
"""Clean up stuck vetting records and verify the cleanup mechanism works."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_stuck_records():
    """Check for stuck vetting records."""
    pool = await get_db_pool()
    
    query = """
    SELECT 
        id,
        media_id,
        vetting_status,
        vetting_error,
        updated_at,
        CASE 
            WHEN vetting_error LIKE 'PROCESSING:%' THEN 
                SUBSTRING(vetting_error FROM 'PROCESSING:VETTING:([^:]+)')
            ELSE NULL 
        END as lock_id,
        NOW() - updated_at as time_stuck
    FROM campaign_media_discoveries
    WHERE campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    AND vetting_status = 'in_progress'
    ORDER BY updated_at ASC
    """
    
    async with pool.acquire() as conn:
        stuck_records = await conn.fetch(query)
    
    logger.info(f"Found {len(stuck_records)} stuck records\n")
    
    if stuck_records:
        logger.info(f"{'ID':<10} {'Media':<10} {'Lock ID':<15} {'Time Stuck':<20} {'Last Updated'}")
        logger.info("-" * 80)
        
        for record in stuck_records[:10]:  # Show first 10
            time_stuck = str(record['time_stuck']).split('.')[0] if record['time_stuck'] else 'Unknown'
            last_updated = record['updated_at'].strftime('%Y-%m-%d %H:%M') if record['updated_at'] else 'Unknown'
            lock_id = record['lock_id'] or 'No lock'
            
            logger.info(f"{record['id']:<10} {record['media_id']:<10} {lock_id:<15} {time_stuck:<20} {last_updated}")
        
        if len(stuck_records) > 10:
            logger.info(f"... and {len(stuck_records) - 10} more")
    
    return stuck_records

async def reset_stuck_records(dry_run=True):
    """Reset stuck records to pending status."""
    pool = await get_db_pool()
    
    # Find records stuck for more than 30 minutes
    query = """
    UPDATE campaign_media_discoveries
    SET vetting_status = 'pending',
        vetting_error = NULL,
        updated_at = NOW()
    WHERE campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
    AND vetting_status = 'in_progress'
    AND updated_at < NOW() - INTERVAL '30 minutes'
    RETURNING id, media_id
    """
    
    if dry_run:
        # Just count them
        count_query = """
        SELECT COUNT(*) as count
        FROM campaign_media_discoveries
        WHERE campaign_id = 'cdc33aee-b0f8-4460-beec-cce66ea3772c'
        AND vetting_status = 'in_progress'
        AND updated_at < NOW() - INTERVAL '30 minutes'
        """
        async with pool.acquire() as conn:
            result = await conn.fetchrow(count_query)
            logger.info(f"\nDRY RUN: Would reset {result['count']} stuck records")
    else:
        async with pool.acquire() as conn:
            reset_records = await conn.fetch(query)
            logger.info(f"\n✅ Reset {len(reset_records)} stuck records to 'pending' status")
            return reset_records

async def test_cleanup_mechanism():
    """Test that the cleanup mechanism is working."""
    logger.info("\n=== Testing Cleanup Mechanism ===\n")
    
    # Call the cleanup function
    cleaned = await cmd_queries.cleanup_stale_vetting_locks(stale_minutes=30)
    logger.info(f"Cleanup function removed {cleaned} stale locks")
    
    # Check if any records still have old processing locks
    pool = await get_db_pool()
    query = """
    SELECT COUNT(*) as count
    FROM campaign_media_discoveries
    WHERE vetting_error LIKE 'PROCESSING:VETTING:%'
    AND updated_at < NOW() - INTERVAL '30 minutes'
    """
    
    async with pool.acquire() as conn:
        result = await conn.fetchrow(query)
        
    if result['count'] > 0:
        logger.warning(f"⚠️ Still {result['count']} records with old processing locks")
    else:
        logger.info("✅ No stale processing locks found")

async def verify_atomic_acquisition():
    """Verify that atomic acquisition is preventing duplicates."""
    logger.info("\n=== Verifying Atomic Acquisition ===\n")
    
    # Try to acquire work twice quickly
    batch1 = await cmd_queries.acquire_vetting_work_batch(limit=5)
    batch2 = await cmd_queries.acquire_vetting_work_batch(limit=5)
    
    # Check for duplicates
    ids1 = {r['id'] for r in batch1}
    ids2 = {r['id'] for r in batch2}
    
    overlap = ids1 & ids2
    
    if overlap:
        logger.error(f"❌ Found {len(overlap)} duplicate acquisitions: {overlap}")
    else:
        logger.info(f"✅ No duplicates! Batch 1: {len(batch1)} records, Batch 2: {len(batch2)} records")
    
    # Clean up - reset these to pending
    if batch1 or batch2:
        all_ids = list(ids1 | ids2)
        pool = await get_db_pool()
        query = """
        UPDATE campaign_media_discoveries
        SET vetting_status = 'pending',
            vetting_error = NULL
        WHERE id = ANY($1)
        """
        async with pool.acquire() as conn:
            await conn.execute(query, all_ids)
        logger.info(f"Cleaned up {len(all_ids)} test records")

async def main():
    """Main function."""
    logger.info("=== Vetting Stuck Records Cleanup ===\n")
    
    # 1. Check current stuck records
    stuck_records = await check_stuck_records()
    
    # 2. Test cleanup mechanism
    await test_cleanup_mechanism()
    
    # 3. Verify atomic acquisition
    await verify_atomic_acquisition()
    
    # 4. Ask to reset stuck records
    if stuck_records:
        logger.info("\n" + "="*50)
        logger.info("To reset all stuck records to 'pending', run:")
        logger.info("python -m podcast_outreach.cleanup_stuck_vetting --reset")
        
        import sys
        if len(sys.argv) > 1 and sys.argv[1] == '--reset':
            await reset_stuck_records(dry_run=False)
        else:
            await reset_stuck_records(dry_run=True)
    
    logger.info("\n=== Cleanup Complete ===")

if __name__ == "__main__":
    import sys
    asyncio.run(main())