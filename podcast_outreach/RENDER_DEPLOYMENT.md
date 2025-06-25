# Render.com Deployment Guide for PGL Podcast App

## Prerequisites
1. A Render.com account
2. Your application code pushed to GitHub
3. All API keys and credentials ready

## Step-by-Step Deployment to Render

### 1. Prepare Your Code for Deployment

First, create a `render.yaml` file in your `podcast_outreach` directory:

```yaml
services:
  - type: web
    name: pgl-podcast-backend
    runtime: docker
    dockerfilePath: ./Dockerfile
    dockerContext: .
    envVars:
      # Override for production
      - key: IS_PRODUCTION
        value: true
      
      # Your frontend URL
      - key: FRONTEND_ORIGIN
        value: https://your-frontend-domain.com
      
      # Port (Render handles this)
      - key: PORT
        value: 8000
```

### 2. Handle the Google Service Account Key

Since you can't mount files in Render, we'll use the JSON string approach:

#### Setting up Google Service Account JSON

1. **Copy your service account JSON as a single line:**
   ```bash
   # Remove newlines and copy to clipboard (Linux/Mac)
   cat credentials/service-account-key.json | jq -c . | pbcopy
   
   # Windows PowerShell
   Get-Content credentials/service-account-key.json | ConvertFrom-Json | ConvertTo-Json -Compress | Set-Clipboard
   ```

2. **The handling code is already prepared** in `config.py` (see below)

3. **In Render**, paste the JSON string into the `GOOGLE_SERVICE_ACCOUNT_JSON` environment variable

### 3. Set Environment Variables in Render

1. Go to your Render dashboard
2. Create a new Web Service
3. Connect your GitHub repository
4. In the Environment section, add all your variables:

```bash
# Neon PostgreSQL Database
PGHOST=your-neon-host.aws.neon.tech
PGPORT=5432
PGDATABASE=neondb
PGUSER=your-username
PGPASSWORD=your-password

# API Keys
AIRTABLE_PERSONAL_TOKEN=your_token
APIFY_API_KEY=your_key
MIPR_CRM_BASE_ID=your_base_id
GOOGLE_PODCAST_INFO_FOLDER_ID=your_folder_id
PGL_AI_DRIVE_FOLDER_ID=your_folder_id
LISTEN_NOTES_API_KEY=your_key
PODSCANAPI=your_key
PODCAST_BASE_ID=your_base_id
ANTHROPIC_API=your_key
OPENAI_API=your_key
GEMINI_API_KEY=your_key
FREE_GEMINI_KEY=your_key
ATTIO_ACCESS_TOKEN=your_token
INSTANTLY_API_KEY=your_key
TAVILY_API_KEY=your_key
CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID=your_folder_id

# Google Service Account (JSON string - paste as single line)
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"your-project",...}

# Email Configuration
GMAIL_USER=your_email
GMAIL_APP_PASSWORD=your_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email
SMTP_PASSWORD=your_password
FROM_EMAIL=your_email

# AWS Configuration
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_S3_BUCKET_NAME=your_bucket
AWS_REGION=your_region

# Application Settings
SESSION_SECRET_KEY=your_secret_key
FRONTEND_ORIGIN=https://your-frontend-url.com
IS_PRODUCTION=true

# FFmpeg (leave empty for system defaults)
FFMPEG_CUSTOM_PATH=
FFPROBE_CUSTOM_PATH=
```

### 4. Deploy

1. Click "Create Web Service"
2. Render will automatically:
   - Build your Docker image
   - Deploy your application
   - Set up HTTPS
   - Provide you with a URL

### 5. Post-Deployment

1. **Check logs**: Dashboard → Logs
2. **Monitor health**: Your app includes health checks at `/api-status`
3. **Set up custom domain**: Settings → Custom Domains

## Important Notes for Render

### Database Connections
- Neon PostgreSQL requires SSL (handled automatically by the connection library)
- Your connection details are split into individual variables (PGHOST, PGPORT, etc.)
- Connection pooling is handled by the application

### File Storage
- Render's filesystem is ephemeral
- Use S3 or similar for persistent file storage
- Temporary files (like decoded credentials) are fine

### Scaling
- Render supports auto-scaling on paid plans
- Configure in Settings → Scaling

### Environment Variables
- Never commit sensitive data
- Use Render's secret files feature for large configs
- Rotate keys regularly

## Troubleshooting

### Common Issues

1. **"Module not found" errors**
   - Ensure your Dockerfile copies all necessary files
   - Check that PYTHONPATH includes your app directory

2. **Database connection fails**
   - Verify all PG* variables are set correctly
   - Check that Neon allows connections from Render's IP ranges
   - Ensure PGHOST includes the full hostname (e.g., ep-xxx.region.aws.neon.tech)

3. **Google API authentication fails**
   - Verify the base64 encoding worked correctly
   - Check that the service account has necessary permissions

4. **Memory issues**
   - Upgrade to a larger instance
   - Optimize your code for memory usage

### Debug Commands

SSH into your Render service:
```bash
# Check environment variables
env | grep GOOGLE

# Check if credentials file was created
ls -la /tmp/service-account-key.json

# Check if JSON parsing worked
cat /tmp/service-account-key.json | jq .type

# Test database connection
python -c "import asyncpg; import asyncio; import os; asyncio.run(asyncpg.connect(host=os.getenv('PGHOST'), port=os.getenv('PGPORT'), database=os.getenv('PGDATABASE'), user=os.getenv('PGUSER'), password=os.getenv('PGPASSWORD'), ssl='require'))"
```

## Security Best Practices for Render

1. **Use environment groups** to manage variables across services
2. **Enable 2FA** on your Render account
3. **Restrict API access** using Render's private services
4. **Monitor usage** to detect anomalies
5. **Set up alerts** for failures and high usage

## Cost Optimization

- Start with Starter plan for testing
- Use background workers for heavy tasks
- Enable auto-scaling only when needed
- Monitor database usage to avoid overages

Remember: Always test your deployment in a staging environment first!