# podcast_outreach/services/database_service.py

import asyncpg
from typing import Optional, Any, Dict, List
import logging

logger = logging.getLogger(__name__)

class DatabaseService:
    """
    Database service abstraction layer that provides clean database access
    without exposing pool management to business logic.
    """
    
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool
    
    async def execute_query(self, query: str, *params) -> Any:
        """Execute a query and return results"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *params)
    
    async def execute_single(self, query: str, *params) -> Optional[Dict]:
        """Execute a query and return single result"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(query, *params)
            return dict(result) if result else None
    
    async def execute_command(self, query: str, *params) -> str:
        """Execute a command (INSERT, UPDATE, DELETE) and return status"""
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *params)
    
    async def execute_transaction(self, queries_and_params: List[tuple]) -> bool:
        """Execute multiple queries in a transaction"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    for query, params in queries_and_params:
                        await conn.execute(query, *params)
                    return True
                except Exception as e:
                    logger.error(f"Transaction failed: {e}")
                    raise