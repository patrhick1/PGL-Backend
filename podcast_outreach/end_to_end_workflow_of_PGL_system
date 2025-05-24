# End-to-End Workflow of the Podcast Outreach System

The system automates and streamlines the entire process of placing B2B clients on relevant podcasts, from initial discovery to successful placement and ongoing reporting. It leverages AI, external APIs, and a robust PostgreSQL backend.

## I. The Core Workflow Stages

Here's a breakdown of the typical lifecycle of a client campaign within the system:

### Phase 1: Client & Campaign Onboarding (Team Action)

#### Client/Person Creation:
- **Actor**: Internal Team (Admin).
- **Description**: A new client (person) is added to the system, typically including their name, email, and dashboard credentials.
- **Backend Interaction**: POST /people/ (creates a new people record).
- **Data**: people table.

#### Campaign Setup:
- **Actor**: Internal Team (Admin).
- **Description**: A new campaign is created for a client, defining its goals, keywords, and linking to the client's person record.
- **Backend Interaction**: POST /campaigns/ (creates a new campaigns record).
- **Data**: campaigns table.

#### Bio & Angles Generation:
- **Actor**: Internal Team (Staff/Admin) triggers, AI performs.
- **Description**: AI generates a comprehensive client bio and a set of talking angles/topics based on provided source materials (e.g., mock interview transcripts, articles, social posts). These are stored as Google Docs links and keywords are saved directly.
- **Backend Interaction**: POST /campaigns/{campaign_id}/generate-angles-bio (triggers services.campaigns.angles_generator.AnglesProcessorPG).
- **Data**: campaigns table (campaign_bio, campaign_angles, campaign_keywords), ai_usage_logs table (for tracking AI calls).

### Phase 2: Podcast Discovery & Match Review (System & Team Action)

#### Podcast Discovery & Initial Matching:
- **Actor**: Internal Team (Staff/Admin) triggers, System/AI performs.
- **Description**: The system searches external podcast databases (ListenNotes, Podscan) using campaign keywords. It then upserts discovered podcasts into the media table and creates initial match_suggestions between the campaign and relevant podcasts. A review_task is automatically created for each new match.
- **Backend Interaction**: POST /match-suggestions/campaigns/{campaign_id}/discover (triggers services.enrichment.discovery.DiscoveryService which uses services.media.podcast_fetcher.MediaFetcher).
- **Data**: media table, match_suggestions table, review_tasks table, ai_usage_logs table.

#### Media Enrichment (Background System Process):
- **Actor**: Background system process (e.g., scheduled task or continuous worker).
- **Description**: For newly added or stale media records, the system fetches additional details (social links, host names, audience metrics) from various sources (Apify, Gemini+Tavily) and calculates a quality_score.
- **Backend Interaction**: Triggered by POST /tasks/run/enrichment_pipeline (runs services.enrichment.enrichment_orchestrator.EnrichmentOrchestrator).
- **Data**: media table (updates various fields), ai_usage_logs table.

#### Episode Sync & Transcription Flagging (Background System Process):
- **Actor**: Background system process (e.g., scheduled task or continuous worker).
- **Description**: For active podcasts, the system fetches new episodes from RSS feeds or Podscan, inserts them into the episodes table, prunes old episodes, and flags the most recent ones for transcription.
- **Backend Interaction**: Triggered by POST /tasks/run/fetch_podcast_episodes (runs services.media.episode_sync.MediaFetcher).
- **Data**: episodes table, media table (updates last_fetched_at).

#### Episode Transcription & Summary (Background System Process):
- **Actor**: Background system process (e.g., scheduled task or continuous worker).
- **Description**: Downloads audio for flagged episodes, transcribes them using AI (Gemini), and generates AI summaries.
- **Backend Interaction**: Triggered by POST /tasks/run/transcribe_podcast (runs services.media.transcriber.MediaTranscriber).
- **Data**: episodes table (updates transcript, ai_episode_summary), ai_usage_logs table.

#### Match Review & Approval (Team/Client Action):
- **Actor**: Internal Team (Staff/Admin) or Client.
- **Description**: The team (or client, via their dashboard) reviews the match_suggestions and approves or rejects them. Approval triggers a new review_task for pitch generation.
- **Backend Interaction**: PATCH /match-suggestions/{match_id}/approve (updates match_suggestions status, creates review_tasks entry).
- **Data**: match_suggestions table, review_tasks table.

### Phase 3: Pitch Generation & Outreach (System & Team Action)

