#!/usr/bin/env python3

import requests
import json

# Test the API endpoint directly
BASE_URL = "http://localhost:8000"

def test_storage_api():
    print("=== Testing Storage API ===")
    
    # First, let's check if the server is running
    try:
        health_response = requests.get(f"{BASE_URL}/health")
        print(f"Health check: {health_response.status_code}")
    except requests.exceptions.ConnectionError:
        print("ERROR: Server is not running at http://localhost:8000")
        return
    
    # Test the storage endpoint (this should fail with 401 since we're not authenticated)
    print("\nTesting storage endpoint without auth...")
    payload = {
        "fileName": "profile.png", 
        "uploadContext": "profile_picture"
    }
    
    response = requests.post(
        f"{BASE_URL}/storage/generate-upload-url",
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
    
    if response.status_code == 401:
        print("OK: Got expected 401 Unauthorized (need to login first)")
    elif response.status_code == 500:
        print("ERROR: Server error - check if AWS is configured properly")
    else:
        print(f"Unexpected status code: {response.status_code}")

if __name__ == "__main__":
    test_storage_api()