# Podcast Outreach Automation System - Codebase Structure & Migration Guide

## Overview
This codebase represents a sophisticated B2B podcast guest placement automation system currently transitioning from Airtable to PostgreSQL. The system automates the entire podcast outreach lifecycle using AI-powered analysis and personalized pitch generation.

## System Architecture
- **Backend**: FastAPI with PostgreSQL
- **AI/ML**: Google Gemini, OpenAI GPT, Anthropic Claude via LangChain
- **External APIs**: ListenNotes, Podscan, Instantly.ai, Apify, Google Workspace
- **Migration Status**: Transitional phase (files with `_pg` suffix are PostgreSQL-focused)

---

## Root Level Files

### Core Application Files
| File | Purpose | Migration Status |
|------|---------|------------------|
| `main_fastapi.py` (in src/) | **Main FastAPI application entry point** | ✅ Active |
| `schema_creation_extended.py` | **Database schema creation for PostgreSQL** | ✅ PostgreSQL |
| `db_service_pg.py` | **Core async PostgreSQL service layer** | ✅ PostgreSQL |
| `internal_dashboard_api/internal_dashboard_api.py` | **Legacy monolithic FastAPI routes** | ❌ Legacy |

### Migration & Database Management
| File | Purpose | Migration Status |
|------|---------|------------------|
| `scripts/migrate_clients.py` | Migrate client/campaign data from Airtable to PostgreSQL | 🔄 Migration Tool |
| `client_management_db.py` | Synchronous client management functions | 🔄 Transitional |
| `instantly_leads_db.py` | Instantly.ai leads data backup/management | 🔄 Transitional |
| `media_manager_db.py` | Legacy media tracking system | ❌ Legacy |

### AI-Powered Processing (PostgreSQL)
| File | Purpose | Migration Status |
|------|---------|------------------|
| `angles_processor_pg.py` | **Generate client bios & talking angles** | ✅ PostgreSQL |
| `batch_podcast_fetcher_pg.py` | **Orchestrate podcast discovery & enrichment** | ✅ PostgreSQL |
| `fetch_episodes_to_pg.py` | **Fetch & sync podcast episodes** | ✅ PostgreSQL |

### External Integrations
| File | Purpose | Migration Status |
|------|---------|------------------|
| `scripts/forward_instantly.py` | Forward Instantly emails to master Gmail | ✅ Active |
| `scripts/sync_crm.py` | Sync Instantly leads to Attio CRM | ✅ Active |
| `scripts/process_webhooks.py` | Process Instantly.ai webhooks | ✅ Active |

### Documentation & Configuration
| File | Purpose |
|------|---------|
| `README.md` | Project overview & setup instructions |
| `postgres_data_dictionary.md` | Database schema documentation |
| `pyproject.toml` | Poetry dependency management |
| `requirements.txt` | Python dependencies |
| `LICENSE.txt` | Proprietary license |
| `.gitignore` | Git ignore rules |

---

## Source Code Directory (`src/`)

### Core Services & Infrastructure

#### Database & API Services
| File | Purpose | Migration Status |
|------|---------|------------------|
| `airtable_service.py` | Airtable API client | ❌ Legacy |
| `base_client.py` | Abstract base for external API clients | ✅ Active |
| `external_api_service.py` | ListenNotes, Podscan, Instantly API clients | ✅ Active |
| `auth_middleware.py` | FastAPI authentication middleware | ✅ Active |
| `exceptions.py` | Custom exception classes | ✅ Active |

#### AI/ML Services
| File | Purpose | Status |
|------|---------|--------|
| `gemini_service.py` | Google Gemini API wrapper | ✅ Active |
| `anthropic_service.py` | Anthropic Claude API wrapper | ✅ Active |
| `openai_service.py` | OpenAI API wrapper | ✅ Active |
| `gemini_search.py` | Gemini with Google Search integration | ✅ Active |
| `ai_usage_tracker.py` | Track LLM usage & costs | ✅ Active |
| `generate_ai_usage_report.py` | Generate AI usage reports | ✅ Active |

#### Google Workspace Integration
| File | Purpose | Status |
|------|---------|--------|
| `google_docs_service.py` | Google Docs API client | ✅ Active |
| `google_sheets_service.py` | Google Sheets API client | ✅ Active |

### AI-Powered Processing

