# podcast_outreach/database/queries/client_profiles.py

"""
Database queries for client profiles.
Handles fetching user plan information (free/paid) and related profile data.
"""

import logging
from typing import Optional, Dict, Any
from podcast_outreach.database.connection import get_db_pool

logger = logging.getLogger(__name__)


async def get_client_profile_by_person_id(person_id: int) -> Optional[Dict[str, Any]]:
    """
    Get client profile including plan type for a specific person.
    
    Args:
        person_id: The ID of the person to fetch profile for
        
    Returns:
        Dictionary containing client profile data including plan_type,
        or None if no profile exists
    """
    query = """
    SELECT 
        client_profile_id,
        person_id,
        plan_type,
        weekly_match_allowance,
        current_weekly_matches,
        last_weekly_match_reset,
        match_notification_enabled,
        match_notification_threshold,
        subscription_status,
        subscription_ends_at,
        created_at,
        updated_at
    FROM client_profiles
    WHERE person_id = $1
    """
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, person_id)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error fetching client profile for person_id {person_id}: {e}")
            return None


async def update_client_plan_type(person_id: int, plan_type: str) -> bool:
    """
    Update the plan type for a client profile.
    
    Args:
        person_id: The ID of the person to update
        plan_type: The new plan type ('free' or 'paid')
        
    Returns:
        True if update was successful, False otherwise
    """
    if plan_type not in ['free', 'paid']:
        logger.error(f"Invalid plan_type: {plan_type}. Must be 'free' or 'paid'")
        return False
    
    query = """
    UPDATE client_profiles
    SET 
        plan_type = $2,
        updated_at = CURRENT_TIMESTAMP
    WHERE person_id = $1
    RETURNING client_profile_id
    """
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.fetchrow(query, person_id, plan_type)
            return result is not None
        except Exception as e:
            logger.exception(f"Error updating plan type for person_id {person_id}: {e}")
            return False


async def create_client_profile(person_id: int, plan_type: str = 'free') -> Optional[Dict[str, Any]]:
    """
    Create a new client profile if one doesn't exist.
    
    Args:
        person_id: The ID of the person to create profile for
        plan_type: The initial plan type (default: 'free')
        
    Returns:
        Dictionary containing the created client profile, or None if creation failed
    """
    query = """
    INSERT INTO client_profiles (
        person_id,
        plan_type,
        weekly_match_allowance,
        current_weekly_matches,
        last_weekly_match_reset,
        created_at,
        updated_at
    ) VALUES (
        $1, $2,
        CASE WHEN $2 = 'paid' THEN 200 ELSE 50 END,  -- Set allowance based on plan
        0,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    )
    ON CONFLICT (person_id) DO UPDATE
    SET updated_at = CURRENT_TIMESTAMP
    RETURNING *
    """
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, person_id, plan_type)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error creating client profile for person_id {person_id}: {e}")
            return None


async def ensure_client_profile_exists(person_id: int) -> Optional[Dict[str, Any]]:
    """
    Ensure a client profile exists for a person, creating one if necessary.
    
    Args:
        person_id: The ID of the person
        
    Returns:
        Dictionary containing the client profile
    """
    # First try to get existing profile
    profile = await get_client_profile_by_person_id(person_id)
    
    if profile:
        return profile
    
    # Create a new profile with default 'free' plan
    logger.info(f"Creating new client profile for person_id {person_id}")
    return await create_client_profile(person_id, 'free')