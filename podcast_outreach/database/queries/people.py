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
    """
    Cascade delete a person and all their related records.
    This is an admin-only function that removes all data associated with a person.
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Start a transaction to ensure atomicity
            async with conn.transaction():
                # First, get person info for logging
                person = await conn.fetchrow("SELECT full_name, email FROM people WHERE person_id = $1", person_id)
                if not person:
                    logger.warning(f"Person not found for deletion: {person_id}")
                    return False
                
                logger.info(f"Starting deletion process for person {person_id} ({person['full_name']}, {person['email']})")
                
                # Delete in order of dependencies (most dependent first)
                
                # 1. Handle review_tasks (NO ACTION constraint - need to nullify)
                result = await conn.execute("UPDATE review_tasks SET assigned_to = NULL WHERE assigned_to = $1", person_id)
                logger.debug(f"Nullified {result} review_tasks assignments")
                
                # 2. Get all campaigns for this person (need to handle campaign-related data)
                campaign_ids = await conn.fetch("SELECT campaign_id FROM campaigns WHERE person_id = $1", person_id)
                logger.info(f"Found {len(campaign_ids)} campaigns for person {person_id}")
                
                # 3. Delete all campaign-dependent data first
                if campaign_ids:
                    campaign_id_list = [str(row['campaign_id']) for row in campaign_ids]
                    
                    # Delete conversation insights first (depends on chatbot_conversations)
                    # Check if table exists first
                    table_exists = await conn.fetchval("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'conversation_insights'
                        )
                    """)
                    
                    if table_exists:
                        result = await conn.execute("""
                            DELETE FROM conversation_insights 
                            WHERE conversation_id IN (
                                SELECT conversation_id FROM chatbot_conversations 
                                WHERE campaign_id = ANY($1::uuid[])
                            )
                        """, campaign_id_list)
                        logger.debug(f"Deleted {result} conversation insights")
                    
                    # Delete status_history (depends on placements)
                    result = await conn.execute("""
                        DELETE FROM status_history 
                        WHERE placement_id IN (
                            SELECT placement_id FROM placements 
                            WHERE campaign_id = ANY($1::uuid[])
                        )
                    """, campaign_id_list)
                    logger.debug(f"Deleted {result} status history records")
                    
                    # Delete AI usage logs
                    result = await conn.execute("""
                        DELETE FROM ai_usage_logs 
                        WHERE related_campaign_id = ANY($1::uuid[])
                    """, campaign_id_list)
                    logger.debug(f"Deleted {result} AI usage logs")
                    
                    # Delete pitches (depends on pitch_generations and placements)
                    result = await conn.execute("""
                        DELETE FROM pitches 
                        WHERE campaign_id = ANY($1::uuid[])
                    """, campaign_id_list)
                    logger.debug(f"Deleted {result} pitches")
                    
                    # Delete pitch_generations
                    result = await conn.execute("""
                        DELETE FROM pitch_generations 
                        WHERE campaign_id = ANY($1::uuid[])
                    """, campaign_id_list)
                    logger.debug(f"Deleted {result} pitch generations")
                    
                    # Delete placements
                    result = await conn.execute("""
                        DELETE FROM placements 
                        WHERE campaign_id = ANY($1::uuid[])
                    """, campaign_id_list)
                    logger.debug(f"Deleted {result} placements")
                    
                    # Delete campaign_media_discoveries BEFORE match_suggestions (FK dependency)
                    result = await conn.execute("""
                        DELETE FROM campaign_media_discoveries 
                        WHERE campaign_id = ANY($1::uuid[])
                    """, campaign_id_list)
                    logger.debug(f"Deleted {result} campaign media discoveries")
                    
                    # Delete match_suggestions (must be after campaign_media_discoveries)
                    result = await conn.execute("""
                        DELETE FROM match_suggestions 
                        WHERE campaign_id = ANY($1::uuid[])
                    """, campaign_id_list)
                    logger.debug(f"Deleted {result} match suggestions")
                    
                    # Delete review_tasks
                    result = await conn.execute("""
                        DELETE FROM review_tasks 
                        WHERE campaign_id = ANY($1::uuid[])
                    """, campaign_id_list)
                    logger.debug(f"Deleted {result} review tasks")
                    
                    # Delete chatbot_conversations
                    result = await conn.execute("""
                        DELETE FROM chatbot_conversations 
                        WHERE campaign_id = ANY($1::uuid[])
                    """, campaign_id_list)
                    logger.debug(f"Deleted {result} chatbot conversations")
                    
                    # Delete media_kits
                    result = await conn.execute("""
                        DELETE FROM media_kits 
                        WHERE campaign_id = ANY($1::uuid[])
                    """, campaign_id_list)
                    logger.debug(f"Deleted {result} media kits")
                    
                    # Delete match_notification_log
                    result = await conn.execute("""
                        DELETE FROM match_notification_log 
                        WHERE campaign_id = ANY($1::uuid[])
                    """, campaign_id_list)
                    logger.debug(f"Deleted {result} match notification logs")
                
                # 4. Now we can safely delete campaigns
                result = await conn.execute("DELETE FROM campaigns WHERE person_id = $1", person_id)
                logger.info(f"Deleted {result} campaigns for person {person_id}")
                
                # 5. Handle any remaining person-related data before deleting the person
                
                # Delete from tables that might not have CASCADE
                # Delete media_people entries
                result = await conn.execute("DELETE FROM media_people WHERE person_id = $1", person_id)
                logger.debug(f"Deleted {result} media_people entries")
                
                # Handle subscription history through client_profiles
                client_profile = await conn.fetchrow("SELECT client_profile_id FROM client_profiles WHERE person_id = $1", person_id)
                if client_profile:
                    result = await conn.execute("DELETE FROM subscription_history WHERE client_profile_id = $1", client_profile['client_profile_id'])
                    logger.debug(f"Deleted {result} subscription history records")
                
                # Delete chatbot conversations that might be directly linked to person (not through campaign)
                result = await conn.execute("DELETE FROM chatbot_conversations WHERE person_id = $1", person_id)
                logger.debug(f"Deleted {result} direct chatbot conversations")
                
                # Delete media kits that might be directly linked to person (not through campaign)
                result = await conn.execute("DELETE FROM media_kits WHERE person_id = $1", person_id)
                logger.debug(f"Deleted {result} direct media kits")
                
                # Check for and delete from tables that might exist
                tables_to_check = [
                    'email_verification_tokens',
                    'onboarding_tokens',
                    'oauth_connections',
                    'oauth_states'
                ]
                
                for table in tables_to_check:
                    table_exists = await conn.fetchval(f"""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = '{table}'
                        )
                    """)
                    
                    if table_exists:
                        result = await conn.execute(f"DELETE FROM {table} WHERE person_id = $1", person_id)
                        logger.debug(f"Deleted {result} from {table}")
                
                # 6. Tables with CASCADE constraints will be automatically deleted when we delete the person
                # These include:
                # - client_profiles
                # - invoices
                # - password_reset_tokens
                # - payment_methods
                
                # 7. Finally, delete the person record (this will CASCADE delete the remaining tables)
                result = await conn.execute("DELETE FROM people WHERE person_id = $1", person_id)
                logger.info(f"Deleted person record: {result}")
                
                logger.info(f"Successfully deleted person and all related data: {person_id} ({person['full_name']}, {person['email']})")
                return True
                
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

