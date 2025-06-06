import requests
import json

# --- Configuration ---
BASE_URL = "http://localhost:8000"
CAMPAIGN_ID = "e06da4a9-8f84-452b-b3a8-0de1a1006b5c" # Replace with your desired campaign_id
MAX_MATCHES = 10  # Replace with your desired limit, or None

# Construct the correct endpoint URL
endpoint_path = f"/match-suggestions/campaigns/{CAMPAIGN_ID}/discover"
params = {}
if MAX_MATCHES is not None:
    params["max_matches"] = MAX_MATCHES

full_url = BASE_URL + endpoint_path

# Headers - Mimic your cURL headers as much as necessary
# The most important one for authentication is usually the cookie.
headers = {
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Content-Type': 'application/json', # Important for POST requests with a body
    'Origin': 'http://localhost:5173',
    'Referer': 'http://localhost:5173/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    'sec-ch-ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    # Add other Sec-Fetch-* headers if you find they are strictly required by your CORS policy or server
}

# Cookies - Extracted from your cURL command's -b argument
# The 'session' cookie seems to be the authentication token.
cookies = {
    'ajs_anonymous_id': '"26a0e4b8-8425-46bd-b226-bd1aceeefc31"', # Ensure quotes are handled if they are part of the value
    'session': 'eyJ1c2VybmFtZSI6ICJwYXNjaGFsQDNyZGJyYWluLmNvIiwgInJvbGUiOiAiYWRtaW4iLCAicGVyc29uX2lkIjogMzAsICJmdWxsX25hbWUiOiAiUEdMIEFkbWluaXN0cmF0b3IifQ==.aD9Upg.y0MH4Bfn6uS62AiqxU0J1f2bjNg'
}

# Body - an empty JSON object as in your cURL command
data_raw = {}

print(f"Sending POST request to: {full_url}")
print(f"With params: {params}")
print(f"With headers: {json.dumps(headers, indent=2)}")
print(f"With cookies: {cookies}")
print(f"With data: {json.dumps(data_raw)}")

try:
    response = requests.post(
        full_url,
        headers=headers,
        params=params, # Query parameters are passed here for GET/POST etc.
        cookies=cookies,
        json=data_raw # Use json parameter for requests to auto-serialize dict and set Content-Type
    )

    print(f"\n--- Response ---")
    print(f"Status Code: {response.status_code}")
    try:
        print(f"Response JSON: {response.json()}")
    except requests.exceptions.JSONDecodeError:
        print(f"Response Text: {response.text}")

except requests.exceptions.RequestException as e:
    print(f"\n--- Error ---")
    print(f"An error occurred: {e}")
