"""
Database queries for email verification tokens
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone
import secrets
from ..connection import get_db_pool

logger = logging.getLogger(__name__)

async def create_verification_token(
    person_id: int, 
    client_ip: Optional[str] = None,
    expiry_hours: int = 24
) -> Optional[str]:
    """
    Create a new email verification token for a user.
    Returns the token string if successful, None otherwise.
    """
    try:
        pool = await get_db_pool()
        
        # Generate secure token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=expiry_hours)
        
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO email_verification_tokens 
                (person_id, token, expires_at, client_ip)
                VALUES ($1, $2, $3, $4)
                """,
                person_id, token, expires_at, client_ip
            )
            
        logger.info(f"Created email verification token for person_id: {person_id}")
        return token
        
    except Exception as e:
        logger.error(f"Error creating verification token for person_id {person_id}: {e}")
        return None

async def validate_and_use_token(token: str) -> Optional[int]:
    """
    Validate a verification token and mark it as used.
    Returns the person_id if token is valid, None otherwise.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            # Start a transaction
            async with conn.transaction():
                # Check if token exists, is not expired, and not used
                row = await conn.fetchrow(
                    """
                    SELECT person_id, expires_at, used_at
                    FROM email_verification_tokens
                    WHERE token = $1
                    """,
                    token
                )
                
                if not row:
                    logger.warning(f"Verification token not found: {token[:8]}...")
                    return None
                
                if row['used_at'] is not None:
                    logger.warning(f"Verification token already used: {token[:8]}...")
                    return None
                
                if row['expires_at'] < datetime.now(timezone.utc):
                    logger.warning(f"Verification token expired: {token[:8]}...")
                    return None
                
                person_id = row['person_id']
                
                # Mark token as used
                await conn.execute(
                    """
                    UPDATE email_verification_tokens
                    SET used_at = NOW()
                    WHERE token = $1
                    """,
                    token
                )
                
                # Update user's email verification status
                await conn.execute(
                    """
                    UPDATE people
                    SET email_verified = TRUE,
                        email_verified_at = NOW()
                    WHERE person_id = $1
                    """,
                    person_id
                )
                
                logger.info(f"Email verified successfully for person_id: {person_id}")
                return person_id
                
    except Exception as e:
        logger.error(f"Error validating verification token: {e}")
        return None

async def get_active_token_for_person(person_id: int) -> Optional[Dict[str, Any]]:
    """
    Get the most recent active (unused, not expired) verification token for a person.
    Returns token info if found, None otherwise.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT token, created_at, expires_at
                FROM email_verification_tokens
                WHERE person_id = $1
                AND used_at IS NULL
                AND expires_at > NOW()
                ORDER BY created_at DESC
                LIMIT 1
                """,
                person_id
            )
            
            if row:
                return dict(row)
            return None
            
    except Exception as e:
        logger.error(f"Error getting active token for person_id {person_id}: {e}")
        return None

async def invalidate_all_tokens_for_person(person_id: int) -> bool:
    """
    Invalidate all unused verification tokens for a person.
    Used when generating a new token to ensure only one active token exists.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE email_verification_tokens
                SET used_at = NOW()
                WHERE person_id = $1
                AND used_at IS NULL
                """,
                person_id
            )
            
        logger.info(f"Invalidated all tokens for person_id: {person_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error invalidating tokens for person_id {person_id}: {e}")
        return False

async def cleanup_expired_tokens() -> int:
    """
    Remove expired and unused verification tokens.
    Returns the number of tokens deleted.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM email_verification_tokens
                WHERE expires_at < NOW()
                AND used_at IS NULL
                """
            )
            
            deleted_count = int(result.split()[-1])
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired verification tokens")
            
            return deleted_count
            
    except Exception as e:
        logger.error(f"Error cleaning up expired tokens: {e}")
        return 0

async def get_verification_status(person_id: int) -> Dict[str, Any]:
    """
    Get the email verification status for a person.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT email_verified, email_verified_at
                FROM people
                WHERE person_id = $1
                """,
                person_id
            )
            
            if row:
                return {
                    "email_verified": row['email_verified'] or False,
                    "email_verified_at": row['email_verified_at'].isoformat() if row['email_verified_at'] else None
                }
            
            return {
                "email_verified": False,
                "email_verified_at": None
            }
            
    except Exception as e:
        logger.error(f"Error getting verification status for person_id {person_id}: {e}")
        return {
            "email_verified": False,
            "email_verified_at": None
        }

async def get_verification_stats() -> Dict[str, int]:
    """
    Get statistics about email verification.
    Useful for monitoring and analytics.
    """
    try:
        pool = await get_db_pool()
        
        async with pool.acquire() as conn:
            # Get user verification stats
            user_stats = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) FILTER (WHERE email_verified = TRUE) as verified_users,
                    COUNT(*) FILTER (WHERE email_verified = FALSE) as unverified_users,
                    COUNT(*) FILTER (WHERE email_verified = TRUE AND email_verified_at > NOW() - INTERVAL '24 hours') as verified_last_24h
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
                    COUNT(*) FILTER (WHERE used_at IS NULL AND expires_at < NOW()) as expired_tokens
                FROM email_verification_tokens
                """
            )
            
            return {
                "verified_users": user_stats['verified_users'] or 0,
                "unverified_users": user_stats['unverified_users'] or 0,
                "verified_last_24h": user_stats['verified_last_24h'] or 0,
                "active_tokens": token_stats['active_tokens'] or 0,
                "used_tokens": token_stats['used_tokens'] or 0,
                "expired_tokens": token_stats['expired_tokens'] or 0
            }
            
    except Exception as e:
        logger.error(f"Error getting verification stats: {e}")
        return {
            "verified_users": 0,
            "unverified_users": 0,
            "verified_last_24h": 0,
            "active_tokens": 0,
            "used_tokens": 0,
            "expired_tokens": 0
        }