# Podcast Outreach Automation System

This repository contains a FastAPI-based automation system for placing B2B clients on relevant podcasts. The project is actively being refactored from an Airtable-centric architecture to a cleaner PostgreSQL design.

## Repository Guides

- **[old_codebase_structure_migration_guide.md](old_codebase_structure_migration_guide.md)** – detailed mapping of legacy files to their new locations.
- **[new_proposed_codebase.md](new_proposed_codebase.md)** – blueprint of the target project layout.

## Current Layout

Key application code lives inside the **`podcast_outreach/`** package:

```
podcast_outreach/
├── main.py
├── config.py
├── logging_config.py
├── api/
│   ├── routers/
│   ├── schemas/
│   └── middleware.py
├── services/
├── database/
├── integrations/
└── scripts/
```

Legacy Airtable code and miscellaneous scripts were relocated according to the migration guide. Refer to the documents above for full details and next steps in the transition.

## Frontend

A separate React application lives in the `frontend/` directory. It communicates with the FastAPI backend purely through JSON endpoints provided by the routers.

Development workflow:

```bash
# start FastAPI backend
uvicorn podcast_outreach.main:app --reload

# in another terminal start the React dev server
cd frontend && npm run dev
```

The React app reads the API base URL from a .env file (see frontend/.env.example). Production builds can be generated with `npm run build` and served as static files via FastAPI if desired.
