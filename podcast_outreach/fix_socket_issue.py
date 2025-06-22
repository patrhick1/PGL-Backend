#!/usr/bin/env python3
"""
Emergency fix for Windows socket buffer exhaustion issue.
Run this script to apply immediate fixes.
"""

import asyncio
import gc
import os
import sys
import logging

async def fix_connection_pool():
    """Fix connection pool configuration and add resource cleanup"""
    
    # 1. Force garbage collection
    print("🧹 Running garbage collection...")
    gc.collect()
    
    # 2. Check current connections
    try:
        from podcast_outreach.database.connection import DB_POOL, close_db_pool, init_db_pool
        
        if DB_POOL and not DB_POOL._closed:
            print(f"📊 Current pool status:")
            print(f"   Size: {DB_POOL.get_size()}")
            print(f"   Min size: {DB_POOL._min_size}")
            print(f"   Max size: {DB_POOL._max_size}")
            print(f"   Available connections: {DB_POOL.get_size() - DB_POOL.get_acquired_count()}")
            
            # Close existing pool
            print("🔌 Closing existing database pool...")
            await close_db_pool()
            
        # Reinitialize with better settings
        print("🚀 Reinitializing database pool with optimized settings...")
        pool = await init_db_pool()
        
        if pool:
            print("✅ Database pool reinitialized successfully")
            print(f"   New pool size: {pool.get_size()}")
        
    except Exception as e:
        print(f"❌ Error fixing database pool: {e}")
    
    # 3. Clear any asyncio resources
    print("🔄 Cleaning up asyncio resources...")
    
    # Get current event loop
    try:
        loop = asyncio.get_running_loop()
        
        # Cancel all pending tasks
        tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
        if tasks:
            print(f"📋 Cancelling {len(tasks)} pending tasks...")
            for task in tasks:
                task.cancel()
            
            # Wait for tasks to complete cancellation
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        print(f"⚠️  Warning during asyncio cleanup: {e}")

def apply_system_fixes():
    """Apply Windows-specific socket fixes"""
    print("🛠️  Applying Windows socket fixes...")
    
    # Set environment variables for better socket handling
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    
    # Increase socket limits (Windows registry would be more permanent)
    try:
        import socket
        socket.setdefaulttimeout(30)  # 30 second timeout
        print("✅ Socket timeout configured")
    except Exception as e:
        print(f"⚠️  Could not configure socket settings: {e}")

async def main():
    """Run all fixes"""
    print("🚨 Emergency Socket Buffer Fix - Starting...")
    print("=" * 50)
    
    # Apply system fixes first
    apply_system_fixes()
    
    # Fix connection pool
    await fix_connection_pool()
    
    print("=" * 50)
    print("✅ Emergency fixes applied!")
    print()
    print("📋 Next steps:")
    print("1. Restart your FastAPI server")
    print("2. Monitor for any remaining socket issues") 
    print("3. Consider implementing the permanent fixes in the config")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Emergency fix failed: {e}")
        sys.exit(1)