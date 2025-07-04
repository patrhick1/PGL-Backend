#!/usr/bin/env python3
"""Apply migration for discovery reliability fields"""

import asyncio
import sys
sys.path.insert(0, '.')

from podcast_outreach.database.connection import init_db_pool, close_db_pool, get_db_pool

async def apply_migration():
    await init_db_pool()
    pool = await get_db_pool()
    
    print("Applying discovery reliability migration...")
    
    try:
        # Read migration file
        with open('migrations/add_discovery_reliability_fields.sql', 'r') as f:
            migration_sql = f.read()
        
        # Execute migration
        async with pool.acquire() as conn:
            await conn.execute(migration_sql)
            
        print("Migration applied successfully")
        
        # Check current campaigns
        check_query = """
        SELECT 
            campaign_id,
            campaign_name,
            auto_discovery_status,
            auto_discovery_last_heartbeat,
            auto_discovery_progress,
            auto_discovery_error
        FROM campaigns
        WHERE auto_discovery_enabled = TRUE
        LIMIT 5
        """
        
        async with pool.acquire() as conn:
            campaigns = await conn.fetch(check_query)
            
        print(f"\nChecked {len(campaigns)} campaigns with new fields:")
        for c in campaigns:
            print(f"  - {c['campaign_name']}: status={c['auto_discovery_status']}, "
                  f"heartbeat={c['auto_discovery_last_heartbeat']}, "
                  f"progress={c['auto_discovery_progress']}")
                  
    except Exception as e:
        print(f"Error applying migration: {e}")
        import traceback
        traceback.print_exc()
    
    await close_db_pool()

if __name__ == "__main__":
    asyncio.run(apply_migration())