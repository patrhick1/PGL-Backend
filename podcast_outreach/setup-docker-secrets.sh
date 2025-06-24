#!/bin/bash
# Script to set up Docker secrets securely

echo "Setting up Docker environment for PGL Podcast App..."

# Create credentials directory if it doesn't exist
if [ ! -d "./credentials" ]; then
    echo "Creating credentials directory..."
    mkdir -p ./credentials
fi

# Check if service account key exists in root directory
if [ -f "../service-account-key.json" ]; then
    echo "Copying service account key to credentials directory..."
    cp ../service-account-key.json ./credentials/
elif [ -f "./service-account-key.json" ]; then
    echo "Moving service account key to credentials directory..."
    mv ./service-account-key.json ./credentials/
else
    echo "WARNING: service-account-key.json not found!"
    echo "Please place your Google service account key in ./credentials/service-account-key.json"
fi

# Create .env.docker from .env if it doesn't exist
if [ ! -f ".env.docker" ] && [ -f "../.env" ]; then
    echo "Creating .env.docker from root .env file..."
    cp ../.env .env.docker
    
    # Update FFmpeg paths for Docker
    sed -i 's|FFMPEG_CUSTOM_PATH=.*|FFMPEG_CUSTOM_PATH=|' .env.docker
    sed -i 's|FFPROBE_CUSTOM_PATH=.*|FFPROBE_CUSTOM_PATH=|' .env.docker
    
    # Update Google credentials path
    sed -i 's|GOOGLE_APPLICATION_CREDENTIALS=.*|GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/service-account-key.json|' .env.docker
    
    echo ".env.docker created successfully!"
elif [ -f ".env.docker" ]; then
    echo ".env.docker already exists. Skipping creation."
else
    echo "WARNING: No .env file found in parent directory!"
    echo "Please create .env.docker based on .env.docker.example"
fi

# Add necessary entries to .gitignore
if [ -f ".gitignore" ]; then
    # Add credentials directory if not already ignored
    if ! grep -q "^credentials/$" .gitignore; then
        echo "credentials/" >> .gitignore
        echo "Added credentials/ to .gitignore"
    fi
    
    # Add .env.docker if not already ignored
    if ! grep -q "^\.env\.docker$" .gitignore; then
        echo ".env.docker" >> .gitignore
        echo "Added .env.docker to .gitignore"
    fi
fi

echo ""
echo "Setup complete! Next steps:"
echo "1. Verify your .env.docker file has all necessary variables"
echo "2. Ensure credentials/service-account-key.json exists"
echo "3. Run: docker-compose up --build"
echo ""
echo "For deployment or sharing:"
echo "- Never commit .env.docker or credentials/ to version control"
echo "- Use environment variables or secret management services"
echo "- See DOCKER_DEPLOYMENT.md for detailed instructions"