#### Pitch Generation:
- **Actor**: Internal Team (Staff/Admin) triggers, AI performs.
- **Description**: For approved matches, AI generates a personalized pitch email and subject line using client info, podcast details, and episode summaries/transcripts. A pitch_generation record is created, and a pitch_review task is generated.
- **Backend Interaction**: POST /pitches/generate (triggers services.pitches.generator.PitchGeneratorService).
- **Data**: pitch_generations table, pitches table (initial entry), review_tasks table, ai_usage_logs table.

#### Pitch Review & Approval:
- **Actor**: Internal Team (Staff/Admin).
- **Description**: The team reviews the AI-generated pitch and subject line, making any necessary edits. Upon approval, the pitch is marked send_ready_bool = TRUE.
- **Backend Interaction**: PATCH /pitches/generations/{pitch_gen_id}/approve (updates pitch_generations and pitches tables, completes review_tasks entry).
- **Data**: pitch_generations table, pitches table, review_tasks table.

#### Pitch Sending:
- **Actor**: Internal Team (Staff/Admin) triggers, System/External API performs.
- **Description**: Approved pitches are sent to the podcast host via Instantly.ai. The pitches record is updated with send timestamp and Instantly lead ID.
- **Backend Interaction**: POST /pitches/{pitch_id}/send (triggers services.pitches.sender.PitchSenderService).
- **Data**: pitches table (updates send_ts, pitch_state, instantly_lead_id).

### Phase 4: Response Tracking & Placement (System & Team Action)

#### Webhook Processing (Automated):
- **Actor**: External API (Instantly.ai) sends, System receives.
- **Description**: Instantly.ai sends webhooks for email events (sent, opened, replied). The system processes these to update the pitches table and sync relevant data to Attio CRM.
- **Backend Interaction**: POST /webhooks/instantly-email-sent, POST /webhooks/instantly-reply-received (triggers integrations.attio functions).
- **Data**: pitches table (updates reply_bool, reply_ts, pitch_state), Attio CRM.

#### Placement Tracking:
- **Actor**: Internal Team (Staff/Admin).
- **Description**: When a positive response leads to a booking, a placement record is created and tracked, including meeting dates, recording dates, and go-live dates. Status changes are logged in status_history.
- **Backend Interaction**: (Future UI: POST /placements/, PUT /placements/{id}).
- **Data**: placements table, status_history table.

### Phase 5: Monitoring & Reporting (Team Action)

#### AI Usage Reporting:
- **Actor**: Internal Team (Admin).
- **Description**: View detailed reports on AI token usage and costs, broken down by model, workflow, or specific pitch generation.
- **Backend Interaction**: GET /ai-usage, GET /ai-usage/cost-dashboard/{pitch_gen_id}.
- **Data**: ai_usage_logs table.

#### Campaign Status Reporting:
- **Actor**: Internal Team (Admin) triggers.
- **Description**: Generates and updates Google Sheets spreadsheets with weekly campaign performance metrics for clients.
- **Backend Interaction**: python podcast_outreach/scripts/generate_reports.py campaign_status.
- **Data**: pitches table, placements table, Google Sheets.

## II. Building the Team Management UI

The team management UI will be a comprehensive dashboard allowing internal staff and administrators to oversee and control all aspects of the podcast outreach system.

### 1. Authentication & Authorization

Your FastAPI backend already has robust authentication and authorization built into `podcast_outreach/api/dependencies.py` and `podcast_outreach/api/middleware.py`.

- **Login**: The frontend will send username and password via a POST request to POST /token.
- **Backend**: `api.routers.auth.login_for_access_token` handles this, authenticates against `ADMIN_USERS`/`STAFF_USERS` (or a proper people table lookup for dashboard users), creates a session ID, and returns it.
- **Frontend**: Upon successful login, the frontend receives the `session_id`. It should then set this `session_id` as an HttpOnly cookie in the browser. This is crucial for security, as HttpOnly cookies cannot be accessed by client-side JavaScript, preventing XSS attacks from stealing session tokens. The `main.py` already sets this cookie on RedirectResponse.
- **Session Validation**: For every subsequent request, the browser automatically sends the `session_id` cookie.
- **Backend**: `api.middleware.AuthMiddleware` intercepts requests, validates the `session_id` using `api.dependencies.validate_session`, and populates `request.state.session` with user info (username, role). If invalid, it redirects to `/login`.

