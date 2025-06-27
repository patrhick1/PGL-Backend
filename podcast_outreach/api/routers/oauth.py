"""
OAuth Authentication Router
Handles OAuth login flows for Google and other providers
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query, Form
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Dict, Any, Optional, List
import logging
import os
from pydantic import BaseModel

from ...services.oauth_service import oauth_service
from ...database.queries import people as people_queries
from ...database.queries import oauth_queries
from ..dependencies import get_current_user, prepare_session_data, verify_password
from ...config import FRONTEND_ORIGIN

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth/oauth", tags=["OAuth Authentication"])

class OAuthProviderResponse(BaseModel):
    """Response model for OAuth provider information"""
    provider: str
    connected: bool
    email: Optional[str] = None
    connected_at: Optional[str] = None

@router.get("/{provider}/authorize", summary="Initiate OAuth Login")
async def oauth_authorize(provider: str, request: Request):
    """
    Initiate OAuth authentication flow
    Redirects user to provider's authorization page
    """
    try:
        # Check if user is logged in (for account linking)
        person_id = None
        is_linking = False
        
        if hasattr(request, 'session') and request.session.get("person_id"):
            person_id = request.session.get("person_id")
            is_linking = True
            logger.info(f"User {person_id} initiating OAuth link with {provider}")
        
        # Generate authorization URL
        auth_url, state = await oauth_service.get_authorization_url(
            provider=provider,
            person_id=person_id,
            is_linking=is_linking
        )
        
        # Return authorization URL for frontend to redirect
        return {"authorization_url": auth_url, "state": state}
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error initiating OAuth flow: {e}")
        raise HTTPException(status_code=500, detail="Failed to initiate OAuth authentication")

@router.get("/{provider}/callback", summary="OAuth Callback Handler")
async def oauth_callback(
    provider: str,
    request: Request,
    response: Response,
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None)
):
    """
    Handle OAuth callback from provider
    Exchange code for tokens and create/update user
    """
    # Handle OAuth errors
    if error:
        logger.error(f"OAuth error from {provider}: {error} - {error_description}")
        # Redirect to frontend with error
        error_url = f"{FRONTEND_ORIGIN}/login?error=oauth_failed&provider={provider}"
        return RedirectResponse(url=error_url)
    
    try:
        # Handle OAuth callback
        result = await oauth_service.handle_oauth_callback(provider, code, state)
        
        person = result["person"]
        is_new_user = result["is_new_user"]
        linked_account = result["linked_account"]
        
        # Create session
        session_data = prepare_session_data({
            "username": person["email"],
            "role": person["role"],
            "person_id": person["person_id"],
            "full_name": person["full_name"]
        })
        request.session.update(session_data)
        
        # Determine redirect URL based on context
        if is_new_user:
            redirect_url = f"{FRONTEND_ORIGIN}/onboarding?welcome=true"
        elif linked_account:
            redirect_url = f"{FRONTEND_ORIGIN}/settings?linked={provider}"
        else:
            redirect_url = f"{FRONTEND_ORIGIN}/dashboard"
        
        logger.info(f"OAuth login successful for {person['email']} via {provider}")
        
        return RedirectResponse(url=redirect_url)
        
    except ValueError as e:
        logger.error(f"OAuth callback error: {e}")
        error_url = f"{FRONTEND_ORIGIN}/login?error={str(e)}"
        return RedirectResponse(url=error_url)
    except Exception as e:
        logger.error(f"Unexpected error in OAuth callback: {e}")
        error_url = f"{FRONTEND_ORIGIN}/login?error=oauth_failed"
        return RedirectResponse(url=error_url)

@router.post("/{provider}/link", summary="Link OAuth Provider to Account")
async def link_oauth_provider(
    provider: str,
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Link an OAuth provider to existing account
    User must be logged in to use this endpoint
    """
    try:
        person_id = current_user["person_id"]
        
        # Check if provider is already linked
        connections = await oauth_queries.get_oauth_connections(person_id)
        if any(conn["provider"] == provider for conn in connections):
            raise HTTPException(status_code=400, detail=f"{provider} is already linked to your account")
        
        # Generate authorization URL for linking
        auth_url, state = await oauth_service.get_authorization_url(
            provider=provider,
            person_id=person_id,
            is_linking=True
        )
        
        return {"authorization_url": auth_url}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error linking OAuth provider: {e}")
        raise HTTPException(status_code=500, detail="Failed to link OAuth provider")

