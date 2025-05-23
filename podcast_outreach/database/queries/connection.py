# podcast_outreach/database/connection.py

import os
import asyncpg
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# --- Connection Pool Management ---
DB_POOL: Optional[asyncpg.Pool] = None

async def init_db_pool():
    """Initializes the global PostgreSQL connection pool."""
    global DB_POOL
    if DB_POOL is None or DB_POOL._closed:
        try:
            user = os.getenv("PGUSER")
            password = os.getenv("PGPASSWORD")
            host = os.getenv("PGHOST")
            port = os.getenv("PGPORT")
            dbname = os.getenv("PGDATABASE")
            connect_timeout_seconds = 30
            pool_acquire_timeout_seconds = 30 # Timeout for pool.acquire()

            if not all([user, password, host, port, dbname]):
                logger.error("Database connection parameters missing.")
                raise ValueError("DB connection parameters missing for DSN.")

            dsn = f"postgresql://{user}:{password}@{host}:{port}/{dbname}?connect_timeout={connect_timeout_seconds}"
            
            logger.info(f"Initializing DB pool with DSN (connect_timeout={connect_timeout_seconds}s, acquire_timeout={pool_acquire_timeout_seconds}s)")

            DB_POOL = await asyncpg.create_pool(
                dsn=dsn,
                min_size=1,
                max_size=10,
                command_timeout=60,
                timeout=pool_acquire_timeout_seconds # Timeout for pool.acquire()
            )
            logger.info("Database connection pool initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing database pool: {e}", exc_info=True)
            raise
    return DB_POOL

async def get_db_pool() -> asyncpg.Pool:
    """Returns the global PostgreSQL connection pool, initializing it if necessary."""
    if DB_POOL is None or DB_POOL._closed:
        return await init_db_pool()
    return DB_POOL

async def close_db_pool():
    """Closes the global PostgreSQL connection pool."""
    global DB_POOL
    if DB_POOL and not DB_POOL._closed:
        await DB_POOL.close()
        DB_POOL = None
        logger.info("Database connection pool closed.")

# FastAPI dependency (if needed for routers to inject a connection)
# async def get_db_connection_dependency() -> asyncpg.Connection:
#     """FastAPI dependency to provide a database connection from the pool."""
#     pool = await get_db_pool()
#     async with pool.acquire() as connection:
#         yield connection
