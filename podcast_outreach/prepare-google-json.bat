@echo off
REM Script to prepare Google service account JSON for Render deployment

echo Preparing Google service account JSON for Render deployment...
echo.

REM Check if the file exists
if not exist "credentials\service-account-key.json" (
    echo ERROR: credentials\service-account-key.json not found!
    echo Please ensure your service account key is in the credentials directory.
    exit /b 1
)

REM Create a minified version using PowerShell
echo Creating minified JSON...
powershell -Command "Get-Content credentials\service-account-key.json | ConvertFrom-Json | ConvertTo-Json -Compress | Out-File -Encoding UTF8 google-service-account-minified.json"
echo Minified JSON created

echo.
echo INSTRUCTIONS FOR RENDER:
echo ========================
echo 1. Copy the content below (it's a single line):
echo.
type google-service-account-minified.json
echo.
echo.
echo 2. In Render dashboard:
echo    - Go to Environment - Add Environment Variable
echo    - Key: GOOGLE_SERVICE_ACCOUNT_JSON
echo    - Value: [paste the JSON string above]
echo.
echo 3. Delete the temporary file when done:
echo    del google-service-account-minified.json
echo.
echo WARNING: This file contains sensitive credentials. Handle with care!
pause