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
        weekly_match_allowance, subscription_provider_id, subscription_status, subscription_ends_at
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
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
            weekly_match_allowance = profile_data.get('weekly_match_allowance')

            if daily_allowance is None:
                daily_allowance = PAID_PLAN_DAILY_DISCOVERY_LIMIT if plan_type != 'free' else FREE_PLAN_DAILY_DISCOVERY_LIMIT
            if weekly_allowance is None:
                weekly_allowance = PAID_PLAN_WEEKLY_DISCOVERY_LIMIT if plan_type != 'free' else FREE_PLAN_WEEKLY_DISCOVERY_LIMIT
            if weekly_match_allowance is None:
                weekly_match_allowance = 50  # Default value as per schema

            row = await conn.fetchrow(
                query,
                person_id,
                plan_type,
                daily_allowance,
                weekly_allowance,
                weekly_match_allowance,
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

# ========== NEW MATCH TRACKING FUNCTIONS ==========

async def reset_match_counts_if_needed(person_id: int) -> Optional[Dict[str, Any]]:
    """Resets weekly match counts if the reset period has passed."""
    profile = await get_client_profile_by_person_id(person_id)
    if not profile:
        return None

    # Check if we have the new match tracking fields
    if 'last_weekly_match_reset' not in profile:
        logger.warning(f"Match tracking fields not found for person_id {person_id}. Run migration 001.")
        return profile

    today = datetime.now(timezone.utc)
    updates = {}

    # Weekly reset (Monday at midnight UTC)
    last_reset = profile['last_weekly_match_reset']
    if last_reset:
        # Convert to timezone-aware if needed
        if last_reset.tzinfo is None:
            last_reset = last_reset.replace(tzinfo=timezone.utc)
        
        # Calculate start of current week (Monday)
        days_since_monday = today.weekday()
        start_of_current_week = today.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)
        
        if last_reset < start_of_current_week:
            updates['current_weekly_matches'] = 0
            updates['last_weekly_match_reset'] = start_of_current_week
            logger.info(f"Resetting weekly match count for person_id {person_id}.")

    if updates:
        return await update_client_profile(person_id, updates)
    return profile


async def increment_match_count(person_id: int, matches_created: int = 1) -> bool:
    """
    Increments match count for a client. Returns False if limits would be exceeded.
    Used when creating matches with vetting_score >= threshold.
    """
    profile = await reset_match_counts_if_needed(person_id)
    if not profile:
        logger.error(f"Cannot increment match count: Profile not found for person_id {person_id}")
        return False

    # Check if we have the new match tracking fields
    if 'weekly_match_allowance' not in profile:
        logger.warning(f"Match allowance field not found for person_id {person_id}. Run migration 001.")
        return True  # Allow the operation to continue

    # Check limits (only for free plans)
    if profile['plan_type'] == 'free' and profile['weekly_match_allowance'] is not None:
        current_matches = profile.get('current_weekly_matches', 0)
        if current_matches + matches_created > profile['weekly_match_allowance']:
            logger.warning(f"Weekly match limit would be exceeded for person_id {person_id}. Current: {current_matches}, Limit: {profile['weekly_match_allowance']}")
            return False

    # Increment count
    update_query = """
    UPDATE client_profiles
    SET current_weekly_matches = COALESCE(current_weekly_matches, 0) + $1,
        updated_at = NOW()
    WHERE person_id = $2
    RETURNING client_profile_id;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            updated = await conn.fetchval(update_query, matches_created, person_id)
            if updated:
                logger.info(f"Incremented match count by {matches_created} for person_id {person_id}.")
                return True
            return False
        except Exception as e:
            logger.exception(f"Error incrementing match count for person_id {person_id}: {e}")
            return False


async def get_remaining_weekly_matches(person_id: int) -> Optional[int]:
    """
    Get the number of remaining weekly matches for a client.
    Returns None if unlimited (paid plans).
    """
    profile = await reset_match_counts_if_needed(person_id)
    if not profile:
        return 0

    if profile['plan_type'] != 'free' or profile.get('weekly_match_allowance') is None:
        return None  # Unlimited for paid plans

    current_matches = profile.get('current_weekly_matches', 0)
    allowance = profile.get('weekly_match_allowance', 50)  # Default to 50 if not set
    remaining = max(0, allowance - current_matches)
    
    return remaining


async def check_can_create_matches(person_id: int, matches_to_create: int) -> tuple[bool, str]:
    """
    Check if a client can create the specified number of matches.
    Returns (can_create, reason_if_not)
    """
    profile = await reset_match_counts_if_needed(person_id)
    if not profile:
        return False, "Client profile not found"

    # Paid plans have no limits
    if profile['plan_type'] != 'free':
        return True, ""

    # Check if we have match tracking fields
    if 'weekly_match_allowance' not in profile:
        logger.warning(f"Match allowance field not found for person_id {person_id}")
        return True, ""  # Allow if fields don't exist yet

    current_matches = profile.get('current_weekly_matches', 0)
    allowance = profile.get('weekly_match_allowance', 50)
    
    if current_matches + matches_to_create > allowance:
        remaining = max(0, allowance - current_matches)
        return False, f"Would exceed weekly match limit. You have {remaining} matches remaining this week."
    
    return True, ""