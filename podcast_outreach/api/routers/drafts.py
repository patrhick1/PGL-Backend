# podcast_outreach/api/routers/drafts.py

from fastapi import APIRouter, HTTPException, Depends, Query, Body
from typing import List, Optional, Dict, Any
from datetime import datetime

from podcast_outreach.database.connection import get_db_async
from podcast_outreach.integrations.nylas import NylasAPIClient
from podcast_outreach.logging_config import get_logger
import json

logger = get_logger(__name__)

router = APIRouter(prefix="/drafts", tags=["Drafts"])


@router.get("/")
async def get_drafts(
    status: Optional[str] = Query(None, enum=["pending", "approved", "sent", "rejected"]),
    campaign_id: Optional[str] = None,
    pitch_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100)
):
    """Get email drafts with filters."""
    
    offset = (page - 1) * size
    
    async with get_db_async() as db:
        query = """
            SELECT 
                ed.*,
                p.subject_line as pitch_subject,
                p.pitch_state,
                c.name as campaign_name
            FROM email_drafts ed
            LEFT JOIN pitches p ON ed.pitch_id = p.pitch_id
            LEFT JOIN campaigns c ON ed.campaign_id::uuid = c.campaign_id
            WHERE 1=1
        """
        
        params = []
        
        if status:
            query += f" AND ed.status = ${len(params) + 1}"
            params.append(status)
        
        if campaign_id:
            query += f" AND ed.campaign_id = ${len(params) + 1}"
            params.append(campaign_id)
        
        if pitch_id:
            query += f" AND ed.pitch_id = ${len(params) + 1}"
            params.append(pitch_id)
        
        query += f" ORDER BY ed.created_at DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        params.extend([size, offset])
        
        drafts = await db.fetch_all(query, *params)
        
        # Count total
        count_query = query.split("ORDER BY")[0].replace("SELECT ed.*", "SELECT COUNT(*)")
        total = await db.fetch_val(count_query, *params[:-2])
    
    return {
        "drafts": [dict(d) for d in drafts] if drafts else [],
        "total": total,
        "page": page,
        "size": size,
        "pages": (total + size - 1) // size if total else 0
    }


@router.get("/{draft_id}")
async def get_draft_detail(draft_id: int):
    """Get detailed information about a specific draft."""
    
    async with get_db_async() as db:
        draft = await db.fetch_one("""
            SELECT 
                ed.*,
                p.subject_line as pitch_subject,
                p.pitch_state,
                p.media_id,
                p.nylas_thread_id,
                c.name as campaign_name,
                c.person_id,
                m.name as media_name,
                m.contact_email
            FROM email_drafts ed
            LEFT JOIN pitches p ON ed.pitch_id = p.pitch_id
            LEFT JOIN campaigns c ON ed.campaign_id::uuid = c.campaign_id
            LEFT JOIN media m ON p.media_id = m.media_id
            WHERE ed.draft_id = $1
        """, draft_id)
        
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        
        # Get thread messages if available
        thread_messages = []
        if draft.get("thread_id"):
            thread_messages = await db.fetch_all("""
                SELECT 
                    message_id, subject, snippet, 
                    from_email, from_name, date
                FROM inbox_messages
                WHERE thread_id = $1
                ORDER BY date DESC
            """, draft["thread_id"])
    
    return {
        "draft": dict(draft),
        "thread_messages": [dict(m) for m in thread_messages] if thread_messages else []
    }


@router.post("/{draft_id}/approve")
async def approve_draft(
    draft_id: int,
    edits: Optional[Dict[str, str]] = Body(None)
):
    """Approve a draft for sending."""
    
    async with get_db_async() as db:
        # Get the draft
        draft = await db.fetch_one("""
            SELECT * FROM email_drafts WHERE draft_id = $1
        """, draft_id)
        
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        
        if draft["status"] != "pending":
            raise HTTPException(
                status_code=400, 
                detail=f"Draft is already {draft['status']}"
            )
        
        # Apply edits if provided
        final_content = draft["draft_content"]
        if edits and edits.get("content"):
            final_content = edits["content"]
        
        # Update draft status
        updated_draft = await db.fetch_one("""
            UPDATE email_drafts
            SET status = 'approved',
                draft_content = $2,
                approved_at = NOW(),
                approved_by = $3
            WHERE draft_id = $1
            RETURNING *
        """, draft_id, final_content, edits.get("approved_by", "user") if edits else "user")
    
    return {
        "status": "success",
        "draft": dict(updated_draft)
    }


