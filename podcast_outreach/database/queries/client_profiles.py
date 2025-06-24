# podcast_outreach/database/queries/client_profiles.py
import logging
from typing import Any, Dict, Optional, List
from datetime import date, datetime, timedelta, timezone
import uuid

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.config import ( # Assuming plan limits are in config
    FREE_PLAN_DAILY_DISCOVERY_LIMIT, FREE_PLAN_WEEKLY_DISCOVERY_LIMIT,
    PAID_PLAN_DAILY_DISCOVERY_LIMIT, PAID_PLAN_WEEKLY_DISCOVERY_LIMIT
)


logger = logging.getLogger(__name__)

async def create_client_profile(person_id: int, profile_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Creates a new client profile linked to a person."""
    query = """
    INSERT INTO client_profiles (
        person_id, plan_type, daily_discovery_allowance, weekly_discovery_allowance,
        subscription_provider_id, subscription_status, subscription_ends_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (person_id) DO NOTHING -- Or DO UPDATE if you want to update if exists
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Set allowances based on plan_type if not explicitly provided
            plan_type = profile_data.get('plan_type', 'free')
            daily_allowance = profile_data.get('daily_discovery_allowance')
            weekly_allowance = profile_data.get('weekly_discovery_allowance')

            if daily_allowance is None:
                daily_allowance = PAID_PLAN_DAILY_DISCOVERY_LIMIT if plan_type != 'free' else FREE_PLAN_DAILY_DISCOVERY_LIMIT
            if weekly_allowance is None:
                weekly_allowance = PAID_PLAN_WEEKLY_DISCOVERY_LIMIT if plan_type != 'free' else FREE_PLAN_WEEKLY_DISCOVERY_LIMIT

            row = await conn.fetchrow(
                query,
                person_id,
                plan_type,
                daily_allowance,
                weekly_allowance,
                profile_data.get('subscription_provider_id'),
                profile_data.get('subscription_status'),
                profile_data.get('subscription_ends_at')
            )
            if row:
                logger.info(f"Client profile created/linked for person_id: {person_id}")
                return dict(row)
            logger.warning(f"Client profile for person_id {person_id} might already exist or insertion failed.")
            return None # Could happen if ON CONFLICT DO NOTHING and it existed
        except Exception as e:
            logger.exception(f"Error creating client profile for person_id {person_id}: {e}")
            raise

async def get_client_profile_by_person_id(person_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a client profile by person_id."""
    query = "SELECT * FROM client_profiles WHERE person_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, person_id)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching client profile for person_id {person_id}: {e}")
            raise

async def update_client_profile(person_id: int, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates an existing client profile."""
    if not update_data:
        return await get_client_profile_by_person_id(person_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_data.items():
        if key == "person_id" or key == "client_profile_id": continue
        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1
    
    if not set_clauses:
        return await get_client_profile_by_person_id(person_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE client_profiles SET {set_clause_str}, updated_at = NOW() WHERE person_id = ${idx} RETURNING *;"
    values.append(person_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            if row:
                logger.info(f"Client profile updated for person_id: {person_id}")
                return dict(row)
            logger.warning(f"Client profile not found for update (person_id: {person_id})")
            return None
        except Exception as e:
            logger.exception(f"Error updating client profile for person_id {person_id}: {e}")
            raise

async def reset_discovery_counts_if_needed(person_id: int) -> Optional[Dict[str, Any]]:
    """Resets daily/weekly discovery counts if the reset period has passed."""
    profile = await get_client_profile_by_person_id(person_id)
    if not profile:
        return None

    today = date.today()
    updates = {}

    # Daily reset
    if profile['last_daily_reset'] < today:
        updates['current_daily_discoveries'] = 0
        updates['last_daily_reset'] = today
        logger.info(f"Resetting daily discovery count for person_id {person_id}.")

    # Weekly reset (assuming reset on Monday)
    start_of_current_week = today - timedelta(days=today.weekday())
    if profile['last_weekly_reset'] < start_of_current_week:
        updates['current_weekly_discoveries'] = 0
        updates['last_weekly_reset'] = start_of_current_week # Set to Monday of current week
        logger.info(f"Resetting weekly discovery count for person_id {person_id}.")

    if updates:
        return await update_client_profile(person_id, updates)
    return profile


async def increment_discovery_counts(person_id: int, discoveries_made: int = 1) -> bool:
    """Increments discovery counts for a client. Returns False if limits would be exceeded."""
    profile = await reset_discovery_counts_if_needed(person_id) # Ensure counts are current
    if not profile:
        logger.error(f"Cannot increment discovery counts: Profile not found for person_id {person_id}")
        return False

    # Check limits
    if profile['current_daily_discoveries'] + discoveries_made > profile['daily_discovery_allowance']:
        logger.warning(f"Daily discovery limit reached for person_id {person_id}.")
        return False
    if profile['current_weekly_discoveries'] + discoveries_made > profile['weekly_discovery_allowance']:
        logger.warning(f"Weekly discovery limit reached for person_id {person_id}.")
        return False

    # Increment counts
    update_query = """
    UPDATE client_profiles
    SET current_daily_discoveries = current_daily_discoveries + $1,
        current_weekly_discoveries = current_weekly_discoveries + $1,
        updated_at = NOW()
    WHERE person_id = $2
    RETURNING client_profile_id;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            updated = await conn.fetchval(update_query, discoveries_made, person_id)
            if updated:
                logger.info(f"Incremented discovery counts by {discoveries_made} for person_id {person_id}.")
                return True
            return False # Should not happen if profile exists
        except Exception as e:
            logger.exception(f"Error incrementing discovery counts for person_id {person_id}: {e}")
            return False