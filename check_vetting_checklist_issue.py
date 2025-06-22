#!/usr/bin/env python3
"""Check vetting_checklist field issue in match_suggestions table"""

import asyncio
import json
from podcast_outreach.database.connection import get_db_connection

async def check_vetting_checklist():
    conn = await get_db_connection()
    try:
        # Check the data type and content of vetting_checklist
        query = """
            SELECT 
                match_id,
                vetting_checklist,
                pg_typeof(vetting_checklist) as data_type
            FROM match_suggestions 
            WHERE vetting_checklist IS NOT NULL 
            LIMIT 5
        """
        
        rows = await conn.fetch(query)
        
        print(f"Found {len(rows)} match suggestions with vetting_checklist data")
        print("-" * 80)
        
        for row in rows:
            print(f"Match ID: {row['match_id']}")
            print(f"Data Type: {row['data_type']}")
            print(f"Raw Value: {row['vetting_checklist']}")
            print(f"Value Type in Python: {type(row['vetting_checklist'])}")
            
            # Try to parse if it's a string
            if isinstance(row['vetting_checklist'], str):
                try:
                    parsed = json.loads(row['vetting_checklist'])
                    print(f"Parsed JSON: {parsed}")
                    print(f"Parsed Type: {type(parsed)}")
                except json.JSONDecodeError as e:
                    print(f"Failed to parse JSON: {e}")
            
            print("-" * 80)
            
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_vetting_checklist())