@router.post("/{draft_id}/reject")
async def reject_draft(
    draft_id: int,
    reason: Optional[str] = Body(None)
):
    """Reject a draft."""
    
    async with get_db_async() as db:
        # Update draft status
        updated_draft = await db.fetch_one("""
            UPDATE email_drafts
            SET status = 'rejected',
                notes = COALESCE(notes, '') || E'\\nRejected: ' || $2,
                updated_at = NOW()
            WHERE draft_id = $1
            RETURNING *
        """, draft_id, reason or "No reason provided")
        
        if not updated_draft:
            raise HTTPException(status_code=404, detail="Draft not found")
    
    return {
        "status": "success",
        "draft": dict(updated_draft)
    }


@router.post("/{draft_id}/send")
async def send_draft(
    draft_id: int,
    grant_id: str = Query(..., description="Nylas grant ID for sending")
):
    """Send an approved draft via Nylas."""
    
    async with get_db_async() as db:
        # Get the draft with related information
        draft = await db.fetch_one("""
            SELECT 
                ed.*,
                p.nylas_thread_id,
                m.contact_email,
                m.name as recipient_name
            FROM email_drafts ed
            LEFT JOIN pitches p ON ed.pitch_id = p.pitch_id
            LEFT JOIN media m ON p.media_id = m.media_id
            WHERE ed.draft_id = $1
        """, draft_id)
        
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        
        if draft["status"] != "approved":
            raise HTTPException(
                status_code=400, 
                detail=f"Draft must be approved before sending (current status: {draft['status']})"
            )
        
        try:
            # Initialize Nylas client
            nylas_client = NylasAPIClient(grant_id=grant_id)
            
            # Prepare email data
            email_data = {
                "to": [{"email": draft["contact_email"], "name": draft.get("recipient_name", "")}],
                "subject": f"Re: {draft.get('subject', 'Follow-up')}",
                "body": draft["draft_content"],
                "reply_to_message_id": draft.get("message_id"),
                "thread_id": draft.get("nylas_thread_id")
            }
            
            # Send the email
            sent_message = nylas_client.send_email(**email_data)
            
            if sent_message:
                # Update draft status
                await db.execute("""
                    UPDATE email_drafts
                    SET status = 'sent',
                        sent_at = NOW(),
                        sent_message_id = $2
                    WHERE draft_id = $1
                """, draft_id, sent_message.get("id"))
                
                # Update pitch if associated
                if draft.get("pitch_id"):
                    await db.execute("""
                        UPDATE pitches
                        SET last_followup_ts = NOW()
                        WHERE pitch_id = $1
                    """, draft["pitch_id"])
                
                return {
                    "status": "success",
                    "message": "Draft sent successfully",
                    "message_id": sent_message.get("id")
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to send email")
                
        except Exception as e:
            logger.exception(f"Error sending draft {draft_id}: {e}")
            
            # Update draft with error
            await db.execute("""
                UPDATE email_drafts
                SET notes = COALESCE(notes, '') || E'\\nSend error: ' || $2,
                    updated_at = NOW()
                WHERE draft_id = $1
            """, draft_id, str(e))
            
            raise HTTPException(
                status_code=500,
                detail=f"Failed to send draft: {str(e)}"
            )


@router.post("/generate")
async def generate_draft(
    thread_id: str,
    message_id: str,
    grant_id: str = Query(..., description="Nylas grant ID")
):
    """Generate a new draft using BookingAssistant."""
    
    try:
        from podcast_outreach.services.inbox.booking_assistant import BookingAssistantService
        from podcast_outreach.integrations.nylas import NylasAPIClient
        
        # Get message details from Nylas
        nylas_client = NylasAPIClient(grant_id=grant_id)
        message = nylas_client.get_message(message_id)
        
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Process through BookingAssistant
        booking_assistant = BookingAssistantService()
        result = await booking_assistant.process_email({
            "email_text": message.get("snippet", ""),
            "subject": message.get("subject", ""),
            "sender_email": message.get("from", [{}])[0].get("email", ""),
            "sender_name": message.get("from", [{}])[0].get("name", ""),
            "thread_id": thread_id,
            "message_id": message_id
        })
        
        if not result.get("draft"):
            raise HTTPException(
                status_code=400,
                detail="BookingAssistant did not generate a draft for this message"
            )
        
        # Store the draft
        async with get_db_async() as db:
            # Find associated pitch if exists
            pitch = await db.fetch_one("""
                SELECT pitch_id, campaign_id
                FROM pitches
                WHERE nylas_thread_id = $1
            """, thread_id)
            
            draft_id = await db.fetch_val("""
                INSERT INTO email_drafts (
                    thread_id, message_id, draft_content,
                    context, pitch_id, campaign_id,
                    status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, 'pending', NOW())
                RETURNING draft_id
            """,
                thread_id,
                message_id,
                result["draft"],
                json.dumps(result.get("relevant_threads", [])),
                pitch["pitch_id"] if pitch else None,
                str(pitch["campaign_id"]) if pitch else None
            )
        
        return {
            "status": "success",
            "draft_id": draft_id,
            "classification": result.get("classification"),
            "draft_content": result["draft"]
        }
        
    except Exception as e:
        logger.exception(f"Error generating draft: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate draft: {str(e)}"
        )


@router.get("/stats/summary")
async def get_draft_statistics(
    campaign_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=90)
):
    """Get statistics about drafts."""
    
    since_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if days > 1:
        since_date = since_date.replace(day=since_date.day - days + 1)
    
    async with get_db_async() as db:
        query = """
            SELECT 
                status,
                COUNT(*) as count,
                COUNT(CASE WHEN created_at >= $1 THEN 1 END) as recent_count
            FROM email_drafts
            WHERE 1=1
        """
        
        params = [since_date]
        
        if campaign_id:
            query += " AND campaign_id = $2"
            params.append(campaign_id)
        
        query += " GROUP BY status"
        
        stats = await db.fetch_all(query, *params)
        
        # Get approval rate
        approval_query = """
            SELECT 
                COUNT(CASE WHEN status = 'approved' THEN 1 END)::float / 
                NULLIF(COUNT(*), 0) as approval_rate,
                COUNT(CASE WHEN status = 'sent' THEN 1 END)::float / 
                NULLIF(COUNT(CASE WHEN status = 'approved' THEN 1 END), 0) as send_rate,
                AVG(EXTRACT(EPOCH FROM (approved_at - created_at))/3600) as avg_approval_time_hours
            FROM email_drafts
            WHERE created_at >= $1
        """
        
        rate_params = [since_date]
        if campaign_id:
            approval_query += " AND campaign_id = $2"
            rate_params.append(campaign_id)
        
        rates = await db.fetch_one(approval_query, *rate_params)
    
    return {
        "period_days": days,
        "campaign_id": campaign_id,
        "status_counts": {s["status"]: s["count"] for s in stats} if stats else {},
        "recent_counts": {s["status"]: s["recent_count"] for s in stats} if stats else {},
        "approval_rate": round(rates["approval_rate"] * 100, 2) if rates and rates["approval_rate"] else 0,
        "send_rate": round(rates["send_rate"] * 100, 2) if rates and rates["send_rate"] else 0,
        "avg_approval_time_hours": round(rates["avg_approval_time_hours"], 2) if rates and rates["avg_approval_time_hours"] else None
    }