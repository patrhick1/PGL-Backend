"""
Database queries for onboarding tokens and tracking
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import secrets
import uuid
from ..connection import get_db_pool

logger = logging.getLogger(__name__)

async def create_onboarding_token(
    person_id: int,
    campaign_id: uuid.UUID,
    created_by: str = 'system',
    client_ip: Optional[str] = None,
    expiry_days: int = 7
) -> Optional[str]:
    """
    Create a new onboarding token for a user.
    Returns the token string if successful, None otherwise.
    """
    try:
        pool = await get_db_pool()
        
        # Generate secure token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=expiry_days)
        
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO onboarding_tokens 
                (person_id, campaign_id, token, expires_at, client_ip, created_by)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                person_id, campaign_id, token, expires_at, client_ip, created_by
            )
            
        logger.info(f"Created onboarding token for person_id: {person_id}, campaign_id: {campaign_id}")
        return token
        
    except Exception as e:
        logger.error(f"Error creating onboarding token for person_id {person_id}: {e}")
        return None

async def validate_onboarding_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Validate an onboarding token and return user/campaign info.
    Does NOT mark the token as used - that happens when onboarding is completed.
    Returns dict with person_id, campaign_id, email, full_name if valid, None otherwise.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            # Check if token exists, is not expired, and not used
            row = await conn.fetchrow(
                """
                SELECT 
                    ot.person_id,
                    ot.campaign_id,
                    ot.expires_at,
                    ot.used_at,
                    p.email,
                    p.full_name,
                    p.email_verified
                FROM onboarding_tokens ot
                JOIN people p ON ot.person_id = p.person_id
                WHERE ot.token = $1
                """,
                token
            )
            
            if not row:
                logger.warning(f"Onboarding token not found: {token[:8]}...")
                return None
            
            if row['used_at'] is not None:
                logger.warning(f"Onboarding token already used: {token[:8]}...")
                return None
            
            if row['expires_at'] < datetime.now(timezone.utc):
                logger.warning(f"Onboarding token expired: {token[:8]}...")
                return None
            
            # Return user and campaign info
            return {
                "person_id": row['person_id'],
                "campaign_id": str(row['campaign_id']),
                "email": row['email'],
                "full_name": row['full_name'],
                "email_verified": row['email_verified']
            }
                
    except Exception as e:
        logger.error(f"Error validating onboarding token: {e}")
        return None

async def mark_onboarding_completed(person_id: int, token: str) -> bool:
    """
    Mark onboarding as completed for a user and invalidate the token.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            # Start a transaction
            async with conn.transaction():
                # Mark token as used
                await conn.execute(
                    """
                    UPDATE onboarding_tokens
                    SET used_at = NOW()
                    WHERE token = $1
                    AND person_id = $2
                    AND used_at IS NULL
                    """,
                    token, person_id
                )
                
                # Update user's onboarding status
                await conn.execute(
                    """
                    UPDATE people
                    SET onboarding_completed = TRUE,
                        onboarding_completed_at = NOW()
                    WHERE person_id = $1
                    """,
                    person_id
                )
                
                logger.info(f"Onboarding completed for person_id: {person_id}")
                return True
                
    except Exception as e:
        logger.error(f"Error marking onboarding completed for person_id {person_id}: {e}")
        return False

