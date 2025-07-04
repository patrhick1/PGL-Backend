"""
Memory monitoring utilities to prevent OOM errors.
"""
import psutil
import os
import logging
import functools
from typing import Callable, Any
import asyncio

logger = logging.getLogger(__name__)


def get_memory_info() -> dict:
    """Get current memory usage information."""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    memory_percent = process.memory_percent()
    
    # Get system-wide memory info
    virtual_memory = psutil.virtual_memory()
    
    return {
        "process_rss_mb": memory_info.rss / 1024 / 1024,
        "process_percent": memory_percent,
        "system_available_mb": virtual_memory.available / 1024 / 1024,
        "system_percent": virtual_memory.percent
    }


def check_memory_usage() -> bool:
    """
    Check current memory usage and warn if high.
    Returns True if memory usage is acceptable, False if too high.
    """
    memory_info = get_memory_info()
    
    # Check process memory
    if memory_info["process_percent"] > 80:
        logger.error(
            f"HIGH MEMORY USAGE: Process using {memory_info['process_percent']:.1f}% "
            f"({memory_info['process_rss_mb']:.1f} MB)"
        )
        return False
    elif memory_info["process_percent"] > 60:
        logger.warning(
            f"Elevated memory usage: Process using {memory_info['process_percent']:.1f}% "
            f"({memory_info['process_rss_mb']:.1f} MB)"
        )
    
    # Check system memory
    if memory_info["system_percent"] > 90:
        logger.error(
            f"SYSTEM MEMORY CRITICAL: {memory_info['system_percent']:.1f}% used, "
            f"only {memory_info['system_available_mb']:.1f} MB available"
        )
        return False
    
    return True


def memory_guard(threshold_percent: float = 80.0):
    """
    Decorator to prevent operations when memory is high.
    
    Args:
        threshold_percent: Memory usage percentage threshold (default: 80%)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            memory_info = get_memory_info()
            if memory_info["process_percent"] > threshold_percent:
                raise MemoryError(
                    f"Memory usage too high ({memory_info['process_percent']:.1f}%), "
                    f"operation cancelled to prevent OOM"
                )
            return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            memory_info = get_memory_info()
            if memory_info["process_percent"] > threshold_percent:
                raise MemoryError(
                    f"Memory usage too high ({memory_info['process_percent']:.1f}%), "
                    f"operation cancelled to prevent OOM"
                )
            return func(*args, **kwargs)
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


async def log_memory_usage_periodically(interval_seconds: int = 300):
    """
    Log memory usage periodically for monitoring.
    
    Args:
        interval_seconds: How often to log memory usage (default: 5 minutes)
    """
    while True:
        try:
            memory_info = get_memory_info()
            logger.info(
                f"Memory usage - Process: {memory_info['process_rss_mb']:.1f} MB "
                f"({memory_info['process_percent']:.1f}%), "
                f"System: {memory_info['system_percent']:.1f}% used"
            )
            await asyncio.sleep(interval_seconds)
        except Exception as e:
            logger.error(f"Error logging memory usage: {e}")
            await asyncio.sleep(interval_seconds)


def cleanup_memory():
    """
    Force garbage collection and log memory status.
    Useful to call after processing large files.
    """
    import gc
    
    memory_before = get_memory_info()
    
    # Force garbage collection
    gc.collect()
    
    memory_after = get_memory_info()
    
    freed_mb = memory_before["process_rss_mb"] - memory_after["process_rss_mb"]
    if freed_mb > 0:
        logger.info(f"Freed {freed_mb:.1f} MB of memory after garbage collection")
    
    return freed_mb