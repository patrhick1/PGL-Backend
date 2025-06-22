# podcast_outreach/api/routers/notifications.py

import logging
import json
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException
from pydantic import BaseModel
import uuid

from podcast_outreach.services.events.notification_service import get_notification_service, NotificationData
from podcast_outreach.api.dependencies import get_current_user
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Real-time Notifications"])

class NotificationHistory(BaseModel):
    """Response model for notification history"""
    notifications: list
    total: int
    has_more: bool

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="Authentication token"),
    campaign_id: Optional[str] = Query(None, description="Campaign ID to subscribe to")
):
    """
    🔗 WebSocket endpoint for real-time notifications
    
    Usage:
    ```javascript
    const ws = new WebSocket(`ws://localhost:8000/notifications/ws?token=${authToken}&campaign_id=${campaignId}`);
    
    ws.onmessage = (event) => {
        const notification = JSON.parse(event.data);
        handleNotification(notification);
    };
    ```
    
    Notification types:
    - discovery_started: Pipeline started
    - discovery_progress: New podcast discovered
    - enrichment_completed: Analysis complete
    - vetting_completed: Vetting done
    - review_ready: Ready for client review
    - match_approved: Match approved by client
    - match_rejected: Match rejected by client
    - discovery_completed: Pipeline finished
    - pipeline_progress: Progress updates
    """
    notification_service = get_notification_service()
    user_id = None
    
    try:
        # Basic authentication via token
        if not token:
            await websocket.close(code=4001, reason="Authentication token required")
            return
        
        # Get user from token (simplified - you might want more robust auth)
        try:
            # This is a simplified auth check - in production you'd validate the JWT token
            user_id = f"user_{token[-8:]}"  # Use last 8 chars of token as user ID
            logger.info(f"WebSocket auth for user {user_id}, campaign: {campaign_id}")
        except Exception as e:
            await websocket.close(code=4001, reason="Invalid authentication token")
            return
        
        # Connect to notification service
        await notification_service.websocket_manager.connect(websocket, user_id, campaign_id)
        
        # Keep connection alive and handle incoming messages
        try:
            while True:
                # Listen for client messages (like ping/pong or subscription changes)
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle different message types
                if message.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong", "timestamp": datetime.utcnow().isoformat()}))
                elif message.get("type") == "subscribe_campaign":
                    # Allow dynamic campaign subscription
                    new_campaign_id = message.get("campaign_id")
                    if new_campaign_id:
                        if user_id not in notification_service.websocket_manager.campaign_subscriptions:
                            notification_service.websocket_manager.campaign_subscriptions[user_id] = set()
                        notification_service.websocket_manager.campaign_subscriptions[user_id].add(new_campaign_id)
                        await websocket.send_text(json.dumps({
                            "type": "subscription_confirmed",
                            "campaign_id": new_campaign_id,
                            "timestamp": datetime.utcnow().isoformat()
                        }))
                
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected normally for user {user_id}")
        except Exception as e:
            logger.error(f"WebSocket error for user {user_id}: {e}")
    
    finally:
        # Clean up connection
        if user_id:
            await notification_service.websocket_manager.disconnect(websocket, user_id)

@router.get("/history", response_model=NotificationHistory)
async def get_notification_history(
    campaign_id: Optional[str] = Query(None, description="Filter by campaign ID"),
    limit: int = Query(50, description="Number of notifications to return", ge=1, le=200),
    offset: int = Query(0, description="Number of notifications to skip", ge=0),
    current_user: dict = Depends(get_current_user)
):
    """
    📜 Get notification history for a user
    
    Returns recent notifications that would have been sent via WebSocket.
    Useful for:
    - Showing notifications when user wasn't connected
    - Displaying notification history in UI
    - Debugging notification delivery
    """
    try:
        # This is a simplified implementation
        # In production, you'd store notifications in database and query them
        
        # For now, return mock data that matches the WebSocket notification format
        mock_notifications = [
            {
                "id": str(uuid.uuid4()),
                "type": "discovery_completed",
                "title": "Discovery Complete",
                "message": "🎉 Found 15 podcasts, 8 ready for review",
                "data": {
                    "campaign_id": campaign_id,
                    "total_discovered": 15,
                    "reviews_ready": 8
                },
                "timestamp": datetime.utcnow().isoformat(),
                "campaign_id": campaign_id,
                "priority": "high"
            },
            {
                "id": str(uuid.uuid4()),
                "type": "review_ready",
                "title": "New Review Ready",
                "message": "✨ Tech Talk Daily passed vetting (score: 8.5/10) - Ready for your review!",
                "data": {
                    "match_id": "123",
                    "media_name": "Tech Talk Daily",
                    "campaign_id": campaign_id,
                    "vetting_score": 8.5
                },
                "timestamp": datetime.utcnow().isoformat(),
                "campaign_id": campaign_id,
                "priority": "high"
            }
        ]
        
        # Filter by campaign if specified
        if campaign_id:
            mock_notifications = [n for n in mock_notifications if n.get("campaign_id") == campaign_id]
        
        # Apply pagination
        total = len(mock_notifications)
        paginated = mock_notifications[offset:offset + limit]
        has_more = (offset + limit) < total
        
        return NotificationHistory(
            notifications=paginated,
            total=total,
            has_more=has_more
        )
        
    except Exception as e:
        logger.exception(f"Error getting notification history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get notification history: {str(e)}")

@router.post("/test")
async def send_test_notification(
    campaign_id: str = Query(..., description="Campaign ID to send test notification to"),
    current_user: dict = Depends(get_current_user)
):
    """
    🧪 Send a test notification (for development/testing)
    
    Useful for:
    - Testing WebSocket connections
    - Verifying notification delivery
    - Frontend development
    """
    try:
        notification_service = get_notification_service()
        
        test_notification = NotificationData(
            id=str(uuid.uuid4()),
            type="test_notification",
            title="Test Notification",
            message="🧪 This is a test notification from the API",
            data={
                "campaign_id": campaign_id,
                "test": True,
                "sent_by": current_user.get("user_id", "unknown")
            },
            timestamp=datetime.utcnow(),
            campaign_id=campaign_id,
            priority="normal"
        )
        
        await notification_service.websocket_manager.send_to_campaign_subscribers(campaign_id, test_notification)
        
        return {"status": "success", "message": "Test notification sent", "notification_id": test_notification.id}
        
    except Exception as e:
        logger.exception(f"Error sending test notification: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send test notification: {str(e)}")

# Note: Using existing get_current_user dependency from dependencies.py
# No need for separate auth function here