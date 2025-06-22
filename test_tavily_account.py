#!/usr/bin/env python3
"""
Test script to check Tavily account status and API functionality
"""
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def test_tavily_account():
    """Test Tavily API account and functionality"""
    
    # Check if API key exists
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    if not tavily_api_key:
        print("[ERROR] TAVILY_API_KEY not found in environment variables")
        return
    
    print(f"[OK] Found Tavily API key: {tavily_api_key[:8]}...")
    
    try:
        # Import and test basic functionality
        from podcast_outreach.services.ai.tavily_client import async_tavily_search
        
        # Test 1: Simple search
        print("\n[TEST] Testing basic search...")
        result = await async_tavily_search("podcast hosts")
        
        if result is None:
            print("[ERROR] Search returned None - possible rate limit or API issue")
        elif isinstance(result, dict):
            if result.get('answer'):
                print(f"[OK] Search successful - Got answer: {result['answer'][:100]}...")
            elif result.get('results'):
                print(f"[OK] Search successful - Got {len(result['results'])} results")
            else:
                print(f"[WARN] Search returned dict but no answer/results: {result}")
        else:
            print(f"[WARN] Unexpected result type: {type(result)}")
            
        # Test 2: Podcast-specific search
        print("\n[TEST] Testing podcast search...")
        result2 = await async_tavily_search("Working In Tech podcast host names")
        
        if result2 is None:
            print("[ERROR] Podcast search returned None")
        elif isinstance(result2, dict):
            if result2.get('answer'):
                print(f"[OK] Podcast search successful - Got answer: {result2['answer'][:100]}...")
            elif result2.get('results'):
                print(f"[OK] Podcast search successful - Got {len(result2['results'])} results")
            else:
                print(f"[WARN] Podcast search returned dict but no answer/results: {result2}")
                
    except Exception as e:
        print(f"[ERROR] Error testing Tavily: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_tavily_account())