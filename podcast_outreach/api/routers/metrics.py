# podcast_outreach/api/routers/metrics.py

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from podcast_outreach.database.connection import get_db_async
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["Metrics & Analytics"])


@router.get("/pitches/{pitch_id}/events")
async def get_pitch_event_timeline(pitch_id: str):
    """Get chronological event timeline for a pitch."""
    
    async with get_db_async() as db:
        # Get pitch details
        pitch = await db.fetch_one("""
            SELECT 
                p.*,
                m.name as media_name,
                c.name as campaign_name
            FROM pitches p
            LEFT JOIN media m ON p.media_id = m.media_id
            LEFT JOIN campaigns c ON p.campaign_id = c.campaign_id
            WHERE p.pitch_id = $1
        """, pitch_id)
        
        if not pitch:
            raise HTTPException(status_code=404, detail="Pitch not found")
        
        # Get all events for this pitch
        events = await db.fetch_all("""
            SELECT 
                event_id,
                event_type,
                timestamp,
                payload_json,
                ip_address,
                user_agent,
                link_url
            FROM message_events
            WHERE pitch_id = $1
            ORDER BY timestamp ASC
        """, pitch_id)
        
        # Format events for timeline
        timeline = []
        for event in events:
            timeline_entry = {
                "event_id": str(event["event_id"]),
                "type": event["event_type"],
                "timestamp": event["timestamp"].isoformat() if event["timestamp"] else None,
                "metadata": {}
            }
            
            # Add type-specific metadata
            if event["event_type"] == "opened":
                timeline_entry["metadata"]["ip_address"] = str(event["ip_address"]) if event["ip_address"] else None
                timeline_entry["metadata"]["user_agent"] = event["user_agent"]
                # Calculate confidence based on user agent
                if event["user_agent"] and "Mozilla" in event["user_agent"]:
                    timeline_entry["confidence"] = "high"
                else:
                    timeline_entry["confidence"] = "medium"
                    
            elif event["event_type"] == "clicked":
                timeline_entry["metadata"]["link_url"] = event["link_url"]
                timeline_entry["confidence"] = "high"  # Clicks are high confidence
                
            elif event["event_type"] == "bounced":
                payload = event["payload_json"] or {}
                timeline_entry["metadata"]["bounce_type"] = payload.get("bounce_type", "unknown")
                timeline_entry["metadata"]["reason"] = payload.get("reason", "")
                
            timeline.append(timeline_entry)
        
        # Add creation and send events from pitch data
        base_timeline = []
        
        if pitch["created_at"]:
            base_timeline.append({
                "type": "created",
                "timestamp": pitch["created_at"].isoformat(),
                "metadata": {}
            })
            
        if pitch["send_ts"]:
            base_timeline.append({
                "type": "sent",
                "timestamp": pitch["send_ts"].isoformat(),
                "metadata": {
                    "provider": pitch.get("email_provider", "unknown"),
                    "message_id": pitch.get("nylas_message_id")
                }
            })
            
        if pitch["opened_ts"]:
            base_timeline.append({
                "type": "first_opened",
                "timestamp": pitch["opened_ts"].isoformat(),
                "metadata": {"total_opens": pitch.get("open_count", 1)}
            })
            
        if pitch["clicked_ts"]:
            base_timeline.append({
                "type": "first_clicked",
                "timestamp": pitch["clicked_ts"].isoformat(),
                "metadata": {"total_clicks": pitch.get("click_count", 1)}
            })
            
        if pitch["reply_ts"]:
            base_timeline.append({
                "type": "replied",
                "timestamp": pitch["reply_ts"].isoformat(),
                "metadata": {}
            })
        
        # Merge and sort all events
        all_events = base_timeline + timeline
        all_events.sort(key=lambda x: x["timestamp"] if x["timestamp"] else "")
        
        return {
            "pitch_id": str(pitch_id),
            "media_name": pitch["media_name"],
            "campaign_name": pitch["campaign_name"],
            "subject": pitch.get("subject_line"),
            "current_state": pitch.get("pitch_state"),
            "total_events": len(all_events),
            "timeline": all_events
        }


