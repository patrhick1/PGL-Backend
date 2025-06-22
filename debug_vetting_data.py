#!/usr/bin/env python3
"""Debug vetting_checklist data to see what's actually stored"""

import asyncio
import json
from podcast_outreach.database.connection import get_db_pool

async def debug_vetting_data():
    pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        # First, let's see what's actually failing in the API call
        query = """
        SELECT 
            ms.*,
            m.name AS media_name,
            m.website AS media_website,
            c.campaign_name AS campaign_name,
            p.full_name AS client_name
        FROM match_suggestions ms
        JOIN media m ON ms.media_id = m.media_id
        JOIN campaigns c ON ms.campaign_id = c.campaign_id
        LEFT JOIN people p ON c.person_id = p.person_id
        WHERE ms.status = 'approved'
        LIMIT 5
        """
        
        rows = await conn.fetch(query)
        print(f"\nFound {len(rows)} approved match_suggestions:\n")
        
        for row in rows:
            row_dict = dict(row)
            print(f"Match ID: {row_dict['match_id']}")
            print(f"Status: {row_dict['status']}")
            
            # Check vetting_checklist specifically
            vc = row_dict.get('vetting_checklist')
            print(f"vetting_checklist Python Type: {type(vc)}")
            print(f"vetting_checklist value: {vc}")
            
            if vc:
                print(f"Is string?: {isinstance(vc, str)}")
                print(f"Is dict?: {isinstance(vc, dict)}")
                
                # If it's a string, show its content
                if isinstance(vc, str):
                    print(f"String length: {len(vc)}")
                    print(f"First 100 chars: {vc[:100]}")
                    print(f"Last 100 chars: {vc[-100:]}")
                    
                    # Try to parse it
                    try:
                        parsed = json.loads(vc)
                        print(f"Successfully parsed! Type: {type(parsed)}")
                    except Exception as e:
                        print(f"Failed to parse: {e}")
            
            print("-" * 80)

if __name__ == "__main__":
    asyncio.run(debug_vetting_data())