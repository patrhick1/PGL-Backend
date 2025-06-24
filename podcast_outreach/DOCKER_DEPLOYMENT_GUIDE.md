# Docker Deployment Guide for PGL Podcast Outreach

This guide will help you deploy your FastAPI application using Docker.

## Prerequisites

1. Docker installed on your machine ([Download Docker](https://www.docker.com/get-started))
2. Docker Compose (usually comes with Docker Desktop)
3. Your `.env` file with all necessary environment variables

## Quick Start

### 1. Build and Run with Docker Compose (Recommended)

```bash
# Navigate to your project directory
cd podcast_outreach

# Build and start the container
docker-compose up --build

# To run in detached mode (background)
docker-compose up -d --build
```

### 2. Build and Run with Docker (Alternative)

```bash
# Build the Docker image
docker build -t pgl-podcast-app .

# Run the container
docker run -p 8000:8000 --env-file .env pgl-podcast-app
```

## Environment Variables

Make sure your `.env` file contains all required variables:

```env
# Database (Neon Postgres)
PGHOST=your-neon-host
PGPORT=5432
PGDATABASE=your-database
PGUSER=your-username
PGPASSWORD=your-password

# API Keys
GEMINI_API_KEY=your-key
OPENAI_API=your-key
ANTHROPIC_API=your-key
LISTEN_NOTES_API_KEY=your-key
PODSCANAPI=your-key
INSTANTLY_API_KEY=your-key
TAVILY_API_KEY=your-key

# Google Services
GOOGLE_APPLICATION_CREDENTIALS=path/to/credentials.json
GOOGLE_PODCAST_INFO_FOLDER_ID=your-folder-id
PGL_AI_DRIVE_FOLDER_ID=your-folder-id

# Application Settings
SESSION_SECRET_KEY=your-secret-key
PORT=8000
IS_PRODUCTION=false
FRONTEND_ORIGIN=http://localhost:5173
```

## Common Docker Commands

```bash
# View running containers
docker ps

# View logs
docker-compose logs -f

# Stop containers
docker-compose down

# Rebuild after code changes
docker-compose up --build

# Remove all containers and volumes
docker-compose down -v

# Enter the running container
docker exec -it pgl-podcast-app bash
```

## Production Deployment

### 1. Update Environment Variables

For production, update these variables in your `.env`:

```env
IS_PRODUCTION=true
FRONTEND_ORIGIN=https://your-frontend-domain.com
```

### 2. Build for Production

```bash
# Build production image
docker build -t pgl-podcast-app:production .

# Tag for your registry
docker tag pgl-podcast-app:production your-registry/pgl-podcast-app:latest

# Push to registry
docker push your-registry/pgl-podcast-app:latest
```

### 3. Deploy to Cloud Providers

#### AWS ECS/Fargate
1. Push image to ECR
2. Create task definition with environment variables
3. Create service with load balancer

#### Google Cloud Run
```bash
# Build and push to GCR
gcloud builds submit --tag gcr.io/your-project/pgl-podcast-app

# Deploy
gcloud run deploy pgl-podcast-app \
  --image gcr.io/your-project/pgl-podcast-app \
  --platform managed \
  --port 8000 \
  --set-env-vars-from-file .env.yaml
```

#### Azure Container Instances
```bash
# Push to ACR
az acr build --registry yourregistry --image pgl-podcast-app .

# Deploy
az container create \
  --resource-group yourgroup \
  --name pgl-podcast-app \
  --image yourregistry.azurecr.io/pgl-podcast-app \
  --ports 8000 \
  --environment-variables-file .env
```

## Troubleshooting

### Container won't start
- Check logs: `docker-compose logs`
- Verify all environment variables are set
- Ensure database is accessible from container

### Can't connect to database
- Verify PGHOST is accessible from Docker network
- Check firewall rules on Neon
- Ensure SSL mode is configured if required

### Application errors
- Check application logs inside container
- Verify all dependencies are installed
- Check file permissions

## Health Checks

The container includes a health check that hits `/api-status` endpoint. You can monitor this:

```bash
# Check health status
docker inspect pgl-podcast-app --format='{{.State.Health.Status}}'

# View health check logs
docker inspect pgl-podcast-app --format='{{range .State.Health.Log}}{{.Output}}{{end}}'
```

## Security Best Practices

1. Never commit `.env` files to version control
2. Use secrets management in production (AWS Secrets Manager, Google Secret Manager, etc.)
3. Keep base images updated
4. Run containers as non-root user (already configured)
5. Use specific version tags instead of `latest` in production

## Scaling

To scale your application:

```bash
# Scale to 3 instances
docker-compose up -d --scale web=3
```

Note: You'll need a load balancer in front of multiple instances.

## Monitoring

Consider adding:
- Prometheus metrics endpoint
- Logging to centralized service (CloudWatch, Stackdriver, etc.)
- APM tools (New Relic, DataDog, etc.)

## Support

For issues specific to Docker deployment, check:
- Container logs: `docker-compose logs`
- Application logs: `docker exec pgl-podcast-app cat /app/logs/app.log`
- System resources: `docker stats`