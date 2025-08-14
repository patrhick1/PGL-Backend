#!/usr/bin/env python
"""Test the webhook challenge response locally."""

import requests
import json

def test_challenge_response(base_url="http://localhost:8000"):
    """Test the webhook challenge endpoint."""
    
    # Test challenge parameter
    challenge_value = "test-challenge-12345"
    
    # Test the endpoint with a challenge parameter
    url = f"{base_url}/webhooks/nylas/events"
    params = {"challenge": challenge_value}
    
    print(f"Testing webhook challenge at: {url}")
    print(f"Challenge value: {challenge_value}")
    print("-" * 50)
    
    try:
        # Send GET request with challenge parameter
        response = requests.get(url, params=params, timeout=5)
        
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type')}")
        print(f"Response Text: '{response.text}'")
        print("-" * 50)
        
        # Verify the response
        if response.status_code == 200:
            if response.text == challenge_value:
                print("✓ Challenge response is CORRECT")
                print("  - Returns raw challenge value")
                print("  - Content-Type is text/plain")
                print("  - No extra characters or quotes")
            else:
                print("✗ Challenge response is INCORRECT")
                print(f"  Expected: '{challenge_value}'")
                print(f"  Got: '{response.text}'")
                print(f"  Length difference: {len(response.text) - len(challenge_value)}")
                
                # Check for common issues
                if response.text.startswith('"') and response.text.endswith('"'):
                    print("  Issue: Response is JSON-encoded (has quotes)")
                if '\n' in response.text:
                    print("  Issue: Response contains newlines")
                if response.text != response.text.strip():
                    print("  Issue: Response has leading/trailing whitespace")
        else:
            print(f"✗ Unexpected status code: {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("✗ Could not connect to the server")
        print("  Make sure your FastAPI app is running on port 8000")
    except requests.exceptions.Timeout:
        print("✗ Request timed out")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("\n" + "=" * 50)
    print("WEBHOOK ENDPOINT REQUIREMENTS:")
    print("=" * 50)
    print("For Nylas v3 webhooks, the endpoint MUST:")
    print("1. Accept GET requests at the exact webhook URL")
    print("2. Look for a 'challenge' query parameter")
    print("3. Return the raw challenge value (no JSON encoding)")
    print("4. Use Content-Type: text/plain")
    print("5. Respond within 10 seconds")
    print("\nYour current endpoint at /webhooks/nylas/events:")
    print("- Line 66-77 in nylas_webhooks.py handles this correctly")

if __name__ == "__main__":
    test_challenge_response()