@router.get("/campaigns/{campaign_id}/metrics")
async def get_campaign_metrics(
    campaign_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
):
    """Get comprehensive metrics for a campaign."""
    
    if not start_date:
        start_date = datetime.now() - timedelta(days=30)
    if not end_date:
        end_date = datetime.now()
    
    async with get_db_async() as db:
        # Verify campaign exists
        campaign = await db.fetch_one("""
            SELECT * FROM campaigns WHERE campaign_id = $1
        """, campaign_id)
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        # Get pitch statistics
        pitch_stats = await db.fetch_one("""
            SELECT 
                COUNT(*) as total_pitches,
                COUNT(CASE WHEN pitch_state = 'sent' THEN 1 END) as sent,
                COUNT(CASE WHEN pitch_state = 'opened' THEN 1 END) as opened,
                COUNT(CASE WHEN pitch_state = 'clicked' THEN 1 END) as clicked,
                COUNT(CASE WHEN pitch_state = 'replied' THEN 1 END) as replied,
                COUNT(CASE WHEN pitch_state = 'bounced' THEN 1 END) as bounced,
                COUNT(placement_id) as placements_created,
                AVG(open_count) as avg_opens_per_email,
                AVG(click_count) as avg_clicks_per_email,
                COUNT(CASE WHEN bounce_type = 'hard' THEN 1 END) as hard_bounces,
                COUNT(CASE WHEN bounce_type = 'soft' THEN 1 END) as soft_bounces
            FROM pitches
            WHERE campaign_id = $1
            AND created_at BETWEEN $2 AND $3
        """, campaign_id, start_date, end_date)
        
        # Get email classifications breakdown
        classifications = await db.fetch_all("""
            SELECT 
                ec.classification,
                COUNT(*) as count,
                AVG(ec.confidence_score) as avg_confidence
            FROM email_classifications ec
            JOIN pitches p ON ec.thread_id = p.nylas_thread_id
            WHERE p.campaign_id = $1
            AND ec.processed_at BETWEEN $2 AND $3
            GROUP BY ec.classification
            ORDER BY count DESC
        """, campaign_id, start_date, end_date)
        
        # Get daily breakdown for chart
        daily_stats = await db.fetch_all("""
            SELECT 
                DATE(send_ts) as date,
                COUNT(*) as sent,
                COUNT(CASE WHEN opened_ts IS NOT NULL THEN 1 END) as opened,
                COUNT(CASE WHEN clicked_ts IS NOT NULL THEN 1 END) as clicked,
                COUNT(CASE WHEN reply_ts IS NOT NULL THEN 1 END) as replied
            FROM pitches
            WHERE campaign_id = $1
            AND send_ts BETWEEN $2 AND $3
            GROUP BY DATE(send_ts)
            ORDER BY date ASC
        """, campaign_id, start_date, end_date)
        
        # Calculate conversion rates
        total = pitch_stats["total_pitches"] or 1  # Avoid division by zero
        sent = pitch_stats["sent"] or 0
        
        metrics = {
            "campaign_id": str(campaign_id),
            "campaign_name": campaign["name"],
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "summary": {
                "total_pitches": pitch_stats["total_pitches"],
                "total_sent": sent,
                "total_opened": pitch_stats["opened"],
                "total_clicked": pitch_stats["clicked"],
                "total_replied": pitch_stats["replied"],
                "total_bounced": pitch_stats["bounced"],
                "placements_created": pitch_stats["placements_created"]
            },
            "rates": {
                "send_rate": round((sent / total) * 100, 2) if total > 0 else 0,
                "open_rate": round((pitch_stats["opened"] / sent) * 100, 2) if sent > 0 else 0,
                "click_rate": round((pitch_stats["clicked"] / sent) * 100, 2) if sent > 0 else 0,
                "reply_rate": round((pitch_stats["replied"] / sent) * 100, 2) if sent > 0 else 0,
                "bounce_rate": round((pitch_stats["bounced"] / sent) * 100, 2) if sent > 0 else 0,
                "booking_rate": round((pitch_stats["placements_created"] / sent) * 100, 2) if sent > 0 else 0
            },
            "engagement": {
                "avg_opens_per_email": round(pitch_stats["avg_opens_per_email"] or 0, 2),
                "avg_clicks_per_email": round(pitch_stats["avg_clicks_per_email"] or 0, 2)
            },
            "deliverability": {
                "hard_bounces": pitch_stats["hard_bounces"],
                "soft_bounces": pitch_stats["soft_bounces"],
                "total_bounces": pitch_stats["bounced"]
            },
            "classifications": [
                {
                    "type": cls["classification"],
                    "count": cls["count"],
                    "avg_confidence": round(cls["avg_confidence"], 2) if cls["avg_confidence"] else 0
                }
                for cls in classifications
            ] if classifications else [],
            "daily_breakdown": [
                {
                    "date": day["date"].isoformat() if day["date"] else None,
                    "sent": day["sent"],
                    "opened": day["opened"],
                    "clicked": day["clicked"],
                    "replied": day["replied"]
                }
                for day in daily_stats
            ] if daily_stats else []
        }
        
        return metrics


