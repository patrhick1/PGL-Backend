#!/usr/bin/env python3
"""
Verify pitch_generations and pitches table schema and field population
"""

import asyncio
import logging
from datetime import datetime
import uuid
from typing import Dict, Any, List

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

async def verify_schema():
    """Verify the schema matches what our queries expect"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Check pitch_generations columns
        pitch_gen_columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'pitch_generations'
            ORDER BY ordinal_position;
        """)
        
        # Check pitches columns
        pitches_columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'pitches'
            ORDER BY ordinal_position;
        """)
        
        print("\n=== PITCH_GENERATIONS TABLE SCHEMA ===")
        for col in pitch_gen_columns:
            print(f"{col['column_name']:25} {col['data_type']:20} {'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL':10} {col['column_default'] or ''}")
        
        print("\n=== PITCHES TABLE SCHEMA ===")
        for col in pitches_columns:
            print(f"{col['column_name']:25} {col['data_type']:20} {'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL':10} {col['column_default'] or ''}")

async def check_sample_data():
    """Check sample data from both tables to see field population"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Get recent pitch generations
        recent_pitch_gens = await conn.fetch("""
            SELECT * FROM pitch_generations
            ORDER BY generated_at DESC
            LIMIT 5;
        """)
        
        # Get recent pitches
        recent_pitches = await conn.fetch("""
            SELECT * FROM pitches
            ORDER BY created_at DESC
            LIMIT 5;
        """)
        
        print("\n=== RECENT PITCH_GENERATIONS RECORDS ===")
        if recent_pitch_gens:
            for i, pg in enumerate(recent_pitch_gens):
                print(f"\n--- Record {i+1} ---")
                for key, value in dict(pg).items():
                    if key == 'draft_text':
                        print(f"{key}: {str(value)[:100]}..." if value else f"{key}: None")
                    else:
                        print(f"{key}: {value}")
        else:
            print("No pitch_generations records found")
        
        print("\n=== RECENT PITCHES RECORDS ===")
        if recent_pitches:
            for i, p in enumerate(recent_pitches):
                print(f"\n--- Record {i+1} ---")
                for key, value in dict(p).items():
                    if key == 'body_snippet':
                        print(f"{key}: {str(value)[:100]}..." if value else f"{key}: None")
                    else:
                        print(f"{key}: {value}")
        else:
            print("No pitches records found")

async def verify_field_mapping():
    """Verify the fields we're trying to insert match the schema"""
    # Expected fields from generator.py
    pitch_gen_expected = {
        "campaign_id": "uuid",
        "media_id": "integer", 
        "template_id": "text",
        "draft_text": "text",
        "ai_model_used": "text",
        "pitch_topic": "text",
        "temperature": "numeric",
        "generation_status": "varchar",
        "send_ready_bool": "boolean"
    }
    
    pitch_expected = {
        "campaign_id": "uuid",
        "media_id": "integer",
        "attempt_no": "integer",
        "match_score": "numeric",
        "matched_keywords": "text[]",
        "score_evaluated_at": "timestamptz",
        "outreach_type": "varchar",
        "subject_line": "text",
        "body_snippet": "text",
        "pitch_gen_id": "integer",
        "pitch_state": "varchar",
        "client_approval_status": "varchar",
        "created_by": "text"
    }
    
    print("\n=== FIELD MAPPING VERIFICATION ===")
    print("\nPitch Generation Fields Expected:")
    for field, expected_type in pitch_gen_expected.items():
        print(f"  {field}: {expected_type}")
    
    print("\nPitch Fields Expected:")
    for field, expected_type in pitch_expected.items():
        print(f"  {field}: {expected_type}")

async def check_timestamps():
    """Check if timestamp fields are being populated correctly"""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # Check pitch_generations timestamps
        pg_timestamps = await conn.fetch("""
            SELECT 
                COUNT(*) as total,
                COUNT(generated_at) as has_generated_at,
                COUNT(reviewed_at) as has_reviewed_at
            FROM pitch_generations;
        """)
        
        # Check pitches timestamps  
        p_timestamps = await conn.fetch("""
            SELECT 
                COUNT(*) as total,
                COUNT(created_at) as has_created_at,
                COUNT(score_evaluated_at) as has_score_evaluated_at,
                COUNT(send_ts) as has_send_ts
            FROM pitches;
        """)
        
        print("\n=== TIMESTAMP FIELD POPULATION ===")
        if pg_timestamps:
            pg = pg_timestamps[0]
            print(f"\nPitch Generations:")
            print(f"  Total records: {pg['total']}")
            print(f"  Has generated_at: {pg['has_generated_at']}")
            print(f"  Has reviewed_at: {pg['has_reviewed_at']}")
        
        if p_timestamps:
            p = p_timestamps[0]
            print(f"\nPitches:")
            print(f"  Total records: {p['total']}")
            print(f"  Has created_at: {p['has_created_at']}")
            print(f"  Has score_evaluated_at: {p['has_score_evaluated_at']}")
            print(f"  Has send_ts: {p['has_send_ts']}")

async def main():
    """Run all verification checks"""
    print("=== PITCH TABLES VERIFICATION REPORT ===")
    print(f"Generated at: {datetime.now().isoformat()}")
    
    try:
        await verify_schema()
        await check_sample_data()
        await verify_field_mapping()
        await check_timestamps()
        
        print("\n=== RECOMMENDATIONS ===")
        print("1. Ensure generated_at in pitch_generations uses DEFAULT CURRENT_TIMESTAMP")
        print("2. Ensure created_at in pitches uses DEFAULT CURRENT_TIMESTAMP")
        print("3. Remove manual timestamp handling from insert queries")
        print("4. Verify all required fields are being populated")
        
    except Exception as e:
        logger.error(f"Error during verification: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main())