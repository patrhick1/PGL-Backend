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

async def get_match_suggestion_by_campaign_and_media_ids(campaign_id: uuid.UUID, media_id: int) -> Optional[Dict[str, Any]]:
    """Checks if a match suggestion exists for a given campaign_id and media_id."""
    query = "SELECT * FROM match_suggestions WHERE campaign_id = $1 AND media_id = $2;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id, media_id)
            if row:
                logger.debug(f"Found existing MatchSuggestion for campaign {campaign_id} and media {media_id}")
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error fetching MatchSuggestion by campaign_id {campaign_id} and media_id {media_id}: {e}")
            return None # Treat errors as "not found" for the purpose of avoiding duplicate creation

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

async def approve_match_suggestion_in_db(match_id: int) -> Optional[Dict[str, Any]]:
    """Updates a match_suggestion record to set it as approved."""
    query = """
    UPDATE match_suggestions
    SET client_approved = TRUE,
        status = 'approved',
        approved_at = NOW()
    WHERE match_id = $1
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, match_id)
            if row:
                logger.info(f"MatchSuggestion ID {match_id} has been approved.")
                return dict(row)
            logger.warning(f"MatchSuggestion ID {match_id} not found for approval update.")
            return None
        except Exception as e:
            logger.exception(f"Error approving MatchSuggestion ID {match_id}: {e}")
            raise

# --- Episode Sync Specific Functions ---

async def get_media_to_sync_episodes(interval_hours: int = 24) -> List[Dict[str, Any]]:
    """Fetches media records that need their episodes synced.
    
    Args:
        interval_hours: The interval in hours to check against last_fetched_at.
                        Podcasts not fetched within this interval will be returned.
    """
    # Fetches media_id, name, rss_url, and api_id (potential Podscan ID).
    # Assumes api_id might be Podscan ID if source_api indicates so (handled by caller).
    query = f"""
    SELECT media_id, name, rss_url, api_id, source_api
    FROM media
    WHERE last_fetched_at IS NULL OR last_fetched_at < (NOW() - INTERVAL '{interval_hours} hours');
    """
    # Note: The interval string formatting might need care depending on DB driver or ORM.
    # For asyncpg, direct parameterization of interval literals like '$1 hours' is tricky.
    # Using an f-string here for clarity, but ensure it's safe if interval_hours could be non-integer.
    # A safer way with asyncpg might be: NOW() - make_interval(hours => $1)
    # For simplicity, let's assume interval_hours is a trusted integer.
    # Corrected query for asyncpg parameterization:
    query_correct = """
    SELECT media_id, name, rss_url, api_id, source_api
    FROM media
    WHERE last_fetched_at IS NULL OR last_fetched_at < (NOW() - make_interval(hours => $1));
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query_correct, interval_hours)
            logger.info(f"Found {len(rows)} media items needing episode sync (interval: {interval_hours}hrs).")
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching media to sync episodes: {e}")
            return []

async def get_existing_episode_identifiers(media_id: int) -> set[tuple[str, datetime.date]]:
    """Fetches a set of (title, publish_date) tuples for a given media_id to check for duplicates."""
    query = "SELECT title, publish_date FROM episodes WHERE media_id = $1 AND title IS NOT NULL AND publish_date IS NOT NULL;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, media_id)
            # Ensure publish_date is converted to date object if it's datetime coming from DB
            # and title is available.
            return {(row['title'], row['publish_date']) for row in rows if row['title'] and row['publish_date']}
        except Exception as e:
            logger.exception(f"Error fetching existing episode identifiers for media_id {media_id}: {e}")
            return set()