async def get_active_onboarding_token(person_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the most recent active (unused, not expired) onboarding token for a person.
    Returns token info if found, None otherwise.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT token, campaign_id, created_at, expires_at
                FROM onboarding_tokens
                WHERE person_id = $1
                AND used_at IS NULL
                AND expires_at > NOW()
                ORDER BY created_at DESC
                LIMIT 1
                """,
                person_id
            )
            
            if row:
                return {
                    "token": row['token'],
                    "campaign_id": str(row['campaign_id']),
                    "created_at": row['created_at'].isoformat(),
                    "expires_at": row['expires_at'].isoformat()
                }
            return None
            
    except Exception as e:
        logger.error(f"Error getting active onboarding token for person_id {person_id}: {e}")
        return None

async def invalidate_all_onboarding_tokens(person_id: int) -> bool:
    """
    Invalidate all unused onboarding tokens for a person.
    Used when generating a new token to ensure only one active token exists.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE onboarding_tokens
                SET used_at = NOW()
                WHERE person_id = $1
                AND used_at IS NULL
                """,
                person_id
            )
            
        logger.info(f"Invalidated all onboarding tokens for person_id: {person_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error invalidating onboarding tokens for person_id {person_id}: {e}")
        return False

async def get_onboarding_status(person_id: int) -> Dict[str, Any]:
    """
    Get the onboarding status for a person.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT onboarding_completed, onboarding_completed_at
                FROM people
                WHERE person_id = $1
                """,
                person_id
            )
            
            if row:
                return {
                    "onboarding_completed": row['onboarding_completed'] or False,
                    "onboarding_completed_at": row['onboarding_completed_at'].isoformat() if row['onboarding_completed_at'] else None
                }
            
            return {
                "onboarding_completed": False,
                "onboarding_completed_at": None
            }
            
    except Exception as e:
        logger.error(f"Error getting onboarding status for person_id {person_id}: {e}")
        return {
            "onboarding_completed": False,
            "onboarding_completed_at": None
        }

async def cleanup_expired_onboarding_tokens() -> int:
    """
    Remove expired and unused onboarding tokens.
    Returns the number of tokens deleted.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM onboarding_tokens
                WHERE expires_at < NOW()
                AND used_at IS NULL
                """
            )
            
            deleted_count = int(result.split()[-1])
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired onboarding tokens")
            
            return deleted_count
            
    except Exception as e:
        logger.error(f"Error cleaning up expired onboarding tokens: {e}")
        return 0

async def get_onboarding_stats() -> Dict[str, int]:
    """
    Get statistics about onboarding.
    Useful for monitoring and analytics.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            # Get user onboarding stats
            user_stats = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) FILTER (WHERE onboarding_completed = TRUE) as completed_onboarding,
                    COUNT(*) FILTER (WHERE onboarding_completed = FALSE) as not_completed_onboarding,
                    COUNT(*) FILTER (WHERE onboarding_completed = TRUE AND onboarding_completed_at > NOW() - INTERVAL '7 days') as completed_last_week
                FROM people
                WHERE role = 'client'
                """
            )
            
            # Get token stats
            token_stats = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) FILTER (WHERE used_at IS NULL AND expires_at > NOW()) as active_tokens,
                    COUNT(*) FILTER (WHERE used_at IS NOT NULL) as used_tokens,
                    COUNT(*) FILTER (WHERE used_at IS NULL AND expires_at < NOW()) as expired_tokens,
                    COUNT(*) FILTER (WHERE created_by = 'admin') as admin_created_tokens,
                    COUNT(*) FILTER (WHERE created_by = 'system') as system_created_tokens
                FROM onboarding_tokens
                """
            )
            
            return {
                "completed_onboarding": user_stats['completed_onboarding'] or 0,
                "not_completed_onboarding": user_stats['not_completed_onboarding'] or 0,
                "completed_last_week": user_stats['completed_last_week'] or 0,
                "active_tokens": token_stats['active_tokens'] or 0,
                "used_tokens": token_stats['used_tokens'] or 0,
                "expired_tokens": token_stats['expired_tokens'] or 0,
                "admin_created_tokens": token_stats['admin_created_tokens'] or 0,
                "system_created_tokens": token_stats['system_created_tokens'] or 0
            }
            
    except Exception as e:
        logger.error(f"Error getting onboarding stats: {e}")
        return {
            "completed_onboarding": 0,
            "not_completed_onboarding": 0,
            "completed_last_week": 0,
            "active_tokens": 0,
            "used_tokens": 0,
            "expired_tokens": 0,
            "admin_created_tokens": 0,
            "system_created_tokens": 0
        }