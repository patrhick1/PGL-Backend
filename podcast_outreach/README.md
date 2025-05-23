# 🎙️ Podcast Outreach Automation System

This project automates the process of placing B2B clients on relevant podcasts. It replaces the previous Airtable-based workflow with a scalable PostgreSQL + AI-powered backend system, built for efficiency, personalization, and team control.

---

## 📌 Project Goals

- Automate podcast discovery, analysis, and episode evaluation
- Use AI to generate bios, talking angles, and pitch drafts
- Maintain client approvals at key stages (match, pitch)
- Enable internal team review via dashboard
- Log all activity into a structured PostgreSQL database

---

## 🏗️ Current Development Phase

**✅ All Migration Phases (1-7) Completed!**

The project has successfully transitioned from a loosely coupled Airtable pipeline to a robust PostgreSQL-backed system. The codebase now follows a clean, scalable, and maintainable architecture with distinct layers for API handling, business logic, data management, and external integrations.

---

## 📁 Project Structure (High-Level Overview)

```
podcast_outreach/
├── README.md
├── LICENSE.txt
├── .env # Environment variables
├── pyproject.toml # Poetry dependency management
├── requirements.txt # Python dependencies
├── .gitignore # Git ignore rules
├── main.py # Main FastAPI application entry point
├── config.py # Centralized environment variables, constants
├── logging_config.py # Standardized logging setup
├── api/ # Web App Layer (FastAPI app, API routers, schemas)
│   ├── __init__.py
│   ├── routers/ # Modular FastAPI routers for different domains
│   │   ├── campaigns.py
│   │   ├── matches.py
│   │   ├── media.py
│   │   ├── pitches.py # Handles pitch generation & review endpoints
│   │   ├── tasks.py
│   │   ├── auth.py
│   │   └── webhooks.py # New: For Instantly.ai and other webhooks
│   ├── dependencies.py # Reusable FastAPI dependencies (e.g., auth)
│   ├── middleware.py # Custom middleware (e.g., authentication)
│   └── schemas/ # Pydantic request/response models
│       ├── __init__.py
│       ├── auth_schemas.py
│       ├── base_schemas.py
│       ├── campaign_schemas.py
│       ├── match_schemas.py
│       ├── media_schemas.py
│       └── pitch_schemas.py # Models for pitches and pitch generations
├── templates/ # Jinja2 HTML templates for dashboard UI
│   ├── dashboard.html # Main user dashboard
│   ├── login.html
│   ├── podcast_cost.html # AI usage cost reporting dashboard
│   └── ...
├── static/ # Static assets (CSS, JS) for web UI
│   ├── styles.css
│   ├── dashboard.css
│   └── dashboard.js
├── services/ # Business Logic (Core domain services)
│   ├── __init__.py
│   ├── ai/ # AI service clients and utilities
│   │   ├── anthropic_client.py
│   │   ├── gemini_client.py
│   │   ├── openai_client.py
│   │   ├── tracker.py # AI usage tracking (now DB-backed)
│   │   ├── templates.py # Loader for AI prompt templates
│   │   └── prompts/ # Directory for AI prompt templates
│   │       ├── pitch/
│   │       ├── campaign/
│   │       └── enrichment/
│   ├── campaigns/ # Client campaign management and content generation
│   │   ├── angles_generator.py # Generates talking angles (from angles_processor_pg.py)
│   │   ├── bio_generator.py # Generates client bios (from angles_processor_pg.py)
│   │   ├── enrichment_orchestrator.py
│   │   └── summary_builder.py
│   ├── enrichment/ # Data enrichment and quality scoring
│   │   ├── discovery.py # Podcast discovery orchestration (from batch_podcast_fetcher_pg.py)
│   │   ├── quality_score.py
│   │   └── social_scraper.py
│   ├── matches/ # Campaign-to-podcast matching algorithms
│   │   ├── filter.py
│   │   └── scorer.py # Assesses podcast-client fit (from determine_fit_optimized.py)
│   ├── media/ # Podcast data fetching, analysis, and transcription
│   │   ├── analyzer.py # Identifies hosts/guests (from summary_guest_identification_optimized.py)
│   │   ├── episode_sync.py # Fetches & syncs podcast episodes (from fetch_episodes_to_pg.py)
│   │   ├── podcast_fetcher.py # Podcast search and initial media upsert (from batch_podcast_fetcher_pg.py)
│   │   └── transcriber.py # Transcribes podcast audio (from podcast_note_transcriber.py, free_tier_episode_transcriber.py)
│   └── pitches/ # Pitch generation and delivery
│       ├── generator.py # Generates personalized pitches (from pitch_writer_optimized.py)
│       ├── sender.py # Sends pitches via Instantly.ai (from send_pitch_to_instantly.py)
│       └── templates.py # Placeholder for pitch-specific templates/logic (distinct from AI prompts)
├── database/ # Data Layer (PostgreSQL models, queries, schema)
│   ├── __init__.py
│   ├── models/ # Database table models (Pydantic)
│   │   ├── campaign_models.py
│   │   ├── media_models.py
│   │   └── pitch_models.py
│   ├── queries/ # Domain-specific database query functions
│   │   ├── ai_usage.py # New: AI usage logs queries
│   │   ├── campaigns.py
│   │   ├── episodes.py
│   │   ├── match_suggestions.py
│   │   ├── media.py
│   │   ├── pitches.py
│   │   ├── pitch_generations.py # New: Pitch generation queries
│   │   └── review_tasks.py
│   └── schema.py # Complete PostgreSQL schema definition
├── integrations/ # Integrations (APIs, CRMs, External Tools)
│   ├── __init__.py
│   ├── attio.py # Attio CRM client (now includes webhook processing)
│   ├── instantly.py # Instantly.ai API client
│   ├── listen_notes.py
│   ├── podscan.py
│   ├── google_docs.py
│   ├── google_sheets.py
│   └── apify_scraper.py
├── scripts/ # CLI & Migration Scripts (One-time jobs, scheduled tasks)
│   ├── forward_instantly.py
│   ├── migrate_clients.py
│   ├── generate_reports.py # Generates AI usage and campaign status reports
│   ├── process_webhooks.py
│   ├── sync_crm.py
│   ├── sync_episodes.py # Script to trigger episode sync
│   └── transcribe_episodes.py # Script to trigger transcription
└── legacy/ # Temporary holding area for Airtable-dependent code during refactor
```

