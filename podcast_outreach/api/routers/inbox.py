# podcast_outreach/api/routers/inbox.py

from fastapi import APIRouter, HTTPException, Depends, Query, Form, File, UploadFile
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, EmailStr
import json

from podcast_outreach.database.connection import get_db_async
from podcast_outreach.services.inbox.booking_assistant import BookingAssistantService
from podcast_outreach.api.routers.nylas_webhooks import store_email_classification
from podcast_outreach.api.dependencies import get_current_user
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/inbox", tags=["Inbox"])

# Request models
class SendEmailRequest(BaseModel):
    to: List[EmailStr]
    subject: str
    body: str
    cc: Optional[List[EmailStr]] = None
    bcc: Optional[List[EmailStr]] = None
    grant_id: Optional[str] = None


@router.get("/nylas-status")
async def get_nylas_status(current_user: dict = Depends(get_current_user)):
    """Check Nylas connection status for the current user."""
    try:
        person_id = current_user.get("person_id")
        if not person_id:
            raise HTTPException(status_code=400, detail="User not properly authenticated")
        
        # Get user's campaigns and their email accounts
        async with get_db_async() as db:
            # First check if nylas_grants table exists, otherwise use campaign_email_accounts
            try:
                # Try nylas_grants table first (if it exists)
                grants = await db.fetch_all("""
                    SELECT DISTINCT cea.nylas_grant_id as grant_id, cea.email_address as email, cea.is_active 
                    FROM campaign_email_accounts cea
                    JOIN campaigns c ON cea.campaign_id = c.campaign_id
                    WHERE c.person_id = $1 
                    AND cea.is_active = true
                    AND cea.nylas_grant_id IS NOT NULL
                    LIMIT 5
                """, person_id)
            except Exception:
                # Fallback to campaign_email_accounts only
                grants = await db.fetch_all("""
                    SELECT DISTINCT cea.nylas_grant_id as grant_id, cea.email_address as email, cea.is_active 
                    FROM campaign_email_accounts cea
                    JOIN campaigns c ON cea.campaign_id = c.campaign_id
                    WHERE c.person_id = $1 
                    AND cea.is_active = true
                    AND cea.nylas_grant_id IS NOT NULL
                    LIMIT 5
                """, person_id)
        
        return {
            "connected": len(grants) > 0 if grants else False,
            "grants": [{"grant_id": g["grant_id"], "email": g["email"]} for g in grants] if grants else [],
            "status": "connected" if grants and len(grants) > 0 else "not_configured"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking Nylas status for user {current_user.get('person_id')}: {e}")
        return {
            "connected": False,
            "grants": [],
            "status": "error",
            "error": str(e)
        }


@router.get("/messages")
async def get_inbox_messages(
    grant_id: Optional[str] = Query(None),
    folder: Optional[str] = Query("inbox"),
    unread_only: bool = Query(False),
    has_classification: bool = Query(False),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100)
):
    """Get inbox messages with optional filters."""
    
    offset = (page - 1) * size
    
    async with get_db_async() as db:
        query = """
            SELECT 
                im.*,
                ec.classification,
                ec.confidence_score,
                ed.draft_id,
                ed.draft_content,
                p.pitch_id,
                p.campaign_id
            FROM inbox_messages im
            LEFT JOIN email_classifications ec ON im.message_id = ec.message_id
            LEFT JOIN email_drafts ed ON im.thread_id = ed.thread_id
            LEFT JOIN pitches p ON im.thread_id = p.nylas_thread_id
            WHERE 1=1
        """
        
        params = []
        
        if grant_id:
            query += f" AND im.grant_id = ${len(params) + 1}"
            params.append(grant_id)
        
        if unread_only:
            query += " AND im.unread = true"
        
        if has_classification:
            query += " AND ec.classification IS NOT NULL"
        
        query += f" ORDER BY im.date DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        params.extend([size, offset])
        
        messages = await db.fetch_all(query, *params)
        
        # Count total
        count_query = query.split("ORDER BY")[0].replace("SELECT im.*", "SELECT COUNT(*)")
        total = await db.fetch_val(count_query, *params[:-2])
        
    return {
        "messages": messages,
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if total else 0
    }


@router.get("/threads/{thread_id}")
async def get_thread_details(thread_id: str):
    """Get full thread with all messages and classifications."""
    
    async with get_db_async() as db:
        # Get all messages in thread
        messages = await db.fetch_all("""
            SELECT 
                im.*,
                ec.classification,
                ec.confidence_score
            FROM inbox_messages im
            LEFT JOIN email_classifications ec ON im.message_id = ec.message_id
            WHERE im.thread_id = $1
            ORDER BY im.date ASC
        """, thread_id)
        
        # Get drafts for thread
        drafts = await db.fetch_all("""
            SELECT * FROM email_drafts
            WHERE thread_id = $1
            ORDER BY created_at DESC
        """, thread_id)
        
        # Get associated pitch and placement
        pitch = await db.fetch_one("""
            SELECT p.*, pl.placement_id, pl.current_status as placement_status
            FROM pitches p
            LEFT JOIN placements pl ON p.pitch_id = pl.pitch_id
            WHERE p.nylas_thread_id = $1
        """, thread_id)
        
    return {
        "thread_id": thread_id,
        "messages": [dict(m) for m in messages] if messages else [],
        "drafts": [dict(d) for d in drafts] if drafts else [],
        "pitch": dict(pitch) if pitch else None,
        "total_messages": len(messages) if messages else 0
    }