#### Role-Based Access Control (RBAC):
- **Backend**: FastAPI dependencies like `Depends(get_current_user)` (for Staff/Admin) and `Depends(get_admin_user)` (for Admin only) ensure that only authorized users can access specific API endpoints.
- **Frontend**: The UI should dynamically adjust its navigation and available actions based on the logged-in user's role (e.g., hide "Admin" sections from Staff users). This role information can be fetched from GET /auth/me after login.

### 2. Key UI Modules/Pages & Backend Connections

The UI should be structured into logical modules, each interacting with specific backend API endpoints:

#### a. Dashboard Overview (/)
- **Purpose**: Provide a high-level summary of active campaigns, pending tasks, and system health.
- **Backend APIs**:
  - GET /tasks/: List all running background tasks.
  - GET /campaigns/: List recent campaigns.
  - GET /match-suggestions/campaign/{campaign_id}: Show pending matches for active campaigns.
  - GET /pitches/generations/: Show pending pitch reviews.
  - GET /ai-usage?group_by=workflow: Show overall AI usage summary.

#### b. Campaign Management (/campaigns)
- **Purpose**: Create, view, edit, and delete client campaigns. Trigger AI generation for bios and angles.
- **Backend APIs**:
  - GET /campaigns/: List all campaigns.
  - POST /campaigns/: Create a new campaign.
  - GET /campaigns/{campaign_id}: View details of a specific campaign.
  - PUT /campaigns/{campaign_id}: Update campaign details.
  - DELETE /campaigns/{campaign_id}: Delete a campaign.
  - POST /campaigns/{campaign_id}/generate-angles-bio: Trigger AI bio/angles generation.

#### c. Media (Podcast) Management (/media)
- **Purpose**: View and manage the database of discovered podcasts.
- **Backend APIs**:
  - GET /media/: List all media records.
  - POST /media/: Manually add a new media record (less common, usually via discovery).
  - GET /media/{media_id}: View details of a specific podcast.
  - PUT /media/{media_id}: Update podcast details.
  - DELETE /media/{media_id}: Delete a podcast record.

#### d. Match Review (/matches)
- **Purpose**: Review AI-generated match suggestions, approve or reject them.
- **Backend APIs**:
  - GET /match-suggestions/campaign/{campaign_id}: List match suggestions for a campaign.
  - PATCH /match-suggestions/{match_id}/approve: Approve a match.
  - (Future: PATCH /match-suggestions/{match_id}/reject to explicitly reject).

#### e. Pitch Review (/pitches)
- **Purpose**: Review AI-generated pitch drafts, make edits, and approve for sending.
- **Backend APIs**:
  - GET /pitches/generations/: List all pitch generations (especially those pending review).
  - GET /pitches/generations/{pitch_gen_id}: View a specific pitch generation.
  - PATCH /pitches/generations/{pitch_gen_id}/approve: Approve a pitch generation.
  - POST /pitches/{pitch_id}/send: Send an approved pitch.
  - GET /pitches/: List all sent pitches and their status.

#### f. Background Task Management (/tasks)
- **Purpose**: Monitor the status of long-running background tasks (e.g., episode sync, transcription, enrichment).
- **Backend APIs**:
  - GET /tasks/: List all running tasks.
  - GET /tasks/{task_id}/status: Get detailed status of a specific task.
  - POST /tasks/run/{action}: Manually trigger a task (e.g., fetch_podcast_episodes, transcribe_podcast, enrichment_pipeline).
  - POST /tasks/{task_id}/stop: Attempt to stop a running task.

#### g. Reporting (/reports)
- **Purpose**: View AI usage costs and campaign performance reports.
- **Backend APIs**:
  - GET /ai-usage/: Get overall AI usage statistics.
  - GET /ai-usage/cost-dashboard/{pitch_gen_id}: View detailed AI cost for a pitch generation.
  - (Campaign status reports are generated via CLI script, so the UI would link to the Google Sheet directly or display aggregated data if a new API endpoint is created).

### 3. Frontend Technologies for Team UI

#### Frameworks:
- **React, Vue.js, Angular, Svelte**: These are excellent choices for building single-page applications (SPAs) with component-based architectures. They provide robust state management, routing, and developer tooling.
- **Jinja2 (Current)**: Your current setup uses Jinja2 for basic HTML rendering. While functional for simple dashboards, it becomes less scalable for complex interactive UIs. You would typically use a modern JS framework for the main application, and keep Jinja2 only for initial page loads (like login) or very static content.
- **State Management**: (e.g., Redux, Vuex, Zustand, Pinia, NGRX) for managing application-wide data like user session, loading states, and cached API responses.
- **Styling**: CSS frameworks (Tailwind CSS, Bootstrap, Material-UI) or custom CSS for a consistent look and feel.