@router.get("/campaigns/{campaign_id}/deliverability")
async def get_campaign_deliverability(campaign_id: str):
    """Get deliverability metrics for a campaign."""
    
    async with get_db_async() as db:
        # Get bounce analysis
        bounce_analysis = await db.fetch_all("""
            SELECT 
                bounce_type,
                bounce_reason,
                COUNT(*) as count
            FROM pitches
            WHERE campaign_id = $1
            AND bounce_type IS NOT NULL
            GROUP BY bounce_type, bounce_reason
            ORDER BY count DESC
        """, campaign_id)
        
        # Get domain-level stats
        domain_stats = await db.fetch_all("""
            SELECT 
                SUBSTRING(m.contact_email FROM '@(.+)') as domain,
                COUNT(p.pitch_id) as total_sent,
                COUNT(CASE WHEN p.bounce_type IS NOT NULL THEN 1 END) as bounced,
                COUNT(CASE WHEN p.opened_ts IS NOT NULL THEN 1 END) as opened
            FROM pitches p
            JOIN media m ON p.media_id = m.media_id
            WHERE p.campaign_id = $1
            GROUP BY domain
            ORDER BY total_sent DESC
            LIMIT 20
        """, campaign_id)
        
        # Get provider performance if using multiple
        provider_stats = await db.fetch_all("""
            SELECT 
                email_provider,
                COUNT(*) as total,
                COUNT(CASE WHEN pitch_state = 'sent' THEN 1 END) as sent,
                COUNT(CASE WHEN pitch_state = 'bounced' THEN 1 END) as bounced,
                AVG(CASE WHEN send_ts IS NOT NULL 
                    THEN EXTRACT(EPOCH FROM (send_ts - created_at)) 
                END) as avg_send_time_seconds
            FROM pitches
            WHERE campaign_id = $1
            GROUP BY email_provider
        """, campaign_id)
        
        return {
            "campaign_id": str(campaign_id),
            "bounce_analysis": [
                {
                    "type": b["bounce_type"],
                    "reason": b["bounce_reason"],
                    "count": b["count"]
                }
                for b in bounce_analysis
            ] if bounce_analysis else [],
            "domain_performance": [
                {
                    "domain": d["domain"],
                    "total_sent": d["total_sent"],
                    "bounced": d["bounced"],
                    "opened": d["opened"],
                    "bounce_rate": round((d["bounced"] / d["total_sent"]) * 100, 2) if d["total_sent"] > 0 else 0,
                    "open_rate": round((d["opened"] / d["total_sent"]) * 100, 2) if d["total_sent"] > 0 else 0
                }
                for d in domain_stats
            ] if domain_stats else [],
            "provider_performance": [
                {
                    "provider": p["email_provider"] or "unknown",
                    "total": p["total"],
                    "sent": p["sent"],
                    "bounced": p["bounced"],
                    "success_rate": round((p["sent"] / p["total"]) * 100, 2) if p["total"] > 0 else 0,
                    "avg_send_time": round(p["avg_send_time_seconds"] or 0, 2)
                }
                for p in provider_stats
            ] if provider_stats else []
        }


