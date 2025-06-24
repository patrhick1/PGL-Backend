"""
Migration: Add host name confidence tracking and failed URL caching
Date: 2024-01-23

This migration adds:
1. Host name confidence tracking columns to media table
2. Failed audio URL tracking columns to episodes table
3. Batch transcription tracking columns to episodes table
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def run_migration():
    """Run the migration to add host confidence and failed URL tracking"""
    
    # Database connection
    conn = await asyncpg.connect(
        host=os.getenv('PGHOST'),
        port=os.getenv('PGPORT'),
        user=os.getenv('PGUSER'),
        password=os.getenv('PGPASSWORD'),
        database=os.getenv('PGDATABASE')
    )
    
    try:
        print("Starting migration: Add host confidence and failed URL tracking...")
        
        # Add host name discovery tracking to media table
        print("Adding host name discovery tracking columns to media table...")
        await conn.execute("""
            ALTER TABLE media
            ADD COLUMN IF NOT EXISTS host_names_discovery_sources JSONB DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS host_names_discovery_confidence JSONB DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS host_names_last_verified TIMESTAMPTZ;
        """)
        
        # Create index for host name verification tracking
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_media_host_names_last_verified 
            ON media (host_names_last_verified);
        """)
        
        # Add failed audio URL tracking to episodes table
        print("Adding audio URL status tracking columns to episodes table...")
        await conn.execute("""
            ALTER TABLE episodes
            ADD COLUMN IF NOT EXISTS audio_url_status VARCHAR(50) DEFAULT 'available' 
                CHECK (audio_url_status IN ('available', 'failed_404', 'failed_temp', 'expired', 'refreshed')),
            ADD COLUMN IF NOT EXISTS audio_url_last_checked TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS audio_url_failure_count INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS audio_url_last_error TEXT;
        """)
        
        # Create indexes for failed URL tracking
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodes_audio_url_status 
            ON episodes (audio_url_status);
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodes_audio_url_last_checked 
            ON episodes (audio_url_last_checked);
        """)
        
        # Add batch transcription tracking
        print("Adding batch transcription tracking columns to episodes table...")
        await conn.execute("""
            ALTER TABLE episodes
            ADD COLUMN IF NOT EXISTS transcription_batch_id UUID,
            ADD COLUMN IF NOT EXISTS transcription_batch_position INTEGER;
        """)
        
        # Create index for batch tracking
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_episodes_transcription_batch_id 
            ON episodes (transcription_batch_id);
        """)
        
        # Add comment documentation
        print("Adding column documentation...")
        await conn.execute("""
            COMMENT ON COLUMN media.host_names_discovery_sources 
            IS 'JSON array of sources where host names were discovered (e.g., ["tavily_search", "episode_transcript", "podcast_description"])';
        """)
        
        await conn.execute("""
            COMMENT ON COLUMN media.host_names_discovery_confidence 
            IS 'JSON object mapping each host name to its confidence score (0.0-1.0)';
        """)
        
        await conn.execute("""
            COMMENT ON COLUMN media.host_names_last_verified 
            IS 'Timestamp of last host name verification check';
        """)
        
        await conn.execute("""
            COMMENT ON COLUMN episodes.audio_url_status 
            IS 'Status of the audio URL: available, failed_404 (permanent), failed_temp (temporary), expired (needs refresh), refreshed';
        """)
        
        await conn.execute("""
            COMMENT ON COLUMN episodes.audio_url_failure_count 
            IS 'Number of consecutive failures for this URL';
        """)
        
        await conn.execute("""
            COMMENT ON COLUMN episodes.transcription_batch_id 
            IS 'UUID identifying the batch this episode belongs to for transcription';
        """)
        
        print("Migration completed successfully!")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        raise
    finally:
        await conn.close()

async def verify_migration():
    """Verify the migration was successful"""
    conn = await asyncpg.connect(
        host=os.getenv('PGHOST'),
        port=os.getenv('PGPORT'),
        user=os.getenv('PGUSER'),
        password=os.getenv('PGPASSWORD'),
        database=os.getenv('PGDATABASE')
    )
    
    try:
        print("\nVerifying migration...")
        
        # Check media table columns
        media_columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'media' 
            AND column_name IN ('host_names_discovery_sources', 'host_names_discovery_confidence', 'host_names_last_verified')
            ORDER BY column_name;
        """)
        
        print("\nMedia table new columns:")
        for col in media_columns:
            print(f"  - {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
        
        # Check episodes table columns
        episodes_columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'episodes' 
            AND column_name IN ('audio_url_status', 'audio_url_last_checked', 'audio_url_failure_count', 
                                'audio_url_last_error', 'transcription_batch_id', 'transcription_batch_position')
            ORDER BY column_name;
        """)
        
        print("\nEpisodes table new columns:")
        for col in episodes_columns:
            print(f"  - {col['column_name']}: {col['data_type']} (nullable: {col['is_nullable']})")
        
        # Check indexes
        indexes = await conn.fetch("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename IN ('media', 'episodes')
            AND indexname IN ('idx_media_host_names_last_verified', 'idx_episodes_audio_url_status', 
                              'idx_episodes_audio_url_last_checked', 'idx_episodes_transcription_batch_id')
            ORDER BY indexname;
        """)
        
        print("\nNew indexes created:")
        for idx in indexes:
            print(f"  - {idx['indexname']}")
        
        print("\nMigration verification complete!")
        
    finally:
        await conn.close()

if __name__ == "__main__":
    print("Running migration: Add host confidence and failed URL tracking")
    print("=" * 60)
    
    # Run the migration
    asyncio.run(run_migration())
    
    # Verify the migration
    asyncio.run(verify_migration())