# Podcast Outreach - PostgreSQL-Based System Architecture

This document outlines the proposed codebase structure for a clean, scalable, and maintainable PostgreSQL-based podcast outreach system. The structure follows clear separation of concerns, with distinct layers for API handling, business logic, data management, and external integrations.

## Directory Structure

```
podcast_outreach/
├── README.md
├── LICENSE.txt
├── .env
├── pyproject.toml
├── requirements.txt
├── .gitignore
# ─────────────────────────────────────────────────────────────
# 📁 App Entry & Configuration
├── main.py                          # Entry point (FastAPI)
├── config.py                        # Environment variables, constants
├── logging_config.py                # Logging setup
# ─────────────────────────────────────────────────────────────
# 📁 Web App Layer (FastAPI app, HTML routes, templates)
├── api/
│   ├── __init__.py
│   ├── routers/
│   │   ├── campaigns.py
│   │   ├── matches.py
│   │   ├── media.py
│   │   ├── pitches.py
│   │   ├── tasks.py
│   │   └── auth.py
│   ├── dependencies.py
│   └── middleware.py
|   ├── schemas/
|   │   ├── __init__.py
|   │   ├── campaign_schemas.py
|   │   ├── person_schemas.py
|   │   ├── media_schemas.py
|   │   ├── match_schemas.py
|   │   ├── pitch_schemas.py
|   │   ├── auth_schemas.py
|   │   └── base.py          # common types or mixins
├── templates/
│   ├── dashboard.html
│   ├── login.html
│   ├── podcast_cost.html
│   └── ...
├── static/
│   ├── styles.css
│   ├── dashboard.css
│   └── dashboard.js
# ─────────────────────────────────────────────────────────────
# 📁 Business Logic (Domain services)
├── services/
│   ├── __init__.py
│   ├── campaigns/
│   │   ├── bio_generator.py
│   │   ├── angles_generator.py
│   │   ├── enrichment_orchestrator.py
│   │   └── summary_builder.py
│   ├── media/
│   │   ├── podcast_fetcher.py
│   │   ├── episode_sync.py
│   │   ├── analyzer.py
│   │   └── transcriber.py
│   ├── matches/
│   │   ├── scorer.py
│   │   └── filter.py
│   ├── pitches/
│   │   ├── generator.py
│   │   ├── sender.py
│   │   └── templates.py
│   ├── enrichment/
│   │   ├── discovery.py
│   │   ├── quality_score.py
│   │   └── social_scraper.py
│   └── ai/
│       ├── gemini_client.py
│       ├── openai_client.py
│       ├── anthropic_client.py
│       ├── tracker.py
│       ├── prompts/
|       │   ├── __init__.py
|       │   ├── pitch/
|       │   │   ├── b2b_startup_template.txt
|       │   │   ├── bold_followup_template.txt
|       │   │   └── friendly_intro_template.txt
|       │   ├── campaign/
|       │   │   ├── angles_v1.txt
|       │   │   ├── angles_v2.txt
|       │   │   └── keyword_generation.txt
|       │   └── enrichment/
|       │       ├── podcast_summary.txt
|       │       └── host_guest_identifier.txt
# ─────────────────────────────────────────────────────────────
# 📁 Data Layer (PostgreSQL models, queries, migrations)
├── database/
│   ├── __init__.py
│   ├── schema.py                  # All table creation logic
│   ├── queries/
│   │   ├── campaigns.py
│   │   ├── episodes.py
│   │   ├── match_suggestions.py
│   │   ├── media.py
│   │   └── pitches.py
│   ├── models/
│   │   ├── campaign_models.py
│   │   ├── media_models.py
│   │   ├── pitch_models.py
│   │   └── llm_outputs.py
│   └── migrations/                # (alembic if using)
# ─────────────────────────────────────────────────────────────
# 📁 Integrations (APIs, CRMs, External Tools)
├── integrations/
│   ├── __init__.py
│   ├── attio.py
│   ├── instantly.py
│   ├── listen_notes.py
│   ├── podscan.py
│   ├── google_docs.py
│   ├── google_sheets.py
│   └── apify_scraper.py
# ─────────────────────────────────────────────────────────────
# 📁 CLI & Migration Scripts (One-time jobs)
├── scripts/
│   ├── migrate_clients.py
│   ├── migrate_airtable.py
│   ├── enrich_legacy_media.py
│   ├── forward_instantly.py
│   ├── sync_crm.py
│   ├── process_webhooks.py
│   └── generate_reports.py
# ─────────────────────────────────────────────────────────────
# 📁 Legacy (Temporary legacy scripts during refactor)
├── legacy/
│   ├── angles_airtable.py
│   ├── fetch_episodes_airtable.py
│   ├── send_pitch_airtable.py
│   └── webhook_handler.py
```

## Architecture Benefits

### Clear Separation of Concerns
- **API Layer** (`api/`): Handles HTTP requests, routing, authentication, and validation
- **Business Logic** (`services/`): Contains core domain logic, AI orchestration, and data transformations
- **Data Layer** (`database/`): Manages PostgreSQL interactions, schema, and data models
- **Integrations** (`integrations/`): Isolates third-party API dependencies

### Modularity and Scalability
Each component can be developed, tested, and scaled independently. Changes to external services or databases are contained within their respective layers.

### Team-Friendly Development
Different team members can work on their respective layers without conflicts, enabling parallel development.

### Maintainability
Clear boundaries make debugging easier and reduce the risk of regressions when adding new features.

## Layer Descriptions

### App Entry & Configuration
- **`main.py`**: FastAPI application entry point
- **`config.py`**: Centralized environment variables and constants
- **`logging_config.py`**: Standardized logging configuration

### Web App Layer
- **`api/routers/`**: Modular FastAPI routers for different domains
- **`api/dependencies.py`**: Reusable FastAPI dependencies
- **`api/middleware.py`**: Custom middleware for authentication and logging
- **`templates/`**: Jinja2 HTML templates
- **`static/`**: CSS and JavaScript assets

### Business Logic Services
- **`services/campaigns/`**: Client campaign management and content generation
- **`services/media/`**: Podcast data fetching, analysis, and transcription
- **`services/matches/`**: Campaign-to-podcast matching algorithms
- **`services/pitches/`**: Pitch generation and delivery
- **`services/enrichment/`**: Data enrichment and quality scoring
- **`services/ai/`**: AI service clients and utilities

### Data Layer
- **`database/schema.py`**: Complete PostgreSQL schema definition
- **`database/queries/`**: Domain-specific database query functions
- **`database/models/`**: Pydantic models for data validation and serialization
- **`database/migrations/`**: Database migration scripts

### Integrations
Dedicated client wrappers for external APIs:
- Attio CRM
- Instantly.ai
- ListenNotes
- Podscan.fm
- Google Docs/Sheets
- Apify scraping platform

### Scripts & Legacy
- **`scripts/`**: One-time migration and reporting scripts
- **`legacy/`**: Temporary holding area for Airtable-dependent code during refactoring

This structure provides a solid foundation for long-term growth while maintaining code quality and developer productivity.