@router.get("/grants/{grant_id}/health")
async def get_grant_health(grant_id: str):
    """Monitor health and usage of a Nylas grant."""
    
    async with get_db_async() as db:
        # Get current usage stats
        usage_stats = await db.fetch_one("""
            SELECT 
                COUNT(CASE WHEN send_ts > NOW() - INTERVAL '24 hours' THEN 1 END) as daily_sent,
                COUNT(CASE WHEN send_ts > NOW() - INTERVAL '1 hour' THEN 1 END) as hourly_sent,
                COUNT(CASE WHEN send_ts > NOW() - INTERVAL '1 minute' THEN 1 END) as minute_sent,
                COUNT(CASE WHEN bounce_type = 'hard' 
                    AND send_ts > NOW() - INTERVAL '7 days' THEN 1 END) as recent_hard_bounces,
                AVG(CASE WHEN send_ts > NOW() - INTERVAL '24 hours' 
                    THEN open_count END) as avg_opens_today
            FROM pitches
            WHERE nylas_grant_id = $1
        """, grant_id)
        
        # Get queue status
        queue_status = await db.fetch_one("""
            SELECT 
                COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'processing' THEN 1 END) as processing,
                COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
                MIN(CASE WHEN status = 'pending' THEN scheduled_for END) as next_send_time
            FROM send_queue
            WHERE grant_id = $1
        """, grant_id)
        
        # Get recent errors
        recent_errors = await db.fetch_all("""
            SELECT 
                created_at,
                error_message
            FROM send_queue
            WHERE grant_id = $1
            AND status = 'failed'
            AND created_at > NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 10
        """, grant_id)
        
        # Calculate health score
        daily_limit = int(os.getenv("EMAIL_SEND_RATE_LIMIT", "700"))
        hourly_limit = int(os.getenv("EMAIL_SEND_HOURLY_LIMIT", "50"))
        
        daily_usage = (usage_stats["daily_sent"] / daily_limit) * 100 if daily_limit > 0 else 0
        hourly_usage = (usage_stats["hourly_sent"] / hourly_limit) * 100 if hourly_limit > 0 else 0
        
        # Determine health status
        if daily_usage > 90 or hourly_usage > 90:
            health_status = "critical"
            health_message = "Approaching rate limits"
        elif usage_stats["recent_hard_bounces"] > 5:
            health_status = "warning"
            health_message = "High bounce rate detected"
        elif queue_status and queue_status["failed"] > 10:
            health_status = "warning"
            health_message = "Multiple failed sends in queue"
        else:
            health_status = "healthy"
            health_message = "All systems operational"
        
        return {
            "grant_id": grant_id,
            "health_status": health_status,
            "health_message": health_message,
            "usage": {
                "daily": {
                    "sent": usage_stats["daily_sent"],
                    "limit": daily_limit,
                    "percentage": round(daily_usage, 2)
                },
                "hourly": {
                    "sent": usage_stats["hourly_sent"],
                    "limit": hourly_limit,
                    "percentage": round(hourly_usage, 2)
                },
                "minute": {
                    "sent": usage_stats["minute_sent"],
                    "limit": 10,
                    "percentage": round((usage_stats["minute_sent"] / 10) * 100, 2)
                }
            },
            "quality_metrics": {
                "recent_hard_bounces": usage_stats["recent_hard_bounces"],
                "avg_opens_today": round(usage_stats["avg_opens_today"] or 0, 2)
            },
            "queue": {
                "pending": queue_status["pending"] if queue_status else 0,
                "processing": queue_status["processing"] if queue_status else 0,
                "failed": queue_status["failed"] if queue_status else 0,
                "next_send_time": queue_status["next_send_time"].isoformat() if queue_status and queue_status["next_send_time"] else None
            },
            "recent_errors": [
                {
                    "timestamp": err["created_at"].isoformat(),
                    "error": err["error_message"]
                }
                for err in recent_errors
            ] if recent_errors else [],
            "recommendations": []
        }


# Import os for environment variables
import os