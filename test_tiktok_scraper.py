#!/usr/bin/env python3
"""
Test script for TikTok scraper using apidojo/tiktok-scraper
"""
import asyncio
import os
from dotenv import load_dotenv
from apify_client import ApifyClient

load_dotenv()

async def test_tiktok_scraper():
    """Test the correct TikTok scraper actor"""
    api_key = os.getenv("APIFY_API_KEY")
    if not api_key:
        print("Error: APIFY_API_KEY not found in environment")
        return
    
    client = ApifyClient(api_key)
    
    # Test with a single TikTok profile URL
    test_url = "https://www.tiktok.com/@garyvee"  # Gary Vaynerchuk's TikTok
    
    print(f"Testing TikTok scraper with URL: {test_url}")
    print("Actor: apidojo/tiktok-scraper")
    
    try:
        # Run the actor
        run_input = {
            "startUrls": [test_url],
            "maxItems": 1
        }
        
        print(f"Input: {run_input}")
        
        run = client.actor('apidojo/tiktok-scraper').call(
            run_input=run_input,
            timeout_secs=120
        )
        
        print(f"Run completed. Status: {run.get('status')}")
        print(f"Run ID: {run.get('id')}")
        
        # Get the dataset items
        dataset_id = run.get('defaultDatasetId')
        if dataset_id:
            items = client.dataset(dataset_id).list_items().items
            print(f"Found {len(items)} items")
            
            if items:
                item = items[0]
                print("\nFirst item structure:")
                for key, value in item.items():
                    if isinstance(value, (str, int, float, bool)):
                        try:
                            print(f"  {key}: {value}")
                        except UnicodeEncodeError:
                            print(f"  {key}: <unicode string>")
                    else:
                        print(f"  {key}: {type(value)} (length: {len(value) if hasattr(value, '__len__') else 'N/A'})")
                
                # Show key fields we're interested in
                print("\nKey fields for social data:")
                relevant_fields = ['id', 'username', 'nickname', 'followerCount', 'followingCount', 'heartCount', 'postCount', 'verified']
                for field in relevant_fields:
                    if field in item:
                        print(f"  {field}: {item[field]}")
            else:
                print("No items returned")
        else:
            print("No dataset ID found")
            
    except Exception as e:
        print(f"Error running TikTok scraper: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_tiktok_scraper())