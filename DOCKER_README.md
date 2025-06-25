# Docker Setup Guide

## Directory Structure

The Docker files are now in the root directory to properly handle Python module imports:

```
PGL - Postgres/
├── Dockerfile              # Main Docker configuration
├── docker-compose.yml      # Local development orchestration
├── render.yaml            # Render.com deployment config
├── .dockerignore          # Files to exclude from Docker build
└── podcast_outreach/      # Your application code
    ├── main.py
    ├── requirements.txt
    ├── .env.docker        # Docker-specific environment variables
    ├── credentials/       # Google service account key
    ├── startup.sh         # Production startup script
    └── ...
```

## Local Development

1. **Setup environment**:
   ```bash
   cd "PGL - Postgres"
   # Copy your .env to podcast_outreach/.env.docker and adjust paths
   ```

2. **Run with Docker Compose**:
   ```bash
   docker-compose up --build
   ```

   This will:
   - Build the image from the root Dockerfile
   - Mount your local code for hot reloading
   - Use the .env.docker file from podcast_outreach/

## Production Deployment (Render)

1. **Push to GitHub** (Docker files are now in root):
   ```bash
   git add Dockerfile docker-compose.yml render.yaml .dockerignore
   git commit -m "Move Docker files to root for proper Python imports"
   git push
   ```

2. **On Render**:
   - The Dockerfile will be found in the root
   - Python imports will work correctly
   - All files in podcast_outreach/ will be copied to /app/podcast_outreach/

## Why This Structure?

- **Python imports**: Having Dockerfile in root allows proper module structure
- **Local dev**: docker-compose mounts the entire project, preserving the structure
- **Production**: Only the podcast_outreach/ folder is copied to the container
- **Works everywhere**: Same structure works locally and on Render

## Troubleshooting

If you get "ModuleNotFoundError: No module named 'podcast_outreach'":
- Ensure Dockerfile is in the root directory
- Check that COPY command includes `podcast_outreach/`
- Verify the working directory is `/app`