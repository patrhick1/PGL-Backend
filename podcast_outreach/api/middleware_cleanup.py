# podcast_outreach/api/middleware_cleanup.py

import asyncio
import gc
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from podcast_outreach.database.connection import get_db_pool

logger = logging.getLogger(__name__)

class ResourceCleanupMiddleware(BaseHTTPMiddleware):
    """
    Middleware to prevent resource leaks and socket exhaustion.
    Monitors and cleans up resources after each request.
    """
    
    def __init__(self, app, cleanup_frequency: int = 100):
        super().__init__(app)
        self.request_count = 0
        self.cleanup_frequency = cleanup_frequency
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        self.request_count += 1
        
        try:
            # Process the request
            response = await call_next(request)
            
            # Periodic cleanup
            if self.request_count % self.cleanup_frequency == 0:
                await self._periodic_cleanup()
            
            return response
            
        except Exception as e:
            logger.error(f"Request failed: {e}")
            # Force cleanup on errors
            await self._emergency_cleanup()
            raise
    
    async def _periodic_cleanup(self):
        """Periodic resource cleanup"""
        try:
            logger.debug(f"Running periodic cleanup (request #{self.request_count})")
            
            # Check database pool health - but only if we can safely access it
            try:
                # Import the pool directly to avoid async context issues
                from podcast_outreach.database.connection import DB_POOL
                if DB_POOL and not DB_POOL._closed:
                    try:
                        # Use correct asyncpg Pool methods
                        pool_size = DB_POOL.get_size()
                        # asyncpg doesn't have get_acquired_count(), use different approach
                        logger.debug(f"DB Pool status: {pool_size} connections in pool")
                        
                        # Check if pool is over 80% capacity (simple heuristic)
                        if pool_size >= 4:  # Close to our max of 5
                            logger.warning(f"High DB connection usage: {pool_size} connections active")
                    except Exception as pool_error:
                        logger.debug(f"Could not check pool status: {pool_error}")
            except ImportError:
                pass  # Pool not available, skip monitoring
            
            # Light garbage collection
            if self.request_count % (self.cleanup_frequency * 5) == 0:
                gc.collect()
                logger.debug("Garbage collection performed")
                
        except Exception as e:
            logger.error(f"Error during periodic cleanup: {e}")
    
    async def _emergency_cleanup(self):
        """Emergency cleanup on errors"""
        try:
            logger.warning("Performing emergency resource cleanup")
            
            # Force garbage collection
            gc.collect()
            
            # Check for leaked connections - safely
            try:
                from podcast_outreach.database.connection import DB_POOL
                if DB_POOL and not DB_POOL._closed:
                    try:
                        pool_size = DB_POOL.get_size()
                        if pool_size > 3:  # More than expected
                            logger.warning(f"Potential connection leak: {pool_size} connections active")
                    except Exception as pool_error:
                        logger.debug(f"Could not check pool in emergency cleanup: {pool_error}")
            except ImportError:
                pass  # Pool not available
            
        except Exception as e:
            logger.error(f"Error during emergency cleanup: {e}")

class ConnectionMonitorMiddleware(BaseHTTPMiddleware):
    """
    Simple middleware to monitor connection usage per request.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Log connection status before request - safely
        before_size = 0
        try:
            # Import pool directly to avoid async context issues
            from podcast_outreach.database.connection import DB_POOL
            if DB_POOL and not DB_POOL._closed:
                try:
                    before_size = DB_POOL.get_size()
                except Exception:
                    pass  # Skip monitoring if pool check fails
        except ImportError:
            pass  # Pool not available
            
        try:
            # Process request
            response = await call_next(request)
            
            # Check for connection issues after request
            try:
                from podcast_outreach.database.connection import DB_POOL
                if DB_POOL and not DB_POOL._closed and before_size > 0:
                    try:
                        after_size = DB_POOL.get_size()
                        
                        # Log detailed pool stats for debugging
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(
                                f"Connection pool stats for {request.method} {request.url.path}: "
                                f"size={after_size}, min={DB_POOL._minsize}, max={DB_POOL._maxsize}, "
                                f"free={len(DB_POOL._free)}, used={DB_POOL._nwaiting}"
                            )
                        
                        # Only warn if we exceed max_size or see a significant increase
                        # Normal pool growth from min_size to max_size is expected
                        if after_size > 10:  # max_size from connection.py
                            logger.warning(
                                f"Connection pool exceeded max size in {request.method} {request.url.path}: "
                                f"pool size {before_size} -> {after_size}"
                            )
                        elif after_size > before_size + 3:  # Significant sudden increase
                            logger.warning(
                                f"Unusual connection pool growth in {request.method} {request.url.path}: "
                                f"pool size {before_size} -> {after_size}"
                            )
                    except Exception:
                        pass  # Skip check if it fails
            except ImportError:
                pass
            
            return response
                
        except Exception as e:
            logger.error(f"Connection monitoring error: {e}")
            return await call_next(request)