async def insert_episodes_batch(episodes_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Batch inserts new episodes into the episodes table.
    
    Args:
        episodes_data: A list of dictionaries, where each dictionary represents an episode
                       and its keys match the column names in the 'episodes' table.
                       Required keys: media_id, title, publish_date.
                       Optional: duration_sec, episode_summary, episode_url, transcript, transcribe, 
                                 downloaded, guest_names, source_api, api_episode_id.
    Returns:
        A list of the inserted records (dictionaries), or an empty list if insertion failed.
    """
    if not episodes_data:
        return []

    query = """
    INSERT INTO episodes (
        media_id, title, publish_date, duration_sec, episode_summary,
        episode_url, transcript, transcribe, downloaded, guest_names,
        source_api, api_episode_id
        -- ai_episode_summary and embedding are typically populated later
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
    RETURNING *;
    """
    
    pool = await get_db_pool()
    inserted_rows = []
    async with pool.acquire() as conn:
        async with conn.transaction(): # Ensure atomicity for batch insert
            for episode_datum in episodes_data:
                try:
                    row = await conn.fetchrow(
                        query,
                        episode_datum['media_id'],
                        episode_datum['title'],
                        episode_datum['publish_date'],
                        episode_datum.get('duration_sec'),
                        episode_datum.get('episode_summary'),
                        episode_datum.get('episode_url'),
                        episode_datum.get('transcript'),
                        episode_datum.get('transcribe', False), # Default to False if not provided
                        episode_datum.get('downloaded', False), # Default to False
                        episode_datum.get('guest_names'),
                        episode_datum.get('source_api'),
                        episode_datum.get('api_episode_id')
                    )
                    if row:
                        inserted_rows.append(dict(row))
                except Exception as e:
                    logger.error(f"Error inserting episode '{episode_datum.get('title')}' for media_id {episode_datum.get('media_id')}: {e}")
                    # Decide on error handling: continue, or raise to rollback transaction?
                    # For now, log and continue with other episodes in the batch.
                    # If a full rollback is desired on any error, re-raise e here.
    
    logger.info(f"Batch inserted {len(inserted_rows)} out of {len(episodes_data)} provided episodes.")
    return inserted_rows

async def trim_old_episodes(media_id: int, keep_count: int = 10) -> int:
    """Deletes the oldest episodes for a given media_id if the total exceeds keep_count.
    
    Args:
        media_id: The ID of the media whose episodes to trim.
        keep_count: The maximum number of recent episodes to keep.
        
    Returns:
        The number of episodes deleted.
    """
    # This query uses a CTE to find the episode_ids to delete.
    # It selects all episodes for the media_id, orders them by publish_date (oldest first),
    # applies an offset (to keep the `keep_count` newest ones), and then deletes those selected.
    query = """
    WITH episodes_to_delete AS (
        SELECT episode_id
        FROM episodes
        WHERE media_id = $1
        ORDER BY publish_date DESC, episode_id DESC -- Ensure stable sort for LIMIT/OFFSET
        OFFSET $2
    )
    DELETE FROM episodes
    WHERE episode_id IN (SELECT episode_id FROM episodes_to_delete)
    RETURNING episode_id;
    """
    # Alternative using a subquery if CTE is complex for the driver or preference:
    # DELETE FROM episodes
    # WHERE episode_id IN (
    # SELECT episode_id
    # FROM episodes
    # WHERE media_id = $1
    # ORDER BY publish_date ASC, episode_id ASC -- Oldest first for deletion
    # OFFSET $2 -- This interpretation of OFFSET might be wrong for some SQL dialects if we want to delete *after* the offset.
    # Correct logic: Delete episodes that are NOT in the most recent 'keep_count'.
    query_correct = """
    DELETE FROM episodes
    WHERE episode_id IN (
        SELECT episode_id
        FROM episodes
        WHERE media_id = $1
        ORDER BY publish_date ASC, episode_id ASC 
        LIMIT (SELECT GREATEST(0, COUNT(*) - $2) FROM episodes WHERE media_id = $1)
    )
    RETURNING episode_id;
    """
    # Simpler: Find IDs of episodes to keep, then delete those NOT IN that set.
    query_final = """
    DELETE FROM episodes
    WHERE media_id = $1 AND episode_id NOT IN (
        SELECT episode_id
        FROM episodes
        WHERE media_id = $1
        ORDER BY publish_date DESC, episode_id DESC
        LIMIT $2
    )
    RETURNING episode_id;
    """
    
    pool = await get_db_pool()
    deleted_count = 0
    async with pool.acquire() as conn:
        try:
            # First check current count to avoid unnecessary delete operation
            current_count_row = await conn.fetchrow("SELECT COUNT(*) as count FROM episodes WHERE media_id = $1;", media_id)
            current_episode_count = current_count_row['count'] if current_count_row else 0

            if current_episode_count > keep_count:
                result = await conn.fetch(query_final, media_id, keep_count)
                deleted_count = len(result)
                logger.info(f"Trimmed {deleted_count} old episodes for media_id {media_id} (kept {keep_count} newest).")
            else:
                logger.info(f"No episodes trimmed for media_id {media_id}, count ({current_episode_count}) does not exceed keep_count ({keep_count}).")
        except Exception as e:
            logger.exception(f"Error trimming old episodes for media_id {media_id}: {e}")
    return deleted_count

async def flag_episodes_for_transcription(media_id: int, count: int = 4) -> int:
    """Flags the most recent 'count' episodes for a media_id to be transcribed.
    Sets 'transcribe = TRUE' for newest episodes that are not yet downloaded and have no transcript.
    Older episodes for the same media_id that were previously TRUE but now fall outside the 'count'
    and are still not downloaded will be set to FALSE.

    Returns:
        The number of episodes newly flagged as TRUE.
    """
    pool = await get_db_pool()
    updated_count = 0
    async with pool.acquire() as conn:
        async with conn.transaction(): # Use a transaction for atomicity
            try:
                # Step 1: Identify episode_ids of the 'count' most recent, unprocessed episodes
                # These are candidates to be set to TRUE.
                candidate_ids_query = """
                SELECT episode_id
                FROM episodes
                WHERE media_id = $1 AND downloaded = FALSE AND (transcript IS NULL OR transcript = '')
                ORDER BY COALESCE(publish_date, '1970-01-01') DESC, episode_id DESC
                LIMIT $2;
                """
                candidate_rows = await conn.fetch(candidate_ids_query, media_id, count)
                candidate_ids = [row['episode_id'] for row in candidate_rows]

                # Step 2: Set transcribe = FALSE for episodes of this media that are:
                #   - Currently TRUE
                #   - AND NOT in our candidate_ids list (i.e., they are older or already processed but somehow still TRUE)
                #   - AND still downloaded = FALSE (don't unflag something already processed if it was TRUE)
                # This prevents unflagging episodes that are already successfully transcribed but might have been left as TRUE.
                # And ensures older, unprocessed episodes that were TRUE are reset if they are no longer in the top 'count'.
                if candidate_ids: # Only run if there are candidates to avoid unsetting all if no candidates found
                    reset_false_query = f"""
                    UPDATE episodes
                    SET transcribe = FALSE, updated_at = NOW()
                    WHERE media_id = $1 AND transcribe = TRUE AND downloaded = FALSE
                    AND episode_id NOT IN ({','.join(map(str, candidate_ids))});
                    """ # Using f-string for IN clause with list of ints, ensure IDs are safe
                    await conn.execute(reset_false_query, media_id)
                else: # No candidates, so ensure all pending for this media are FALSE if they are TRUE and not downloaded
                    await conn.execute(
                        "UPDATE episodes SET transcribe = FALSE, updated_at = NOW() WHERE media_id = $1 AND transcribe = TRUE AND downloaded = FALSE;",
                        media_id
                    )

                # Step 3: Set transcribe = TRUE for the identified candidate_ids
                if candidate_ids:
                    set_true_query = f"""
                    UPDATE episodes
                    SET transcribe = TRUE, updated_at = NOW()
                    WHERE episode_id IN ({','.join(map(str, candidate_ids))})
                    RETURNING episode_id;
                    """
                    flagged_rows = await conn.fetch(set_true_query)
                    updated_count = len(flagged_rows)
                    logger.info(f"Flagged {updated_count} episodes for transcription for media_id {media_id} (target: {count}). Candidates: {candidate_ids}")
                else:
                    logger.info(f"No new episodes to flag for transcription for media_id {media_id} (target: {count}).")

            except Exception as e:
                logger.exception(f"Error flagging episodes for transcription for media_id {media_id}: {e}")
                # Transaction will be rolled back on exception
                # Re-raise to ensure the caller knows it failed.
                raise
    return updated_count

async def update_media_after_sync(media_id: int) -> bool:
    """Updates the last_fetched_at timestamp and sets fetched_episodes to TRUE for a media record."""
    query = "UPDATE media SET last_fetched_at = NOW(), fetched_episodes = TRUE WHERE media_id = $1 RETURNING media_id;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            updated_row = await conn.fetchrow(query, media_id)
            if updated_row:
                logger.info(f"Updated last_fetched_at and fetched_episodes for media_id {media_id}.")
                return True
            logger.warning(f"Failed to update sync status for media_id {media_id} (not found or no change).")
            return False
        except Exception as e:
            logger.exception(f"Error updating sync status for media_id {media_id}: {e}")
            return False

async def update_media_latest_episode_date(media_id: int) -> bool:
    """Updates the latest_episode_date for a media record based on its current episodes."""
    query = """
    UPDATE media
    SET latest_episode_date = (SELECT MAX(publish_date) FROM episodes WHERE media_id = media.media_id)
    WHERE media_id = $1
    RETURNING media_id;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            updated_row = await conn.fetchrow(query, media_id)
            if updated_row:
                logger.info(f"Updated latest_episode_date for media_id {media_id}.")
                return True
            logger.warning(f"Failed to update latest_episode_date for media_id {media_id} (not found or no episodes).")
            return False
        except Exception as e:
            logger.exception(f"Error updating latest_episode_date for media_id {media_id}: {e}")
            return False

# --- ReviewTasks Table CRUD Operations ---

async def create_review_task_in_db(review_task_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Creates a new review task in the database."""
    query = """
    INSERT INTO review_tasks (
        task_type, related_id, campaign_id, assigned_to, status, notes
    ) VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                review_task_data['task_type'],
                review_task_data['related_id'],
                review_task_data.get('campaign_id'), # campaign_id can be None for other task types potentially
                review_task_data.get('assigned_to'),
                review_task_data.get('status', 'pending'), # Default status if not provided
                review_task_data.get('notes')
            )
            if row:
                logger.info(f"ReviewTask created for type '{row['task_type']}' related_id {row['related_id']}")
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error creating ReviewTask in DB: {e}")
            raise

async def update_review_task_status_in_db(review_task_id: int, status: str, notes: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Updates the status and completed_at timestamp of a review task. Optionally updates notes."""
    set_clauses = ["status = $1", "completed_at = NOW()"]
    values = [status]
    idx = 2 # Start parameter index from $2

    if notes is not None:
        set_clauses.append(f"notes = ${idx}")
        values.append(notes)
        idx += 1

    query = f"""
    UPDATE review_tasks
    SET {', '.join(set_clauses)}
    WHERE review_task_id = ${idx}
    RETURNING *;
    """
    values.append(review_task_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            if row:
                logger.info(f"ReviewTask ID {review_task_id} updated to status '{status}'.")
                return dict(row)
            logger.warning(f"ReviewTask ID {review_task_id} not found for update.")
            return None
        except Exception as e:
            logger.exception(f"Error updating ReviewTask ID {review_task_id}: {e}")
            raise

async def get_review_task_by_id_from_db(review_task_id: int) -> Optional[Dict[str, Any]]: # Helper function, assuming it might be needed
    """Fetches a review task by its ID."""
    query = "SELECT * FROM review_tasks WHERE review_task_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, review_task_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching ReviewTask by ID {review_task_id}: {e}")
            raise # Or return None depending on desired error handling for callers

async def process_match_suggestion_approval(review_task_id: int, new_status: str, approver_notes: Optional[str] = None) -> bool:
    """Processes the approval/rejection of a review task, specifically handling match_suggestion approvals."""
    
    # Step 1: Fetch the review task to get its details (like task_type and related_id)
    review_task = await get_review_task_by_id_from_db(review_task_id)
    if not review_task:
        logger.error(f"ReviewTask ID {review_task_id} not found. Cannot process approval.")
        return False

    # Step 2: Update the review task itself
    updated_review_task = await update_review_task_status_in_db(review_task_id, new_status, approver_notes)
    if not updated_review_task:
        logger.error(f"Failed to update ReviewTask ID {review_task_id}. Aborting further processing.")
        return False

    logger.info(f"ReviewTask ID {review_task_id} status updated to '{new_status}'.")

    # Step 3: If the task was a 'match_suggestion' and it was 'approved', update the match_suggestion table
    if review_task.get('task_type') == 'match_suggestion' and new_status == 'approved':
        related_match_id = review_task.get('related_id')
        if related_match_id is None:
            logger.error(f"ReviewTask ID {review_task_id} is a match_suggestion but has no related_id. Cannot approve match.")
            return False # Or raise an error for data inconsistency
        
        approved_match = await approve_match_suggestion_in_db(related_match_id)
        if not approved_match:
            logger.error(f"Failed to approve MatchSuggestion ID {related_match_id} linked to ReviewTask ID {review_task_id}.")
            # Potentially consider rolling back the review_task update or setting its status to an error state
            return False
        logger.info(f"Successfully approved MatchSuggestion ID {related_match_id} as part of ReviewTask ID {review_task_id} approval.")
    
    elif review_task.get('task_type') == 'match_suggestion' and new_status == 'rejected':
        # Optionally, handle rejection of a match_suggestion if specific logic is needed
        # For example, update match_suggestions.status to 'rejected'
        related_match_id = review_task.get('related_id')
        if related_match_id:
             # update_data = {'status': 'rejected', 'client_approved': False} # Example
             # await update_match_suggestion_in_db(related_match_id, update_data) # Assuming update_match_suggestion_in_db exists
             logger.info(f"MatchSuggestion ID {related_match_id} (from ReviewTask {review_task_id}) was marked as '{new_status}'. Additional logic for match_suggestions update can be added here.")
        else:
            logger.warning(f"ReviewTask ID {review_task_id} (match_suggestion) was rejected but has no related_id.")

    # Add more task_type handling here if needed in the future
    # elif review_task.get('task_type') == 'another_type' and new_status == 'approved':
    #     # ... logic for another_type ...

    return True

# --- Placeholder for other table CRUDs ---

# --- Life-cycle events for FastAPI (optional, can be in main_api.py) ---
# async def startup_event():
#     await init_db_pool()

# async def shutdown_event():
#     await close_db_pool()

# --- Media Enrichment Functions ---

async def get_media_for_enrichment(batch_size: int = 10, enriched_before_hours: int = 168) -> List[Dict[str, Any]]: # Default to 1 week
    """Fetches a batch of media records for metadata enrichment.

    Args:
        batch_size: Number of records to fetch.
        enriched_before_hours: Fetches media last enriched more than this many hours ago,
                               or never enriched (last_enriched_timestamp IS NULL).
                               Also prioritizes media with no quality_score.

    Returns:
        A list of dictionaries, where each dictionary represents a media record.
    """
    query = """
    SELECT 
        media_id, api_id, name, title, description, rss_url, image_url, website, 
        language, podcast_spotify_id, itunes_id, total_episodes, last_posted_at, 
        listen_score, listen_score_global_rank, audience_size, 
        itunes_rating_average, itunes_rating_count, spotify_rating_average, spotify_rating_count,
        podcast_twitter_url, podcast_linkedin_url, podcast_instagram_url, 
        podcast_facebook_url, podcast_youtube_url, podcast_tiktok_url, podcast_other_social_url,
        rss_owner_name, rss_owner_email, host_names, contact_email, category, company_id,
        last_enriched_timestamp, quality_score, first_episode_date
        -- Add any other fields needed by the EnrichmentAgent's initial processing
    FROM media
    WHERE 
        (last_enriched_timestamp IS NULL OR last_enriched_timestamp < (NOW() - make_interval(hours => $1)))
        OR quality_score IS NULL -- Prioritize those that have never been quality scored
    ORDER BY 
        (quality_score IS NULL) DESC, -- True (IS NULL) comes before False (IS NOT NULL)
        last_enriched_timestamp ASC NULLS FIRST, 
        media_id ASC
    LIMIT $2;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, enriched_before_hours, batch_size)
            logger.info(f"Fetched {len(rows)} media items for enrichment (batch_size={batch_size}, enriched_before_hours={enriched_before_hours}).")
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching media for enrichment: {e}")
            return []

async def update_media_enrichment_data(media_id: int, enriched_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates a media record with enriched data.
    
    Note: quality_score is typically updated by a separate process after transcriptions.
    This function primarily updates metadata fields and last_enriched_timestamp.

    Args:
        media_id: The ID of the media record to update.
        enriched_data: A dictionary of fields to update. Keys should match column names.
                       Expected to always include `last_enriched_timestamp`.

    Returns:
        The updated media record as a dictionary, or None if update failed.
    """
    if not enriched_data:
        logger.warning(f"No enrichment data provided for media_id {media_id}. Skipping update.")
        return await get_media_by_id_from_db(media_id) # Return current state

    # Ensure last_enriched_timestamp is set, even if not explicitly in enriched_data, 
    # as this function signifies an enrichment attempt.
    if 'last_enriched_timestamp' not in enriched_data:
        enriched_data['last_enriched_timestamp'] = datetime.utcnow() # Use a Python datetime object

    set_clauses = []
    values = []
    placeholder_idx = 1
    for key, value in enriched_data.items():
        if key in ['media_id', 'updated_at', 'created_at', 'quality_score']: # These are not updated here or handled by DB
            continue 
        set_clauses.append(f"{key} = ${placeholder_idx}")
        values.append(value)
        placeholder_idx += 1

    if not set_clauses:
        logger.info(f"No valid fields to update for media_id {media_id} after filtering. Fetching current.")
        return await get_media_by_id_from_db(media_id)

    # updated_at is handled by a trigger, but explicitly setting last_enriched_timestamp is important.
    query = f"""
    UPDATE media 
    SET {', '.join(set_clauses)}
    WHERE media_id = ${placeholder_idx}
    RETURNING *;
    """
    values.append(media_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            updated_row = await conn.fetchrow(query, *values)
            if updated_row:
                logger.info(f"Successfully updated enriched data for media_id {media_id}. Fields: {list(enriched_data.keys())}")
                return dict(updated_row)
            else:
                logger.warning(f"Failed to update or find media_id {media_id} for enrichment update.")
                return None
        except asyncpg.exceptions.DataError as de:
             logger.error(f"DataError updating media_id {media_id}: {de}. Values: {values}")
             raise
        except Exception as e:
            logger.exception(f"Error updating enriched data for media_id {media_id}: {e}")
            raise

# --- Episode Transcription & Quality Score Related Functions ---

async def get_episodes_to_transcribe(batch_size: int = 50) -> List[Dict[str, Any]]:
    """Fetches episodes that are marked for transcription and not yet downloaded/processed."""
    query = """
    SELECT episode_id, media_id, episode_url, title
    FROM episodes
    WHERE transcribe = TRUE AND downloaded = FALSE
    ORDER BY media_id, COALESCE(publish_date, '1970-01-01') DESC, episode_id DESC
    LIMIT $1;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, batch_size)
            logger.info(f"Fetched {len(rows)} episodes to transcribe.")
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching episodes to transcribe: {e}")
            return []

async def update_episode_transcript(episode_id: int, transcript_text: str, guest_names_str: Optional[str]) -> bool:
    """Updates an episode with the transcript, guest names, and marks it as downloaded."""
    query = """
    UPDATE episodes 
    SET transcript = $1, guest_names = $2, downloaded = TRUE, updated_at = NOW()
    WHERE episode_id = $3
    RETURNING episode_id;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.fetchval(query, transcript_text, guest_names_str, episode_id)
            if result == episode_id:
                logger.info(f"Successfully updated transcript for episode_id {episode_id}.")
                return True
            logger.warning(f"Failed to update transcript for episode_id {episode_id} (not found or no change).")
            return False
        except Exception as e:
            logger.exception(f"Error updating transcript for episode_id {episode_id}: {e}")
            return False

async def count_transcribed_episodes_for_media(media_id: int) -> int:
    """Counts episodes for a given media_id that have a non-empty transcript and are marked downloaded."""
    query = """
    SELECT COUNT(*) 
    FROM episodes 
    WHERE media_id = $1 AND downloaded = TRUE AND transcript IS NOT NULL AND transcript != '';
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            count = await conn.fetchval(query, media_id)
            return count if count is not None else 0
        except Exception as e:
            logger.exception(f"Error counting transcribed episodes for media_id {media_id}: {e}")
            return 0

async def update_media_quality_score(media_id: int, score: float) -> bool:
    """Updates the quality_score for a given media_id."""
    query = """
    UPDATE media 
    SET quality_score = $1, updated_at = NOW()
    WHERE media_id = $2
    RETURNING media_id;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.fetchval(query, score, media_id)
            if result == media_id:
                logger.info(f"Successfully updated quality_score for media_id {media_id} to {score}.")
                return True
            logger.warning(f"Failed to update quality_score for media_id {media_id} (not found or no change).")
            return False
        except Exception as e:
            logger.exception(f"Error updating quality_score for media_id {media_id}: {e}")
            return False

# --- END: Media Enrichment Functions ---