#### Current (PostgreSQL) Versions
| File | Purpose | AI Models Used |
|------|---------|----------------|
| `determine_fit_optimized.py` | Assess podcast-client compatibility | Claude/Gemini |
| `pitch_writer_optimized.py` | Generate personalized pitches | Claude/Gemini |
| `summary_guest_identification_optimized.py` | Identify hosts/guests from content | Gemini |
| `podcast_note_transcriber.py` | Transcribe podcast audio | Gemini |

#### Legacy (Airtable) Versions
| File | Purpose | Migration Status |
|------|---------|------------------|
| `angles.py` | Generate bios/angles (Airtable version) | ❌ Legacy |
| `batch_podcast_fetcher.py` | Podcast discovery (Airtable version) | ❌ Legacy |
| `fetch_episodes.py` | Episode fetching (Airtable version) | ❌ Legacy |
| `mipr_podcast.py` | Podcast search logic (Airtable version) | ❌ Legacy |

### Advanced Features

#### Enrichment System (`enrichment/`)
| File | Purpose |
|------|---------|
| `enrichment_orchestrator.py` | **Main enrichment pipeline orchestrator** |
| `enrichment_agent.py` | Single podcast enrichment coordinator |
| `data_merger_service.py` | Merge data from multiple sources |
| `quality_service.py` | Calculate podcast quality scores |
| `social_discovery_service.py` | Scrape social media metrics via Apify |

#### Data Models (`models/`)
| File | Purpose |
|------|---------|
| `podcast_profile_models.py` | Standardized podcast data models |
| `llm_output_models.py` | Structured LLM output models |

#### Additional Services (`services/`)
| File | Purpose |
|------|---------|
| `gemini_service.py` | Duplicate Gemini service (consolidation needed) |
| `tavily_service.py` | Tavily Search API client |

### CRM & Outreach Integration
| File | Purpose | Status |
|------|---------|--------|
| `attio_service.py` | Attio CRM API client | ✅ Active |
| `attio_email_sent.py` | Handle email sent webhooks | ✅ Active |
| `attio_response.py` | Handle email reply webhooks | ✅ Active |
| `send_pitch_to_instantly.py` | Send pitches to Instantly.ai | ✅ Active |

### Legacy Webhook Handlers
| File | Purpose | Migration Status |
|------|---------|------------------|
| `instantly_email_sent.py` | Instantly email webhooks (Airtable) | ❌ Legacy |
| `instantly_response.py` | Instantly reply webhooks (Airtable) | ❌ Legacy |
| `webhook_handler.py` | Airtable polling system | ❌ Legacy |

### Utilities
| File | Purpose |
|------|---------|
| `file_manipulation.py` | Basic file operations |
| `data_processor.py` | Data manipulation utilities |
| `task_manager.py` | Background task management |
| `campaign_status_tracker.py` | Campaign reporting to Google Sheets |
| `free_tier_episode_transcriber.py` | Audio transcription (free tier) |

---

## Frontend Assets

### Static Files (`static/`)
| File | Purpose |
|------|---------|
| `dashboard.css` | Internal dashboard styles |
| `dashboard.js` | Dashboard interactivity & automation triggers |
| `styles.css` | General application styles |

### Templates (`templates/`)
| File | Purpose |
|------|---------|
| `index.html` | Main user dashboard |
| `admin_dashboard.html` | Admin-specific dashboard |
| `llm_test_dashboard.html` | AI model testing interface |
| `login.html` | User authentication |
| `podcast_cost.html` | AI usage cost reporting |

---

## Migration Status Guide

### ✅ **Fully Migrated (Use These)**
- All files with `_pg` suffix
- `db_service_pg.py` - Core database layer
- `internal_dashboard_api/` - API endpoints
- AI services (`gemini_service.py`, `anthropic_service.py`, etc.)
- External API services
- Google Workspace integrations

### 🔄 **Transitional (Review Needed)**
- `client_management_db.py` - May need integration
- `instantly_leads_db.py` - Backup system
- `media_manager_db.py` - Assess necessity

### ❌ **Legacy (Phase Out)**
- All Airtable-dependent files
- `webhook_handler.py` - Replace with direct API calls
- Duplicate services in `services/` directory

---

## Key Refactoring Priorities

### 1. **Service Consolidation**
- Merge duplicate `gemini_service.py` files
- Standardize AI service interfaces
- Consolidate external API clients

### 2. **Database Layer**
- Complete Airtable removal
- Standardize on async PostgreSQL patterns
- Implement proper transaction management

