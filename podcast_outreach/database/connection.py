# podcast_outreach/database/connection.py

import os
import asyncpg
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# --- Connection Pool Management ---
DB_POOL: Optional[asyncpg.Pool] = None
BACKGROUND_TASK_POOL: Optional[asyncpg.Pool] = None

async def init_db_pool():
    """Initializes the global PostgreSQL connection pool for frontend requests."""
    global DB_POOL
    if DB_POOL is None or DB_POOL._closed:
        try:
            user = os.getenv("PGUSER")
            password = os.getenv("PGPASSWORD")
            host = os.getenv("PGHOST")
            port = os.getenv("PGPORT")
            dbname = os.getenv("PGDATABASE")
            connect_timeout_seconds = 30
            pool_acquire_timeout_seconds = 10 # Shorter timeout for frontend requests

            if not all([user, password, host, port, dbname]):
                logger.error("Database connection parameters missing.")
                raise ValueError("DB connection parameters missing for DSN.")

            dsn = f"postgresql://{user}:{password}@{host}:{port}/{dbname}?connect_timeout={connect_timeout_seconds}&command_timeout=60"
            
            logger.info(f"Initializing frontend DB pool with DSN (connect_timeout={connect_timeout_seconds}s, acquire_timeout={pool_acquire_timeout_seconds}s)")

            DB_POOL = await asyncpg.create_pool(
                dsn=dsn,
                min_size=3,         # Smaller pool for frontend requests
                max_size=10,        # Reasonable limit for web requests  
                command_timeout=60, # Shorter timeout for frontend operations
                timeout=pool_acquire_timeout_seconds, # Quick timeout for responsive UI
                max_queries=10000,  # Reasonable limit per connection
                max_inactive_connection_lifetime=300  # 5 minutes for frontend connections
            )
            logger.info("Frontend database connection pool initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing frontend database pool: {e}", exc_info=True)
            raise
    return DB_POOL

async def init_background_task_pool():
    """Initializes a separate connection pool specifically for background tasks."""
    global BACKGROUND_TASK_POOL
    if BACKGROUND_TASK_POOL is None or BACKGROUND_TASK_POOL._closed:
        try:
            user = os.getenv("PGUSER")
            password = os.getenv("PGPASSWORD")
            host = os.getenv("PGHOST")
            port = os.getenv("PGPORT")
            dbname = os.getenv("PGDATABASE")
            connect_timeout_seconds = 60
            pool_acquire_timeout_seconds = 60 # Longer timeout for background tasks

            if not all([user, password, host, port, dbname]):
                logger.error("Database connection parameters missing.")
                raise ValueError("DB connection parameters missing for DSN.")

            dsn = f"postgresql://{user}:{password}@{host}:{port}/{dbname}?connect_timeout={connect_timeout_seconds}&command_timeout=1800"
            
            logger.info(f"Initializing background task DB pool with DSN (connect_timeout={connect_timeout_seconds}s, acquire_timeout={pool_acquire_timeout_seconds}s)")

            BACKGROUND_TASK_POOL = await asyncpg.create_pool(
                dsn=dsn,
                min_size=2,         # Small dedicated pool for background tasks
                max_size=8,         # Sufficient for concurrent background operations
                command_timeout=1800, # Extended timeout for long AI operations (30 minutes)
                timeout=pool_acquire_timeout_seconds, # Longer timeout for background tasks
                max_queries=50000,  # Higher limit for background processing
                max_inactive_connection_lifetime=3600  # 1 hour for long-running tasks
            )
            logger.info("Background task database connection pool initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing background task database pool: {e}", exc_info=True)
            raise
    return BACKGROUND_TASK_POOL

async def get_db_pool() -> asyncpg.Pool:
    """Returns the frontend PostgreSQL connection pool, initializing it if necessary."""
    if DB_POOL is None or DB_POOL._closed:
        return await init_db_pool()
    return DB_POOL

async def get_background_task_pool() -> asyncpg.Pool:
    """Returns the background task PostgreSQL connection pool, initializing it if necessary."""
    if BACKGROUND_TASK_POOL is None or BACKGROUND_TASK_POOL._closed:
        return await init_background_task_pool()
    return BACKGROUND_TASK_POOL

async def reset_db_pool():
    """Forces recreation of the frontend database pool with current configuration."""
    global DB_POOL
    if DB_POOL and not DB_POOL._closed:
        await DB_POOL.close()
        DB_POOL = None
        logger.info("Frontend database connection pool reset.")
    return await init_db_pool()

async def reset_background_task_pool():
    """Forces recreation of the background task database pool with current configuration."""
    global BACKGROUND_TASK_POOL
    if BACKGROUND_TASK_POOL and not BACKGROUND_TASK_POOL._closed:
        await BACKGROUND_TASK_POOL.close()
        BACKGROUND_TASK_POOL = None
        logger.info("Background task database connection pool reset.")
    return await init_background_task_pool()

async def close_db_pool():
    """Closes the frontend PostgreSQL connection pool."""
    global DB_POOL
    if DB_POOL and not DB_POOL._closed:
        await DB_POOL.close()
        DB_POOL = None
        logger.info("Frontend database connection pool closed.")

async def close_background_task_pool():
    """Closes the background task PostgreSQL connection pool."""
    global BACKGROUND_TASK_POOL
    if BACKGROUND_TASK_POOL and not BACKGROUND_TASK_POOL._closed:
        await BACKGROUND_TASK_POOL.close()
        BACKGROUND_TASK_POOL = None
        logger.info("Background task database connection pool closed.")

async def close_all_pools():
    """Closes both frontend and background task connection pools."""
    await close_db_pool()
    await close_background_task_pool()

# FastAPI dependency (if needed for routers to inject a connection)
# async def get_db_connection_dependency() -> asyncpg.Connection:
#     """FastAPI dependency to provide a database connection from the pool."""
#     pool = await get_db_pool()
#     async with pool.acquire() as connection:
#         yield connection
