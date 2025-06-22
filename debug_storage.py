#!/usr/bin/env python3

import os
from dotenv import load_dotenv

# Load the .env file
load_dotenv()

print("=== Environment Variables Check ===")
print(f"AWS_ACCESS_KEY_ID: {'SET' if os.getenv('AWS_ACCESS_KEY_ID') else 'NOT SET'}")
print(f"AWS_SECRET_ACCESS_KEY: {'SET' if os.getenv('AWS_SECRET_ACCESS_KEY') else 'NOT SET'}")
print(f"AWS_REGION: {os.getenv('AWS_REGION', 'NOT SET')}")
print(f"AWS_S3_BUCKET_NAME: {os.getenv('AWS_S3_BUCKET_NAME', 'NOT SET')}")

print("\n=== Testing Storage Service ===")
try:
    from podcast_outreach.services.storage_service import storage_service
    print("OK Storage service imported successfully")
    
    # Test generating a presigned URL
    test_key = "test/debug_test.png"
    url = storage_service.generate_presigned_upload_url(test_key)
    
    if url:
        print("OK Presigned URL generated successfully")
        print(f"URL: {url[:100]}...")
    else:
        print("FAIL Failed to generate presigned URL")
        
except Exception as e:
    print(f"ERROR testing storage service: {e}")
    import traceback
    traceback.print_exc()