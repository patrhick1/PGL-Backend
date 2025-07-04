#!/usr/bin/env pgl_env/Scripts/python.exe
"""
Test which webhook endpoints exist in your FastAPI app
"""

import requests

BASE_URL = "http://localhost:8000"

def test_endpoints():
    """Test various webhook endpoint variations"""
    endpoints = [
        "/api/webhooks/instantly-email-sent",
        "/api/webhooks/instantly-reply-received",
        "/api/webhooks/instantly-email-opened",
        "/webhooks/instantly-email-sent",
        "/webhooks/instantly-reply-received",
        "/api/webhooks",
        "/webhooks"
    ]
    
    print("Testing webhook endpoints...")
    print("="*60)
    
    for endpoint in endpoints:
        url = f"{BASE_URL}{endpoint}"
        try:
            # Try GET first to see if endpoint exists
            response = requests.get(url)
            if response.status_code == 405:  # Method not allowed means endpoint exists but needs POST
                print(f"✓ {endpoint} - Exists (requires POST)")
            elif response.status_code == 404:
                print(f"✗ {endpoint} - Not found")
            else:
                print(f"? {endpoint} - Status: {response.status_code}")
                
            # Try POST for webhook endpoints
            if "email-sent" in endpoint or "reply-received" in endpoint:
                response = requests.post(url, json={"test": "data"})
                print(f"  POST: {response.status_code}")
                
        except Exception as e:
            print(f"✗ {endpoint} - Error: {e}")
    
    # Check OpenAPI docs to see all available endpoints
    print("\n" + "="*60)
    print("Checking API documentation...")
    try:
        response = requests.get(f"{BASE_URL}/docs")
        if response.status_code == 200:
            print("✓ API docs available at: http://localhost:8000/docs")
            print("  Check there for all available endpoints")
    except:
        pass

def main():
    print("FastAPI Webhook Endpoint Tester")
    print("="*60)
    print(f"Testing against: {BASE_URL}")
    print("="*60)
    
    test_endpoints()
    
    print("\n" + "="*60)
    print("If endpoints are not found:")
    print("1. Make sure your FastAPI app is running")
    print("2. Check if the webhook router is registered in main.py")
    print("3. The paths might be different (check /docs)")
    print("="*60)

if __name__ == "__main__":
    main()