import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from ..connection import get_db_pool

logger = logging.getLogger(__name__)

async def create_password_reset_token(person_id: int, token: str, client_ip: str = None) -> bool:
    """Create a password reset token for a user"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Token expires in 30 minutes
            expires_at = datetime.utcnow() + timedelta(minutes=30)
            
            # Deactivate any existing tokens for this user
            await conn.execute("""
                UPDATE password_reset_tokens 
                SET is_active = FALSE 
                WHERE person_id = $1 AND is_active = TRUE
            """, person_id)
            
            # Create new token
            await conn.execute("""
                INSERT INTO password_reset_tokens (person_id, token, expires_at, created_by_ip)
                VALUES ($1, $2, $3, $4)
            """, person_id, token, expires_at, client_ip)
            
            logger.info(f"Password reset token created for person_id: {person_id}")
            return True
        
    except Exception as e:
        logger.error(f"Error creating password reset token: {e}")
        return False

async def validate_and_use_reset_token(token: str) -> Optional[int]:
    """Validate password reset token and mark as used, return person_id if valid"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Check if token exists, is active, and not expired
            result = await conn.fetchrow("""
                SELECT person_id, expires_at, used_at 
                FROM password_reset_tokens 
                WHERE token = $1 AND is_active = TRUE
            """, token)
            
            if not result:
                logger.warning(f"Invalid or inactive token attempted: {token[:8]}...")
                return None
            
            person_id, expires_at, used_at = result
            
            # Check if already used
            if used_at:
                logger.warning(f"Already used token attempted: {token[:8]}...")
                return None
            
            # Check if expired
            if datetime.utcnow() > expires_at:
                logger.warning(f"Expired token attempted: {token[:8]}...")
                return None
            
            # Mark token as used
            await conn.execute("""
                UPDATE password_reset_tokens 
                SET used_at = CURRENT_TIMESTAMP, is_active = FALSE 
                WHERE token = $1
            """, token)
            
            logger.info(f"Password reset token validated and used for person_id: {person_id}")
            return person_id
        
    except Exception as e:
        logger.error(f"Error validating reset token: {e}")
        return None

async def cleanup_expired_tokens() -> int:
    """Clean up expired and used tokens (for maintenance)"""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Delete tokens older than 24 hours
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            
            result = await conn.execute("""
                DELETE FROM password_reset_tokens 
                WHERE created_at < $1 OR (used_at IS NOT NULL AND used_at < $2)
            """, cutoff_time, cutoff_time)
            
            # Extract row count from result string like "DELETE 5"
            deleted_count = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
            
            logger.info(f"Cleaned up {deleted_count} expired/used password reset tokens")
            return deleted_count
        
    except Exception as e:
        logger.error(f"Error cleaning up expired tokens: {e}")
        return 0 