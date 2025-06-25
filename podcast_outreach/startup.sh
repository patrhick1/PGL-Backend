#!/bin/bash

# Startup script for production deployments
# This script handles runtime configuration that can't be done at build time

echo "Starting PGL Podcast Backend..."

# Google credentials are now handled in config.py for better JSON parsing
# Just log if the environment variable is present
if [ ! -z "$GOOGLE_SERVICE_ACCOUNT_JSON" ]; then
    echo "Google service account JSON detected in environment"
fi

# Ensure FFmpeg paths are set (or empty for system defaults)
export FFMPEG_CUSTOM_PATH="${FFMPEG_CUSTOM_PATH:-}"
export FFPROBE_CUSTOM_PATH="${FFPROBE_CUSTOM_PATH:-}"

# Log the configuration (without sensitive data)
echo "Configuration:"
echo "- PORT: ${PORT:-8000}"
echo "- IS_PRODUCTION: ${IS_PRODUCTION:-false}"
echo "- FRONTEND_ORIGIN: ${FRONTEND_ORIGIN}"
echo "- Google credentials: $([ -f /tmp/service-account-key.json ] && echo 'Configured' || echo 'Not configured')"
echo "- Database: $([ ! -z "$DATABASE_URL" ] && echo 'Configured' || echo 'Not configured')"

# Start the application
echo "Starting Uvicorn..."
exec uvicorn podcast_outreach.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers ${WORKERS:-1} \
    --log-level ${LOG_LEVEL:-info}