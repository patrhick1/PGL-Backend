# Docker Deployment Guide for PGL Podcast App

## Overview
This guide explains how to securely deploy the PGL Podcast App using Docker, with proper handling of secrets and credentials.

## Local Development Setup

### 1. Initial Setup
Run the setup script to prepare your Docker environment:
```bash
cd podcast_outreach
./setup-docker-secrets.sh
```

This script will:
- Create a `credentials/` directory for your Google service account key
- Copy your `.env` file to `.env.docker` with Docker-specific paths
- Update `.gitignore` to exclude sensitive files

### 2. Manual Configuration
If the script doesn't find your files, manually:

1. Create `.env.docker` from the example:
   ```bash
   cp .env.docker.example .env.docker
   ```

2. Edit `.env.docker` and add your actual values

3. Place your Google service account key:
   ```bash
   mkdir -p credentials
   cp ../service-account-key.json credentials/
   ```

### 3. Run with Docker
```bash
docker-compose up --build
```

## Deployment to Production (Render, AWS, etc.)

### Environment Variables
Never commit `.env.docker` or credentials to version control. Instead:

1. **For Render.com:**
   - Go to your service's Environment tab
   - Add each variable from `.env.docker` individually
   - For the Google service account, use the file contents as a secret

2. **For AWS/Other Providers:**
   - Use AWS Secrets Manager or similar service
   - Store each API key as a separate secret
   - Mount secrets as environment variables

### Handling Google Service Account

#### Option 1: Environment Variable (Recommended for Production)
1. Convert your `service-account-key.json` to a base64 string:
   ```bash
   base64 -w 0 credentials/service-account-key.json > service-account-base64.txt
   ```

2. Add to your deployment platform as `GOOGLE_SERVICE_ACCOUNT_BASE64`

3. Update your application to decode it on startup:
   ```python
   import base64
   import json
   import os
   
   # In your config.py or startup code
   if os.getenv('GOOGLE_SERVICE_ACCOUNT_BASE64'):
       decoded = base64.b64decode(os.getenv('GOOGLE_SERVICE_ACCOUNT_BASE64'))
       with open('/tmp/service-account-key.json', 'w') as f:
           f.write(decoded.decode('utf-8'))
       os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = '/tmp/service-account-key.json'
   ```

#### Option 2: Secret Management Service
Use your cloud provider's secret management:
- **AWS**: Secrets Manager
- **GCP**: Secret Manager
- **Azure**: Key Vault

### Security Best Practices

1. **Never commit secrets** to version control
2. **Use different credentials** for development and production
3. **Rotate API keys** regularly
4. **Limit permissions** for service accounts to only what's needed
5. **Use read-only mounts** for credential files in Docker

### Sharing with Team Members

When sharing the project:

1. **Provide the example file**:
   - Share `.env.docker.example`
   - Team members create their own `.env.docker`

2. **Document required services**:
   - List all external services needed
   - Provide links to obtain API keys

3. **Use a password manager**:
   - Store shared credentials in a team password manager
   - Never share via email or chat

## Troubleshooting

### FFmpeg Issues
The Docker image includes FFmpeg. If you see errors:
- Ensure `FFMPEG_CUSTOM_PATH` and `FFPROBE_CUSTOM_PATH` are empty in `.env.docker`
- The application will automatically use system FFmpeg

### Google Credentials Issues
If Google APIs fail:
1. Check the credentials are mounted: `docker exec <container> ls -la /app/credentials/`
2. Verify the path in environment: `docker exec <container> env | grep GOOGLE`
3. Ensure the service account has necessary permissions

### Database Connection Issues
- Verify your database allows connections from Docker's IP
- Check if SSL is required (add `?sslmode=require` to DATABASE_URL)
- Ensure firewall rules allow the connection

## Example Deployment Configurations

### Render.com
```yaml
# render.yaml
services:
  - type: web
    name: pgl-podcast-app
    env: docker
    dockerfilePath: ./podcast_outreach/Dockerfile
    dockerContext: ./podcast_outreach
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: pgl-db
          property: connectionString
      # Add other environment variables in Render dashboard
```

### Docker Swarm/Kubernetes
Use Docker secrets or Kubernetes secrets:
```bash
# Create secrets
docker secret create google-creds ./credentials/service-account-key.json
kubectl create secret generic api-keys --from-env-file=.env.docker
```

Remember: Security is paramount. Always follow your organization's security policies when handling credentials and deploying applications.