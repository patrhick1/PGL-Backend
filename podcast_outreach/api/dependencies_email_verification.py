"""
Email verification dependencies for protected endpoints
"""

from fastapi import Depends, HTTPException, status
from typing import Dict, Any, Optional
import logging
from .dependencies import get_current_user
from ..database.queries import email_verification_queries

logger = logging.getLogger(__name__)

async def get_verified_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Dependency that ensures the current user has a verified email.
    Use this for endpoints that require email verification.
    """
    person_id = current_user.get("person_id")
    
    if not person_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated"
        )
    
    # Check email verification status
    verification_status = await email_verification_queries.get_verification_status(person_id)
    
    if not verification_status.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Please verify your email address to access this feature."
        )
    
    # Add verification status to user info
    current_user["email_verified"] = True
    current_user["email_verified_at"] = verification_status.get("email_verified_at")
    
    return current_user

async def get_user_with_verification_status(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Dependency that adds email verification status to the current user.
    Use this for endpoints that need to know verification status but don't require it.
    """
    person_id = current_user.get("person_id")
    
    if person_id:
        # Get verification status
        verification_status = await email_verification_queries.get_verification_status(person_id)
        current_user["email_verified"] = verification_status.get("email_verified", False)
        current_user["email_verified_at"] = verification_status.get("email_verified_at")
    else:
        current_user["email_verified"] = False
        current_user["email_verified_at"] = None
    
    return current_user

def require_email_verification(feature_name: Optional[str] = None):
    """
    Decorator factory for endpoints that require email verification.
    
    Usage:
        @router.post("/create-campaign")
        @require_email_verification("campaign creation")
        async def create_campaign(...):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs
            current_user = None
            for key, value in kwargs.items():
                if isinstance(value, dict) and "person_id" in value:
                    current_user = value
                    break
            
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not authenticated"
                )
            
            person_id = current_user.get("person_id")
            if not person_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User not authenticated"
                )
            
            # Check email verification
            verification_status = await email_verification_queries.get_verification_status(person_id)
            
            if not verification_status.get("email_verified", False):
                feature_msg = f" to use {feature_name}" if feature_name else ""
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Email verification required{feature_msg}. Please verify your email address."
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator