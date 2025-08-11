# podcast_outreach/services/sending/throttle.py

"""
Send Throttler Service for Nylas Rate Limiting
Manages send queue and enforces rate limits per grant
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from podcast_outreach.database.connection import get_db_async
from podcast_outreach.database.queries import pitches as pitch_queries
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)


class SendThrottler:
    """
    Manages email send throttling to respect Nylas rate limits.
    Default limits: 700 emails/day, 50 emails/hour per grant.
    """
    
    # Default rate limits (can be overridden per grant)
    MAX_PER_GRANT_PER_DAY = 700
    MAX_PER_GRANT_PER_HOUR = 50
    MAX_PER_GRANT_PER_MINUTE = 10
    
    # Queue processing settings
    BATCH_SIZE = 10
    PROCESS_INTERVAL_SECONDS = 30
    
    def __init__(self):
        self._processing = False
        self._queue_processor_task = None
        logger.info(f"SendThrottler initialized with limits: {self.MAX_PER_GRANT_PER_DAY}/day, {self.MAX_PER_GRANT_PER_HOUR}/hour")
    
    async def can_send_now(self, grant_id: str) -> Tuple[bool, Optional[str]]:
        """
        Check if we can send an email now for a given grant.
        
        Args:
            grant_id: Nylas grant ID
            
        Returns:
            Tuple of (can_send, reason_if_not)
        """
        async with get_db_async() as db:
            # Use the database function to check limits
            result = await db.fetch_one(
                "SELECT can_send_for_grant($1) as can_send",
                grant_id
            )
            
            if result and result['can_send']:
                return True, None
            
            # Get specific reason why we can't send
            limits = await db.fetch_one("""
                SELECT 
                    current_daily_count,
                    current_hourly_count,
                    daily_limit,
                    hourly_limit,
                    daily_reset_at,
                    hourly_reset_at
                FROM grant_send_limits
                WHERE grant_id = $1
            """, grant_id)
            
            if not limits:
                # No record exists, we can send
                return True, None
            
            reason = None
            if limits['current_daily_count'] >= limits['daily_limit']:
                hours_until_reset = (limits['daily_reset_at'] + timedelta(days=1) - datetime.now(timezone.utc)).total_seconds() / 3600
                reason = f"Daily limit reached ({limits['daily_limit']}/day). Resets in {hours_until_reset:.1f} hours"
            elif limits['current_hourly_count'] >= limits['hourly_limit']:
                minutes_until_reset = (limits['hourly_reset_at'] + timedelta(hours=1) - datetime.now(timezone.utc)).total_seconds() / 60
                reason = f"Hourly limit reached ({limits['hourly_limit']}/hour). Resets in {minutes_until_reset:.0f} minutes"
            
            return False, reason
    
    async def queue_send(self, 
                        pitch_id: int,
                        grant_id: str,
                        priority: int = 5,
                        scheduled_for: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Queue an email for sending with rate limit management.
        
        Args:
            pitch_id: ID of the pitch to send
            grant_id: Nylas grant ID to use
            priority: Priority (1-10, 10 is highest)
            scheduled_for: When to send (None = ASAP)
            
        Returns:
            Queue result with queue_id and status
        """
        result = {
            "success": False,
            "queue_id": None,
            "message": "",
            "scheduled_for": None
        }
        
        try:
            # Check if we can send now
            can_send, reason = await self.can_send_now(grant_id)
            
            if not scheduled_for:
                if can_send:
                    # Schedule for immediate send
                    scheduled_for = datetime.now(timezone.utc)
                else:
                    # Calculate next available send time
                    scheduled_for = await self.get_next_send_time(grant_id)
            
            # Add to queue
            queue_id = str(uuid4())
            
            async with get_db_async() as db:
                await db.execute("""
                    INSERT INTO send_queue (
                        queue_id, pitch_id, grant_id, scheduled_for,
                        priority, status, created_at
                    )
                    VALUES ($1, $2, $3, $4, $5, 'pending', NOW())
                """, queue_id, pitch_id, grant_id, scheduled_for, priority)
                
                # Update pitch status
                await db.execute("""
                    UPDATE pitches 
                    SET send_status = 'queued',
                        scheduled_send_at = $2
                    WHERE pitch_id = $1
                """, pitch_id, scheduled_for)
            
            result["success"] = True
            result["queue_id"] = queue_id
            result["scheduled_for"] = scheduled_for
            result["message"] = f"Queued for sending at {scheduled_for.isoformat()}"
            
            if reason:
                result["message"] += f" (Rate limited: {reason})"
            
            logger.info(f"Queued pitch {pitch_id} for grant {grant_id} at {scheduled_for}")
            
        except Exception as e:
            logger.exception(f"Error queuing send: {e}")
            result["message"] = f"Failed to queue: {str(e)}"
        
        return result
    
    async def get_next_send_time(self, grant_id: str) -> datetime:
        """
        Calculate the next available time to send for a grant.
        
        Args:
            grant_id: Nylas grant ID
            
        Returns:
            Next available send time
        """
        async with get_db_async() as db:
            # Get current limits
            limits = await db.fetch_one("""
                SELECT 
                    current_daily_count,
                    current_hourly_count,
                    daily_limit,
                    hourly_limit,
                    daily_reset_at,
                    hourly_reset_at
                FROM grant_send_limits
                WHERE grant_id = $1
            """, grant_id)
            
            if not limits:
                # No limits recorded, can send now
                return datetime.now(timezone.utc)
            
            now = datetime.now(timezone.utc)
            
            # Check which limit is hit
            if limits['current_daily_count'] >= limits['daily_limit']:
                # Daily limit hit, return tomorrow
                return limits['daily_reset_at'] + timedelta(days=1, seconds=5)
            elif limits['current_hourly_count'] >= limits['hourly_limit']:
                # Hourly limit hit, return next hour
                return limits['hourly_reset_at'] + timedelta(hours=1, seconds=5)
            else:
                # No limits hit, can send now
                return now
    
    async def process_queue(self) -> Dict[str, Any]:
        """
        Process pending items in the send queue.
        
        Returns:
            Summary of processed items
        """
        summary = {
            "processed": 0,
            "failed": 0,
            "rate_limited": 0,
            "details": []
        }
        
        async with get_db_async() as db:
            # Get pending items that are ready to send
            pending_items = await db.fetch_all("""
                SELECT 
                    sq.queue_id,
                    sq.pitch_id,
                    sq.grant_id,
                    sq.priority,
                    sq.attempts,
                    p.pitch_gen_id
                FROM send_queue sq
                JOIN pitches p ON sq.pitch_id = p.pitch_id
                WHERE sq.status = 'pending'
                AND sq.scheduled_for <= NOW()
                ORDER BY sq.priority DESC, sq.scheduled_for ASC
                LIMIT $1
            """, self.BATCH_SIZE)
            
            for item in pending_items:
                # Check rate limits
                can_send, reason = await self.can_send_now(item['grant_id'])
                
                if not can_send:
                    # Rate limited, reschedule
                    next_time = await self.get_next_send_time(item['grant_id'])
                    
                    await db.execute("""
                        UPDATE send_queue 
                        SET scheduled_for = $2,
                            updated_at = NOW()
                        WHERE queue_id = $1
                    """, item['queue_id'], next_time)
                    
                    summary["rate_limited"] += 1
                    summary["details"].append({
                        "queue_id": item['queue_id'],
                        "status": "rate_limited",
                        "rescheduled_for": next_time.isoformat()
                    })
                    continue
                
                # Process the send
                try:
                    # Mark as processing
                    await db.execute("""
                        UPDATE send_queue 
                        SET status = 'processing',
                            last_attempt_at = NOW(),
                            attempts = attempts + 1
                        WHERE queue_id = $1
                    """, item['queue_id'])
                    
                    # Import sender service (avoid circular import)
                    from podcast_outreach.services.pitches.sender_v2 import pitch_sender_service
                    
                    # Send the pitch
                    send_result = await pitch_sender_service.send_pitch(item['pitch_gen_id'])
                    
                    if send_result.get("success"):
                        # Mark as sent
                        await db.execute("""
                            UPDATE send_queue 
                            SET status = 'sent',
                                updated_at = NOW()
                            WHERE queue_id = $1
                        """, item['queue_id'])
                        
                        # Increment grant send count
                        await db.execute(
                            "SELECT increment_grant_send_count($1)",
                            item['grant_id']
                        )
                        
                        summary["processed"] += 1
                        summary["details"].append({
                            "queue_id": item['queue_id'],
                            "status": "sent",
                            "message": send_result.get("message")
                        })
                    else:
                        # Send failed
                        error_msg = send_result.get("message", "Unknown error")
                        
                        # Check if we should retry
                        if item['attempts'] < 3:
                            # Reschedule with exponential backoff
                            retry_delay = 2 ** item['attempts']  # 2, 4, 8 minutes
                            next_attempt = datetime.now(timezone.utc) + timedelta(minutes=retry_delay)
                            
                            await db.execute("""
                                UPDATE send_queue 
                                SET status = 'pending',
                                    scheduled_for = $2,
                                    error_message = $3,
                                    updated_at = NOW()
                                WHERE queue_id = $1
                            """, item['queue_id'], next_attempt, error_msg)
                            
                            summary["details"].append({
                                "queue_id": item['queue_id'],
                                "status": "retry_scheduled",
                                "retry_at": next_attempt.isoformat(),
                                "attempt": item['attempts'] + 1
                            })
                        else:
                            # Max retries exceeded
                            await db.execute("""
                                UPDATE send_queue 
                                SET status = 'failed',
                                    error_message = $2,
                                    updated_at = NOW()
                                WHERE queue_id = $1
                            """, item['queue_id'], error_msg)
                            
                            # Update pitch status
                            await db.execute("""
                                UPDATE pitches 
                                SET send_status = 'failed'
                                WHERE pitch_id = $1
                            """, item['pitch_id'])
                            
                            summary["failed"] += 1
                            summary["details"].append({
                                "queue_id": item['queue_id'],
                                "status": "failed",
                                "error": error_msg
                            })
                
                except Exception as e:
                    logger.exception(f"Error processing queue item {item['queue_id']}: {e}")
                    
                    # Mark as failed
                    await db.execute("""
                        UPDATE send_queue 
                        SET status = 'failed',
                            error_message = $2,
                            updated_at = NOW()
                        WHERE queue_id = $1
                    """, item['queue_id'], str(e))
                    
                    summary["failed"] += 1
                    summary["details"].append({
                        "queue_id": item['queue_id'],
                        "status": "error",
                        "error": str(e)
                    })
        
        if summary["processed"] > 0 or summary["failed"] > 0 or summary["rate_limited"] > 0:
            logger.info(f"Queue processed: {summary['processed']} sent, {summary['failed']} failed, {summary['rate_limited']} rate limited")
        
        return summary
    
    async def start_queue_processor(self):
        """Start the background queue processor."""
        if self._processing:
            logger.warning("Queue processor already running")
            return
        
        self._processing = True
        self._queue_processor_task = asyncio.create_task(self._process_queue_loop())
        logger.info("Queue processor started")
    
    async def stop_queue_processor(self):
        """Stop the background queue processor."""
        self._processing = False
        if self._queue_processor_task:
            await self._queue_processor_task
            self._queue_processor_task = None
        logger.info("Queue processor stopped")
    
    async def _process_queue_loop(self):
        """Background loop to process the queue."""
        while self._processing:
            try:
                await self.process_queue()
                await asyncio.sleep(self.PROCESS_INTERVAL_SECONDS)
            except Exception as e:
                logger.exception(f"Error in queue processor loop: {e}")
                await asyncio.sleep(self.PROCESS_INTERVAL_SECONDS)
    
    async def get_queue_status(self, grant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get current queue status and statistics.
        
        Args:
            grant_id: Optional grant ID to filter by
            
        Returns:
            Queue statistics
        """
        async with get_db_async() as db:
            if grant_id:
                stats = await db.fetch_one("""
                    SELECT 
                        COUNT(*) FILTER (WHERE status = 'pending') as pending,
                        COUNT(*) FILTER (WHERE status = 'processing') as processing,
                        COUNT(*) FILTER (WHERE status = 'sent') as sent,
                        COUNT(*) FILTER (WHERE status = 'failed') as failed,
                        MIN(scheduled_for) FILTER (WHERE status = 'pending') as next_send_time
                    FROM send_queue
                    WHERE grant_id = $1
                    AND created_at > NOW() - INTERVAL '24 hours'
                """, grant_id)
                
                limits = await db.fetch_one("""
                    SELECT 
                        current_daily_count,
                        current_hourly_count,
                        daily_limit,
                        hourly_limit
                    FROM grant_send_limits
                    WHERE grant_id = $1
                """, grant_id)
            else:
                stats = await db.fetch_one("""
                    SELECT 
                        COUNT(*) FILTER (WHERE status = 'pending') as pending,
                        COUNT(*) FILTER (WHERE status = 'processing') as processing,
                        COUNT(*) FILTER (WHERE status = 'sent') as sent,
                        COUNT(*) FILTER (WHERE status = 'failed') as failed,
                        MIN(scheduled_for) FILTER (WHERE status = 'pending') as next_send_time
                    FROM send_queue
                    WHERE created_at > NOW() - INTERVAL '24 hours'
                """)
                limits = None
            
            return {
                "queue_stats": {
                    "pending": stats['pending'] if stats else 0,
                    "processing": stats['processing'] if stats else 0,
                    "sent": stats['sent'] if stats else 0,
                    "failed": stats['failed'] if stats else 0,
                    "next_send_time": stats['next_send_time'].isoformat() if stats and stats['next_send_time'] else None
                },
                "rate_limits": {
                    "daily": f"{limits['current_daily_count']}/{limits['daily_limit']}" if limits else "N/A",
                    "hourly": f"{limits['current_hourly_count']}/{limits['hourly_limit']}" if limits else "N/A"
                } if limits else None,
                "processor_running": self._processing
            }


# Singleton instance
send_throttler = SendThrottler()