@router.post("/classify/{message_id}")
async def classify_message(message_id: str):
    """Manually trigger classification for a message."""
    
    # Get message details
    async with get_db_async() as db:
        message = await db.fetch_one("""
            SELECT * FROM inbox_messages WHERE message_id = $1
        """, message_id)
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Process through BookingAssistant
    booking_assistant = BookingAssistantService()
    result = await booking_assistant.process_email({
        "email_text": message["body_plain"] or message["snippet"],
        "subject": message["subject"],
        "sender_email": message["from_email"],
        "sender_name": message["from_name"],
        "thread_id": message["thread_id"],
        "message_id": message_id
    })
    
    # Store classification
    await store_email_classification(
        message_id=message_id,
        thread_id=message["thread_id"],
        classification_result=result
    )
    
    return result


@router.get("/classifications/summary")
async def get_classification_summary(
    days: int = Query(7, ge=1, le=90),
    campaign_id: Optional[str] = None
):
    """Get summary of email classifications."""
    
    since_date = datetime.now() - timedelta(days=days)
    
    async with get_db_async() as db:
        query = """
            SELECT 
                classification,
                COUNT(*) as count,
                AVG(confidence_score) as avg_confidence
            FROM email_classifications ec
            LEFT JOIN pitches p ON ec.thread_id = p.nylas_thread_id
            WHERE ec.processed_at >= $1
        """
        
        params = [since_date]
        
        if campaign_id:
            query += " AND p.campaign_id = $2"
            params.append(campaign_id)
        
        query += " GROUP BY classification ORDER BY count DESC"
        
        results = await db.fetch_all(query, *params)
    
    return {
        "period_days": days,
        "campaign_id": campaign_id,
        "classifications": [dict(r) for r in results] if results else [],
        "total": sum(r["count"] for r in results) if results else 0
    }


@router.get("/review-tasks")
async def get_review_tasks(
    task_type: Optional[str] = None,
    campaign_id: Optional[str] = None,
    status: Optional[str] = Query("pending", enum=["pending", "in_progress", "completed", "cancelled"]),
    priority: Optional[str] = Query(None, enum=["low", "normal", "high"]),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100)
):
    """Get review tasks for human verification."""
    
    offset = (page - 1) * size
    
    async with get_db_async() as db:
        query = """
            SELECT * FROM review_tasks
            WHERE 1=1
        """
        
        params = []
        
        if task_type:
            query += f" AND task_type = ${len(params) + 1}"
            params.append(task_type)
        
        if campaign_id:
            query += f" AND campaign_id = ${len(params) + 1}::uuid"
            params.append(campaign_id)
        
        if status:
            query += f" AND status = ${len(params) + 1}"
            params.append(status)
        
        if priority:
            query += f" AND priority = ${len(params) + 1}"
            params.append(priority)
        
        query += f" ORDER BY created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        params.extend([size, offset])
        
        tasks = await db.fetch_all(query, *params)
        
        # Count total
        count_query = query.split("ORDER BY")[0].replace("SELECT *", "SELECT COUNT(*)")
        total = await db.fetch_val(count_query, *params[:-2])
    
    return {
        "tasks": [dict(t) for t in tasks] if tasks else [],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if total else 0
    }


@router.put("/review-tasks/{task_id}/status")
async def update_review_task_status(
    task_id: int,
    status: str = Query(..., enum=["pending", "in_progress", "completed", "cancelled"]),
    notes: Optional[str] = None
):
    """Update the status of a review task."""
    
    async with get_db_async() as db:
        query = """
            UPDATE review_tasks
            SET status = $2,
                updated_at = NOW()
        """
        params = [task_id, status]
        
        if notes:
            query = query.replace("updated_at = NOW()", "updated_at = NOW(), notes = notes || E'\\n\\n' || $3")
            params.append(notes)
        
        query += " WHERE task_id = $1 RETURNING *"
        
        updated_task = await db.fetch_one(query, *params)
        
        if not updated_task:
            raise HTTPException(status_code=404, detail="Task not found")
    
    return dict(updated_task)


