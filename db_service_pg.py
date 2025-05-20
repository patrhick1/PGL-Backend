"""
db_service_pg.py

A simple async PostgreSQL service using asyncpg. 
Provides helper methods for reading and updating campaign data 
relevant to the Bio/Angles generation.

Adjust column names/table structure to match your actual schema.
"""

import os
import asyncpg
import logging
import uuid # For campaign_id if needed
from typing import List, Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# --- Connection Pool Management ---
DB_POOL: Optional[asyncpg.Pool] = None

async def init_db_pool():
    global DB_POOL
    if DB_POOL is None or DB_POOL._closed:
        try:
            user = os.getenv("PGUSER")
            password = os.getenv("PGPASSWORD")
            host = os.getenv("PGHOST")
            port = os.getenv("PGPORT")
            dbname = os.getenv("PGDATABASE")
            connect_timeout_seconds = 30
            pool_acquire_timeout_seconds = 30 # Timeout for pool.acquire()

            if not all([user, password, host, port, dbname]):
                logger.error("Database connection parameters missing.")
                raise ValueError("DB connection parameters missing for DSN.")

            dsn = f"postgresql://{user}:{password}@{host}:{port}/{dbname}?connect_timeout={connect_timeout_seconds}"
            
            logger.info(f"Initializing DB pool with DSN (connect_timeout={connect_timeout_seconds}s, acquire_timeout={pool_acquire_timeout_seconds}s)")

            DB_POOL = await asyncpg.create_pool(
                dsn=dsn,
                min_size=1,
                max_size=10,
                command_timeout=60,
                timeout=pool_acquire_timeout_seconds # Timeout for pool.acquire()
            )
            logger.info("Database connection pool initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing database pool: {e}", exc_info=True)
            raise
    return DB_POOL

async def get_db_pool(): # Renamed for clarity, as it returns the pool itself
    if DB_POOL is None or DB_POOL._closed:
        return await init_db_pool()
    return DB_POOL

async def close_db_pool():
    global DB_POOL
    if DB_POOL and not DB_POOL._closed:
        await DB_POOL.close()
        DB_POOL = None
        logger.info("Database connection pool closed.")

# --- Campaign Table CRUD Operations ---

