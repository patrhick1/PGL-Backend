#!/usr/bin/env python3
"""
Add this debug monitoring to your application to track actual memory usage.
"""

import psutil
import os
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class MemoryDebugger:
    """Track detailed memory usage to identify discrepancies."""
    
    def __init__(self):
        self.pid = os.getpid()
        self.process = psutil.Process(self.pid)
        
    def get_detailed_memory_info(self):
        """Get comprehensive memory metrics."""
        try:
            # Get memory info
            memory_info = self.process.memory_info()
            memory_full = self.process.memory_full_info()
            memory_percent = self.process.memory_percent()
            
            # Get system memory
            virtual_memory = psutil.virtual_memory()
            
            # Count children
            children = self.process.children(recursive=True)
            children_memory = sum(child.memory_info().rss for child in children if child.is_running())
            
            # Get open files count
            open_files = len(self.process.open_files())
            
            return {
                "timestamp": datetime.now().isoformat(),
                "pid": self.pid,
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "uss_mb": memory_full.uss / 1024 / 1024,  # Unique Set Size
                "pss_mb": memory_full.pss / 1024 / 1024,  # Proportional Set Size
                "shared_mb": memory_info.rss / 1024 / 1024 - memory_full.uss / 1024 / 1024,
                "percent": memory_percent,
                "children_count": len(children),
                "children_memory_mb": children_memory / 1024 / 1024,
                "total_with_children_mb": (memory_info.rss + children_memory) / 1024 / 1024,
                "open_files": open_files,
                "system_available_mb": virtual_memory.available / 1024 / 1024,
                "system_percent": virtual_memory.percent
            }
        except Exception as e:
            logger.error(f"Error getting memory info: {e}")
            return {"error": str(e)}
    
    async def monitor_memory_continuously(self, interval=10):
        """Log memory usage every interval seconds."""
        while True:
            info = self.get_detailed_memory_info()
            
            # Log critical info
            logger.warning(
                f"MEMORY DEBUG - RSS: {info.get('rss_mb', 0):.1f}MB, "
                f"VMS: {info.get('vms_mb', 0):.1f}MB, "
                f"Total+Children: {info.get('total_with_children_mb', 0):.1f}MB, "
                f"Children: {info.get('children_count', 0)}, "
                f"Files: {info.get('open_files', 0)}"
            )
            
            # Alert if approaching limit
            total_mb = info.get('total_with_children_mb', 0)
            if total_mb > 1500:
                logger.error(f"MEMORY CRITICAL: {total_mb:.1f}MB used (including children)")
            elif total_mb > 1000:
                logger.warning(f"MEMORY HIGH: {total_mb:.1f}MB used (including children)")
            
            await asyncio.sleep(interval)

# Add to your main.py startup:
async def start_memory_debugging():
    """Start memory debugging in background."""
    if os.getenv("DEBUG_MEMORY", "false").lower() == "true":
        debugger = MemoryDebugger()
        asyncio.create_task(debugger.monitor_memory_continuously())
        logger.info("Memory debugging started")

# Also add this endpoint to check memory on demand:
from fastapi import APIRouter

debug_router = APIRouter()

@debug_router.get("/debug/memory")
async def get_memory_debug():
    """Get current detailed memory usage."""
    debugger = MemoryDebugger()
    return debugger.get_detailed_memory_info()

# Check for memory leaks in specific operations:
def check_temp_files():
    """Check for accumulated temp files."""
    import tempfile
    temp_dir = tempfile.gettempdir()
    
    audio_extensions = ['.mp3', '.wav', '.m4a', '.flac', '.ogg']
    temp_files = []
    
    for root, dirs, files in os.walk(temp_dir):
        for file in files:
            if any(file.endswith(ext) for ext in audio_extensions):
                filepath = os.path.join(root, file)
                try:
                    stat = os.stat(filepath)
                    temp_files.append({
                        "file": filepath,
                        "size_mb": stat.st_size / 1024 / 1024,
                        "age_hours": (datetime.now().timestamp() - stat.st_mtime) / 3600
                    })
                except:
                    pass
    
    total_size_mb = sum(f["size_mb"] for f in temp_files)
    logger.warning(f"Found {len(temp_files)} temp audio files using {total_size_mb:.1f}MB")
    
    return temp_files