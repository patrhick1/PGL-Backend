@echo off
echo Setting up Docker environment for PGL Podcast App...

REM Create credentials directory if it doesn't exist
if not exist "credentials" (
    echo Creating credentials directory...
    mkdir credentials
)

REM Check if service account key exists in root directory
if exist "..\service-account-key.json" (
    echo Copying service account key to credentials directory...
    copy "..\service-account-key.json" "credentials\"
) else if exist "service-account-key.json" (
    echo Moving service account key to credentials directory...
    move "service-account-key.json" "credentials\"
) else (
    echo WARNING: service-account-key.json not found!
    echo Please place your Google service account key in credentials\service-account-key.json
)

REM Create .env.docker from .env if it doesn't exist
if not exist ".env.docker" (
    if exist "..\.env" (
        echo Creating .env.docker from root .env file...
        copy "..\.env" ".env.docker"
        echo .env.docker created successfully!
        echo Please update FFMPEG paths and GOOGLE_APPLICATION_CREDENTIALS in .env.docker
    ) else (
        echo WARNING: No .env file found in parent directory!
        echo Please create .env.docker based on .env.docker.example
    )
) else (
    echo .env.docker already exists. Skipping creation.
)

echo.
echo Setup complete! Next steps:
echo 1. Edit .env.docker to set:
echo    - FFMPEG_CUSTOM_PATH=(leave empty)
echo    - FFPROBE_CUSTOM_PATH=(leave empty)
echo    - GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account-key.json
echo 2. Ensure credentials\service-account-key.json exists
echo 3. Run: docker-compose up --build
echo.
pause