# Simple Setup & Deployment Guide

This guide explains how to share your project with others and how they can run it.

## 🎁 For Project Owner (Sharing Your Project)

### What to Share

1. **Create a ZIP file with these folders/files:**
   ```
   podcast_outreach/
   ├── api/
   ├── database/
   ├── services/
   ├── static/
   ├── templates/
   ├── utils/
   ├── main.py
   ├── config.py
   ├── requirements.txt
   ├── Dockerfile
   ├── docker-compose.yml
   ├── .dockerignore
   └── .env.example
   ```

2. **Create `.env.example` file** (copy your .env but remove sensitive values):
   ```bash
   cp .env .env.example
   ```
   Then edit `.env.example` and replace actual values with placeholders:
   ```env
   # Database (They need their own Neon database)
   PGHOST=your-neon-host.neon.tech
   PGPORT=5432
   PGDATABASE=your-database-name
   PGUSER=your-username
   PGPASSWORD=your-password

   # API Keys (They need to get their own)
   GEMINI_API_KEY=get-from-google-ai-studio
   OPENAI_API=get-from-openai.com
   ANTHROPIC_API=get-from-anthropic.com
   LISTEN_NOTES_API_KEY=get-from-listennotes.com
   PODSCANAPI=get-from-podscan.fm
   INSTANTLY_API_KEY=get-from-instantly.ai
   TAVILY_API_KEY=get-from-tavily.com

   # Application Settings
   SESSION_SECRET_KEY=generate-a-random-string
   PORT=8000
   IS_PRODUCTION=false
   FRONTEND_ORIGIN=http://localhost:5173
   ```

3. **DO NOT SHARE:**
   - Your actual `.env` file
   - Any `pgl_env/` or virtual environment folders
   - `__pycache__/` folders
   - Any personal API keys or passwords

---

## 👥 For Your Friend (Running the Project)

### Prerequisites
- Install Docker Desktop: https://www.docker.com/products/docker-desktop/

### Step-by-Step Setup

1. **Extract the project** to a folder on your computer

2. **Open Terminal/Command Prompt** and navigate to the project:
   ```bash
   cd path/to/podcast_outreach
   ```

3. **Create your `.env` file**:
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Open `.env` in a text editor and fill in your actual values

4. **Get Required Services**:
   
   **Database (Required):**
   - Sign up for Neon: https://neon.tech
   - Create a new project
   - Copy connection details to your `.env`

   **API Keys (Get what you need):**
   - Google AI (Gemini): https://makersuite.google.com/app/apikey
   - OpenAI: https://platform.openai.com/api-keys
   - Anthropic: https://console.anthropic.com/settings/keys
   - Listen Notes: https://www.listennotes.com/api/
   - And others as needed...

5. **Run with Docker**:
   ```bash
   # Make sure Docker Desktop is running first!
   
   # Build and start the application
   docker-compose up --build
   ```

6. **Access the Application**:
   - Open browser: http://localhost:8000
   - Default login: Check with project owner for credentials

### Quick Commands

```bash
# Start the app
docker-compose up

# Stop the app
docker-compose down

# View logs if something goes wrong
docker-compose logs

# Restart after making changes
docker-compose restart
```

---

## 🚀 Deployment Options

### Option 1: Deploy to Render (Easiest)

1. **Push to GitHub** (project owner does this)
2. **On Render.com**:
   - Connect GitHub repo
   - Choose "Docker" environment
   - Add all environment variables
   - Deploy!

### Option 2: Deploy to Railway

1. **Install Railway CLI**: https://docs.railway.app/develop/cli
2. **Deploy**:
   ```bash
   railway login
   railway init
   railway up
   railway domain
   ```

### Option 3: Deploy to Google Cloud Run

1. **Install gcloud CLI**
2. **Deploy**:
   ```bash
   # Build and push
   gcloud builds submit --tag gcr.io/YOUR-PROJECT/pgl-app

   # Deploy
   gcloud run deploy --image gcr.io/YOUR-PROJECT/pgl-app --platform managed
   ```

### Option 4: Deploy to a VPS (DigitalOcean, Linode, etc.)

1. **SSH into your server**
2. **Install Docker**:
   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sh get-docker.sh
   ```
3. **Copy files and run**:
   ```bash
   # Copy your project files
   scp -r podcast_outreach/ user@your-server:/home/user/

   # SSH in and run
   ssh user@your-server
   cd podcast_outreach
   docker-compose up -d
   ```

---

## ❓ Troubleshooting

### "Cannot connect to database"
- Check your Neon connection string in `.env`
- Make sure Neon allows connections from your IP

### "Missing API key errors"
- Check `.env` file has all required keys
- Restart Docker after adding keys: `docker-compose restart`

### "Port already in use"
- Change PORT in `.env` to something else (like 8001)
- Or stop other services using port 8000

### "Docker command not found"
- Make sure Docker Desktop is installed and running
- On Windows: Make sure to use PowerShell or WSL2

---

## 📞 Getting Help

If you run into issues:
1. Check the logs: `docker-compose logs`
2. Make sure all `.env` variables are filled
3. Try rebuilding: `docker-compose down && docker-compose up --build`
4. Contact the project owner with the error message

---

## 🎯 Summary

**For Sharing:**
1. ZIP the project (without .env and virtual environments)
2. Include .env.example
3. Share this guide

**For Running:**
1. Install Docker
2. Create .env from .env.example
3. Run: `docker-compose up --build`
4. Open: http://localhost:8000

That's it! 🎉