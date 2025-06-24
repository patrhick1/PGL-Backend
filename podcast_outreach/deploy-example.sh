#!/bin/bash
# Example deployment script showing different environments

# Development
echo "Running in development mode..."
FRONTEND_ORIGIN=http://localhost:5173 docker-compose up

# Staging
echo "Running in staging mode..."
FRONTEND_ORIGIN=https://staging.myapp.com docker-compose up

# Production
echo "Running in production mode..."
FRONTEND_ORIGIN=https://myapp.com IS_PRODUCTION=true docker-compose up

# Or use .env files for different environments
# docker-compose --env-file .env.production up