@router.delete("/{provider}/disconnect", summary="Disconnect OAuth Provider")
async def disconnect_oauth_provider(
    provider: str,
    password: Optional[str] = Form(None),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Disconnect an OAuth provider from account
    If it's the only auth method, user must set a password first
    """
    try:
        person_id = current_user["person_id"]
        
        # Get person details
        person = await people_queries.get_person_by_id_from_db(person_id)
        if not person:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if user has a password
        has_password = bool(person.get("dashboard_password_hash"))
        
        # If no password and trying to disconnect primary OAuth
        if not has_password and person.get("oauth_provider") == provider:
            if not password:
                raise HTTPException(
                    status_code=400,
                    detail="You must set a password before disconnecting your only login method"
                )
            
            # Verify the provided password meets requirements
            if len(password) < 8:
                raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
            
            # Set the password
            from ..dependencies import hash_password
            hashed_password = hash_password(password)
            await people_queries.update_person_in_db(person_id, {"dashboard_password_hash": hashed_password})
        
        # Disconnect the provider
        success = await oauth_service.disconnect_provider(person_id, provider)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to disconnect provider")
        
        return {"message": f"Successfully disconnected {provider}"}
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error disconnecting OAuth provider: {e}")
        raise HTTPException(status_code=500, detail="Failed to disconnect OAuth provider")

@router.get("/providers", summary="Get Connected OAuth Providers")
async def get_oauth_providers(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> List[OAuthProviderResponse]:
    """
    Get list of OAuth providers and their connection status for current user
    """
    try:
        person_id = current_user["person_id"]
        
        # Get all OAuth connections
        connections = await oauth_queries.get_oauth_connections(person_id)
        
        # Build response for available providers
        providers = ["google"]  # Add more providers here as you implement them
        
        response = []
        for provider in providers:
            connection = next((c for c in connections if c["provider"] == provider), None)
            
            response.append(OAuthProviderResponse(
                provider=provider,
                connected=bool(connection),
                email=connection["provider_email"] if connection else None,
                connected_at=connection["connected_at"].isoformat() if connection else None
            ))
        
        return response
        
    except Exception as e:
        logger.error(f"Error getting OAuth providers: {e}")
        raise HTTPException(status_code=500, detail="Failed to get OAuth providers")

@router.post("/switch-to-oauth/{provider}", summary="Switch to OAuth Authentication")
async def switch_to_oauth(
    provider: str,
    password: str = Form(..., description="Current password for verification"),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Allow existing email/password users to switch to OAuth authentication
    Requires password verification for security
    """
    try:
        person_id = current_user["person_id"]
        
        # Get person details
        person = await people_queries.get_person_by_id_from_db(person_id)
        if not person:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify password
        if not person.get("dashboard_password_hash"):
            raise HTTPException(status_code=400, detail="No password set for this account")
        
        if not verify_password(password, person["dashboard_password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid password")
        
        # Check if already using OAuth
        if person.get("oauth_provider"):
            raise HTTPException(
                status_code=400,
                detail=f"Already using {person['oauth_provider']} for authentication"
            )
        
        # Generate authorization URL for linking
        auth_url, state = await oauth_service.get_authorization_url(
            provider=provider,
            person_id=person_id,
            is_linking=True
        )
        
        return {
            "authorization_url": auth_url,
            "message": "Password verified. Redirecting to OAuth provider..."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching to OAuth: {e}")
        raise HTTPException(status_code=500, detail="Failed to switch to OAuth authentication")

@router.get("/status", summary="Get OAuth Configuration Status")
async def get_oauth_status():
    """
    Get OAuth configuration status (for debugging)
    Only shows if providers are configured, not the actual secrets
    """
    providers_status = {}
    
    for provider, config in oauth_service.providers.items():
        providers_status[provider] = {
            "configured": bool(config.get("client_id") and config.get("client_secret")),
            "scopes": config.get("scopes", [])
        }
    
    return {
        "providers": providers_status,
        "encryption_configured": bool(os.getenv("TOKEN_ENCRYPTION_KEY"))
    }

