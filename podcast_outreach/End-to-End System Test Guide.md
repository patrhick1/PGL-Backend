# End-to-End System Test Guide (API/CLI)

This document provides step-by-step instructions to test the full workflow of your Podcast Outreach Automation System, from client onboarding to pitch sending and response tracking. Since a full UI is not yet available, we will use FastAPI's Swagger UI (/docs), curl commands, and direct execution of Python scripts.

## Tools You'll Need

- **Terminal/Command Prompt**: For curl commands and running Python scripts
- **Web Browser**: To access Swagger UI (/docs) and view HTML dashboards
- **PostgreSQL Client** (e.g., psql, DBeaver, pgAdmin): To inspect database records and verify data at each step
- **Text Editor**: To create/modify .env files and potentially JSON payloads

## 0. Prerequisites & Initial Setup

Before you begin, ensure the following are in place:

### Project Cloned & Dependencies Installed

```bash
git clone <your-repo-url>
cd podcast_outreach
# If using Poetry (recommended)
poetry install
# If using pip
pip install -r requirements.txt
```

### .env File Configured

Create a `.env` file in the `podcast_outreach/` directory. Populate it with all necessary API keys and database credentials. Refer to `podcast_outreach/config.py` for a full list of expected variables.

Crucially, ensure you have:
- `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGPORT` for PostgreSQL
- `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API`, `LISTEN_NOTES_API_KEY`, `PODSCANAPI`, `INSTANTLY_API_KEY`, `ATTIO_ACCESS_TOKEN`, `TAVILY_API_KEY`
- `GOOGLE_APPLICATION_CREDENTIALS` (path to your service account JSON key)
- `PGL_AI_DRIVE_FOLDER_ID` (a Google Drive folder ID where AI usage logs will be backed up)
- `CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID` (a Google Drive folder ID for client status reports)

**Important**: For `podcast_outreach/api/dependencies.py`, the mock `ADMIN_USERS` and `STAFF_USERS` are hardcoded. For testing, you can use username: `admin`, password: `pgl_admin_password`. Change these in a real deployment!

### Database Schema Created/Updated

Run the schema script to ensure your database tables are up-to-date, including the new columns for episode analysis.

```bash
python podcast_outreach/database/schema.py
```

**Self-check**: Connect to your PostgreSQL database and verify the `episodes` table has `episode_themes` (TEXT[]), `episode_keywords` (TEXT[]), and `ai_analysis_done` (BOOLEAN) columns.

### FastAPI Application Running

Start the FastAPI backend. Keep this terminal window open.

```bash
uvicorn podcast_outreach.main:app --reload
```

The application should be accessible at http://127.0.0.1:8000 (or the port specified in config.py).

### Access Swagger UI

Open your browser and navigate to http://127.0.0.1:8000/docs. This interface allows you to interact with the API endpoints.

## 1. Test Flow Overview

We will simulate the following end-to-end process:

1. **Login**: Authenticate as an admin user
2. **Client Onboarding**: Create a client (Person) and a campaign for them. Trigger AI to generate their bio and angles
3. **Podcast Discovery**: Initiate a search for podcasts relevant to the campaign
4. **Match Review**: Manually approve a discovered podcast match
5. **Episode Processing**: Trigger the system to fetch, transcribe, and analyze episodes for the approved podcast
6. **Pitch Generation**: Generate a personalized pitch email for the approved match
7. **Pitch Approval & Sending**: Approve the pitch and send it via Instantly.ai
8. **Response Tracking**: Simulate Instantly webhooks for email sent and reply received
9. **Reporting**: Check AI usage reports

## 2. Detailed Test Steps

Throughout these steps, you'll need to copy IDs (UUIDs, integers) from API responses and use them in subsequent requests.

### Phase 0: Initial Setup & Verification

#### Verify FastAPI is Running

Open http://127.0.0.1:8000/api-status in your browser. You should see:

```json
{"message": "PGL Automation API is running (FastAPI version)!"}
```

#### Login to Get Session Cookie

1. Go to http://127.0.0.1:8000/login
2. Enter username: `admin`, password: `pgl_admin_password`
3. Click "Login"
4. You should be redirected to http://127.0.0.1:8000/

**Important**: Your browser now holds a `session_id` cookie. All subsequent requests made from this browser session (e.g., via Swagger UI) will automatically include this cookie for authentication. If using curl, you'll need to manually extract and pass this cookie. For simplicity, we'll primarily use Swagger UI for authenticated API calls.