---

## 🧠 Key Components

### AI Services
- `services/campaigns/bio_generator.py` & `angles_generator.py`: Summarize client interviews and generate comprehensive bios and talking angles.
- `services/pitches/generator.py`: Generates highly personalized pitch emails and compelling subject lines using AI.
- `services/ai/gemini_client.py`, `openai_client.py`, `anthropic_client.py`: Dedicated wrappers for various LLM providers, ensuring consistent API interaction.
- `services/ai/tracker.py`: Centralized system for tracking LLM token usage, costs, and performance, with data persisted in PostgreSQL.

### Episode Handling
- `services/media/episode_sync.py`: Manages fetching and storing recent podcast episodes from various sources (e.g., RSS, Podscan).
- `services/media/transcriber.py`: Handles downloading audio, transcribing it using AI, and generating AI-powered episode summaries.
- `services/media/analyzer.py`: Identifies hosts and guests from episode content.

### Database
- `database/schema.py`: Defines the entire PostgreSQL database schema, including tables for campaigns, media, episodes, pitches, and AI usage logs.
- `database/queries/`: A collection of modular query functions (e.g., `campaigns.py`, `episodes.py`, `pitches.py`, `ai_usage.py`) for interacting with the PostgreSQL database.

### Match & Pitching Workflow
- `services/media/podcast_fetcher.py`: Discovers relevant podcasts based on client keywords and campaign angles.
- `database/queries/match_suggestions.py`: Stores AI-assessed compatibility scores between clients and podcasts.
- `database/queries/pitch_generations.py`: Stores AI-generated pitch drafts, awaiting internal team review.
- `database/queries/pitches.py`: Tracks the lifecycle of each outreach attempt, including send status and replies.
- `services/pitches/sender.py`: Integrates with Instantly.ai to dispatch approved pitches.

### Reporting & Monitoring
- `scripts/generate_reports.py`: Command-line interface for generating detailed reports on AI usage costs and overall campaign performance.
- `services/ai/tracker.py`: Provides the underlying data for AI usage reports, now directly querying the PostgreSQL database.
- **Note on Campaign Status Reporting**: The `CampaignStatusReporter` currently aggregates weekly metrics from the `pitches` and `placements` tables. While the `status_history` table tracks every status change, generating weekly summary reports from it would require more complex aggregation logic. The current implementation focuses on key events like pitches sent, replies received, and meetings booked.

---

## 🛠️ How to Use

### Setup

1. **Clone the repository**:
   ```bash
   git clone <your-repo-url>
   cd podcast_outreach
   ```

2. **Install dependencies** (using Poetry, or pip with `requirements.txt`):
   ```bash
   # If using Poetry (recommended)
   poetry install

   # If using pip
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**: Create a `.env` file in the `podcast_outreach/` directory with your API keys and database credentials. Refer to `config.py` for required variables (e.g., `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `INSTANTLY_API_KEY`, `ATTIO_ACCESS_TOKEN`, `GOOGLE_APPLICATION_CREDENTIALS`, `CLIENT_SPREADSHEETS_TRACKING_FOLDER_ID`, `PGL_AI_DRIVE_FOLDER_ID`).

4. **Create your PostgreSQL database schema**:
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
- `GET /podcast-cost-dashboard/{pitch_gen_id}`: To view a detailed AI cost dashboard for a specific pitch generation.

#### CLI Scripts
For batch processing or one-off tasks, refer to `podcast_outreach/scripts/`:

- `python podcast_outreach/scripts/sync_episodes.py`: To fetch and sync new podcast episodes.
- `python podcast_outreach/scripts/transcribe_episodes.py`: To transcribe flagged episodes.
- `python podcast_outreach/scripts/generate_reports.py ai_usage --format text`: To generate AI usage reports from the command line.
- `python podcast_outreach/scripts/generate_reports.py campaign_status`: To update client campaign status spreadsheets.

---

## ✅ Future Work / Enhancements

- **Comprehensive Testing**: Implement a full suite of unit, integration, and end-to-end tests.
- **Alembic Migrations**: Integrate Alembic for robust database schema versioning and migrations.
- **Improved Error Handling**: Standardize and enhance error logging and user feedback across all layers.
- **Frontend UI Development**: Expand the internal dashboard to provide full visibility and control over all new PostgreSQL-backed workflows (e.g., pitch review UI, detailed campaign analytics).
- **Queueing System**: Implement a message queue (e.g., Celery, RabbitMQ) for long-running tasks to decouple them from the FastAPI request-response cycle.
- **Refine Legacy Script Calls**: Fully migrate remaining Airtable-dependent logic from `src/` and `webhook_handler.py` into the new `podcast_outreach/` services and scripts.
- **Advanced Reporting**: Develop more sophisticated reporting features, potentially leveraging the `status_history` table for granular historical campaign performance analysis.

---

## 📜 License

This project is licensed under the MIT License.

---

## 👤 Maintained by

Paschal Okonkwor