async def create_campaign_in_db(campaign_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    query = """
    INSERT INTO campaigns (
        campaign_id, person_id, attio_client_id, campaign_name, campaign_type,
        campaign_bio, campaign_angles, campaign_keywords, compiled_social_posts,
        podcast_transcript_link, compiled_articles_link, mock_interview_trancript,
        start_date, end_date, goal_note, media_kit_url
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
    ) RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            keywords = campaign_data.get("campaign_keywords", [])
            if keywords is None:
                keywords = []

            row = await conn.fetchrow(
                query,
                campaign_data['campaign_id'], campaign_data['person_id'], campaign_data.get('attio_client_id'),
                campaign_data['campaign_name'], campaign_data.get('campaign_type'),
                campaign_data.get('campaign_bio'), campaign_data.get('campaign_angles'), keywords,
                campaign_data.get('compiled_social_posts'), campaign_data.get('podcast_transcript_link'),
                campaign_data.get('compiled_articles_link'), campaign_data.get('mock_interview_trancript'),
                campaign_data.get('start_date'), campaign_data.get('end_date'),
                campaign_data.get('goal_note'), campaign_data.get('media_kit_url')
            )
            logger.info(f"Campaign created: {campaign_data.get('campaign_id')}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error creating campaign (ID: {campaign_data.get('campaign_id')}) in DB: {e}")
            raise

async def get_campaign_by_id(campaign_id: uuid.UUID) -> Optional[Dict[str, Any]]: # Renamed from get_campaign_by_id_from_db for consistency with old name
    # This is the critical function for AnglesProcessorPG
    query = "SELECT * FROM campaigns WHERE campaign_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id)
            if not row:
                logger.warning(f"Campaign not found: {campaign_id}")
                return None
            return dict(row)
        except Exception as e:
            logger.exception(f"Error fetching campaign {campaign_id}: {e}")
            raise

async def get_all_campaigns_from_db(skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    query = "SELECT * FROM campaigns ORDER BY created_at DESC OFFSET $1 LIMIT $2;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, skip, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching all campaigns: {e}")
            raise

async def update_campaign(campaign_id: uuid.UUID, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]: # Renamed from update_campaign_in_db
    if not update_fields:
        logger.warning(f"No update data for campaign {campaign_id}. Fetching current.")
        return await get_campaign_by_id(campaign_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_fields.items():
        if key == "campaign_keywords" and val is not None and not isinstance(val, list):
            keywords_list = [kw.strip() for kw in str(val).split(',') if kw.strip()] 
            if not keywords_list and str(val).strip():
                keywords_list = [kw.strip() for kw in str(val).split() if kw.strip()]
            val = keywords_list
        
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses:
        return await get_campaign_by_id(campaign_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE campaigns SET {set_clause_str} WHERE campaign_id = ${idx} RETURNING *;"
    values.append(campaign_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Campaign updated: {campaign_id} with fields: {list(update_fields.keys())}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error updating campaign {campaign_id}: {e}")
            raise

async def delete_campaign_from_db(campaign_id: uuid.UUID) -> bool:
    query = "DELETE FROM campaigns WHERE campaign_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, campaign_id)
            deleted_count = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
            if deleted_count > 0:
                logger.info(f"Campaign deleted: {campaign_id}")
                return True
            logger.warning(f"Campaign not found for deletion or delete failed: {campaign_id}")
            return False
        except Exception as e:
            logger.exception(f"Error deleting campaign {campaign_id} from DB: {e}")
            raise

# --- People Table CRUD Operations ---

async def create_person_in_db(person_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # person_id is SERIAL, email is UNIQUE
    # created_at and updated_at have defaults
    query = """
    INSERT INTO people (
        company_id, full_name, email, linkedin_profile_url, twitter_profile_url,
        instagram_profile_url, tiktok_profile_url, dashboard_username, 
        attio_contact_id, role
        -- dashboard_password_hash is not set here; handle separately if/when password is set
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                person_data.get('company_id'),
                person_data.get('full_name'),
                person_data['email'], # Email is required by Pydantic model PersonBase
                person_data.get('linkedin_profile_url'),
                person_data.get('twitter_profile_url'),
                person_data.get('instagram_profile_url'),
                person_data.get('tiktok_profile_url'),
                person_data.get('dashboard_username'),
                person_data.get('attio_contact_id'),
                person_data.get('role')
            )
            logger.info(f"Person created with email: {person_data['email']}")
            return dict(row) if row else None
        except asyncpg.exceptions.UniqueViolationError as uve:
            logger.warning(f"Failed to create person, email already exists: {person_data['email']} - {uve}")
            # Consider how the API layer should handle this - it will raise an exception to be caught by FastAPI handler
            raise # Re-raise to be handled by API layer (e.g., return 409 Conflict)
        except Exception as e:
            logger.exception(f"Error creating person with email {person_data['email']} in DB: {e}")
            raise

async def get_person_by_id_from_db(person_id: int) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM people WHERE person_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, person_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching person {person_id}: {e}")
            raise

async def get_person_by_email_from_db(email: str) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM people WHERE email = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, email)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching person by email {email}: {e}")
            raise

async def get_all_people_from_db(skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    query = "SELECT * FROM people ORDER BY created_at DESC OFFSET $1 LIMIT $2;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, skip, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching all people: {e}")
            raise

