# 🎙️ Podcast Outreach Automation System

This project automates the process of placing B2B clients on relevant podcasts. It has successfully transitioned from a legacy Airtable-based workflow to a robust, scalable PostgreSQL + AI-powered backend system, built for efficiency, personalization, and comprehensive team control.

---

## 📌 Project Status: Migration Complete!

The entire codebase has been successfully migrated from the legacy Airtable-centric architecture to a robust, scalable PostgreSQL-backed system. All core functionalities are now integrated within the `podcast_outreach/` package, adhering to a clean separation of concerns.

The `src/` and `legacy/` directories, containing the old codebase and Airtable dependencies, have been deprecated and can now be safely removed.

---

## 🧠 Key Features & Architecture Benefits

This system is designed with modularity, scalability, and maintainability in mind, offering:

*   **Automated Discovery & Matching**: Efficiently finds and analyzes podcasts from various sources (ListenNotes, Podscan) and suggests matches for client campaigns.
*   **AI-Powered Content Generation**: Leverages advanced AI models (Gemini, Claude, OpenAI) to generate client bios, talking angles, personalized pitch drafts, and episode summaries.
*   **Structured Data Management**: All operational data, including campaigns, media, episodes, pitches, and AI usage logs, is stored and managed in a PostgreSQL database.
*   **Streamlined Workflows**: Supports end-to-end outreach, from initial discovery and match review to pitch generation, sending, and response tracking.
*   **Internal Dashboard & Reporting**: Provides a FastAPI-based internal dashboard for team review, task management, and detailed AI usage and campaign performance reports.
*   **External Integrations**: Seamlessly connects with third-party services like Instantly.ai (for email outreach), Attio (CRM), Google Docs/Sheets (for client content and reporting), and Apify (for social scraping).

---

## 📁 Project Structure

The entire application code now resides within the `podcast_outreach/` package, organized into distinct layers:

