"""
Match Notification Service
Sends email notifications to clients when they have match suggestions to review
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import uuid

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.services.email_service import EmailService
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.database.queries import campaigns as campaign_queries

logger = logging.getLogger(__name__)

class MatchNotificationService:
    """Service for sending match suggestion notifications to clients"""
    
    def __init__(self):
        self.email_service = EmailService()
        self.notification_threshold = 30  # Send notification at 30 matches
        
    async def check_and_send_match_notifications(self):
        """
        Check all campaigns for pending match suggestions and send notifications
        This should be called periodically (e.g., via a cron job or scheduled task)
        """
        try:
            pool = await get_db_pool()
            
            # Query to get campaigns with pending matches count
            # Check client preferences and avoid sending too frequently
            query = """
            WITH pending_matches AS (
                SELECT 
                    c.campaign_id,
                    c.campaign_name,
                    c.person_id,
                    COUNT(ms.match_id) as pending_count,
                    MAX(ms.created_at) as latest_match_date,
                    MIN(ms.created_at) as oldest_match_date
                FROM campaigns c
                JOIN match_suggestions ms ON c.campaign_id = ms.campaign_id
                WHERE ms.status = 'pending_client_review'
                AND ms.client_approved = false
                GROUP BY c.campaign_id, c.campaign_name, c.person_id
            ),
            notification_tracking AS (
                -- Track when we last sent notification for this campaign
                SELECT 
                    campaign_id,
                    MAX(sent_at) as last_notification_sent
                FROM match_notification_log
                GROUP BY campaign_id
            )
            SELECT 
                pm.*,
                p.email,
                p.full_name,
                cp.plan_type,
                cp.match_notification_enabled,
                cp.match_notification_threshold,
                nt.last_notification_sent
            FROM pending_matches pm
            JOIN people p ON pm.person_id = p.person_id
            LEFT JOIN client_profiles cp ON p.person_id = cp.person_id
            LEFT JOIN notification_tracking nt ON pm.campaign_id = nt.campaign_id
            WHERE 
                -- Check if notifications are enabled
                (cp.match_notification_enabled IS NULL OR cp.match_notification_enabled = true)
                -- Check if we've reached the threshold (default 30)
                AND pm.pending_count >= COALESCE(cp.match_notification_threshold, 30)
                -- Don't send more than once per week for the same campaign
                AND (
                    nt.last_notification_sent IS NULL 
                    OR nt.last_notification_sent < NOW() - INTERVAL '7 days'
                )
            """
            
            async with pool.acquire() as conn:
                rows = await conn.fetch(query)
                
                for row in rows:
                    await self._send_match_notification(dict(row))
                    
                logger.info(f"Processed match notifications for {len(rows)} campaigns")
                
        except Exception as e:
            logger.error(f"Error checking match notifications: {e}", exc_info=True)
    
    async def _send_match_notification(self, campaign_data: Dict[str, Any]) -> bool:
        """Send notification email for a specific campaign"""
        try:
            campaign_id = campaign_data['campaign_id']
            email = campaign_data['email']
            full_name = campaign_data['full_name']
            campaign_name = campaign_data['campaign_name']
            pending_count = campaign_data['pending_count']
            plan_type = campaign_data.get('plan_type', 'free')
            
            # Get some sample matches for the email
            sample_matches = await self._get_sample_matches(campaign_id, limit=5)
            
            # Send the email
            success = await self.email_service.send_match_notification_email(
                to_email=email,
                full_name=full_name,
                campaign_name=campaign_name,
                pending_count=pending_count,
                sample_matches=sample_matches,
                plan_type=plan_type
            )
            
            if success:
                # Log the notification
                await self._log_notification(campaign_id, campaign_data['person_id'], pending_count)
                logger.info(f"Sent match notification to {email} for campaign {campaign_id}")
            else:
                logger.error(f"Failed to send match notification to {email}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error sending match notification: {e}", exc_info=True)
            return False
    
    async def _get_sample_matches(self, campaign_id: uuid.UUID, limit: int = 5) -> List[Dict[str, Any]]:
        """Get sample match suggestions for the email"""
        query = """
        SELECT 
            ms.match_id,
            ms.vetting_score,
            ms.created_at,
            m.name as podcast_name,
            m.description,
            m.category,
            m.listen_score,
            m.audience_size
        FROM match_suggestions ms
        JOIN media m ON ms.media_id = m.media_id
        WHERE ms.campaign_id = $1
        AND ms.status = 'pending_client_review'
        AND ms.client_approved = false
        ORDER BY ms.vetting_score DESC, ms.created_at DESC
        LIMIT $2
        """
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, campaign_id, limit)
            return [dict(row) for row in rows]
    
    async def _log_notification(self, campaign_id: uuid.UUID, person_id: int, match_count: int):
        """Log that a notification was sent"""
        query = """
        INSERT INTO match_notification_log (
            campaign_id, person_id, match_count, sent_at
        ) VALUES ($1, $2, $3, $4)
        """
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                query,
                campaign_id,
                person_id,
                match_count,
                datetime.now(timezone.utc)
            )
            
            # Also update client_profiles last notification timestamp
            update_profile = """
            UPDATE client_profiles 
            SET last_match_notification_sent = $1
            WHERE person_id = $2
            """
            await conn.execute(update_profile, datetime.now(timezone.utc), person_id)
    
    async def get_notification_stats(self, campaign_id: uuid.UUID) -> Dict[str, Any]:
        """Get notification statistics for a campaign"""
        query = """
        SELECT 
            COUNT(*) as total_notifications,
            MAX(sent_at) as last_sent,
            SUM(match_count) as total_matches_notified
        FROM match_notification_log
        WHERE campaign_id = $1
        """
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, campaign_id)
            return dict(row) if row else {
                'total_notifications': 0,
                'last_sent': None,
                'total_matches_notified': 0
            }


# Add the email template method to EmailService
async def send_match_notification_email(
    self,
    to_email: str,
    full_name: str,
    campaign_name: str,
    pending_count: int,
    sample_matches: List[Dict[str, Any]],
    plan_type: str = 'free'
) -> bool:
    """Send email notification about pending match suggestions"""
    try:
        # Determine match limit based on plan
        match_limit = 50 if plan_type == 'free' else 200
        
        # Email content
        subject = f"🎯 {pending_count} New Podcast Matches Ready for Review!"
        
        # Build sample matches HTML
        matches_html = ""
        for match in sample_matches[:5]:
            score_color = '#28a745' if match['vetting_score'] >= 70 else '#ffc107' if match['vetting_score'] >= 50 else '#dc3545'
            matches_html += f"""
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                <h4 style="margin: 0 0 10px 0; color: #333;">{match['podcast_name']}</h4>
                <p style="margin: 5px 0; color: #666; font-size: 14px;">{match['description'][:150]}...</p>
                <div style="margin-top: 10px;">
                    <span style="display: inline-block; padding: 4px 8px; background-color: {score_color}; color: white; border-radius: 4px; font-size: 12px;">
                        Match Score: {match['vetting_score']:.0f}/100
                    </span>
                    {f'<span style="display: inline-block; margin-left: 10px; padding: 4px 8px; background-color: #6c757d; color: white; border-radius: 4px; font-size: 12px;">Category: {match["category"]}</span>' if match.get('category') else ''}
                </div>
            </div>
            """
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #007bff;">Great News, {full_name}! 🎉</h2>
                
                <p>We've found <strong>{pending_count} new podcast matches</strong> for your campaign "{campaign_name}" that are ready for your review!</p>
                
                <div style="background-color: #e7f3ff; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #0056b3;">📊 Your Match Summary</h3>
                    <ul style="margin: 10px 0;">
                        <li><strong>{pending_count}</strong> podcasts matched your criteria</li>
                        <li>All have been vetted and scored by our AI</li>
                        <li>Your plan allows up to <strong>{match_limit}</strong> matches {'per week' if plan_type == 'free' else 'total'}</li>
                    </ul>
                </div>
                
                <h3 style="color: #333; margin-top: 30px;">🔥 Top Matches Preview:</h3>
                {matches_html}
                
                {f'<p style="color: #666; font-style: italic;">...and {pending_count - len(sample_matches)} more waiting for you!</p>' if pending_count > len(sample_matches) else ''}
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{self.frontend_url}/campaigns/{campaign_name}/matches" style="background-color: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                        Review All Matches
                    </a>
                </div>
                
                <div style="background-color: #fff3cd; padding: 15px; border-radius: 8px; margin-top: 20px;">
                    <p style="margin: 0; color: #856404;">
                        <strong>⏰ Action Required:</strong> Please review and approve/reject these matches to move forward with your outreach campaign.
                    </p>
                </div>
                
                <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                
                <p style="color: #666; font-size: 14px;">
                    You're receiving this email because you have pending matches that need your review. 
                    {'As a free plan user, you can approve up to 50 matches per week.' if plan_type == 'free' else 'As a paid plan user, you can approve up to 200 matches.'}
                </p>
                
                <p style="color: #666; font-size: 14px;">
                    Need help? Reply to this email or contact us at {self.support_email}
                </p>
                
                <p style="margin-top: 30px;">
                    Best regards,<br>
                    The PGL Team
                </p>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        Great News, {full_name}!
        
        We've found {pending_count} new podcast matches for your campaign "{campaign_name}" that are ready for your review!
        
        Your Match Summary:
        - {pending_count} podcasts matched your criteria
        - All have been vetted and scored by our AI
        - Your plan allows up to {match_limit} matches {'per week' if plan_type == 'free' else 'total'}
        
        Top Matches:
        {chr(10).join([f"- {m['podcast_name']} (Score: {m['vetting_score']:.0f}/100)" for m in sample_matches[:5]])}
        {f"...and {pending_count - len(sample_matches)} more waiting for you!" if pending_count > len(sample_matches) else ""}
        
        Review your matches here:
        {self.frontend_url}/campaigns/{campaign_name}/matches
        
        Action Required: Please review and approve/reject these matches to move forward with your outreach campaign.
        
        You're receiving this email because you have pending matches that need your review.
        {'As a free plan user, you can approve up to 50 matches per week.' if plan_type == 'free' else 'As a paid plan user, you can approve up to 200 matches.'}
        
        Need help? Reply to this email or contact us at {self.support_email}
        
        Best regards,
        The PGL Team
        """
        
        return await self._send_email(to_email, subject, html_body, text_body)
        
    except Exception as e:
        logger.error(f"Failed to send match notification email to {to_email}: {e}")
        return False


# Monkey patch the EmailService class to add the new method
EmailService.send_match_notification_email = send_match_notification_email