async def update_person_in_db(person_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not update_data:
        logger.warning(f"No update data provided for person {person_id}.")
        return await get_person_by_id_from_db(person_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_data.items():
        if key == 'person_id': continue # Cannot update person_id
        if key == 'dashboard_password_hash': continue # Should not be updated via this generic method
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses:
        return await get_person_by_id_from_db(person_id)

    # updated_at is handled by trigger, so no need to explicitly set it here unless desired
    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE people SET {set_clause_str} WHERE person_id = ${idx} RETURNING *;"
    values.append(person_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Person updated: {person_id} with fields: {list(update_data.keys())}")
            return dict(row) if row else None
        except asyncpg.exceptions.UniqueViolationError as uve:
            logger.warning(f"Failed to update person {person_id}, unique constraint violated (e.g., email exists): {uve}")
            raise # Re-raise to be handled by API layer
        except Exception as e:
            logger.exception(f"Error updating person {person_id}: {e}")
            raise

async def delete_person_from_db(person_id: int) -> bool:
    query = "DELETE FROM people WHERE person_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, person_id)
            deleted_count = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
            if deleted_count > 0:
                logger.info(f"Person deleted: {person_id}")
                return True
            logger.warning(f"Person {person_id} not found for deletion or delete failed.")
            return False
        except Exception as e:
            logger.exception(f"Error deleting person {person_id}: {e}")
            raise

async def update_person_password_hash(person_id: int, new_hashed_password: str) -> bool:
    """Specifically updates the dashboard_password_hash for a given person_id."""
    query = "UPDATE people SET dashboard_password_hash = $1, updated_at = CURRENT_TIMESTAMP WHERE person_id = $2;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, new_hashed_password, person_id)
            if result.startswith("UPDATE ") and int(result.split(" ")[1]) > 0:
                logger.info(f"Password hash updated for person_id: {person_id}")
                return True
            else:
                logger.warning(f"Password hash update did not affect any rows for person_id: {person_id} (person may not exist or hash is the same).")
                return False
        except Exception as e:
            logger.exception(f"Error updating password hash for person {person_id}: {e}")
            raise

# --- Media Table CRUD Operations ---

async def create_media_in_db(media_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # media_id is SERIAL, created_at has default, fetched_episodes defaults to FALSE in Pydantic/DB
    query = """
    INSERT INTO media (
        name, rss_url, company_id, category, language, avg_downloads, 
        contact_email, fetched_episodes, description, ai_description
        -- embedding is not handled here
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                media_data['name'], # Name is required by MediaCreate
                media_data.get('rss_url'),
                media_data.get('company_id'),
                media_data.get('category'),
                media_data.get('language'),
                media_data.get('avg_downloads'),
                media_data.get('contact_email'),
                media_data.get('fetched_episodes', False), # Default if not provided
                media_data.get('description'),
                media_data.get('ai_description')
            )
            logger.info(f"Media created: {media_data.get('name')}")
            return dict(row) if row else None
        except asyncpg.exceptions.UniqueViolationError as uve: # e.g. if rss_url has a UNIQUE constraint
            logger.warning(f"Failed to create media {media_data.get('name')}, unique constraint violated (e.g., RSS URL exists): {uve}")
            raise
        except Exception as e:
            logger.exception(f"Error creating media {media_data.get('name')} in DB: {e}")
            raise

async def get_media_by_id_from_db(media_id: int) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM media WHERE media_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, media_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching media by ID {media_id}: {e}")
            raise

async def get_media_by_rss_url_from_db(rss_url: str) -> Optional[Dict[str, Any]]:
    if not rss_url: return None
    query = "SELECT * FROM media WHERE rss_url = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, rss_url)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching media by RSS URL {rss_url}: {e}")
            raise

async def get_all_media_from_db(skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    query = "SELECT * FROM media ORDER BY created_at DESC OFFSET $1 LIMIT $2;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, skip, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching all media: {e}")
            raise

async def update_media_in_db(media_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not update_data:
        logger.warning(f"No update data provided for media {media_id}.")
        return await get_media_by_id_from_db(media_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_data.items():
        if key == 'media_id': continue
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses:
        return await get_media_by_id_from_db(media_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE media SET {set_clause_str} WHERE media_id = ${idx} RETURNING *;"
    values.append(media_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Media updated: {media_id} with fields: {list(update_data.keys())}")
            return dict(row) if row else None
        except asyncpg.exceptions.UniqueViolationError as uve: # e.g. if rss_url has a UNIQUE constraint
            logger.warning(f"Failed to update media {media_id}, unique constraint violated: {uve}")
            raise
        except Exception as e:
            logger.exception(f"Error updating media {media_id}: {e}")
            raise

async def upsert_media_in_db(media_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Tries to find media by rss_url. If found, updates it. Otherwise, creates it."""
    rss_url = media_data.get('rss_url')
    existing_media = None
    if rss_url:
        existing_media = await get_media_by_rss_url_from_db(rss_url)
    
    if existing_media:
        media_id = existing_media['media_id']
        # Prepare update_data: exclude fields that shouldn't overwrite or are primary key
        update_payload = {k: v for k, v in media_data.items() if k != 'media_id' and v is not None}
        # Only update if there's something to update besides keys that match existing values
        # This is a simple check; more sophisticated diffing could be done
        changed = False
        for key, value in update_payload.items():
            if key in existing_media and existing_media[key] != value:
                changed = True
                break
            elif key not in existing_media:
                changed = True # New field being added
                break
        
        if changed or not update_payload: # if no payload, just return existing, if payload but no change, also return existing
            if changed:
                 logger.info(f"Updating existing media (ID: {media_id}) found by RSS: {rss_url}")
                 return await update_media_in_db(media_id, update_payload)
            else:
                 logger.info(f"Existing media (ID: {media_id}) found by RSS: {rss_url}. No changes detected in provided data.")
                 return existing_media # Return existing if no changes
        else:
            logger.info(f"Media found by RSS {rss_url}, no new data to update.")
            return existing_media
    else:
        # RSS URL not found or not provided, try to create new media
        # Ensure 'name' is present as it's required by MediaCreate / create_media_in_db
        if not media_data.get('name'):
            logger.warning("Attempted to upsert media without a name and non-matching RSS. Skipping.")
            return None
        logger.info(f"No existing media found by RSS: {rss_url} (or RSS not provided). Creating new media: {media_data.get('name')}")
        return await create_media_in_db(media_data)

async def delete_media_from_db(media_id: int) -> bool:
    query = "DELETE FROM media WHERE media_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, media_id)
            deleted_count = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
            if deleted_count > 0:
                logger.info(f"Media deleted: {media_id}")
                return True
            logger.warning(f"Media {media_id} not found for deletion or delete failed.")
            return False
        except Exception as e:
            logger.exception(f"Error deleting media {media_id}: {e}")
            raise

# --- MatchSuggestion Table CRUD Operations ---

async def create_match_suggestion_in_db(suggestion_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # match_id is SERIAL; created_at, client_approved, status have defaults in DB/Pydantic
    query = """
    INSERT INTO match_suggestions (
        campaign_id, media_id, match_score, matched_keywords, ai_reasoning, status, client_approved, approved_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Ensure matched_keywords is a list, even if empty or None
            keywords = suggestion_data.get("matched_keywords", [])
            if keywords is None:
                keywords = []

            row = await conn.fetchrow(
                query,
                suggestion_data['campaign_id'],
                suggestion_data['media_id'],
                suggestion_data.get('match_score'),
                keywords,
                suggestion_data.get('ai_reasoning'),
                suggestion_data.get('status', 'pending'), # Default if not provided
                suggestion_data.get('client_approved', False), # Default if not provided
                suggestion_data.get('approved_at')
            )
            logger.info(f"MatchSuggestion created for campaign {suggestion_data['campaign_id']} and media {suggestion_data['media_id']}")
            return dict(row) if row else None
        except Exception as e:
            # Could be UniqueViolationError if you add a unique constraint on (campaign_id, media_id)
            logger.exception(f"Error creating MatchSuggestion in DB: {e}")
            raise

async def get_match_suggestion_by_id_from_db(match_id: int) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM match_suggestions WHERE match_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, match_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching MatchSuggestion by ID {match_id}: {e}")
            raise

async def get_match_suggestions_for_campaign_from_db(campaign_id: uuid.UUID, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    query = "SELECT * FROM match_suggestions WHERE campaign_id = $1 ORDER BY created_at DESC OFFSET $2 LIMIT $3;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, campaign_id, skip, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching MatchSuggestions for campaign {campaign_id}: {e}")
            raise

async def update_match_suggestion_in_db(match_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not update_data:
        return await get_match_suggestion_by_id_from_db(match_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_data.items():
        if key == 'match_id': continue
        if key == 'campaign_id': continue # Usually not updated
        if key == 'media_id': continue    # Usually not updated
        
        # Ensure matched_keywords is a list if being updated
        if key == "matched_keywords" and val is not None and not isinstance(val, list):
            val = [kw.strip() for kw in str(val).split(',') if kw.strip()] 

        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses:
        return await get_match_suggestion_by_id_from_db(match_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE match_suggestions SET {set_clause_str} WHERE match_id = ${idx} RETURNING *;"
    values.append(match_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"MatchSuggestion {match_id} updated with fields: {list(update_data.keys())}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error updating MatchSuggestion {match_id}: {e}")
            raise

async def delete_match_suggestion_from_db(match_id: int) -> bool:
    query = "DELETE FROM match_suggestions WHERE match_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, match_id)
            deleted_count = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
            if deleted_count > 0:
                logger.info(f"MatchSuggestion deleted: {match_id}")
                return True
            return False
        except Exception as e:
            logger.exception(f"Error deleting MatchSuggestion {match_id}: {e}")
            raise

# --- Placeholder for other table CRUDs ---

# --- Life-cycle events for FastAPI (optional, can be in main_api.py) ---
# async def startup_event():
#     await init_db_pool()

# async def shutdown_event():
#     await close_db_pool()

