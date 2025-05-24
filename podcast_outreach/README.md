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
│ ├── forward_instantly.py # Forwards Instantly emails to master Gmail
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

## ✅ Future Work / Enhancements

- **Comprehensive Testing**: Implement a full suite of unit, integration, and end-to-end tests.
- **Alembic Migrations**: Integrate Alembic for robust database schema versioning and migrations.
- **Improved Error Handling**: Standardize and enhance error logging and user feedback across all layers.
- **Frontend UI Development**: Expand the internal dashboard to provide full visibility and control over all new PostgreSQL-backed workflows (e.g., pitch review UI, detailed campaign analytics).
- **Queueing System**: Implement a message queue (e.g., Celery, RabbitMQ) for long-running tasks to decouple them from the FastAPI request-response cycle.
- **Refine instantly_leads.py and instantly_leads_db.py**: These currently use psycopg2 directly and are more akin to legacy scripts. They should be refactored to use the asyncpg connection pool and integrated fully into the new database/queries structure or removed if their functionality is entirely superseded.
- **Advanced Reporting**: Develop more sophisticated reporting features, potentially leveraging the status_history table for granular historical campaign performance analysis.

---

## 📜 License

This project is licensed under the MIT License.

---

## 👤 Maintained by

Paschal Okonkwor
