#!/usr/bin/env python3
"""
Migration Runner Script
Run all pending migrations or rollback as needed.
"""

import asyncio
import os
import sys
import importlib.util
from pathlib import Path
from typing import List, Tuple
import asyncpg
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

# Migration tracking table
MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT NOW()
);
"""

async def get_connection():
    """Create a database connection."""
    return await asyncpg.connect(
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        host=os.getenv("PGHOST"),
        port=os.getenv("PGPORT"),
        database=os.getenv("PGDATABASE")
    )

async def ensure_migration_table(conn):
    """Ensure the migration tracking table exists."""
    await conn.execute(MIGRATION_TABLE_SQL)

async def get_applied_migrations(conn) -> List[str]:
    """Get list of applied migration versions."""
    rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
    return [row['version'] for row in rows]

async def mark_migration_applied(conn, version: str):
    """Mark a migration as applied."""
    await conn.execute(
        "INSERT INTO schema_migrations (version) VALUES ($1) ON CONFLICT DO NOTHING",
        version
    )

async def unmark_migration_applied(conn, version: str):
    """Remove a migration from the applied list."""
    await conn.execute("DELETE FROM schema_migrations WHERE version = $1", version)

def get_migration_files() -> List[Tuple[str, Path]]:
    """Get all migration files sorted by version."""
    migrations_dir = Path(__file__).parent / 'migrations'
    if not migrations_dir.exists():
        logger.error(f"Migrations directory not found: {migrations_dir}")
        return []
    
    migration_files = []
    for file_path in migrations_dir.glob('*.py'):
        if file_path.name.startswith('__'):
            continue
        
        # Extract version from filename (e.g., "001" from "001_add_client_match_tracking.py")
        version = file_path.stem.split('_')[0]
        if version.isdigit():
            migration_files.append((version, file_path))
    
    # Sort by version
    migration_files.sort(key=lambda x: x[0])
    return migration_files

async def load_and_run_migration(file_path: Path, direction: str = 'up'):
    """Load and run a migration file."""
    # Load the migration module
    spec = importlib.util.spec_from_file_location("migration", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    # Get the migration function
    if direction == 'up':
        if hasattr(module, 'migrate_up'):
            conn = await get_connection()
            try:
                await module.migrate_up(conn)
            finally:
                await conn.close()
        else:
            logger.warning(f"No migrate_up function found in {file_path}")
    else:
        if hasattr(module, 'migrate_down'):
            conn = await get_connection()
            try:
                await module.migrate_down(conn)
            finally:
                await conn.close()
        else:
            logger.warning(f"No migrate_down function found in {file_path}")

async def run_migrations():
    """Run all pending migrations."""
    conn = await get_connection()
    
    try:
        # Ensure migration table exists
        await ensure_migration_table(conn)
        
        # Get applied migrations
        applied = await get_applied_migrations(conn)
        logger.info(f"Currently applied migrations: {applied}")
        
        # Get all migration files
        migration_files = get_migration_files()
        logger.info(f"Found {len(migration_files)} migration files")
        
        # Run pending migrations
        pending_count = 0
        for version, file_path in migration_files:
            if version not in applied:
                logger.info(f"\nRunning migration {version}: {file_path.name}")
                try:
                    await load_and_run_migration(file_path, 'up')
                    await mark_migration_applied(conn, version)
                    logger.info(f"✅ Migration {version} completed successfully")
                    pending_count += 1
                except Exception as e:
                    logger.error(f"❌ Migration {version} failed: {e}")
                    raise
        
        if pending_count == 0:
            logger.info("\n✅ No pending migrations to run")
        else:
            logger.info(f"\n✅ Successfully ran {pending_count} migrations")
            
    finally:
        await conn.close()

async def rollback_migration(version: str):
    """Rollback a specific migration."""
    conn = await get_connection()
    
    try:
        # Check if migration is applied
        applied = await get_applied_migrations(conn)
        if version not in applied:
            logger.error(f"Migration {version} is not applied")
            return
        
        # Find the migration file
        migration_files = get_migration_files()
        file_path = None
        for v, p in migration_files:
            if v == version:
                file_path = p
                break
        
        if not file_path:
            logger.error(f"Migration file not found for version {version}")
            return
        
        logger.info(f"Rolling back migration {version}: {file_path.name}")
        try:
            await load_and_run_migration(file_path, 'down')
            await unmark_migration_applied(conn, version)
            logger.info(f"✅ Migration {version} rolled back successfully")
        except Exception as e:
            logger.error(f"❌ Rollback failed: {e}")
            raise
            
    finally:
        await conn.close()

async def show_status():
    """Show migration status."""
    conn = await get_connection()
    
    try:
        await ensure_migration_table(conn)
        
        # Get applied migrations
        applied = await get_applied_migrations(conn)
        
        # Get all migration files
        migration_files = get_migration_files()
        
        logger.info("\nMigration Status:")
        logger.info("-" * 60)
        
        for version, file_path in migration_files:
            status = "✅ Applied" if version in applied else "⏳ Pending"
            logger.info(f"{version}: {file_path.name:50} {status}")
            
    finally:
        await conn.close()

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python run_migrations.py migrate     # Run all pending migrations")
        print("  python run_migrations.py rollback <version>  # Rollback specific migration")
        print("  python run_migrations.py status      # Show migration status")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "migrate":
        asyncio.run(run_migrations())
    elif command == "rollback":
        if len(sys.argv) < 3:
            print("Please specify migration version to rollback")
            sys.exit(1)
        version = sys.argv[2]
        asyncio.run(rollback_migration(version))
    elif command == "status":
        asyncio.run(show_status())
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()