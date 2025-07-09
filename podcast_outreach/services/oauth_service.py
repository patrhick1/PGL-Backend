"""
OAuth Service for handling Google authentication
"""

import os
import secrets
import httpx
import logging
import uuid
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlencode
import json
import base64
from cryptography.fernet import Fernet

from ..database.queries import people as people_queries
from ..database.queries import oauth_queries
from ..database.queries import campaigns as campaign_queries
from ..database.queries import client_profiles as client_profile_queries
from ..api.dependencies import prepare_session_data
from ..config import FRONTEND_ORIGIN, BACKEND_URL

logger = logging.getLogger(__name__)

class OAuthService:
    """Service for handling OAuth authentication flows"""
    
    def __init__(self):
        # OAuth provider configurations
        self.providers = {
            "google": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",
                "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
                "scopes": ["openid", "email", "profile"],
                "redirect_uri": f"{BACKEND_URL}/auth/oauth/google/callback"
            }
        }
        
        # Initialize encryption for token storage
        encryption_key = os.getenv("TOKEN_ENCRYPTION_KEY")
        if not encryption_key:
            # Generate a key for development - in production, this should be in env
            encryption_key = Fernet.generate_key().decode()
            logger.warning("No TOKEN_ENCRYPTION_KEY found in environment. Generated temporary key.")
        
        self.cipher = Fernet(encryption_key.encode() if isinstance(encryption_key, str) else encryption_key)
        
        # HTTP client for making OAuth requests
        self.client = httpx.AsyncClient()
        
    def encrypt_token(self, token: str) -> str:
        """Encrypt a token for storage"""
        if not token:
            return None
        return self.cipher.encrypt(token.encode()).decode()
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt a stored token"""
        if not encrypted_token:
            return None
        return self.cipher.decrypt(encrypted_token.encode()).decode()
    
    async def get_authorization_url(self, provider: str, person_id: Optional[int] = None, is_linking: bool = False) -> Tuple[str, str]:
        """Generate OAuth authorization URL with state parameter"""
        if provider not in self.providers:
            raise ValueError(f"Unsupported OAuth provider: {provider}")
        
        config = self.providers[provider]
        
        # Generate secure state parameter
        state = secrets.token_urlsafe(32)
        
        # Store state in database for verification
        await oauth_queries.create_oauth_state(
            state=state,
            provider=provider,
            redirect_uri=config["redirect_uri"],
            person_id=person_id,
            is_linking=is_linking
        )
        
        # Build authorization URL
        params = {
            "client_id": config["client_id"],
            "redirect_uri": config["redirect_uri"],
            "response_type": "code",
            "scope": " ".join(config["scopes"]),
            "state": state,
            "access_type": "offline",  # Request refresh token
            "prompt": "select_account"  # Always show account selection
        }
        
        auth_url = f"{config['authorize_url']}?{urlencode(params)}"
        return auth_url, state
    
    async def exchange_code_for_tokens(self, provider: str, code: str, state: str) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens"""
        if provider not in self.providers:
            raise ValueError(f"Unsupported OAuth provider: {provider}")
        
        config = self.providers[provider]
        
        # Verify state parameter
        state_data = await oauth_queries.validate_and_get_oauth_state(state)
        if not state_data:
            raise ValueError("Invalid or expired state parameter")
        
        # Exchange code for tokens
        data = {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "redirect_uri": config["redirect_uri"],
            "grant_type": "authorization_code"
        }
        
        response = await self.client.post(config["token_url"], data=data)
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
            raise ValueError("Failed to exchange code for tokens")
        
        tokens = response.json()
        
        # Mark state as used
        await oauth_queries.mark_oauth_state_used(state)
        
        return {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "expires_in": tokens.get("expires_in"),
            "state_data": state_data
        }
    
    async def get_user_info(self, provider: str, access_token: str) -> Dict[str, Any]:
        """Get user information from OAuth provider"""
        if provider not in self.providers:
            raise ValueError(f"Unsupported OAuth provider: {provider}")
        
        config = self.providers[provider]
        
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await self.client.get(config["userinfo_url"], headers=headers)
        
        if response.status_code != 200:
            logger.error(f"Failed to get user info: {response.status_code} - {response.text}")
            raise ValueError("Failed to get user information")
        
        user_info = response.json()
        
        # Normalize user info across providers
        normalized = {
            "provider_id": user_info.get("id") or user_info.get("sub"),
            "email": user_info.get("email"),
            "email_verified": user_info.get("email_verified", False),
            "full_name": user_info.get("name"),
            "picture": user_info.get("picture"),
            "raw_data": user_info
        }
        
        return normalized
    
    async def handle_oauth_callback(self, provider: str, code: str, state: str) -> Dict[str, Any]:
        """Handle OAuth callback and create/update user"""
        # Exchange code for tokens
        token_data = await self.exchange_code_for_tokens(provider, code, state)
        access_token = token_data["access_token"]
        refresh_token = token_data["refresh_token"]
        expires_in = token_data["expires_in"]
        state_data = token_data["state_data"]
        
        # Get user info from provider
        user_info = await self.get_user_info(provider, access_token)
        
        # Calculate token expiration
        token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None
        
        # Check if this is account linking
        if state_data["is_linking"] and state_data["person_id"]:
            # Link OAuth to existing account
            await self._link_oauth_to_account(
                person_id=state_data["person_id"],
                provider=provider,
                user_info=user_info,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at
            )
            
            # Get the updated person record
            person = await people_queries.get_person_by_id_from_db(state_data["person_id"])
            return {
                "person": person,
                "is_new_user": False,
                "linked_account": True
            }
        
        # Check if user exists by OAuth provider
        existing_person = await oauth_queries.get_person_by_oauth_provider(provider, user_info["provider_id"])
        
        if existing_person:
            # Update OAuth tokens and login time
            await self._update_oauth_login(
                person_id=existing_person["person_id"],
                provider=provider,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at
            )
            
            return {
                "person": existing_person,
                "is_new_user": False,
                "linked_account": False
            }
        
        # Check if email already exists
        existing_by_email = await people_queries.get_person_by_email_from_db(user_info["email"])
        
        if existing_by_email:
            # Email exists but no OAuth link
            if existing_by_email.get("oauth_provider"):
                # Already linked to different provider
                raise ValueError(f"This email is already associated with {existing_by_email['oauth_provider']} login")
            
            # Auto-link OAuth to existing email account
            await self._link_oauth_to_account(
                person_id=existing_by_email["person_id"],
                provider=provider,
                user_info=user_info,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at
            )
            
            return {
                "person": existing_by_email,
                "is_new_user": False,
                "linked_account": True
            }
        
        # Create new user
        new_person = await self._create_oauth_user(
            provider=provider,
            user_info=user_info,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at
        )
        
        return {
            "person": new_person,
            "is_new_user": True,
            "linked_account": False
        }
    
    async def _create_oauth_user(self, provider: str, user_info: Dict[str, Any], 
                                access_token: str, refresh_token: str, 
                                token_expires_at: Optional[datetime]) -> Dict[str, Any]:
        """Create a new user from OAuth data"""
        # Encrypt tokens
        encrypted_refresh = self.encrypt_token(refresh_token) if refresh_token else None
        
        # Create person record
        person_data = {
            "full_name": user_info["full_name"],
            "email": user_info["email"],
            "dashboard_username": user_info["email"],
            "role": "client",
            "oauth_provider": provider,
            "oauth_provider_id": user_info["provider_id"],
            "oauth_email_verified": user_info["email_verified"],
            "oauth_refresh_token": encrypted_refresh,
            "oauth_access_token_expires": token_expires_at,
            "last_oauth_login": datetime.utcnow(),
            "profile_image_url": user_info.get("picture")
        }
        
        created_person = await people_queries.create_person_in_db(person_data)
        
        if not created_person:
            raise ValueError("Failed to create user account")
        
        # Create OAuth connection record
        await oauth_queries.create_oauth_connection(
            person_id=created_person["person_id"],
            provider=provider,
            provider_user_id=user_info["provider_id"],
            provider_email=user_info["email"],
            access_token=self.encrypt_token(access_token),
            refresh_token=encrypted_refresh,
            token_expires_at=token_expires_at,
            provider_data=user_info["raw_data"]
        )
        
        # Create default campaign
        campaign_data = {
            "campaign_id": uuid.uuid4(),
            "person_id": created_person["person_id"],
            "campaign_name": f"{created_person['full_name']}'s First Campaign",
            "campaign_type": "targetted media campaign"
        }
        await campaign_queries.create_campaign_in_db(campaign_data)
        
        # Create client profile
        profile_data = {
            "plan_type": "free",
            "daily_discovery_allowance": 10,
            "weekly_discovery_allowance": 50,
        }
        await client_profile_queries.create_client_profile(created_person["person_id"], profile_data)
        
        logger.info(f"Created new OAuth user: {created_person['email']} via {provider}")
        
        return created_person
    
    async def _link_oauth_to_account(self, person_id: int, provider: str, 
                                    user_info: Dict[str, Any], access_token: str, 
                                    refresh_token: str, token_expires_at: Optional[datetime]):
        """Link OAuth provider to existing account"""
        # Encrypt tokens
        encrypted_refresh = self.encrypt_token(refresh_token) if refresh_token else None
        
        # Update person record with OAuth info
        update_data = {
            "oauth_provider": provider,
            "oauth_provider_id": user_info["provider_id"],
            "oauth_email_verified": user_info["email_verified"],
            "oauth_refresh_token": encrypted_refresh,
            "oauth_access_token_expires": token_expires_at,
            "last_oauth_login": datetime.utcnow()
        }
        
        # Update profile image if not already set
        person = await people_queries.get_person_by_id_from_db(person_id)
        if not person.get("profile_image_url") and user_info.get("picture"):
            update_data["profile_image_url"] = user_info["picture"]
        
        await people_queries.update_person_in_db(person_id, update_data)
        
        # Create OAuth connection record
        await oauth_queries.create_or_update_oauth_connection(
            person_id=person_id,
            provider=provider,
            provider_user_id=user_info["provider_id"],
            provider_email=user_info["email"],
            access_token=self.encrypt_token(access_token),
            refresh_token=encrypted_refresh,
            token_expires_at=token_expires_at,
            provider_data=user_info["raw_data"]
        )
        
        logger.info(f"Linked {provider} OAuth to person_id: {person_id}")
    
    async def _update_oauth_login(self, person_id: int, provider: str, 
                                 access_token: str, refresh_token: str, 
                                 token_expires_at: Optional[datetime]):
        """Update OAuth tokens and login time for existing user"""
        # Encrypt tokens
        encrypted_refresh = self.encrypt_token(refresh_token) if refresh_token else None
        
        # Update person record
        update_data = {
            "oauth_refresh_token": encrypted_refresh,
            "oauth_access_token_expires": token_expires_at,
            "last_oauth_login": datetime.utcnow()
        }
        
        await people_queries.update_person_in_db(person_id, update_data)
        
        # Update OAuth connection
        await oauth_queries.update_oauth_connection_tokens(
            person_id=person_id,
            provider=provider,
            access_token=self.encrypt_token(access_token),
            refresh_token=encrypted_refresh,
            token_expires_at=token_expires_at
        )
        
        logger.info(f"Updated OAuth login for person_id: {person_id}")
    
    async def refresh_access_token(self, person_id: int, provider: str) -> Optional[str]:
        """Refresh expired access token using refresh token"""
        person = await people_queries.get_person_by_id_from_db(person_id)
        if not person or not person.get("oauth_refresh_token"):
            return None
        
        config = self.providers.get(provider)
        if not config:
            return None
        
        # Decrypt refresh token
        refresh_token = self.decrypt_token(person["oauth_refresh_token"])
        
        # Request new access token
        data = {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }
        
        response = await self.client.post(config["token_url"], data=data)
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
            return None
        
        tokens = response.json()
        new_access_token = tokens.get("access_token")
        new_refresh_token = tokens.get("refresh_token", refresh_token)  # Some providers return new refresh token
        expires_in = tokens.get("expires_in")
        
        # Update stored tokens
        token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None
        
        await self._update_oauth_login(
            person_id=person_id,
            provider=provider,
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_expires_at=token_expires_at
        )
        
        return new_access_token
    
    async def disconnect_provider(self, person_id: int, provider: str) -> bool:
        """Disconnect OAuth provider from account"""
        person = await people_queries.get_person_by_id_from_db(person_id)
        
        if not person:
            return False
        
        # Check if user has a password set
        has_password = bool(person.get("dashboard_password_hash"))
        
        # Check if this is the only auth method
        if not has_password and person.get("oauth_provider") == provider:
            raise ValueError("Cannot disconnect the only authentication method. Please set a password first.")
        
        # Remove OAuth fields from person record
        if person.get("oauth_provider") == provider:
            update_data = {
                "oauth_provider": None,
                "oauth_provider_id": None,
                "oauth_email_verified": False,
                "oauth_refresh_token": None,
                "oauth_access_token_expires": None,
                "last_oauth_login": None
            }
            await people_queries.update_person_in_db(person_id, update_data)
        
        # Remove OAuth connection record
        await oauth_queries.delete_oauth_connection(person_id, provider)
        
        logger.info(f"Disconnected {provider} OAuth from person_id: {person_id}")
        return True
    
    async def cleanup(self):
        """Cleanup resources"""
        await self.client.aclose()
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()

# Global instance
oauth_service = OAuthService()

