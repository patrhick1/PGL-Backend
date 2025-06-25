# Render Deployment Checklist

## Pre-Deployment Preparation

### 1. Prepare Google Service Account JSON
```bash
# Windows
./prepare-google-json.bat

# Linux/Mac  
./prepare-google-json.sh
```
This will create a single-line JSON string to paste into Render.

### 2. Gather All Environment Variables
You'll need to set these in Render's dashboard:

#### Database (Neon PostgreSQL)
- [ ] `PGHOST` - Your Neon host (e.g., ep-floral-frog-a6kkbjyj.us-west-2.aws.neon.tech)
- [ ] `PGPORT` - 5432
- [ ] `PGDATABASE` - neondb
- [ ] `PGUSER` - neondb_owner
- [ ] `PGPASSWORD` - Your password

#### API Keys
- [ ] `AIRTABLE_PERSONAL_TOKEN`
- [ ] `APIFY_API_KEY`
- [ ] `MIPR_CRM_BASE_ID`
- [ ] `GOOGLE_PODCAST_INFO_FOLDER_ID`
- [ ] `PGL_AI_DRIVE_FOLDER_ID`
- [ ] `LISTEN_NOTES_API_KEY`
- [ ] `PODSCANAPI`
- [ ] `PODCAST_BASE_ID`
- [ ] `ANTHROPIC_API`
- [ ] `OPENAI_API`
- [ ] `GEMINI_API_KEY`
- [ ] `FREE_GEMINI_KEY`
- [ ] `ATTIO_ACCESS_TOKEN`
- [ ] `INSTANTLY_API_KEY`
- [ ] `TAVILY_API_KEY`
- [ ] `CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID`

#### Google Service Account
- [ ] `GOOGLE_SERVICE_ACCOUNT_JSON` - The minified JSON string from step 1

#### Email Configuration
- [ ] `GMAIL_USER`
- [ ] `GMAIL_APP_PASSWORD`
- [ ] `SMTP_SERVER` - smtp.gmail.com
- [ ] `SMTP_PORT` - 587
- [ ] `SMTP_USERNAME`
- [ ] `SMTP_PASSWORD`
- [ ] `FROM_EMAIL`

#### AWS Configuration
- [ ] `AWS_ACCESS_KEY_ID`
- [ ] `AWS_SECRET_ACCESS_KEY`
- [ ] `AWS_S3_BUCKET_NAME`
- [ ] `AWS_REGION`

#### Application Settings
- [ ] `SESSION_SECRET_KEY`
- [ ] `FRONTEND_ORIGIN` - Your frontend URL (e.g., https://your-app.com)
- [ ] `IS_PRODUCTION` - true
- [ ] `PORT` - 8000 (Render will override this)

#### FFmpeg (Leave empty)
- [ ] `FFMPEG_CUSTOM_PATH` - (empty string)
- [ ] `FFPROBE_CUSTOM_PATH` - (empty string)

## Deployment Steps

### 1. Push to GitHub
```bash
git add .
git commit -m "Prepare for Render deployment"
git push origin master
```

### 2. Create New Web Service on Render
1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name**: pgl-podcast-backend
   - **Root Directory**: podcast_outreach
   - **Environment**: Docker
   - **Instance Type**: Start with Starter, upgrade as needed

### 3. Add Environment Variables
1. Before deploying, go to "Environment" tab
2. Add each variable from the checklist above
3. For `GOOGLE_SERVICE_ACCOUNT_JSON`, paste the entire minified JSON as the value

### 4. Deploy
1. Click "Create Web Service"
2. Render will build and deploy automatically
3. Watch the logs for any errors

## Post-Deployment Verification

### 1. Check Application Health
```bash
curl https://your-app.onrender.com/api-status
```

### 2. Verify in Logs
- Check for "Google credentials configured from JSON at /tmp/..."
- Ensure "Uvicorn running on http://0.0.0.0:8000"
- No database connection errors

### 3. Test Endpoints
- [ ] `/docs` - Should show API documentation
- [ ] `/api-status` - Should return health status
- [ ] Try a simple API call

## Troubleshooting

### If Google Auth Fails
1. Check logs for "Error parsing GOOGLE_SERVICE_ACCOUNT_JSON"
2. Ensure the JSON was pasted correctly (no extra quotes or escaping)
3. Verify the service account has necessary permissions

### If Database Connection Fails
1. Verify all PG* variables are set
2. Check that Neon allows connections from Render IPs
3. Look for connection errors in logs

### If Build Fails
1. Check Dockerfile syntax
2. Ensure all required files are committed to Git
3. Check build logs for specific errors

## Important Notes
- Never commit credentials to Git
- The `google-service-account-minified.json` file is temporary - delete after use
- Render provides automatic HTTPS
- Your app will be available at: https://[your-service-name].onrender.com