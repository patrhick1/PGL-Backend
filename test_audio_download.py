#!/usr/bin/env python3
"""
Test script to verify audio download fix
"""
import asyncio
import os
import sys
sys.path.append('/mnt/c/Users/ebube/Documents/PGL - Postgres')

from podcast_outreach.services.media.transcriber import MediaTranscriber

async def test_audio_download():
    """Test the improved audio download functionality"""
    
    # Sample URL from the logs (this was the failing one)
    test_url = "https://sphinx.acast.com/p/open/s/67354b03a7d4829cee346819/e/684801e522eb752c2f1f3cfb/media.mp3"
    
    try:
        # Initialize transcriber (requires GEMINI_API_KEY)
        transcriber = MediaTranscriber()
        
        print(f"Testing audio download from: {test_url}")
        print("This may take a moment...")
        
        # Test the download
        result = await transcriber.download_audio(test_url)
        
        if result:
            print("SUCCESS: Audio downloaded to", result)
            file_size = os.path.getsize(result)
            print(f"File size: {file_size} bytes ({file_size / (1024*1024):.2f} MB)")
            
            # Clean up
            os.remove(result)
            print("Temporary file cleaned up.")
        else:
            print("FAILED: Audio download returned None")
            
    except Exception as e:
        print("ERROR:", str(e))

if __name__ == "__main__":
    asyncio.run(test_audio_download())