# podcast_outreach/api/routers/email_accounts.py

from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from pydantic import BaseModel, EmailStr
import logging

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.integrations.nylas import NylasAPIClient
from podcast_outreach.api.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/email-accounts", tags=["Email Accounts"])


class EmailAccountCreate(BaseModel):
    campaign_id: str
    email_address: EmailStr
    display_name: Optional[str] = None
    email_provider: str = "nylas"
    nylas_grant_id: Optional[str] = None
    instantly_campaign_id: Optional[str] = None
    is_primary: bool = False
    daily_send_limit: int = 50


class EmailAccountResponse(BaseModel):
    id: int
    campaign_id: str
    email_address: str
    display_name: Optional[str]
    email_provider: str
    is_active: bool
    is_primary: bool
    daily_send_limit: int
    total_sent: int
    total_opens: int
    total_replies: int


@router.post("/", response_model=EmailAccountResponse)
async def add_email_account(
    account: EmailAccountCreate,
    current_user: dict = Depends(get_current_user)
):
    """
    Add a new email account to a campaign.
    
    For Nylas accounts, you must provide a valid grant_id.
    For Instantly accounts, you must provide an instantly_campaign_id.
    """
    # Validate provider-specific requirements
    if account.email_provider == "nylas" and not account.nylas_grant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="nylas_grant_id is required for Nylas email accounts"
        )
    
    if account.email_provider == "instantly" and not account.instantly_campaign_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="instantly_campaign_id is required for Instantly email accounts"
        )
    
    # Test Nylas connection if it's a Nylas account
    if account.email_provider == "nylas":
        nylas_client = NylasAPIClient(grant_id=account.nylas_grant_id)
        if not nylas_client.test_connection():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Nylas grant ID or connection failed"
            )
    
    pool = await get_db_pool()
    
    try:
        # If marking as primary, unset other primary accounts
        if account.is_primary:
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE campaign_email_accounts 
                    SET is_primary = FALSE 
                    WHERE campaign_id = $1
                    """,
                    account.campaign_id
                )
        
        # Insert new email account
        query = """
            INSERT INTO campaign_email_accounts (
                campaign_id, email_address, display_name, email_provider,
                nylas_grant_id, instantly_campaign_id, is_primary, daily_send_limit
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
        """
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                account.campaign_id,
                account.email_address,
                account.display_name,
                account.email_provider,
                account.nylas_grant_id,
                account.instantly_campaign_id,
                account.is_primary,
                account.daily_send_limit
            )
            
            if row:
                return EmailAccountResponse(**dict(row))
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create email account"
                )
                
    except Exception as e:
        logger.error(f"Error adding email account: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/campaign/{campaign_id}", response_model=List[EmailAccountResponse])
async def get_campaign_email_accounts(
    campaign_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all email accounts for a campaign."""
    pool = await get_db_pool()
    
    query = """
        SELECT * FROM campaign_email_accounts 
        WHERE campaign_id = $1 
        ORDER BY is_primary DESC, created_at ASC
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, campaign_id)
        return [EmailAccountResponse(**dict(row)) for row in rows]


@router.delete("/{account_id}")
async def delete_email_account(
    account_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Delete an email account."""
    pool = await get_db_pool()
    
    query = """
        DELETE FROM campaign_email_accounts 
        WHERE id = $1 
        RETURNING id
    """
    
    async with pool.acquire() as conn:
        result = await conn.fetchval(query, account_id)
        
        if result:
            return {"message": "Email account deleted successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email account not found"
            )


@router.post("/{account_id}/test")
async def test_email_account(
    account_id: int,
    current_user: dict = Depends(get_current_user)
):
    """Test an email account connection."""
    pool = await get_db_pool()
    
    # Get account details
    query = """
        SELECT email_provider, nylas_grant_id, instantly_campaign_id 
        FROM campaign_email_accounts 
        WHERE id = $1
    """
    
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, account_id)
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email account not found"
            )
        
        if row['email_provider'] == 'nylas':
            nylas_client = NylasAPIClient(grant_id=row['nylas_grant_id'])
            if nylas_client.test_connection():
                return {"status": "success", "message": "Nylas connection successful"}
            else:
                return {"status": "error", "message": "Nylas connection failed"}
        else:
            # For Instantly, you could add a test here
            return {"status": "success", "message": "Instantly accounts are not tested via API"}


@router.post("/nylas-auth-callback")
async def nylas_auth_callback(
    code: str,
    campaign_id: str,
    email_address: EmailStr,
    current_user: dict = Depends(get_current_user)
):
    """
    Handle Nylas OAuth callback to get grant ID.
    This is called after user authorizes their email account.
    """
    # This is a simplified example - you'd need to implement the full OAuth flow
    # including exchanging the code for a grant ID using Nylas API
    
    # For now, this is a placeholder
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Nylas OAuth flow not implemented. Use Nylas Hosted Authentication or provide grant_id directly."
    )