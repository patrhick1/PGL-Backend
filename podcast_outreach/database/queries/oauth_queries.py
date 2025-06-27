"""
OAuth-specific database queries
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from ..connection import get_db_pool

logger = logging.getLogger(__name__)

async def create_oauth_state(state: str, provider: str, redirect_uri: str, 
                           person_id: Optional[int] = None, is_linking: bool = False) -> bool:
    """Create OAuth state for CSRF protection"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # State expires in 10 minutes
            expires_at = datetime.utcnow() + timedelta(minutes=10)
            
            await conn.execute("""
                INSERT INTO oauth_states (state, provider, redirect_uri, person_id, is_linking, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, state, provider, redirect_uri, person_id, is_linking, expires_at)
            
            logger.debug(f"Created OAuth state for provider: {provider}")
            return True
            
    except Exception as e:
        logger.error(f"Error creating OAuth state: {e}")
        return False

async def validate_and_get_oauth_state(state: str) -> Optional[Dict[str, Any]]:
    """Validate OAuth state and return its data"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT id, provider, redirect_uri, person_id, is_linking, expires_at
                FROM oauth_states
                WHERE state = $1 AND expires_at > NOW()
            """, state)
            
            if not result:
                logger.warning(f"Invalid or expired OAuth state attempted")
                return None
            
            return dict(result)
            
    except Exception as e:
        logger.error(f"Error validating OAuth state: {e}")
        return None

async def mark_oauth_state_used(state: str) -> bool:
    """Mark OAuth state as used (delete it)"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM oauth_states WHERE state = $1
            """, state)
            
            return True
            
    except Exception as e:
        logger.error(f"Error marking OAuth state as used: {e}")
        return False

async def get_person_by_oauth_provider(provider: str, provider_id: str) -> Optional[Dict[str, Any]]:
    """Get person by OAuth provider and provider user ID"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchrow("""
                SELECT p.*, cp.client_profile_id, cp.plan_type, 
                       cp.daily_discovery_allowance, cp.weekly_discovery_allowance,
                       cp.current_daily_discoveries, cp.current_weekly_discoveries
                FROM people p
                LEFT JOIN client_profiles cp ON p.person_id = cp.person_id
                WHERE p.oauth_provider = $1 AND p.oauth_provider_id = $2
            """, provider, provider_id)
            
            if result:
                return dict(result)
            return None
            
    except Exception as e:
        logger.error(f"Error getting person by OAuth provider: {e}")
        return None

async def create_oauth_connection(person_id: int, provider: str, provider_user_id: str,
                                provider_email: str, access_token: str, refresh_token: Optional[str],
                                token_expires_at: Optional[datetime], provider_data: Dict) -> bool:
    """Create OAuth connection record"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO oauth_connections 
                (person_id, provider, provider_user_id, provider_email, access_token, 
                 refresh_token, token_expires_at, provider_data, last_used_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
            """, person_id, provider, provider_user_id, provider_email, access_token,
                refresh_token, token_expires_at, provider_data)
            
            logger.info(f"Created OAuth connection for person_id: {person_id}, provider: {provider}")
            return True
            
    except Exception as e:
        logger.error(f"Error creating OAuth connection: {e}")
        return False

async def create_or_update_oauth_connection(person_id: int, provider: str, provider_user_id: str,
                                          provider_email: str, access_token: str, refresh_token: Optional[str],
                                          token_expires_at: Optional[datetime], provider_data: Dict) -> bool:
    """Create or update OAuth connection record"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO oauth_connections 
                (person_id, provider, provider_user_id, provider_email, access_token, 
                 refresh_token, token_expires_at, provider_data, last_used_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
                ON CONFLICT (person_id, provider) 
                DO UPDATE SET
                    provider_user_id = EXCLUDED.provider_user_id,
                    provider_email = EXCLUDED.provider_email,
                    access_token = EXCLUDED.access_token,
                    refresh_token = COALESCE(EXCLUDED.refresh_token, oauth_connections.refresh_token),
                    token_expires_at = EXCLUDED.token_expires_at,
                    provider_data = EXCLUDED.provider_data,
                    last_used_at = NOW(),
                    updated_at = NOW()
            """, person_id, provider, provider_user_id, provider_email, access_token,
                refresh_token, token_expires_at, provider_data)
            
            logger.info(f"Created/updated OAuth connection for person_id: {person_id}, provider: {provider}")
            return True
            
    except Exception as e:
        logger.error(f"Error creating/updating OAuth connection: {e}")
        return False

async def update_oauth_connection_tokens(person_id: int, provider: str, access_token: str,
                                       refresh_token: Optional[str], token_expires_at: Optional[datetime]) -> bool:
    """Update OAuth tokens for existing connection"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE oauth_connections
                SET access_token = $3,
                    refresh_token = COALESCE($4, refresh_token),
                    token_expires_at = $5,
                    last_used_at = NOW(),
                    updated_at = NOW()
                WHERE person_id = $1 AND provider = $2
            """, person_id, provider, access_token, refresh_token, token_expires_at)
            
            return True
            
    except Exception as e:
        logger.error(f"Error updating OAuth connection tokens: {e}")
        return False

async def get_oauth_connections(person_id: int) -> List[Dict[str, Any]]:
    """Get all OAuth connections for a person"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            results = await conn.fetch("""
                SELECT provider, provider_email, connected_at, last_used_at
                FROM oauth_connections
                WHERE person_id = $1
                ORDER BY connected_at DESC
            """, person_id)
            
            return [dict(row) for row in results]
            
    except Exception as e:
        logger.error(f"Error getting OAuth connections: {e}")
        return []

async def delete_oauth_connection(person_id: int, provider: str) -> bool:
    """Delete OAuth connection"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM oauth_connections
                WHERE person_id = $1 AND provider = $2
            """, person_id, provider)
            
            # Check if any rows were deleted
            deleted = result.split()[-1] != '0' if result else False
            
            if deleted:
                logger.info(f"Deleted OAuth connection for person_id: {person_id}, provider: {provider}")
            
            return deleted
            
    except Exception as e:
        logger.error(f"Error deleting OAuth connection: {e}")
        return False

async def cleanup_expired_oauth_states() -> int:
    """Clean up expired OAuth states (for maintenance)"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM oauth_states
                WHERE expires_at < NOW()
            """)
            
            # Extract row count from result
            deleted_count = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired OAuth states")
            
            return deleted_count
            
    except Exception as e:
        logger.error(f"Error cleaning up expired OAuth states: {e}")
        return 0