### 3. **Architecture Cleanup**
- Move all services to consistent directory structure
- Implement proper dependency injection
- Standardize error handling patterns

### 4. **Legacy Code Removal**
- Remove all Airtable dependencies
- Clean up webhook polling systems
- Consolidate similar functionality

### 5. **Testing & Documentation**
- Add comprehensive test coverage
- Document API endpoints
- Create deployment guides

---

## Development Workflow

### Current Entry Points
1. **Main Application**: `main.py` (replaces `src/main_fastapi.py`)
2. **Database Setup**: `schema_creation_extended.py`
3. **Dashboard API**: Split from `internal_dashboard_api.py` into domain routers

### Key Integration Points
1. **AI Processing**: `enrichment/enrichment_orchestrator.py`
2. **Database Operations**: `db_service_pg.py`
3. **External APIs**: `external_api_service.py`
4. **CRM Integration**: `attio_service.py`

### Background Tasks
- Managed by `task_manager.py`
- Triggered via dashboard or API endpoints
- Status monitoring through web interface

---

## 🎯 Proposed New Architecture

### Target Directory Structure
```
podcast_outreach/
├── main.py                          # Entry point (replaces main_fastapi.py)
├── config.py                        # Environment variables, constants
├── logging_config.py                # Logging setup
├── api/
│   ├── routers/
│   │   ├── campaigns.py
│   │   ├── matches.py
│   │   ├── media.py
│   │   ├── pitches.py
│   │   ├── tasks.py
│   │   └── auth.py
│   ├── schemas/                     # Pydantic request/response models
│   │   ├── campaign_schemas.py
│   │   ├── media_schemas.py
│   │   └── pitch_schemas.py
│   ├── dependencies.py
│   └── middleware.py
├── services/
│   ├── campaigns/
│   ├── media/
│   ├── matches/
│   ├── pitches/
│   ├── enrichment/
│   └── ai/
│       ├── prompts/
│       │   ├── pitch/
│       │   │   ├── b2b_startup_template.txt
│       │   │   ├── bold_followup_template.txt
│       │   │   └── friendly_intro_template.txt
│       │   ├── campaign/
│       │   │   ├── angles_v1.txt
│       │   │   ├── angles_v2.txt
│       │   │   └── keyword_generation.txt
│       │   └── enrichment/
│       │       ├── podcast_summary.txt
│       │       └── host_guest_identifier.txt
├── database/
│   ├── schema.py
│   ├── queries/
│   ├── models/                      # Database table models
│   └── migrations/
├── integrations/
├── scripts/
├── tests/                           # Testing framework
│   ├── test_campaigns.py
│   ├── test_media.py
│   ├── test_matches.py
│   └── test_api.py
└── legacy/
```

## 📋 File Migration Mapping

### Current → New Structure Migration

#### **API Schemas (Pydantic)**
| Current File | New Location | Action |
|--------------|--------------|--------|
| N/A | `api/schemas/campaign_schemas.py` | 🆕 Define CampaignCreate, CampaignOut |
| N/A | `api/schemas/media_schemas.py` | 🆕 Define MediaCreate, MediaOut |
| N/A | `api/schemas/episode_schemas.py` | 🆕 For EPISODES table inputs/outputs |
| N/A | `api/schemas/pitch_schemas.py` | 🆕 Define PitchCreate, PitchReview |
| N/A | `api/schemas/match_schemas.py` | 🆕 For match_suggestions API |
| N/A | `api/schemas/review_task_schemas.py` | 🆕 For review_tasks endpoints |

#### **Database Connections**
| Current File | New Location | Action |
|--------------|--------------|--------|
| Top of `db_service_pg.py` | `database/connection.py` | 🔄 **EXTRACT** DB connection/init logic |
| `get_db()` from old dashboard | `api/dependencies.py` | ✅ Inject via FastAPI dependency |

#### **Config & Logging**
| Current File | New Location | Action |
|--------------|--------------|--------|
| `.env` usage scattered | `config.py` | 🆕 Load + validate environment variables |
| Scattered logging setup | `logging_config.py` | 🆕 Unified logging setup + formats |

#### **Prompt Templates**
| Current File | New Location | Action |
|--------------|--------------|--------|
| Inline prompts in `angles_processor_pg.py` etc. | `services/ai/prompts/` | 🔄 **EXTRACT** to versioned .txt files or prompts.py |
| Hardcoded pitch prompts | `services/ai/prompts/pitch/` | 🆕 Break into template files by tone/style |

