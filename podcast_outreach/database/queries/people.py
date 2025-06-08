# podcast_outreach/database/queries/people.py

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncpg # For specific asyncpg exceptions
import json # ADD THIS IMPORT

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool

logger = get_logger(__name__)

def _process_person_row(row_proxy) -> Optional[Dict[str, Any]]:
    if not row_proxy:
        return None
    row_dict = dict(row_proxy)
    # This list should contain all your JSON/JSONB column names
    jsonb_field_names = ['notification_settings', 'privacy_settings']
    for field_name in jsonb_field_names:
        if field_name in row_dict and isinstance(row_dict[field_name], str):
            try:
                row_dict[field_name] = json.loads(row_dict[field_name])
            except json.JSONDecodeError:
                logger.warning(f"Could not parse JSON string for {field_name} in person_id {row_dict.get('person_id')}. Setting to None.")
                row_dict[field_name] = None
        elif field_name in row_dict and row_dict[field_name] is None:
            pass 
        elif field_name in row_dict and not isinstance(row_dict[field_name], dict) and not isinstance(row_dict[field_name], list): # Allow lists too for JSON
            logger.warning(f"Unexpected type for {field_name} in person_id {row_dict.get('person_id')}: {type(row_dict[field_name])}. Setting to None.")
            row_dict[field_name] = None
    return row_dict

async def create_person_in_db(person_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # Define JSONB fields that might be part of person_data
    jsonb_fields_on_create = ['notification_settings', 'privacy_settings']
    
    # Prepare base query parts
    columns = [
        "company_id", "full_name", "email", "linkedin_profile_url", "twitter_profile_url",
        "instagram_profile_url", "tiktok_profile_url", "dashboard_username",
        "dashboard_password_hash", "attio_contact_id", "role"
    ]
    values_placeholders = [f"${i+1}" for i in range(len(columns))]
    
    insert_values = [
        person_data.get('company_id'), person_data.get('full_name'), person_data.get('email'),
        person_data.get('linkedin_profile_url'), person_data.get('twitter_profile_url'),
        person_data.get('instagram_profile_url'), person_data.get('tiktok_profile_url'),
        person_data.get('dashboard_username'), person_data.get('dashboard_password_hash'),
        person_data.get('attio_contact_id'), person_data.get('role')
    ]

    # Dynamically add JSONB fields if they are present in person_data
    # This assumes these fields are optional and might not always be provided on creation.
    # If they are mandatory or have defaults in DB, this might need adjustment.
    current_placeholder_idx = len(columns) + 1
    for field_name in jsonb_fields_on_create:
        if field_name in person_data:
            columns.append(field_name)
            values_placeholders.append(f"${current_placeholder_idx}")
            current_placeholder_idx += 1
            
            val = person_data.get(field_name)
            if isinstance(val, (dict, list)):
                insert_values.append(json.dumps(val))
            else: # Handles None, str, or other types (which might be an issue if not str/None)
                insert_values.append(val)

    query = f"""
    INSERT INTO people ({", ".join(columns)})
    VALUES ({", ".join(values_placeholders)})
    RETURNING *;
    """
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *insert_values)
            logger.info(f"Person created: {person_data.get('full_name')} (Email: {person_data.get('email', 'N/A')})")
            return _process_person_row(row) # Use _process_person_row here
        except asyncpg.exceptions.UniqueViolationError:
            logger.warning(f"Person with email {person_data.get('email')} already exists.")
            return None
        except Exception as e:
            logger.exception(f"Error creating person {person_data.get('email')} in DB: {e}")
            raise

async def get_person_by_id_from_db(person_id: int) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM people WHERE person_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row_proxy = await conn.fetchrow(query, person_id)
            if not row_proxy:
                logger.debug(f"Person not found: {person_id}")
                return None
            return _process_person_row(row_proxy)
        except Exception as e:
            logger.exception(f"Error fetching person {person_id}: {e}")
            raise

async def get_person_by_email_from_db(email: str) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM people WHERE email = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row_proxy = await conn.fetchrow(query, email)
            if not row_proxy:
                logger.debug(f"Person not found by email: {email}")
                return None
            return _process_person_row(row_proxy)
        except Exception as e:
            logger.exception(f"Error fetching person by email {email}: {e}")
            raise

async def get_all_people_from_db(skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    query = "SELECT * FROM people ORDER BY created_at DESC OFFSET $1 LIMIT $2;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows_proxy = await conn.fetch(query, skip, limit)
            return [_process_person_row(row) for row in rows_proxy if row]
        except Exception as e:
            logger.exception(f"Error fetching all people: {e}")
            return []

async def update_person_in_db(person_id: int, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not update_fields:
        logger.warning(f"No update data for person {person_id}. Fetching current.")
        return await get_person_by_id_from_db(person_id)

    set_clauses = []
    values = []
    idx = 1
    
    # Define which fields are JSONB and need special handling for serialization
    jsonb_fields_on_update = ['notification_settings', 'privacy_settings']

    for key, val in update_fields.items():
        if key == "person_id": continue # Don't update the ID
        
        set_clauses.append(f"{key} = ${idx}")
        
        if key in jsonb_fields_on_update and isinstance(val, (dict, list)):
            # If the field is a JSONB field and the value is a dict or list,
            # serialize it to a JSON string.
            values.append(json.dumps(val))
        else:
            # For other fields, or if the JSONB field value is already a string or None,
            # append the value directly. asyncpg handles None as SQL NULL.
            # If val is a string, it's assumed to be a valid JSON string if for a JSONB field.
            values.append(val)
        idx += 1

    if not set_clauses: # No valid fields to update
        logger.warning(f"No valid fields to update for person {person_id} after filtering. Fetching current.")
        return await get_person_by_id_from_db(person_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE people SET {set_clause_str} WHERE person_id = ${idx} RETURNING *;"
    values.append(person_id) # Add person_id for the WHERE clause

    # Your existing debug block. Consider making the setLevel temporary or conditional.
    # current_log_level = logger.level
    # logger.setLevel(logging.DEBUG)
    logger.debug(f"FORCED DEBUG: Executing update_person_in_db query: {query}")
    logger.debug(f"FORCED DEBUG: With values: {values}")
    for i, v_debug in enumerate(values):
        logger.debug(f"FORCED DEBUG: Value at index {i} (for ${i+1}): {v_debug} (type: {type(v_debug)})")
    # logger.setLevel(current_log_level) # Revert logger level

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            logger.info(f"Person updated: {person_id} with fields: {list(update_fields.keys())}")
            return _process_person_row(row) # Correctly using _process_person_row
        except asyncpg.exceptions.UniqueViolationError:
            logger.warning(f"Update failed for person {person_id} due to unique constraint: email {update_fields.get('email')} may already exist.")
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
            row_proxy = await conn.fetchrow(query, dashboard_username)
            return _process_person_row(row_proxy)
        except Exception as e:
            logger.error(f"Error fetching person by dashboard username {dashboard_username}: {e}")
            return 

async def get_person_by_full_name(full_name: str) -> Optional[Dict[str, Any]]:
    """
    Fetches a person record by their full name.
    NOTE: This is a simple case-sensitive match. For more robust matching,
    consider using ILIKE or other text-matching functions.
    """
    query = "SELECT * FROM people WHERE full_name = $1 LIMIT 1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row_proxy = await conn.fetchrow(query, full_name)
            return _process_person_row(row_proxy)
        except Exception as e:
            logger.error(f"Error fetching person by full name '{full_name}': {e}")
            return None