### 4. Connecting to the Backend (Team UI)

HTTP Client: Use fetch API (built-in browser API) or a library like Axios for making HTTP requests to your FastAPI backend.

**API Calls**:

```javascript
// Example: Fetching campaigns
async function fetchCampaigns() {
    try {
        const response = await fetch('/campaigns/', {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                // Session cookie is automatically sent by the browser for same-origin requests
            },
        });
        if (!response.ok) {
            if (response.status === 401) {
                window.location.href = '/login'; // Redirect to login on auth failure
            }
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        return data;
    } catch (error) {
        console.error("Error fetching campaigns:", error);
        // Display error message to user
        return [];
    }
}

// Example: Triggering AI generation
async function triggerAnglesBioGeneration(campaignId) {
    try {
        const response = await fetch(`/campaigns/${campaignId}/generate-angles-bio`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            // No body needed for this specific endpoint as per current API router
        });
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        console.log("AI generation triggered:", data);
        // Update UI to show task status or success message
    } catch (error) {
        console.error("Error triggering AI generation:", error);
        // Display error message
    }
}
```

- **Error Handling**: Implement global error handling (e.g., interceptors in Axios, or a custom fetch wrapper) to catch HTTP errors (401, 403, 500) and display user-friendly messages or redirect as necessary.
- **Loading States**: Show loading spinners or skeletons while data is being fetched.
- **Form Handling**: Use form libraries (e.g., Formik, React Hook Form) for complex forms, ensuring data validation before sending to the backend.
- **Real-time Updates**: For task monitoring, consider:
  - **Polling**: Periodically send GET /tasks/{task_id}/status requests.
  - **WebSockets (Advanced)**: For true real-time updates, you could integrate WebSockets into FastAPI (e.g., using Starlette's WebSocket capabilities) and have the backend push task status updates to connected clients. This would require more complex frontend and backend setup.

## III. Building the Client-Facing Dashboard

The client dashboard will offer a simplified, highly secure view of their specific campaigns and allow them to perform limited actions like approving matches or pitches.

### 1. Authentication & Authorization (Client UI)

This is the most critical aspect for a client-facing UI.

- **Client User Accounts**: You would typically create people records for your clients with `dashboard_username` and `dashboard_password_hash` fields. Their role could be `client`.
- **Login**: Clients would log in via POST /token using their `dashboard_username` and plain password.
- **Backend**: `api.dependencies.authenticate_user` would need to be extended to check the people table for `dashboard_username` and `dashboard_password_hash` (using `passlib.context.CryptContext` for password verification).

#### Strict Authorization (Row-Level Security):
- **Backend (Crucial)**: Every API endpoint accessed by the client UI must filter data based on the authenticated client's `person_id`.
  - For example, GET /campaigns/ for a client should internally translate to `SELECT * FROM campaigns WHERE person_id = <logged_in_client_person_id>`.
  - Similarly, PATCH /match-suggestions/{match_id}/approve must verify that the `match_id` belongs to a campaign associated with the logged-in client.
  - This means your database query functions (e.g., in `podcast_outreach/database/queries/`) will need to accept `person_id` as a parameter and include it in their WHERE clauses.
- **Frontend**: The UI should never assume it has access to all data. It should only display what the backend explicitly returns for the authenticated client.

### 2. Key UI Modules/Pages & Backend Connections (Client UI)

The client UI will be a subset of the team UI's functionality, with strict data filtering.

#### a. Client Dashboard (/client-dashboard)
- **Purpose**: Overview of their active campaigns and pending actions.
- **Backend APIs**:
  - GET /campaigns/: (Filtered by client's person_id).
  - GET /match-suggestions/campaign/{campaign_id}: (Filtered by client's person_id).
  - GET /pitches/generations/: (Filtered by client's person_id, showing only pending_review pitches).

#### b. My Campaigns (/client-campaigns)
- **Purpose**: View details of their campaigns.
- **Backend APIs**:
  - GET /campaigns/: List their campaigns.
  - GET /campaigns/{campaign_id}: View details of a specific campaign (must belong to them).

#### c. Match Approvals (/client-matches)
- **Purpose**: Review and approve/reject match suggestions for their campaigns.
- **Backend APIs**:
  - GET /match-suggestions/campaign/{campaign_id}: List their match suggestions.
  - PATCH /match-suggestions/{match_id}/approve: Approve a match (backend must verify ownership).

#### d. Pitch Approvals (/client-pitches)
- **Purpose**: Review and approve AI-generated pitches for their campaigns.
- **Backend APIs**:
  - GET /pitches/generations/: List their pitch generations pending review.
  - PATCH /pitches/generations/{pitch_gen_id}/approve: Approve a pitch (backend must verify ownership).

#### e. Campaign Progress (/client-progress)
- **Purpose**: Track the status of their pitches and placements.
- **Backend APIs**:
  - GET /pitches/: List their pitches.
  - GET /placements/campaign/{campaign_id}: List their placements.

### 3. Connecting to the Backend (Client UI)

The technical connection methods are similar to the team UI (Fetch/Axios). The key difference is the backend's rigorous enforcement of data ownership based on the authenticated client's `person_id`.

**Example of Backend Filtering for Client UI**:

In `podcast_outreach/api/routers/campaigns.py`, the `list_campaigns_api` and `get_campaign_api` would need to be modified or new endpoints created to filter by `person_id`.

```python
# In api/routers/campaigns.py (example for client-specific endpoint)

from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional, Dict, Any
import uuid

from api.schemas.campaign_schemas import CampaignInDB
from podcast_outreach.database.queries import campaigns as campaign_queries
from api.dependencies import get_current_user # This gets the logged-in user's info

router = APIRouter(prefix="/client-campaigns", tags=["Client Campaigns"])

@router.get("/", response_model=List[CampaignInDB], summary="List Client's Campaigns")
async def list_client_campaigns_api(
    skip: int = 0,
    limit: int = 100,
    user: dict = Depends(get_current_user) # Get current user info
):
    """
    Lists all campaign records belonging to the authenticated client.
    """
    client_person_id = user.get("person_id") # Assuming 'person_id' is added to user session/token
    if not client_person_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Client ID not found in session.")

    try:
        # This query function would need to be updated to accept person_id
        campaigns_from_db = await campaign_queries.get_campaigns_by_person_id(
            person_id=client_person_id,
            skip=skip,
            limit=limit
        )
        return [CampaignInDB(**c) for c in campaigns_from_db]
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# Similarly for /client-matches and /client-pitches
```

**Note on `api.dependencies.get_current_user`**: To make `user.get("person_id")` work, you'll need to store the `person_id` in the session data when the client logs in. This means:
1. When a client logs in, retrieve their `person_id` from the people table.
2. Store this `person_id` in the SESSIONS dictionary (or your actual session store) along with username and role.
3. Modify `api.dependencies.get_current_user` to return this `person_id` in the user dictionary.

## IV. General Frontend Development Considerations

- **API Design Consistency**: Your FastAPI backend is already designed with RESTful principles, which makes frontend integration straightforward. Maintain clear API contracts (request/response schemas).

- **Error Handling & User Feedback**:
  - Always handle API errors gracefully (e.g., network issues, 4xx/5xx responses).
  - Provide clear, actionable feedback to the user (e.g., "Failed to save data," "Invalid input," "Access Denied").
  - Implement toast notifications or alert messages for non-blocking feedback.

- **Loading States & Optimistic UI**:
  - Use loading indicators (spinners, skeletons) for data fetching.
  - Consider optimistic UI updates where appropriate (e.g., immediately show a match as "approved" on the UI while the API call is in progress, then revert if it fails).

- **Input Validation**: Implement client-side validation for forms to provide immediate feedback to users and reduce unnecessary API calls. Backend validation is still essential for security.

- **Security**:
  - **HTTPS**: Always deploy with HTTPS.
  - **CORS**: Configure CORS headers in FastAPI if your frontend is hosted on a different domain/port.
  - **Input Sanitization**: While FastAPI/Pydantic handles much of this, ensure any user-generated content displayed on the UI is properly sanitized to prevent XSS.
  - **Least Privilege**: Ensure both backend and frontend components only have the minimum necessary permissions.

- **Deployment**:
  - **Backend**: Your FastAPI app can be deployed using Gunicorn/Uvicorn behind a reverse proxy (Nginx, Caddy) on a cloud VM (AWS EC2, DigitalOcean, Google Cloud Run) or using serverless options.
  - **Frontend**: SPAs can be deployed on static site hosting services (Netlify, Vercel, AWS S3 + CloudFront) or served by your backend's web server.

By following this structured approach, you can effectively build powerful and secure UIs that fully leverage your well-migrated FastAPI backend.