#### **Entry Point & Configuration**
| Current File | New Location | Action |
|--------------|--------------|--------|
| `src/main_fastapi.py` | `main.py` | 🔄 **RENAME** + Refactor & simplify |
| Environment variables scattered | `config.py` | 🆕 Centralize configuration |
| No centralized logging | `logging_config.py` | 🆕 Create logging setup |

#### **API Layer Migration**
| Current File | New Location | Action |
|--------------|--------------|--------|
| `internal_dashboard_api/internal_dashboard_api.py` | `api/routers/` (split into modules) | 🔄 Break into domain routers |
| `src/auth_middleware.py` | `api/middleware.py` | 🔄 **RENAME** + enhance |
| Various auth logic | `api/dependencies.py` + `api/routers/auth.py` | ✅ Consolidate |

#### **Business Logic Services**
| Current File | New Location | Action |
|--------------|--------------|--------|
| `angles_processor_pg.py` | `services/campaigns/bio_generator.py` + `angles_generator.py` | 🔄 **RENAME** + Split functionality |
| `batch_podcast_fetcher_pg.py` | `services/media/fetcher.py` | 🔄 **RENAME** + Refactor |
| `fetch_episodes_to_pg.py` | `services/media/fetcher.py` (episodes) | 🔄 **RENAME** + Integrate |
| `src/enrichment/enrichment_orchestrator.py` | `services/campaigns/enrichment_orchestrator.py` | ✅ Move |
| `src/enrichment/quality_service.py` | `services/enrichment/quality_score.py` | 🔄 **RENAME** |
| `src/enrichment/social_discovery_service.py` | `services/enrichment/social_scraper.py` | 🔄 **RENAME** |
| `src/determine_fit_optimized.py` | `services/matches/scorer.py` | 🔄 **RENAME** + Refactor |
| `src/pitch_writer_optimized.py` | `services/pitches/generator.py` | 🔄 **RENAME** + Refactor |
| `src/send_pitch_to_instantly.py` | `services/pitches/sender.py` | 🔄 **RENAME** + Refactor |
| `src/podcast_note_transcriber.py` | `services/media/transcriber.py` | 🔄 **RENAME** |
| `src/summary_guest_identification_optimized.py` | `services/media/analyzer.py` | 🔄 **RENAME** + Refactor |

#### **AI Services Consolidation**
| Current File | New Location | Action |
|--------------|--------------|--------|
| `src/gemini_service.py` | `services/ai/gemini_client.py` | 🔄 **RENAME** + Consolidate duplicates |
| `src/services/gemini_service.py` | ↑ (merge with above) | 🗑️ Remove duplicate |
| `src/anthropic_service.py` | `services/ai/anthropic_client.py` | 🔄 **RENAME** |
| `src/openai_service.py` | `services/ai/openai_client.py` | 🔄 **RENAME** |
| `src/ai_usage_tracker.py` | `services/ai/tracker.py` | 🔄 **RENAME** + Replace CSV with DB option |
| `src/services/tavily_service.py` | `services/ai/tavily_client.py` | 🔄 **RENAME** |
| Various prompt templates | `services/ai/prompts/` | 🆕 Organize prompts |

#### **Database Layer**
| Current File | New Location | Action |
|--------------|--------------|--------|
| `schema_creation_extended.py` | `database/schema.py` | 🔄 **RENAME** + Refactor |
| `db_service_pg.py` | `database/queries/` (split by domain) | 🔄 **RENAME** + Split into domain queries |
| `src/models/podcast_profile_models.py` | `database/models/media_models.py` | 🔄 **RENAME** |
| `src/models/llm_output_models.py` | `database/models/llm_outputs.py` | 🔄 **RENAME** |
| No centralized models | `database/models/campaign_models.py` | 🆕 Create |
| No centralized models | `api/schemas/campaign_schemas.py` | 🆕 Create Pydantic models |
| No centralized models | `api/schemas/media_schemas.py` | 🆕 Create Pydantic models |
| No centralized models | `api/schemas/pitch_schemas.py` | 🆕 Create Pydantic models |
| `client_management_db.py` | `database/models/campaign_models.py` | 🔄 **RENAME** + Integrate |
| `instantly_leads_db.py` | `database/queries/leads.py` | 🔄 **RENAME** + Refactor |

