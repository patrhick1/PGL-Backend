# Migration Log

This document tracks the ongoing refactor from the legacy structure to the new `podcast_outreach` package.

## ✅ Migrated Files
- `schema_creation_extended.py` → `podcast_outreach/database/schema.py`
- `src/main_fastapi.py` → `podcast_outreach/main.py`
- `db_service_pg.py` (campaign queries) → `podcast_outreach/database/queries/campaigns.py`
- Central configuration consolidated into `podcast_outreach/config.py`
- Central logging setup in `podcast_outreach/logging_config.py`

## 🔄 Pending Work
- Split remaining query functions from `db_service_pg.py` into domain modules
- Adapt services and API routers to use the new query modules

## ⚠️ Issues
- Many legacy scripts still reference the old module paths and will need updates.
- Full test coverage is not yet in place to validate database operations after the split.
