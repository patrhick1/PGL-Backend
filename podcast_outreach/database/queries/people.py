# podcast_outreach/database/queries/people.py

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncpg # For specific asyncpg exceptions

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool

logger = get_logger(__name__)

async def create_person_in_db(person_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    query = """
    INSERT INTO people (
        company_id, full_name, email, linkedin_profile_url, twitter_profile_url,
        instagram_profile_url, tiktok_profile_url, dashboard_username,
        dashboard_password_hash, attio_contact_id, role
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
    ) RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                person_data.get('company_id'), person_data.get('full_name'), person_data['email'],
                person_data.get('linkedin_profile_url'), person_data.get('twitter_profile_url'),
                person_data.get('instagram_profile_url'), person_data.get('tiktok_profile_url'),
                person_data.get('dashboard_username'), person_data.get('dashboard_password_hash'),
                person_data.get('attio_contact_id'), person_data.get('role')
            )
            logger.info(f"Person created: {person_data.get('email')}")
            return dict(row) if row else None
        except asyncpg.exceptions.UniqueViolationError:
            logger.warning(f"Person with email {person_data['email']} already exists.")
            return None
        except Exception as e:
            logger.exception(f"Error creating person {person_data.get('email')} in DB: {e}")
            raise

async def get_person_by_id_from_db(person_id: int) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM people WHERE person_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, person_id)
            if not row:
                logger.debug(f"Person not found: {person_id}")
                return None
            return dict(row)
        except Exception as e:
            logger.exception(f"Error fetching person {person_id}: {e}")
            raise

async def get_person_by_email_from_db(email: str) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM people WHERE email = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, email)
            if not row:
                logger.debug(f"Person not found by email: {email}")
                return None
            return dict(row)
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

async def update_person_in_db(person_id: int, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not update_fields:
        logger.warning(f"No update data for person {person_id}. Fetching current.")
        return await get_person_by_id_from_db(person_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_fields.items():
        if key == "person_id": continue # Don't update the ID
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses: # No valid fields to update
        return await get_person_by_id_from_db(person_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE people SET {set_clause_str} WHERE person_id = ${idx} RETURNING *;"
    values.append(person_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Person updated: {person_id} with fields: {list(update_fields.keys())}")
            return dict(row) if row else None
        except asyncpg.exceptions.UniqueViolationError:
            logger.warning(f"Update failed for person {person_id}: email {update_fields.get('email')} already exists.")
            return None
        except Exception as e:
            logger.exception(f"Error updating person {person_id}: {e}")
            raise

async def update_person_password_hash(person_id: int, password_hash: str) -> bool:
    query = "UPDATE people SET dashboard_password_hash = $1 WHERE person_id = $2;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, password_hash, person_id)
            updated_count = int(result.split(" ")[1]) if result.startswith("UPDATE ") else 0
            if updated_count > 0:
                logger.info(f"Password hash updated for person {person_id}.")
                return True
            logger.warning(f"Person {person_id} not found for password hash update.")
            return False
        except Exception as e:
            logger.exception(f"Error updating password hash for person {person_id}: {e}")
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
            logger.warning(f"Person not found for deletion or delete failed: {person_id}")
            return False
        except Exception as e:
            logger.exception(f"Error deleting person {person_id} from DB: {e}")
            raise

async def get_person_by_dashboard_username(dashboard_username: str) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM people WHERE dashboard_username = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, dashboard_username)
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching person by dashboard username {dashboard_username}: {e}")
            return None