#!/bin/bash
# Script to prepare Google service account JSON for Render deployment

echo "Preparing Google service account JSON for Render deployment..."
echo ""

# Check if the file exists
if [ ! -f "credentials/service-account-key.json" ]; then
    echo "ERROR: credentials/service-account-key.json not found!"
    echo "Please ensure your service account key is in the credentials directory."
    exit 1
fi

# Create a minified version
echo "Creating minified JSON..."
if command -v jq &> /dev/null; then
    # Use jq if available
    jq -c . credentials/service-account-key.json > google-service-account-minified.json
    echo "✓ Minified JSON created using jq"
else
    # Fallback to Python
    python3 -c "import json; print(json.dumps(json.load(open('credentials/service-account-key.json'))))" > google-service-account-minified.json
    echo "✓ Minified JSON created using Python"
fi

echo ""
echo "INSTRUCTIONS FOR RENDER:"
echo "========================"
echo "1. Copy the content below (it's a single line):"
echo ""
cat google-service-account-minified.json
echo ""
echo ""
echo "2. In Render dashboard:"
echo "   - Go to Environment → Add Environment Variable"
echo "   - Key: GOOGLE_SERVICE_ACCOUNT_JSON"
echo "   - Value: [paste the JSON string above]"
echo ""
echo "3. Delete the temporary file when done:"
echo "   rm google-service-account-minified.json"
echo ""
echo "WARNING: This file contains sensitive credentials. Handle with care!"