@router.get("/threads")
async def get_inbox_threads(
    grant_id: Optional[str] = Query(None),
    folder: Optional[str] = Query("inbox"),
    unread_only: bool = Query(False),
    starred_only: bool = Query(False),
    search_query: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Get email threads with optional filters for the current user."""
    
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=400, detail="User not properly authenticated")
    
    offset = (page - 1) * size
    
    async with get_db_async() as db:
        # First get valid grant_ids for this user
        user_grants = await db.fetch_all("""
            SELECT DISTINCT cea.nylas_grant_id 
            FROM campaign_email_accounts cea
            JOIN campaigns c ON cea.campaign_id = c.campaign_id
            WHERE c.person_id = $1 
            AND cea.nylas_grant_id IS NOT NULL
        """, person_id)
        
        valid_grant_ids = [g["nylas_grant_id"] for g in user_grants] if user_grants else []
        
        if not valid_grant_ids:
            return {
                "threads": [],
                "total": 0,
                "page": page,
                "size": size,
                "pages": 0
            }
        
        # Get unique threads with latest message info
        query = """
            SELECT DISTINCT ON (im.thread_id)
                im.thread_id,
                im.subject,
                im.snippet,
                im.from_email,
                im.from_name,
                im.date,
                im.unread,
                im.starred,
                im.has_attachments,
                COUNT(*) OVER (PARTITION BY im.thread_id) as message_count,
                ec.classification,
                p.pitch_id,
                p.campaign_id
            FROM inbox_messages im
            LEFT JOIN email_classifications ec ON im.message_id = ec.message_id
            LEFT JOIN pitches p ON im.thread_id = p.nylas_thread_id
            WHERE 1=1
        """
        
        params = []
        
        # Always filter by user's valid grant IDs
        if grant_id:
            # Verify the grant_id belongs to the user
            if grant_id not in valid_grant_ids:
                raise HTTPException(status_code=403, detail="Access denied to this grant")
            query += f" AND im.grant_id = ${len(params) + 1}"
            params.append(grant_id)
        else:
            # Filter by all user's grant IDs
            query += f" AND im.grant_id = ANY(${len(params) + 1})"
            params.append(valid_grant_ids)
        
        if unread_only:
            query += " AND im.unread = true"
        
        if starred_only:
            query += " AND im.starred = true"
            
        if search_query:
            query += f" AND (im.subject ILIKE ${len(params) + 1} OR im.body_plain ILIKE ${len(params) + 1})"
            params.append(f"%{search_query}%")
        
        query += " ORDER BY im.thread_id, im.date DESC"
        
        # Wrap in subquery for pagination
        paginated_query = f"""
            SELECT * FROM ({query}) t
            ORDER BY date DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """
        params.extend([size, offset])
        
        threads = await db.fetch_all(paginated_query, *params)
        
        # Count total threads
        count_query = f"""
            SELECT COUNT(DISTINCT thread_id) FROM inbox_messages im
            WHERE 1=1
        """
        if grant_id:
            count_query += " AND im.grant_id = $1"
            total = await db.fetch_val(count_query, grant_id)
        else:
            total = await db.fetch_val(count_query)
        
    return {
        "threads": [dict(t) for t in threads] if threads else [],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if total else 0
    }


@router.post("/threads/{thread_id}/archive")
async def archive_thread(thread_id: str):
    """Archive an email thread."""
    
    async with get_db_async() as db:
        # Update all messages in thread to archived folder
        await db.execute("""
            UPDATE inbox_messages 
            SET folder_id = 'archive',
                updated_at = NOW()
            WHERE thread_id = $1
        """, thread_id)
        
    return {"status": "success", "thread_id": thread_id, "action": "archived"}


@router.post("/threads/{thread_id}/mark-read")
async def mark_thread_read(thread_id: str):
    """Mark all messages in a thread as read."""
    
    async with get_db_async() as db:
        result = await db.execute("""
            UPDATE inbox_messages 
            SET unread = false,
                updated_at = NOW()
            WHERE thread_id = $1 AND unread = true
        """, thread_id)
        
    return {"status": "success", "thread_id": thread_id, "messages_updated": result}


@router.post("/threads/{thread_id}/star")
async def toggle_thread_star(thread_id: str):
    """Toggle star status for a thread."""
    
    async with get_db_async() as db:
        # Get current star status
        current = await db.fetch_one("""
            SELECT starred FROM inbox_messages 
            WHERE thread_id = $1 
            ORDER BY date DESC LIMIT 1
        """, thread_id)
        
        new_starred = not (current["starred"] if current else False)
        
        # Update all messages in thread
        await db.execute("""
            UPDATE inbox_messages 
            SET starred = $1,
                updated_at = NOW()
            WHERE thread_id = $2
        """, new_starred, thread_id)
        
    return {"status": "success", "thread_id": thread_id, "starred": new_starred}


@router.get("/threads/{thread_id}/smart-replies")
async def get_smart_replies(thread_id: str):
    """Get AI-generated smart reply suggestions for a thread."""
    
    async with get_db_async() as db:
        # Get the latest message in thread
        message = await db.fetch_one("""
            SELECT body_plain, subject, from_email, from_name
            FROM inbox_messages 
            WHERE thread_id = $1
            ORDER BY date DESC LIMIT 1
        """, thread_id)
        
    if not message:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Generate smart replies using AI
    from podcast_outreach.services.ai.gemini_client import GeminiService
    gemini = GeminiService()
    
    prompt = f"""
    Generate 3 short, professional reply options for this email:
    
    Subject: {message['subject']}
    From: {message['from_name']} <{message['from_email']}>
    Message: {message['body_plain'][:500]}
    
    Provide 3 different reply options:
    1. A positive/accepting response
    2. A neutral/need more info response  
    3. A polite declining response
    
    Keep each reply under 100 words. Return as JSON array with 'type' and 'text' fields.
    """
    
    try:
        response = await gemini.create_message(
            prompt, 
            workflow="smart_replies",
            temperature=0.7
        )
        
        # Parse response as JSON
        import json
        replies = json.loads(response) if isinstance(response, str) else response
        
        return {
            "thread_id": thread_id,
            "replies": replies
        }
    except Exception as e:
        logger.error(f"Error generating smart replies: {e}")
        # Return default replies
        return {
            "thread_id": thread_id,
            "replies": [
                {"type": "positive", "text": "Thank you for reaching out! I'd be happy to discuss this further."},
                {"type": "neutral", "text": "Thanks for your message. Could you provide more details about your proposal?"},
                {"type": "decline", "text": "Thank you for thinking of me, but this isn't a good fit at this time."}
            ]
        }


@router.post("/nylas/connect")
async def connect_nylas_account(
    provider: str = Query("google", description="Email provider (google, microsoft, etc.)"),
    login_hint: Optional[str] = Query(None, description="User's email to pre-fill"),
    state: Optional[str] = Query(None, description="CSRF/session token"),
    current_user: dict = Depends(get_current_user)
):
    """Initiate Nylas OAuth flow to connect email account."""
    
    from podcast_outreach.config import NYLAS_CLIENT_ID, FRONTEND_ORIGIN, NYLAS_API_URI
    import secrets
    
    if not NYLAS_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Nylas client ID not configured")
    
    # Generate state token if not provided (for CSRF protection)
    if not state:
        state = secrets.token_urlsafe(32)
        # Store state in session/database for verification in callback
        # For now, we'll pass it through
    
    redirect_uri = f"{FRONTEND_ORIGIN}/nylas/callback"
    
    # Build OAuth URL with proper parameters
    oauth_params = {
        "client_id": NYLAS_CLIENT_ID,
        "provider": provider,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "access_type": "online",
        "state": state
    }
    
    # Add Gmail-specific scopes if provider is Google
    if provider == "google":
        oauth_params["scope"] = "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.modify"
    
    # Add login hint if provided
    if login_hint:
        oauth_params["login_hint"] = login_hint
    
    # Build query string
    from urllib.parse import urlencode
    query_string = urlencode(oauth_params)
    oauth_url = f"{NYLAS_API_URI}/v3/connect/auth?{query_string}"
    
    return {
        "oauth_url": oauth_url,
        "state": state,
        "message": "Redirect user to OAuth URL to connect their email account"
    }


@router.get("/nylas/callback")
async def nylas_oauth_callback(
    code: str = Query(..., description="Authorization code from Nylas"),
    state: str = Query(..., description="State token for CSRF protection"),
    campaign_id: Optional[str] = Query(None, description="Campaign to associate email with"),
    current_user: dict = Depends(get_current_user)
):
    """
    Handle Nylas OAuth callback to exchange code for grant_id.
    This is called after user authorizes their email account.
    """
    from podcast_outreach.config import NYLAS_API_KEY, NYLAS_API_URI, FRONTEND_ORIGIN
    import httpx
    
    if not NYLAS_API_KEY:
        raise HTTPException(status_code=500, detail="Nylas API key not configured")
    
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=400, detail="User not properly authenticated")
    
    # TODO: Verify state matches stored state for CSRF protection
    # For now, we'll skip this check but it should be implemented in production
    
    # Exchange code for grant
    from podcast_outreach.config import NYLAS_CLIENT_ID, FRONTEND_ORIGIN
    
    if not NYLAS_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Nylas client ID not configured")
    
    # Build the redirect URI - must match exactly what was used in the authorization request
    redirect_uri = f"{FRONTEND_ORIGIN}/nylas/callback"
    
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            # Nylas v3 token exchange - client_secret is the API key
            response = await client.post(
                f"{NYLAS_API_URI}/v3/connect/token",
                headers={
                    "Content-Type": "application/json"
                },
                json={
                    "code": code,
                    "client_id": NYLAS_CLIENT_ID,
                    "client_secret": NYLAS_API_KEY,  # In v3, this is the API key
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": "nylas"  # Recommended per Nylas docs
                }
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Nylas token exchange failed: {e.response.text}")
            raise HTTPException(
                status_code=400, 
                detail=f"Failed to exchange code for grant: {e.response.text}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during token exchange: {e}")
            raise HTTPException(status_code=500, detail="Token exchange failed")
    
    data = response.json()
    grant_id = data.get("grant_id")
    email = data.get("email", "")
    provider = data.get("provider", "google")
    
    if not grant_id:
        raise HTTPException(status_code=400, detail="No grant_id received from Nylas")
    
    # Save grant_id to database
    async with get_db_async() as db:
        # If campaign_id provided, update that specific campaign
        if campaign_id:
            # Update the campaign with the Nylas grant_id and email
            await db.execute("""
                UPDATE campaigns 
                SET nylas_grant_id = $1,
                    email_account = $2,
                    email_provider = 'nylas'
                WHERE campaign_id = $3
            """, grant_id, email, campaign_id)
            
            # Also check/update campaign_email_accounts table if it exists
            try:
                existing = await db.fetch_one("""
                    SELECT id FROM campaign_email_accounts 
                    WHERE campaign_id = $1 AND email_address = $2
                """, campaign_id, email)
                
                if existing:
                    await db.execute("""
                        UPDATE campaign_email_accounts 
                        SET nylas_grant_id = $1, 
                            is_active = true,
                            email_provider = 'nylas',
                            updated_at = NOW()
                        WHERE id = $2
                    """, grant_id, existing["id"])
                else:
                    await db.execute("""
                        INSERT INTO campaign_email_accounts 
                        (campaign_id, email_address, nylas_grant_id, email_provider, is_active, is_primary)
                        VALUES ($1, $2, $3, 'nylas', true, false)
                    """, campaign_id, email, grant_id)
            except Exception as e:
                logger.warning(f"campaign_email_accounts table may not exist: {e}")
        else:
            # Get user's most recent campaign
            campaign = await db.fetch_one("""
                SELECT campaign_id FROM campaigns 
                WHERE person_id = $1 
                ORDER BY created_at DESC 
                LIMIT 1
            """, person_id)
            
            if campaign:
                campaign_id = campaign["campaign_id"]
                
                # Update the campaign with Nylas grant_id
                await db.execute("""
                    UPDATE campaigns 
                    SET nylas_grant_id = $1,
                        email_account = $2,
                        email_provider = 'nylas'
                    WHERE campaign_id = $3
                """, grant_id, email, campaign_id)
                
                # Also try to update campaign_email_accounts if it exists
                try:
                    existing = await db.fetch_one("""
                        SELECT id FROM campaign_email_accounts 
                        WHERE campaign_id = $1 AND email_address = $2
                    """, campaign_id, email)
                    
                    if existing:
                        await db.execute("""
                            UPDATE campaign_email_accounts 
                            SET nylas_grant_id = $1, 
                                is_active = true,
                                email_provider = 'nylas',
                                updated_at = NOW()
                            WHERE id = $2
                        """, grant_id, existing["id"])
                    else:
                        await db.execute("""
                            INSERT INTO campaign_email_accounts 
                            (campaign_id, email_address, nylas_grant_id, email_provider, is_active, is_primary)
                            VALUES ($1, $2, $3, 'nylas', true, false)
                        """, campaign_id, email, grant_id)
                except Exception as e:
                    logger.warning(f"campaign_email_accounts table may not exist: {e}")
    
    logger.info(f"Successfully connected email {email} for user {person_id}")
    
    # Return success with redirect URL
    redirect_url = f"{FRONTEND_ORIGIN}/settings/integrations?connected=success&email={email}"
    
    return {
        "status": "success",
        "grant_id": grant_id,
        "email": email,
        "provider": provider,
        "redirect_url": redirect_url,
        "message": f"Successfully connected {email}"
    }


@router.post("/nylas/disconnect")
async def disconnect_nylas_account(
    grant_id: str, 
    campaign_id: Optional[str] = Query(None, description="Specific campaign to disconnect"),
    current_user: dict = Depends(get_current_user)
):
    """Disconnect a Nylas email account and revoke the grant."""
    
    from podcast_outreach.config import NYLAS_API_KEY, NYLAS_API_URI
    import httpx
    
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=400, detail="User not properly authenticated")
    
    async with get_db_async() as db:
        # Verify grant belongs to user (check campaigns table)
        if campaign_id:
            grant_check = await db.fetch_one("""
                SELECT campaign_id, nylas_grant_id 
                FROM campaigns 
                WHERE campaign_id = $1 AND person_id = $2 AND nylas_grant_id = $3
            """, campaign_id, person_id, grant_id)
        else:
            grant_check = await db.fetch_one("""
                SELECT campaign_id, nylas_grant_id 
                FROM campaigns 
                WHERE person_id = $1 AND nylas_grant_id = $2
            """, person_id, grant_id)
        
        if not grant_check:
            # Also check campaign_email_accounts table if exists
            try:
                grant_check = await db.fetch_one("""
                    SELECT cea.id
                    FROM campaign_email_accounts cea
                    JOIN campaigns c ON cea.campaign_id = c.campaign_id
                    WHERE c.person_id = $1 AND cea.nylas_grant_id = $2
                """, person_id, grant_id)
                
                if not grant_check:
                    raise HTTPException(status_code=403, detail="Access denied to this grant")
            except:
                raise HTTPException(status_code=403, detail="Access denied to this grant")
        
        # Clear grant from campaigns table
        if campaign_id:
            await db.execute("""
                UPDATE campaigns 
                SET nylas_grant_id = NULL,
                    email_account = NULL,
                    email_provider = 'instantly'
                WHERE campaign_id = $1
            """, campaign_id)
        else:
            # Clear from all user's campaigns
            await db.execute("""
                UPDATE campaigns 
                SET nylas_grant_id = NULL,
                    email_account = NULL,
                    email_provider = 'instantly'
                WHERE person_id = $1 AND nylas_grant_id = $2
            """, person_id, grant_id)
        
        # Also mark as inactive in campaign_email_accounts if exists
        try:
            await db.execute("""
                UPDATE campaign_email_accounts 
                SET is_active = false,
                    updated_at = NOW()
                WHERE nylas_grant_id = $1
            """, grant_id)
        except:
            pass  # Table might not exist
        
        # Revoke grant via Nylas API
        if NYLAS_API_KEY:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.delete(
                        f"{NYLAS_API_URI}/v3/grants/{grant_id}",
                        headers={"Authorization": f"Bearer {NYLAS_API_KEY}"}
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"Successfully revoked Nylas grant {grant_id}")
                    else:
                        logger.warning(f"Failed to revoke grant {grant_id}: {response.status_code}")
            except Exception as e:
                logger.error(f"Error revoking Nylas grant: {e}")
                # Continue even if revocation fails - we've already removed from our DB
    
    return {"status": "success", "message": "Email account disconnected", "grant_id": grant_id}


@router.post("/send-json")
async def send_email_json(
    request: SendEmailRequest,
    current_user: dict = Depends(get_current_user)
):
    """Send a new email through Nylas (JSON version)."""
    
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=400, detail="User not properly authenticated")
    
    from podcast_outreach.integrations.nylas import NylasAPIClient
    
    # Extract from request object
    to = request.to
    subject = request.subject
    body = request.body
    cc = request.cc
    bcc = request.bcc
    grant_id = request.grant_id
    
    if not grant_id:
        # Get default grant for user's campaigns
        async with get_db_async() as db:
            grant = await db.fetch_one("""
                SELECT nylas_grant_id as grant_id 
                FROM campaigns
                WHERE person_id = $1 
                AND nylas_grant_id IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
            """, person_id)
            
            if not grant:
                # Try campaign_email_accounts as fallback
                grant = await db.fetch_one("""
                    SELECT cea.nylas_grant_id as grant_id 
                    FROM campaign_email_accounts cea
                    JOIN campaigns c ON cea.campaign_id = c.campaign_id
                    WHERE c.person_id = $1 
                    AND cea.is_active = true 
                    AND cea.nylas_grant_id IS NOT NULL
                    LIMIT 1
                """, person_id)
                
            if not grant:
                raise HTTPException(status_code=400, detail="No active email account connected")
            grant_id = grant["grant_id"]
    else:
        # Verify the provided grant_id belongs to the user
        async with get_db_async() as db:
            grant_check = await db.fetch_one("""
                SELECT campaign_id
                FROM campaigns
                WHERE person_id = $1 AND nylas_grant_id = $2
            """, person_id, grant_id)
            
            if not grant_check:
                # Try campaign_email_accounts as fallback
                grant_check = await db.fetch_one("""
                    SELECT cea.id
                    FROM campaign_email_accounts cea
                    JOIN campaigns c ON cea.campaign_id = c.campaign_id
                    WHERE c.person_id = $1 AND cea.nylas_grant_id = $2
                """, person_id, grant_id)
                
                if not grant_check:
                    raise HTTPException(status_code=403, detail="Access denied to this grant")
    
    client = NylasAPIClient(grant_id=grant_id)
    
    # Ensure HTML is properly formatted if not already
    if body and not body.strip().startswith('<'):
        # Plain text - convert to HTML
        body = f"<html><body><p>{body.replace(chr(10), '<br>')}</p></body></html>"
    elif body and '<html>' not in body.lower():
        # Partial HTML - wrap it
        body = f"<html><body>{body}</body></html>"
    
    try:
        result = client.send_email_v3(
            to_emails=to,
            subject=subject,
            body=body,
            cc_emails=cc,
            bcc_emails=bcc,
            tracking=False  # Disable tracking to avoid spam filters
        )
        
        # Store the sent message in inbox_messages table
        async with get_db_async() as db:
            await db.execute("""
                INSERT INTO inbox_messages (
                    message_id, grant_id, thread_id, folder_id,
                    subject, snippet, body_html, body_plain,
                    from_email, from_name, to_json,
                    date, unread, starred, synced_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
                ON CONFLICT (message_id) DO UPDATE SET
                    folder_id = 'sent',
                    synced_at = NOW()
            """, 
                result.get("id"),
                grant_id,
                result.get("thread_id"),
                'sent',  # Folder is 'sent'
                subject,
                body[:200] if body else '',  # Snippet
                body if body.startswith('<') else f"<html><body>{body}</body></html>",
                body.replace('<br>', '\n').replace('</p>', '\n').replace('<[^>]+>', '') if '<' in body else body,
                result.get("from", [{}])[0].get("email", ""),
                result.get("from", [{}])[0].get("name", ""),
                json.dumps([{"email": email} for email in to]),
                datetime.now(timezone.utc),
                False,  # Not unread (we sent it)
                False   # Not starred
            )
        
        return {
            "status": "success",
            "message_id": result.get("id"),
            "thread_id": result.get("thread_id"),
            "stored": True  # Indicate message was stored
        }
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send")
async def send_email(
    subject: str = Form(...),
    body: str = Form(...),
    to: str = Form(...),  # JSON string like '["email@example.com"]'
    cc: Optional[str] = Form(None),  # JSON string
    bcc: Optional[str] = Form(None),  # JSON string
    grant_id: Optional[str] = Form(None),
    attachments: Optional[List[UploadFile]] = File(None),
    current_user: dict = Depends(get_current_user)
):
    """Send a new email through Nylas (multipart/form-data version)."""
    
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=400, detail="User not properly authenticated")
    
    from podcast_outreach.integrations.nylas import NylasAPIClient
    import json
    
    # Parse JSON strings from form data
    try:
        to = json.loads(to) if isinstance(to, str) else to
        cc = json.loads(cc) if cc else None
        bcc = json.loads(bcc) if bcc else None
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in email addresses: {e}")
    
    # Validate email addresses
    if not to or not isinstance(to, list):
        raise HTTPException(status_code=400, detail="'to' must be a list of email addresses")
    
    if not grant_id:
        # Get default grant for user's campaigns
        async with get_db_async() as db:
            # First try campaigns table
            grant = await db.fetch_one("""
                SELECT nylas_grant_id as grant_id 
                FROM campaigns
                WHERE person_id = $1 
                AND nylas_grant_id IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
            """, person_id)
            
            if not grant:
                # Try campaign_email_accounts as fallback
                grant = await db.fetch_one("""
                    SELECT cea.nylas_grant_id as grant_id 
                    FROM campaign_email_accounts cea
                    JOIN campaigns c ON cea.campaign_id = c.campaign_id
                    WHERE c.person_id = $1 
                    AND cea.is_active = true 
                    AND cea.nylas_grant_id IS NOT NULL
                    LIMIT 1
                """, person_id)
                
            if not grant:
                raise HTTPException(status_code=400, detail="No active email account connected")
            grant_id = grant["grant_id"]
    else:
        # Verify the provided grant_id belongs to the user
        async with get_db_async() as db:
            # First try campaigns table
            grant_check = await db.fetch_one("""
                SELECT campaign_id
                FROM campaigns
                WHERE person_id = $1 AND nylas_grant_id = $2
            """, person_id, grant_id)
            
            if not grant_check:
                # Try campaign_email_accounts as fallback
                grant_check = await db.fetch_one("""
                    SELECT cea.id
                    FROM campaign_email_accounts cea
                    JOIN campaigns c ON cea.campaign_id = c.campaign_id
                    WHERE c.person_id = $1 AND cea.nylas_grant_id = $2
                """, person_id, grant_id)
                
                if not grant_check:
                    raise HTTPException(status_code=403, detail="Access denied to this grant")
    
    client = NylasAPIClient(grant_id=grant_id)
    
    # Ensure HTML is properly formatted if not already
    if body and not body.strip().startswith('<'):
        # Plain text - convert to HTML
        body = f"<html><body><p>{body.replace(chr(10), '<br>')}</p></body></html>"
    elif body and '<html>' not in body.lower():
        # Partial HTML - wrap it
        body = f"<html><body>{body}</body></html>"
    
    try:
        result = client.send_email_v3(
            to_emails=to,
            subject=subject,
            body=body,
            cc_emails=cc,
            bcc_emails=bcc,
            tracking=False  # Disable tracking to avoid spam filters
        )
        
        # Store the sent message in inbox_messages table
        async with get_db_async() as db:
            await db.execute("""
                INSERT INTO inbox_messages (
                    message_id, grant_id, thread_id, folder_id,
                    subject, snippet, body_html, body_plain,
                    from_email, from_name, to_json,
                    date, unread, starred, synced_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
                ON CONFLICT (message_id) DO UPDATE SET
                    folder_id = 'sent',
                    synced_at = NOW()
            """, 
                result.get("id"),
                grant_id,
                result.get("thread_id"),
                'sent',  # Folder is 'sent'
                subject,
                body[:200] if body else '',  # Snippet
                body if body.startswith('<') else f"<html><body>{body}</body></html>",
                body.replace('<br>', '\n').replace('</p>', '\n').replace('<[^>]+>', '') if '<' in body else body,
                result.get("from", [{}])[0].get("email", ""),
                result.get("from", [{}])[0].get("name", ""),
                json.dumps([{"email": email} for email in to]),
                datetime.now(timezone.utc),
                False,  # Not unread (we sent it)
                False   # Not starred
            )
        
        return {
            "status": "success",
            "message_id": result.get("id"),
            "thread_id": result.get("thread_id"),
            "stored": True  # Indicate message was stored
        }
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages/{message_id}/reply")
async def reply_to_message(
    message_id: str,
    body: str,
    reply_all: bool = False
):
    """Reply to a specific message."""
    
    async with get_db_async() as db:
        # Get original message details
        message = await db.fetch_one("""
            SELECT * FROM inbox_messages 
            WHERE message_id = $1
        """, message_id)
        
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    from podcast_outreach.integrations.nylas import NylasAPIClient
    client = NylasAPIClient(grant_id=message["grant_id"])
    
    # Prepare recipients
    to_emails = [message["from_email"]]
    cc_emails = []
    
    if reply_all and message.get("to_json"):
        import json
        original_recipients = json.loads(message["to_json"]) if isinstance(message["to_json"], str) else message["to_json"]
        cc_emails = [email for email in original_recipients if email != message["from_email"]]
    
    try:
        result = client.send_email(
            to_emails=to_emails,
            cc_emails=cc_emails if reply_all else None,
            subject=f"Re: {message['subject']}",
            body=body,
            thread_id=message["thread_id"]
        )
        
        return {
            "status": "success",
            "message_id": result.get("id"),
            "thread_id": message["thread_id"]
        }
    except Exception as e:
        logger.error(f"Error sending reply: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_inbox_messages(
    grant_id: Optional[str] = Query(None),
    folder: Optional[str] = Query(None, description="Specific folder to sync (inbox, sent, trash, etc.)"),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user)
):
    """Sync inbox messages from Nylas for the current user."""
    
    person_id = current_user.get("person_id")
    if not person_id:
        raise HTTPException(status_code=400, detail="User not properly authenticated")
    
    # Verify grant belongs to user
    async with get_db_async() as db:
        grant_check = await db.fetch_one("""
            SELECT cea.id
            FROM campaign_email_accounts cea
            JOIN campaigns c ON cea.campaign_id = c.campaign_id
            WHERE c.person_id = $1 AND cea.nylas_grant_id = $2
        """, person_id, grant_id)
        
        if not grant_check:
            raise HTTPException(status_code=403, detail="Access denied to this grant")
    
    try:
        from podcast_outreach.integrations.nylas import NylasAPIClient
        
        # Initialize Nylas client
        nylas_client = NylasAPIClient(grant_id=grant_id)
        
        # Get recent messages (with folder filter if specified)
        search_params = {
            "after_date": datetime.now() - timedelta(days=7),
            "limit": limit
        }
        
        # Add folder filter if specified
        if folder:
            search_params["folder"] = folder
            
        messages = nylas_client.search_messages(**search_params)
        
        # Store messages in inbox_messages table
        async with get_db_async() as db:
            for message in messages:
                query = """
                    INSERT INTO inbox_messages (
                        message_id, thread_id, grant_id,
                        subject, snippet, body_plain, body_html,
                        from_email, from_name, to_emails,
                        date, unread, folders, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
                    ON CONFLICT (message_id) DO UPDATE SET
                        unread = EXCLUDED.unread,
                        folders = EXCLUDED.folders,
                        updated_at = NOW()
                """
                
                await db.execute(
                    query,
                    message.get("id"),
                    message.get("thread_id"),
                    grant_id,
                    message.get("subject"),
                    message.get("snippet"),
                    message.get("body_plain"),
                    message.get("body"),
                    message.get("from", [{}])[0].get("email"),
                    message.get("from", [{}])[0].get("name"),
                    json.dumps([p.get("email") for p in message.get("to", [])]),
                    datetime.fromtimestamp(message.get("date", 0)),
                    message.get("unread", False),
                    json.dumps(message.get("folders", []))
                )
        
        return {
            "status": "success",
            "messages_synced": len(messages),
            "grant_id": grant_id
        }
        
    except Exception as e:
        logger.exception(f"Error syncing inbox messages: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync messages: {str(e)}"
        )