#### **External Integrations**
| Current File | New Location | Action |
|--------------|--------------|--------|
| `src/external_api_service.py` | Split into `integrations/listen_notes.py`, `podscan.py`, `instantly.py` | 🔄 **RENAME** + Split by service |
| `src/attio_service.py` | `integrations/attio.py` | 🔄 **RENAME** |
| `src/google_docs_service.py` | `integrations/google_docs.py` | 🔄 **RENAME** |
| `src/google_sheets_service.py` | `integrations/google_sheets.py` | 🔄 **RENAME** |
| `src/enrichment/social_discovery_service.py` | `integrations/apify_scraper.py` | 🔄 **RENAME** |

#### **Scripts & Utilities**
| Current File | New Location | Action |
|--------------|--------------|--------|
| `migrate_clients.py` | `scripts/migrate_clients.py` | ✅ Move |
| `forward_instantly_emails.py` | `scripts/forward_instantly.py` | 🔄 **RENAME** |
| `src/generate_ai_usage_report.py` | `scripts/generate_reports.py` | 🔄 **RENAME** |
| `instantly_to_attio.py` | `scripts/sync_crm.py` | 🔄 **RENAME** |
| `instantly_webhook_processor.py` | `scripts/process_webhooks.py` | 🔄 **RENAME** |
| `src/campaign_status_tracker.py` | `scripts/generate_reports.py` | 🔄 **RENAME** + Integrate |

#### **Legacy Files (Temporary)**
| Current File | New Location | Action |
|--------------|--------------|--------|
| `src/angles.py` | `legacy/angles_airtable.py` | 🔄 **RENAME** + Phase out |
| `src/batch_podcast_fetcher.py` | `legacy/batch_podcast_fetcher_airtable.py` | 🔄 **RENAME** + Phase out |
| `src/fetch_episodes.py` | `legacy/fetch_episodes_airtable.py` | 🔄 **RENAME** + Phase out |
| `src/webhook_handler.py` | `legacy/webhook_handler.py` | ✅ Move + Phase out |
| `src/mipr_podcast.py` | `legacy/mipr_podcast_airtable.py` | 🔄 **RENAME** + Phase out |
| All other Airtable dependencies | `legacy/` | 🔄 **RENAME** appropriately |

#### **Frontend Assets**
| Current Location | New Location | Action |
|------------------|--------------|--------|
| `templates/` | `templates/` | ✅ Keep structure |
| `static/` | `static/` | ✅ Keep structure |

---

## 🚀 Migration Action Plan

### Phase 1: Foundation Setup
1. **Create new directory structure**
2. **Set up `config.py`** - Centralize all environment variables
3. **Implement `logging_config.py`** - Standardize logging
4. **Refactor `main.py`** - Simplify entry point

### Phase 2: Core Services Migration
1. **Database layer** - Migrate `schema.py` and split queries
2. **AI services** - Consolidate duplicate services
3. **External integrations** - Split monolithic API service
4. **Business logic** - Move domain services to appropriate folders

### Phase 3: API Restructuring
1. **Split API routers** - Break monolithic dashboard API
2. **Enhance middleware** - Improve auth and error handling
3. **Update templates** - Ensure frontend works with new API structure

### Phase 4: Testing & Cleanup
1. **Move scripts** - Organize one-time utilities
2. **Archive legacy** - Move Airtable code to legacy folder
3. **Update documentation** - Reflect new structure
4. **Remove duplicates** - Clean up consolidated code

### Phase 5: Production Deployment & Security
1. **Update deployment configs**
2. **Migrate to centralized `config.py`** with support for `.env` loading
3. **Audit & rotate legacy secrets** - Remove Airtable keys and rotate API secrets
4. **Test all integrations**
5. **Remove legacy folder**

---

## 🎯 Benefits of New Structure

### **Improved Developer Experience**
- **Clear file locations** - No more hunting for functionality
- **Domain separation** - Work on campaigns without touching media logic
- **Reduced conflicts** - Multiple developers can work simultaneously

### **Better Maintainability**
- **Single responsibility** - Each file has one clear purpose
- **Easy testing** - Services can be tested in isolation
- **Clear dependencies** - External APIs are clearly separated

### **Enhanced Scalability**
- **Modular growth** - Add new features without affecting existing code
- **Performance optimization** - Optimize specific services independently
- **Team specialization** - Team members can focus on their expertise areas

This migration plan provides a clear roadmap from your current complex structure to a clean, maintainable PostgreSQL-based system that will serve your team well as the project grows.