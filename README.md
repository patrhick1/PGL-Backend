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

**Phase 1: Refactor from Airtable to PostgreSQL**

This project is in early transition from a loosely coupled Airtable pipeline to a robust Postgres-backed system. The structure is still evolving — expect some overlap and duplication during refactoring.

---

## 📁 Project Structure (High-Level Overview)

```
├── schema_creation_extended.py     # PostgreSQL table setup
├── angles_processor_pg.py          # Generate bios & angles using Gemini/OpenAI
├── fetch_episodes_to_pg.py         # Fetch podcast episodes, summarize, and embed
├── batch_podcast_fetcher_pg.py     # Podcast search + media insert
├── pitch_writer_optimized.py       # Embedding-based pitch generator
├── send_pitch_to_instantly.py      # Outreach dispatch (Instantly API)
├── internal_dashboard_api/         # Flask/FastAPI routes for team dashboard
├── src/
│   ├── ai_usage_tracker.py         # Tracks tokens & latency across LLMs
│   ├── services/                   # LLM service integrations (Gemini, Claude, Tavily)
│   ├── enrichment/                 # Enrich data with guest names, social links, etc.
│   ├── models/                     # Pydantic output models for LLM responses
│   ├── external_api_service.py     # Unified wrapper for third-party APIs
│   ├── summary_guest_identification_optimized.py
│   └── podcast_note_transcriber.py
├── static/                         # CSS and JS for internal web UI
├── templates/                      # HTML views for team dashboard
```

---

## 🧠 Key Components

### AI Services
- `angles_processor_pg.py`: Summarizes interviews + writes bios and angles
- `pitch_writer_optimized.py`: Generates contextualized, personalized pitches
- `gemini_service.py`, `openai_service.py`: Model-specific wrappers

### Episode Handling
- `fetch_episodes_to_pg.py`: Pulls and stores recent podcast episodes
- `podcast_note_transcriber.py`: Converts audio/transcript to summary and embeddings

### Database
- `schema_creation_extended.py`: Full schema setup for PostgreSQL (includes embeddings, triggers)
- `db_service_pg.py`: Core query and data access layer (will be refactored into `src` soon)

### Match & Pitching Workflow
- `batch_podcast_fetcher_pg.py`: Uses keywords/angles to find podcasts
- `match_suggestions`: Stores AI-assessed campaign-to-podcast fits
- `pitches`: Tracks all outreach attempts and statuses

---

## 🛠️ How to Use

### Setup

1. Clone the repo
2. Add your `.env` file with PostgreSQL, Gemini, OpenAI, and Google API keys
3. Create your database:
   ```bash
   python schema_creation_extended.py
   ```

### Run a sample angle generation:
```bash
python angles_processor_pg.py --record_id=<CAMPAIGN_ID>
```

### FastAPI Internal Dashboard
Run the internal dashboard to view campaigns, approve pitches, and track placements:

```bash
uvicorn src.main_fastapi:app --reload
```

---

## ✅ To-Do / Refactor Notes

- Consolidate scattered service files into `src/services/`
- Migrate legacy Airtable handlers to unified `db_service_pg.py`
- Normalize logging & error handling across all scripts
- Add test suite & seed data scripts
- Finish UI views for pitch review + analytics

---

## 📜 License

This project is licensed under the MIT License.

---

## 👤 Maintained by

Paschal Okonkwor