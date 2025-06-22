#!/usr/bin/env python3
"""
Test script to verify the database connection fixes work correctly.
"""

import asyncio
import logging
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.connection import get_db_pool, close_db_pool
from services.tasks.manager import TaskManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_main_pool_connection():
    """Test the main database pool connection"""
    print("🔍 Testing main database pool...")
    
    try:
        pool = await get_db_pool()
        print(f"✅ Pool created successfully")
        print(f"   Pool size: {pool.get_size()}")
        print(f"   Pool closed: {pool._closed}")
        
        # Test acquiring a connection
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            print(f"✅ Test query result: {result}")
        
        print("✅ Main pool connection test passed")
        return True
        
    except Exception as e:
        print(f"❌ Main pool test failed: {e}")
        return False

async def test_task_manager_connection():
    """Test the TaskManager database connection handling"""
    print("\n🔍 Testing TaskManager connection...")
    
    try:
        # Create a simple test function that uses database queries
        async def test_db_function(db_service):
            # This simulates what the actual tasks do
            pool = db_service.pool
            
            # Test the acquire context manager
            async with pool.acquire() as conn:
                result = await conn.fetchval("SELECT 'TaskManager test successful' as message")
                print(f"✅ TaskManager query result: {result}")
                return True
        
        # Create TaskManager and test
        task_manager = TaskManager()
        
        # Simulate what happens in _run_business_logic_task
        result = await task_manager._run_business_logic_task(test_db_function)
        
        if result:
            print("✅ TaskManager connection test passed")
            return True
        else:
            print("❌ TaskManager test returned False")
            return False
            
    except Exception as e:
        print(f"❌ TaskManager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_multiple_connections():
    """Test multiple simultaneous connections"""
    print("\n🔍 Testing multiple simultaneous connections...")
    
    try:
        pool = await get_db_pool()
        
        async def test_connection(conn_id):
            async with pool.acquire() as conn:
                result = await conn.fetchval(f"SELECT {conn_id} as connection_id")
                print(f"   Connection {conn_id}: {result}")
                return result
        
        # Test 3 simultaneous connections (within our pool limit of 5)
        tasks = [test_connection(i) for i in range(1, 4)]
        results = await asyncio.gather(*tasks)
        
        if len(results) == 3 and all(results):
            print("✅ Multiple connections test passed")
            return True
        else:
            print(f"❌ Multiple connections test failed: {results}")
            return False
            
    except Exception as e:
        print(f"❌ Multiple connections test failed: {e}")
        return False

async def main():
    """Run all tests"""
    print("🧪 Database Connection Fix Tests")
    print("=" * 50)
    
    tests_passed = 0
    total_tests = 3
    
    # Test 1: Main pool
    if await test_main_pool_connection():
        tests_passed += 1
    
    # Test 2: TaskManager
    if await test_task_manager_connection():
        tests_passed += 1
    
    # Test 3: Multiple connections
    if await test_multiple_connections():
        tests_passed += 1
    
    # Cleanup
    print("\n🧹 Cleaning up...")
    await close_db_pool()
    
    # Results
    print("=" * 50)
    print(f"📊 Test Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! Connection fixes are working correctly.")
        return True
    else:
        print("❌ Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Test runner failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)