async def get_people_by_role_from_db(role: Optional[str] = None, exclude_role: Optional[str] = None, skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetches people filtered by role or excluding a specific role.
    If role is provided, returns only people with that role.
    If exclude_role is provided, returns all people except those with that role.
    If both are None, returns all people.
    """
    if role and exclude_role:
        raise ValueError("Cannot filter by both role and exclude_role simultaneously")
    
    if role:
        query = "SELECT * FROM people WHERE role = $1 ORDER BY created_at DESC OFFSET $2 LIMIT $3;"
        params = [role, skip, limit]
    elif exclude_role:
        query = "SELECT * FROM people WHERE role != $1 OR role IS NULL ORDER BY created_at DESC OFFSET $2 LIMIT $3;"
        params = [exclude_role, skip, limit]
    else:
        query = "SELECT * FROM people ORDER BY created_at DESC OFFSET $1 LIMIT $2;"
        params = [skip, limit]
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows_proxy = await conn.fetch(query, *params)
            return [_process_person_row(row) for row in rows_proxy if row]
        except Exception as e:
            logger.exception(f"Error fetching people by role: {e}")
            return []

async def get_non_host_people_from_db(skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Fetches all people who are not hosts (clients, admins, staff, etc.)
    """
    query = """
    SELECT * FROM people 
    WHERE role != 'host' OR role IS NULL 
    ORDER BY created_at DESC 
    OFFSET $1 LIMIT $2;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows_proxy = await conn.fetch(query, skip, limit)
            return [_process_person_row(row) for row in rows_proxy if row]
        except Exception as e:
            logger.exception(f"Error fetching non-host people: {e}")
            return []