```
podcast_outreach/
├── README.md
├── LICENSE.txt
├── .env # Environment variables (ignored by Git)
├── pyproject.toml # Poetry dependency management
├── requirements.txt # Python dependencies (for pip users)
├── .gitignore # Git ignore rules
─────────────────────────────────────────────────────────────
📁 App Entry & Configuration
├── main.py # Main FastAPI application entry point
├── config.py # Centralized environment variables, constants
├── logging_config.py # Standardized logging setup
─────────────────────────────────────────────────────────────
📁 Web App Layer (FastAPI app, HTML routes, templates)
├── api/
│ ├── __init__.py
│ ├── routers/ # Modular FastAPI routers for different domains
│ │ ├── ai_usage.py # AI usage & cost reporting endpoints
│ │ ├── auth.py # Authentication endpoints
│ │ ├── campaigns.py # Campaign management endpoints
│ │ ├── health.py # Health check endpoint
│ │ ├── matches.py # Match suggestion endpoints
│ │ ├── media.py # Media (podcast) management endpoints
│ │ ├── people.py # People (client/host) management endpoints
│ │ ├── pitches.py # Pitch generation & sending endpoints
│ │ ├── tasks.py # Background task triggering & monitoring
│ │ └── webhooks.py # Webhook handlers (e.g., Instantly.ai)
│ ├── dependencies.py # Reusable FastAPI dependencies (e.g., auth, DB session)
│ └── middleware.py # Custom middleware (e.g., authentication)
│ └── schemas/ # Pydantic request/response models
│ ├── __init__.py
│ ├── auth_schemas.py
│ ├── base_schemas.py
│ ├── campaign_schemas.py
│ ├── match_schemas.py
│ ├── media_schemas.py
│ ├── person_schemas.py
│ └── pitch_schemas.py
├── templates/ # Jinja2 HTML templates for dashboard UI
│ ├── dashboard.html # Main user dashboard
│ ├── login.html
│ └── podcast_cost.html # AI usage cost reporting dashboard
├── static/ # Static assets (CSS, JS) for web UI
│ ├── dashboard.css
│ ├── dashboard.js
│ └── styles.css
─────────────────────────────────────────────────────────────
📁 Business Logic (Core domain services)
├── services/
│ ├── __init__.py
│ ├── ai/ # AI service clients and utilities
│ │ ├── anthropic_client.py
│ │ ├── gemini_client.py
│ │ ├── openai_client.py
│ │ ├── prompts/ # Directory for AI prompt templates (.txt files)
│ │ │ └── pitch/
│ │ │ ├── friendly_intro_template.txt
│ │ │ └── subject_line_template.txt
│ │ ├── tavily_client.py # Tavily Search API client
│ │ ├── templates.py # Loader for AI prompt templates
│ │ └── tracker.py # AI usage tracking (now DB-backed)
│ ├── campaigns/ # Client campaign management and content generation
│ │ ├── angles_generator.py # Generates talking angles
│ │ ├── bio_generator.py # Generates client bios
│ │ ├── enrichment_orchestrator.py # Orchestrates campaign data enrichment
│ │ └── summary_builder.py
│ ├── enrichment/ # Data enrichment and quality scoring
│ │ ├── data_merger.py # Merges data from various sources
│ │ ├── discovery.py # Podcast discovery orchestration
│ │ ├── enrichment_agent.py # Coordinates enrichment for a single podcast
│ │ ├── enrichment_orchestrator.py # Orchestrates the full enrichment pipeline
│ │ ├── quality_score.py # Calculates podcast quality scores
│ │ └── social_scraper.py # Scrapes social media metrics via Apify
│ ├── matches/ # Campaign-to-podcast matching algorithms
│ │ ├── filter.py
│ │ └── scorer.py # Assesses podcast-client fit
│ ├── media/ # Podcast data fetching, analysis, and transcription
│ │ ├── analyzer.py # Identifies hosts/guests from episode content
│ │ ├── episode_sync.py # Fetches & syncs podcast episodes
│ │ ├── podcast_fetcher.py # Podcast search and initial media upsert
│ │ └── transcriber.py # Transcribes podcast audio
│ ├── pitches/ # Pitch generation and delivery
│ │ ├── generator.py # Generates personalized pitches
│ │ ├── sender.py # Sends pitches via Instantly.ai
│ │ └── templates.py # Placeholder for pitch-specific templates/logic
│ └── tasks/
│ └── manager.py # Manages background tasks
─────────────────────────────────────────────────────────────
📁 Data Layer (PostgreSQL models, queries, schema)
├── database/
│ ├── __init__.py
│ ├── models/ # Database table models (Pydantic for ORM-like mapping)
│ │ ├── campaign_models.py
│ │ ├── llm_outputs.py
│ │ ├── media_models.py
│ │ └── pitch_models.py
│ ├── queries/ # Domain-specific database query functions
│ │ ├── __init__.py
│ │ ├── ai_usage.py # AI usage logs queries
│ │ ├── campaigns.py
│ │ ├── connection.py # PostgreSQL connection pool management
│ │ ├── episodes.py
│ │ ├── instantly_leads.py # Legacy Instantly leads backup (to be refactored/removed)
│ │ ├── match_suggestions.py
│ │ ├── media.py
│ │ ├── people.py
│ │ ├── pitch_generations.py # Pitch generation queries
│ │ ├── pitches.py
│ │ ├── placements.py
│ │ └── review_tasks.py
│ └── schema.py # Complete PostgreSQL schema definition (for initial setup)
─────────────────────────────────────────────────────────────
📁 Integrations (APIs, CRMs, External Tools)
├── integrations/
│ ├── __init__.py
│ ├── attio.py # Attio CRM client (now includes webhook processing)
│ ├── base_client.py # Abstract base for external API clients
│ ├── google_docs.py
│ ├── google_sheets.py
│ ├── instantly.py # Instantly.ai API client
│ ├── listen_notes.py
│ └── podscan.py
─────────────────────────────────────────────────────────────
📁 CLI & Scheduled Scripts (One-time jobs, recurring tasks)
├── scripts/
│ ├── generate_reports.py # Generates AI usage and campaign status reports
│ ├── instantly_leads_db.py # Legacy Instantly leads backup script (to be refactored/removed)
│ ├── migrate_clients.py # One-time script to migrate client/campaign data
│ ├── process_webhooks.py # Processes Instantly.ai webhooks (CLI/standalone version)
│ ├── sync_crm.py # Syncs Instantly leads to Attio CRM
│ ├── sync_episodes.py # Script to trigger episode sync
│ └── transcribe_episodes.py # Script to trigger transcription
─────────────────────────────────────────────────────────────
📁 Utilities
└── utils/
├── data_processor.py
├── exceptions.py
└── file_manipulation.py
```