### Phase 1: Client & Campaign Onboarding

#### Create a New Person (Client)

1. Go to Swagger UI (http://127.0.0.1:8000/docs)
2. Expand the **People** section
3. Find **POST /people/** (Create New Person). Click "Try it out"
4. Modify the Request body to create a new client. Example:

```json
{
  "full_name": "Test Client",
  "email": "test.client@example.com",
  "role": "client",
  "dashboard_username": "testclient",
  "dashboard_password_hash": "hashedpassword"
}
```

**Note**: `dashboard_password_hash` is usually set via a separate endpoint, but for initial creation, you can put a placeholder.

5. Click "Execute"
6. **Record the `person_id` from the response** (e.g., 1)

#### Set Password for the New Person (Optional but Recommended)

1. Still in People section, find **PUT /people/{person_id}/set-password**. Click "Try it out"
2. Enter the `person_id` you just recorded
3. In Request body, provide a plain password (e.g., `{"password": "securepassword123"}`)
4. Click "Execute". You should get a 204 No Content response

#### Create a New Campaign

1. Expand the **Campaigns** section
2. Find **POST /campaigns/** (Create New Campaign). Click "Try it out"
3. Modify the Request body. Use the `person_id` from step 1:

```json
{
  "person_id": <YOUR_PERSON_ID_HERE>,
  "campaign_name": "Test Campaign for Automation",
  "campaign_type": "B2B SaaS",
  "campaign_keywords": ["AI", "automation", "productivity", "software development"],
  "mock_interview_trancript": "This is a mock interview transcript for the test client. It talks about AI, automation, and how software development can boost productivity. The client has deep expertise in building scalable solutions.",
  "media_kit_url": "https://docs.google.com/document/d/1_YOUR_GOOGLE_DOC_ID_HERE_FOR_MEDIA_KIT/edit"
}
```

**Note**: For `mock_interview_trancript`, you can provide a short text directly. If you use a Google Doc link, ensure your Google Service Account has read access to it.

4. Click "Execute"
5. **Record the `campaign_id` (UUID) from the response** (e.g., afe3a4d7-5ed7-4fd4-9f8f-cf4e2ddc843d)

#### Trigger Bio & Angles Generation

1. Still in Campaigns section, find **POST /campaigns/{campaign_id}/generate-angles-bio** (Trigger Bio & Angles Generation). Click "Try it out"
2. Enter the `campaign_id` you just recorded
3. Click "Execute"
4. The response should indicate `status: success` or `processing_started`

#### Verification (DB)

Connect to your PostgreSQL client:

```sql
SELECT campaign_id, campaign_name, campaign_bio, campaign_angles, campaign_keywords 
FROM campaigns 
WHERE campaign_id = '<YOUR_CAMPAIGN_ID>';
```

Verify that `campaign_bio`, `campaign_angles` are populated (likely with Google Doc links if `create_document` was successful) and `campaign_keywords` is a list. Check the logs in your FastAPI terminal for AnglesProcessorPG activity.

### Phase 2: Podcast Discovery & Match Review

#### Trigger Podcast Discovery

1. Expand the **Match Suggestions** section
2. Find **POST /match-suggestions/campaigns/{campaign_id}/discover** (Discover podcasts for a campaign). Click "Try it out"
3. Enter the `campaign_id` you recorded
4. Click "Execute"

This will trigger searches on ListenNotes and Podscan using your campaign's keywords. It will create media records, match_suggestions, and review_tasks. This might take a moment.

5. The response will be a list of MatchSuggestionInDB objects
6. **Record one `match_id` (integer) from the response** (e.g., 101)

#### Verify Media and Match Suggestions in DB

Connect to your PostgreSQL client:

```sql
SELECT media_id, name, rss_url, source_api, last_fetched_at 
FROM media 
ORDER BY created_at DESC 
LIMIT 5;

SELECT match_id, campaign_id, media_id, match_score, status 
FROM match_suggestions 
WHERE campaign_id = '<YOUR_CAMPAIGN_ID>' 
ORDER BY created_at DESC;

SELECT review_task_id, task_type, related_id, status 
FROM review_tasks 
WHERE campaign_id = '<YOUR_CAMPAIGN_ID>' 
ORDER BY created_at DESC;
```

You should see new media entries, match_suggestions with `status: pending`, and review_tasks of type `match_suggestion`.

#### List Review Tasks (New API Endpoint)

1. Go to Swagger UI (http://127.0.0.1:8000/docs)
2. Expand the **Review Tasks** section.
3. Find **GET /review-tasks/** (List review tasks with filtering and pagination). Click "Try it out".
4. You can try filtering by `campaign_id` (using the one you recorded), `task_type` (e.g., `match_suggestion`), or `status` (e.g., `pending`).
5. Click "Execute".
6. Verify the response shows a list of review tasks, matching your filters, and includes pagination details.

#### Approve a Match Suggestion

1. Expand the **Match Suggestions** section (or use the **Review Tasks** PATCH endpoint if you prefer after verifying its functionality).
2. Find **PATCH /match-suggestions/{match_id}/approve** (Approve Match Suggestion). Click "Try it out"
3. Enter the `match_id` you recorded from step 1
4. Click "Execute"
5. The response should show the match_suggestion with `status: approved` and `client_approved: true`

#### Verification (DB)

```sql
SELECT match_id, status, client_approved, approved_at 
FROM match_suggestions 
WHERE match_id = <YOUR_MATCH_ID>;

SELECT review_task_id, task_type, related_id, status 
FROM review_tasks 
WHERE related_id = <YOUR_MATCH_ID> AND task_type = 'pitch_review';
```

The match should be approved, and a new review_task of type `pitch_review` should be created and marked pending.

### Phase 3: Episode Fetching & Processing

#### Trigger Episode Sync

1. Expand the **Background Tasks** section
2. Find **POST /tasks/run/{action}** (Trigger Background Automation Task). Click "Try it out"
3. For action, enter `fetch_podcast_episodes`
4. Click "Execute"

This will run the `sync_episodes.py` script in a background thread. It fetches episodes for media that need syncing, prunes old ones, and flags recent ones for transcription.

#### Verification (DB)

```sql
SELECT episode_id, media_id, title, publish_date, episode_url, transcribe, downloaded 
FROM episodes 
WHERE media_id = (SELECT media_id FROM match_suggestions WHERE match_id = <YOUR_MATCH_ID>) 
ORDER BY publish_date DESC;
```

You should see new episodes entries for the media_id associated with your approved match. Some recent episodes should have `transcribe = TRUE`.

#### Trigger Episode Transcription & Analysis

1. Still in Background Tasks section, find **POST /tasks/run/{action}**. Click "Try it out"
2. For action, enter `transcribe_podcast`
3. Click "Execute"

This will run the `transcribe_episodes.py` script in a background thread. It downloads audio, transcribes it, generates an AI summary, and then performs the new AI analysis (host/guest, themes, keywords). This can take a while depending on episode length and API speeds.

#### Verification (DB)

```sql
SELECT episode_id, title, 
       transcript IS NOT NULL AS has_transcript, 
       ai_episode_summary IS NOT NULL AS has_ai_summary, 
       ai_analysis_done, episode_themes, episode_keywords, guest_names 
FROM episodes 
WHERE media_id = (SELECT media_id FROM match_suggestions WHERE match_id = <YOUR_MATCH_ID>) 
ORDER BY publish_date DESC;
```

Verify that `transcript`, `ai_episode_summary`, `ai_analysis_done` are populated for the processed episodes. Check `episode_themes`, `episode_keywords`, and `guest_names` (which now stores identified hosts/guests).

### Phase 4: Pitch Generation & Outreach

#### Trigger Pitch Generation

1. Expand the **Pitches** section
2. Find **POST /pitches/generate** (Generate Pitch for Approved Match). Click "Try it out"
3. In Request body, provide the `match_id` you approved earlier:

```json
{
  "match_id": <YOUR_MATCH_ID_HERE>,
  "pitch_template_name": "friendly_intro_template"
}
```

4. Click "Execute"
5. The response should indicate `status: success` and provide a `pitch_gen_id` and `review_task_id`
6. **Record the `pitch_gen_id` (integer) and the new `review_task_id` (integer)** (e.g., 201, 301)

#### Verify Pitch Generation and Pitch Records in DB

Connect to your PostgreSQL client:

```sql
SELECT pitch_gen_id, campaign_id, media_id, draft_text, ai_model_used, generation_status, send_ready_bool 
FROM pitch_generations 
WHERE pitch_gen_id = <YOUR_PITCH_GEN_ID>;

SELECT pitch_id, campaign_id, media_id, subject_line, body_snippet, pitch_state, client_approval_status, pitch_gen_id 
FROM pitches 
WHERE pitch_gen_id = <YOUR_PITCH_GEN_ID>;

SELECT review_task_id, task_type, related_id, status 
FROM review_tasks 
WHERE review_task_id = <YOUR_PITCH_REVIEW_TASK_ID>;
```

You should see a new `pitch_generations` record (`generation_status: draft`, `send_ready_bool: false`), a new `pitches` record (`pitch_state: generated`, `client_approval_status: pending_review`), and the `pitch_review` task should be pending.

#### Approve Pitch Generation

1. Still in Pitches section, find **PATCH /pitches/generations/{pitch_gen_id}/approve** (Approve a Generated Pitch). Click "Try it out"
2. Enter the `pitch_gen_id` you just recorded
3. Click "Execute"
4. The response should show the pitch_generation with `send_ready_bool: true` and `generation_status: approved`

#### Verification (DB)

```sql
SELECT pitch_gen_id, generation_status, send_ready_bool 
FROM pitch_generations 
WHERE pitch_gen_id = <YOUR_PITCH_GEN_ID>;

SELECT pitch_id, pitch_state, client_approval_status 
FROM pitches 
WHERE pitch_gen_id = <YOUR_PITCH_GEN_ID>;

SELECT review_task_id, status 
FROM review_tasks 
WHERE review_task_id = <YOUR_PITCH_REVIEW_TASK_ID>;
```

The `pitch_generation` should be approved and `send_ready_bool: true`. The `pitches` record should be `pitch_state: ready_to_send`, `client_approval_status: approved`. The `pitch_review` task should be completed.

#### Trigger Pitch Sending to Instantly

1. Still in Pitches section, find **POST /pitches/{pitch_id}/send** (Send Pitch via Instantly.ai). Click "Try it out"
2. You need the `pitch_id` from the pitches table (not `pitch_gen_id`). You can get this from your DB query in the previous step
3. Enter the `pitch_id`
4. Click "Execute"
5. The response should indicate `status: accepted`

#### Verification (DB)

```sql
SELECT pitch_id, send_ts, pitch_state, instantly_lead_id 
FROM pitches 
WHERE pitch_id = <YOUR_PITCH_ID>;
```

The `pitch_id` should now have `send_ts` populated, `pitch_state: sent`, and `instantly_lead_id` populated with a UUID from Instantly.

### Phase 5: Response Tracking (Simulation)

The `process_webhooks.py` script can be used to simulate Instantly.ai webhook payloads. This script directly calls the `integrations.attio` functions that your FastAPI webhook router would call.

#### Simulate Instantly Email Sent Webhook

1. Open a new terminal window
2. Navigate to your project's `podcast_outreach/scripts` directory
3. You'll need the `instantly_lead_id` from the previous step
4. Create a dummy JSON file (e.g., `email_sent_payload.json`) with the following content, replacing `<YOUR_INSTANTLY_LEAD_ID>`:

```json
{
  "event": "lead.email_sent",
  "lead_id": "<YOUR_INSTANTLY_LEAD_ID>",
  "timestamp": "2025-05-23T10:00:00Z",
  "event_type": "EMAIL_SENT",
  "personalization": "Hello, this is a test email sent to you.",
  "attio_record_id": "rec_YOUR_ATTIO_PODCAST_RECORD_ID"
}
```

**Note**: The `attio_record_id` is crucial for Attio integration. If you don't have a real one, the Attio part of the webhook processing might fail or create a new dummy record. For this test, it's okay if Attio integration is not fully set up, as long as the pitches table updates.

5. Run the script, passing the JSON payload:

```bash
python podcast_outreach/scripts/process_webhooks.py < email_sent_payload.json
```

#### Verification (DB)

```sql
SELECT pitch_id, pitch_state 
FROM pitches 
WHERE instantly_lead_id = '<YOUR_INSTANTLY_LEAD_ID>';
```

The `pitch_state` should remain `sent` (as this event confirms sending, not a new state change).

#### Simulate Instantly Reply Received Webhook

1. Create another dummy JSON file (e.g., `reply_received_payload.json`) with the following content, replacing `<YOUR_INSTANTLY_LEAD_ID>`:

```json
{
  "event": "lead.reply_received",
  "lead_id": "<YOUR_INSTANTLY_LEAD_ID>",
  "timestamp": "2025-05-23T11:30:00Z",
  "event_type": "REPLY_RECEIVED",
  "reply_text_snippet": "Thanks for reaching out! I'm interested.",
  "attio_record_id": "rec_YOUR_ATTIO_PODCAST_RECORD_ID"
}
```

2. Run the script:

```bash
python podcast_outreach/scripts/process_webhooks.py < reply_received_payload.json
```

#### Verification (DB)

```sql
SELECT pitch_id, pitch_state, reply_bool, reply_ts 
FROM pitches 
WHERE instantly_lead_id = '<YOUR_INSTANTLY_LEAD_ID>';
```

The `pitch_state` should now be `replied`, `reply_bool` should be TRUE, and `reply_ts` should be populated.

### Phase 6: Monitoring & Reporting

#### Get AI Usage Report (API)

1. Expand the **AI Usage & Cost** section in Swagger UI
2. Find **GET /ai-usage/** (Get AI Usage Statistics). Click "Try it out"
3. You can leave parameters as default (`group_by: model`, `format: json`) or try `format: text` or `csv`
4. Click "Execute"
5. The response will show aggregated AI usage data

#### View AI Cost Dashboard (HTML)

1. Still in AI Usage & Cost section, find **GET /ai-usage/cost-dashboard/{pitch_gen_id}** (View AI Cost Dashboard for Pitch Generation). Click "Try it out"
2. Enter the `pitch_gen_id` you recorded earlier
3. Click "Execute"
4. This will open a new browser tab/window displaying an HTML report of the AI costs associated with that specific pitch generation

#### Generate Campaign Status Report (CLI)

1. Open a new terminal window
2. Navigate to your project's `podcast_outreach/scripts` directory
3. Run the report generation script:

```bash
python podcast_outreach/scripts/generate_reports.py campaign_status
```

This script will attempt to find or create a Google Sheet for your client (based on their `full_name`) in the Google Drive folder specified by `CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID`. It will then populate the sheet with weekly campaign metrics.

**Verification**: Check the Google Drive folder you configured. A new spreadsheet named "Test Client - Campaign Status Tracker" (or similar) should appear, populated with data.

## 3. Troubleshooting Tips

### HTTP 401 Unauthorized / HTTP 403 Forbidden
- Ensure you logged in successfully via http://127.0.0.1:8000/login
- Verify your `session_id` cookie is present in your browser
- Check if the endpoint requires admin privileges (`Depends(get_admin_user)`) and you are logged in as admin

### HTTP 500 Internal Server Error
- Check the FastAPI terminal logs immediately. This is where detailed Python tracebacks will appear
- Common causes: Missing environment variables, incorrect API keys, database connection issues, unexpected data formats from external APIs, or bugs in your Python code

### ValueError: API key not found / AuthenticationError
- Double-check your `.env` file for the specific API key mentioned in the error
- Ensure the `GOOGLE_APPLICATION_CREDENTIALS` path is correct and the service account JSON file exists and has the necessary permissions (Drive, Docs, Sheets)

### psycopg2.OperationalError
- Your PostgreSQL database might not be running, or your `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` environment variables are incorrect

### File not found (for prompts/templates)
- Ensure the paths in `services/ai/templates.py` and `services/matches/scorer.py` (for `prompt_determine_good_fit.txt`) are correct relative to the `podcast_outreach` directory

### AI Model Errors (e.g., ResourceExhausted, ServiceUnavailable, ContentPolicyViolation)
- You might be hitting rate limits for your AI API keys. Wait and retry
- Your API key might not have access to the specific model (e.g., `gemini-1.5-flash-001`)
- The content being sent to the LLM might be flagged by safety filters

### No leads found in campaign... (Instantly)
- Ensure the `instantly_campaign_id` in your campaigns table is a real, active campaign ID from your Instantly.ai account
- Verify your `INSTANTLY_API_KEY` is correct

### Could not find or create an Attio person record...
- Verify your `ATTIO_ACCESS_TOKEN` is correct
- Ensure the `ATTIO_PERSON_OBJECT_SLUG` and `ATTIO_PODCAST_OBJECT_SLUG` in `integrations/attio.py` match your Attio workspace's object slugs

By following these steps and carefully checking the logs and database at each stage, you should be able to verify the end-to-end functionality of your system.