---

## 🛠️ How to Use

### Setup

1.  **Clone the repository**:
    ```bash
    git clone <your-repo-url>
    cd podcast_outreach
    ```

2.  **Install dependencies** (using Poetry, or pip with `requirements.txt`):
    ```bash
    # If using Poetry (recommended)
    poetry install

    # If using pip
    pip install -r requirements.txt
    ```

3.  **Configure Environment Variables**: Create a `.env` file in the `podcast_outreach/` directory with your API keys and database credentials. Refer to `config.py` for required variables (e.g., `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `INSTANTLY_API_KEY`, `ATTIO_ACCESS_TOKEN`, `GOOGLE_APPLICATION_CREDENTIALS`, `CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID`, `PGL_AI_DRIVE_FOLDER_ID`).

4.  **Create your PostgreSQL database schema**:
    ```bash
    python podcast_outreach/database/schema.py
    ```
    *(Note: If you have existing data, consider using a proper migration tool like Alembic for schema updates to avoid data loss.)*

### Running the FastAPI Internal Dashboard

To run the main FastAPI application, which serves the internal dashboard and API endpoints:

```bash
uvicorn podcast_outreach.main:app --reload
```

Access the dashboard at http://127.0.0.1:8000/ (or the PORT specified in config.py). You will be redirected to the login page.

### Triggering Automations (via API or Scripts)

#### API Endpoints

The core functionalities are exposed via FastAPI endpoints under `podcast_outreach/api/routers/`. For example:

- `POST /campaigns/{campaign_id}/discover`: To initiate podcast discovery for a campaign.
- `PATCH /match-suggestions/{match_id}/approve`: To approve a match and trigger pitch generation.
- `POST /pitches/generate`: To manually trigger pitch generation for an approved match.
- `PATCH /pitches/generations/{pitch_gen_id}/approve`: To approve a generated pitch for sending.
- `POST /pitches/{pitch_id}/send`: To send an approved pitch via Instantly.ai.
- `GET /ai-usage`: To retrieve AI usage reports.
- `GET /ai-usage/cost-dashboard/{pitch_gen_id}`: To view a detailed AI cost dashboard for a specific pitch generation.
- `POST /tasks/run/{action}`: To trigger various background automation tasks (e.g., `generate_bio_angles`, `fetch_podcast_episodes`, `transcribe_podcast`).

#### CLI Scripts

For batch processing or one-off tasks, refer to `podcast_outreach/scripts/`:

- `python podcast_outreach/scripts/sync_episodes.py`: To fetch and sync new podcast episodes.
- `python podcast_outreach/scripts/transcribe_episodes.py`: To transcribe flagged episodes.
- `python podcast_outreach/scripts/generate_reports.py ai_usage --format text`: To generate AI usage reports from the command line.
- `python podcast_outreach/scripts/generate_reports.py campaign_status`: To update client campaign status spreadsheets.
- `python podcast_outreach/scripts/sync_crm.py`: To synchronize Instantly.ai lead data with Attio CRM.
- `python podcast_outreach/scripts/process_webhooks.py`: A standalone script for testing or manually processing Instantly.ai webhook payloads (the API router handles live webhooks).

---

# PGL Podcast Outreach System - Backend (FastAPI)

This document outlines the architecture, workflow, and key components of the PGL Podcast Outreach System's FastAPI backend. The system is designed to automate and streamline the process of placing clients on relevant podcasts.

## Core Architecture

The backend is built using FastAPI and leverages PostgreSQL for data persistence. Key architectural principles include:

*   **Modular Routers**: API endpoints are organized into domain-specific routers (e.g., campaigns, media, pitches) located in `podcast_outreach/api/routers/`.
*   **Service Layer**: Business logic is encapsulated in service classes (e.g., `PitchGeneratorService`, `MediaKitService`, `ClientContentProcessor`) found in `podcast_outreach/services/`.
*   **Database Queries**: All direct database interactions are handled by asynchronous functions in `podcast_outreach/database/queries/`, using `asyncpg` for non-blocking operations.
*   **Pydantic Schemas**: Data validation and serialization are managed by Pydantic models defined in `podcast_outreach/api/schemas/`.
*   **Integrations**: External API interactions (ListenNotes, Podscan, Instantly.ai, Google Workspace, Apify, AI Models) are handled by dedicated client classes in `podcast_outreach/integrations/` and `podcast_outreach/services/ai/`.
*   **Background Tasks**: Long-running processes are managed by `podcast_outreach/services/tasks/manager.py` and can be triggered via API endpoints.
*   **Authentication & Authorization**: Handled by `SessionMiddleware` and custom dependencies in `podcast_outreach/api/dependencies.py`, supporting role-based access control (Client, Staff, Admin).

## System Workflows

The system supports distinct workflows for clients and internal staff/admin users.

### I. Client Workflow (Simplified)

Clients interact with the system primarily through a dedicated frontend UI.

1.  **Onboarding & Profile Setup (`/profile-setup` on frontend):**
    *   Client selects an active **Campaign**.
    *   **Questionnaire**: Client fills out a detailed questionnaire.
        *   *Backend*: `POST /campaigns/{campaign_id}/submit-questionnaire` is called. `QuestionnaireProcessor` saves responses and extracts `questionnaire_keywords`. This triggers the `process_campaign_content` background task.
    *   **Media Kit Link**: Client provides a URL to their existing media kit (optional).
        *   *Backend*: `PUT /campaigns/{campaign_id}` updates `media_kit_url`.
    *   **AI Bio & Angles (View/Trigger if allowed):** Client views AI-generated bio/angles (sourced from GDocs populated by staff/AI).
        *   *Backend*: `AnglesProcessorPG` (triggered by staff or system) populates GDoc links and `gdoc_keywords` in the `campaigns` table. This also triggers the `process_campaign_content` background task.
    *   **Content Processing (Automated Background Task):**
        *   `ClientContentProcessor` (`process_campaign_content` task) runs:
            *   Aggregates text from questionnaire, GDocs (bio, angles, mock interview, articles, social posts).
            *   Consolidates `questionnaire_keywords` and `gdoc_keywords` into final `campaigns.campaign_keywords` (potentially with LLM refinement).
            *   Generates and saves `campaigns.embedding`.
            *   Updates `campaigns.embedding_status`.

2.  **Podcast Discovery (Limited - `/discover` on frontend):**
    *   Client selects a campaign.
    *   Client can trigger a limited podcast discovery.
        *   *Backend*: `POST /client/discover-preview` is called. The backend uses campaign keywords to fetch a small number of podcast previews from ListenNotes/Podscan. These are temporarily stored or directly returned. Usage is tracked against plan limits (`client_profiles` table).
    *   Client selects up to 5 previews for full team review.
        *   *Backend*: `POST /client/request-match-review` is called. This creates `match_suggestions` records with status `pending_internal_review` and a `review_task` for the team.

3.  **Match Approvals (`/approvals` on frontend):**
    *   Client views `match_suggestions` that have been vetted by the team and AI (status `pending_human_approval`). These suggestions include a quantitative `match_score` and qualitative `ai_reasoning`.
    *   Client approves or rejects matches.
        *   *Backend*: `PATCH /match-suggestions/{match_id}/approve` (or via review task update). This updates `match_suggestions.status` to `approved` (by client) and is the primary trigger for the internal team to proceed with pitch generation.

4.  **Campaign & Placement Tracking (`/my-campaigns`, `/placement-tracking` on frontend):**
    *   Client views details of their campaigns, including associated matches, pitches (status only), and confirmed placements.
    *   *Backend APIs*: `GET /campaigns/{id}`, `GET /match-suggestions/campaign/{id}`, `GET /pitches/?campaign_id={id}`, `GET /placements/?person_id={id}` (all filtered by client's `person_id`).

5.  **Media Kit Management (`/media-kit` or `/profile-setup` on frontend):**
    *   Client views their media kit content (bio/angles pulled from campaign GDocs).
    *   Client edits specific fields (headline, custom intro, achievements, headshots, CTA, public page settings).
        *   *Backend*: `POST /campaigns/{campaign_id}/media-kit` calls `MediaKitService` which aggregates GDoc content with user edits and updates/creates the `media_kits` record. Social stats are also refreshed.
    *   Client can view their public media kit page.
        *   *Backend*: `GET /public/media-kit/{slug}`.

### II. Staff/Admin Workflow (Comprehensive)

Staff and Admins have full access to manage all aspects of the system.

1.  **User & Campaign Management (`/admin`, `/campaign-management` on frontend):**
    *   CRUD operations for `People` (clients, staff, admins).
        *   *Backend APIs*: `POST, GET, PUT, DELETE /people/*`.
    *   CRUD operations for `Campaigns`.
        *   *Backend APIs*: `POST, GET, PUT, DELETE /campaigns/*`.
        *   Trigger GDoc-based Bio/Angles generation: `POST /campaigns/{id}/generate-angles-bio`.
        *   Trigger Campaign Content Processing & Embedding: `POST /tasks/run/process_campaign_content?campaign_id={id}`.

2.  **Media Database Management (`/media-library` - new frontend page, `/podcast-discovery` on frontend):**
    *   View and manage all `media` records.
        *   *Backend API*: `GET /media/`, `GET /media/{id}`.
    *   Manually trigger discovery for specific keywords or campaigns.
        *   *Backend API*: `POST /media/discover-admin`.
    *   Trigger background tasks for media processing:
        *   Episode Sync: `POST /tasks/run/fetch_podcast_episodes`.
        *   Transcription & Analysis: `POST /tasks/run/transcribe_podcast`.
        *   Full Enrichment Pipeline: `POST /tasks/run/enrichment_pipeline`.

3.  **Intelligent Matching & Review (`/discover`, `/approvals` on frontend):**
    *   **System (Automated)**:
        *   `MatchCreationService` (or similar) runs, creating `match_suggestions` with quantitative scores (`match_score`, initial `ai_reasoning`) and `status='pending_qualitative_review'`. Creates `review_task` (type `match_suggestion_qualitative_review`).
    *   **System (Automated)**:
        *   `DetermineFitProcessor` processes `match_suggestion_qualitative_review` tasks. Updates `match_suggestions.status` (e.g., to `pending_human_approval`) and `ai_reasoning`. Creates `review_task` (type `match_suggestion`) if fit.
    *   **Staff/Admin**:
        *   Reviews `match_suggestion` tasks (now highly filtered and pre-assessed) in the "Approval Queue".
        *   Approves or rejects. Approval (`PATCH /match-suggestions/{id}/approve`) updates `match_suggestions.status` to `approved`.
        *   **Crucially, this approval now triggers the pitch generation flow.**

4.  **Pitch Workflow (`/pitch-outreach`, `/pitch-templates` on frontend):**
    *   **Template Management**: Staff/Admin CRUD `pitch_templates` via the new UI.
        *   *Backend APIs*: `POST, GET, PUT, DELETE /pitch-templates/*`.
    *   **Pitch Generation Initiation**:
        *   After a match is approved by staff, the UI (e.g., in `PitchOutreach.tsx` "Approved Matches" tab) allows staff to select a `pitch_template_id` from the DB.
        *   Staff clicks "Generate Pitch Draft".
        *   *Backend*: `POST /pitches/generate` (with `match_id`, `pitch_template_id`) is called.
    *   **Pitch Generation (System)**:
        *   `PitchGeneratorService` fetches the template, gathers dynamic data, uses LLM to craft the pitch body and subject.
        *   Creates `pitch_generations` (status `draft`) and `pitches` (status `generated`) records.
        *   Creates `review_task` (type `pitch_review`, `related_id` = `pitch_gen_id`).
    *   **Pitch Review & Approval**:
        *   Staff reviews drafts in `PitchOutreach.tsx` ("Drafts Review" tab).
        *   Edits content: `PATCH /pitches/generations/{id}/content`.
        *   Approves pitch: `PATCH /pitches/generations/{id}/approve`.
            *   Updates `pitch_generations` and `pitches` status, completes review task.
    *   **Pitch Sending**:
        *   Staff sends approved pitches from "Ready to Send" tab.
        *   *Backend*: `POST /pitches/{id}/send` calls `PitchSenderService` (Instantly.ai). Updates `pitches` status.

5.  **Placement & Status Tracking (`/placement-tracking` on frontend):**
    *   Staff manually create `placements` records when bookings are confirmed, linking the originating `pitch_id`.
        *   *Backend API*: `POST /placements/`.
    *   Staff update `placements.current_status` as the engagement progresses.
        *   *Backend API*: `PUT /placements/{id}`.
        *   *DB Trigger*: Automatically logs changes to `status_history`.

6.  **System Monitoring & Reporting (`/admin`, AI Usage HTML views):**
    *   View task statuses, AI usage reports, trigger manual tasks.
    *   *Backend APIs*: `/tasks/*`, `/ai-usage/*`.

## Future Improvements & Considerations

1.  **Advanced Recommendation Engine**:
    *   Beyond basic keyword/embedding matching, incorporate factors like guest history, audience demographics (if available), podcast style, and client feedback on past matches.
    *   Collaborative filtering: "Clients similar to X also appeared on Y."

2.  **Automated Pitch Template Selection**:
    *   AI could suggest or automatically select the most appropriate `pitch_template_id` based on campaign type, podcast category, or desired tone, reducing manual selection for staff.

3.  **Enhanced Client Dashboard**:
    *   More detailed analytics on pitch success rates, placement progress.
    *   Direct feedback mechanisms on matches or pitches.
    *   Self-service options for minor campaign adjustments (if desired).

4.  **Sophisticated Task Queue & Workers**:
    *   For high-volume processing, replace the current `threading` based `task_manager` with a robust distributed task queue like Celery with Redis/RabbitMQ for better scalability, retries, and monitoring of background jobs.

5.  **Attio CRM Deeper Integration**:
    *   More comprehensive two-way sync with Attio beyond just notes for email events. Sync campaign statuses, placement details, etc.
    *   Use Attio as a richer source for initial client data.

6.  **Feedback Loop for AI Models**:
    *   Collect data on which AI-generated content (summaries, angles, pitches) performs well (e.g., leads to replies, bookings) and use this data to fine-tune prompts or models (requires significant MLOps infrastructure).

7.  **A/B Testing for Pitches**:
    *   Allow staff to easily A/B test different pitch templates or subject lines for the same podcast/campaign and track performance.

8.  **Automated Follow-up Sequences**:
    *   Integrate with Instantly.ai's sequencing features more deeply, potentially managing follow-up logic from within the PGL system based on response types.

9.  **Granular User Permissions**:
    *   Beyond "client", "staff", "admin", introduce more fine-grained permissions if needed (e.g., "pitch writer", "campaign manager").

10. **Improved Error Reporting and Alerting**:
    *   Proactive alerts for failing background tasks or critical API integration issues.

This README provides a solid overview for anyone working on or understanding the backend system.

## 📜 License

This project is licensed under the MIT License.

---

## 👤 Maintained by

Paschal Okonkwor
