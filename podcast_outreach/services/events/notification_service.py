# podcast_outreach/services/events/notification_service.py

import asyncio
import json
import logging
from typing import Dict, List, Set, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from fastapi import WebSocket
import uuid

from .event_bus import Event, EventType, get_event_bus

logger = logging.getLogger(__name__)

@dataclass
class NotificationData:
    """Structure for notifications sent to clients"""
    id: str
    type: str  # "discovery_progress", "review_ready", "pipeline_complete", etc.
    title: str
    message: str
    data: Dict[str, Any]
    timestamp: datetime
    campaign_id: Optional[str] = None
    priority: str = "normal"  # low, normal, high, urgent
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = asdict(self)
        result['timestamp'] = self.timestamp.isoformat()
        return result

class WebSocketManager:
    """Manages WebSocket connections and notification broadcasting"""
    
    def __init__(self):
        # Active connections grouped by user/campaign
        self.connections: Dict[str, Set[WebSocket]] = {}
        # Campaign subscriptions: user_id -> set of campaign_ids
        self.campaign_subscriptions: Dict[str, Set[str]] = {}
        logger.info("WebSocketManager initialized")
    
    async def connect(self, websocket: WebSocket, user_id: str, campaign_id: Optional[str] = None):
        """Connect a WebSocket for a user and optionally subscribe to campaign updates"""
        await websocket.accept()
        
        if user_id not in self.connections:
            self.connections[user_id] = set()
        self.connections[user_id].add(websocket)
        
        # Subscribe to campaign updates if specified
        if campaign_id:
            if user_id not in self.campaign_subscriptions:
                self.campaign_subscriptions[user_id] = set()
            self.campaign_subscriptions[user_id].add(campaign_id)
        
        logger.info(f"WebSocket connected for user {user_id}, campaign: {campaign_id}")
        
        # Send connection confirmation
        await self.send_to_user(user_id, NotificationData(
            id=str(uuid.uuid4()),
            type="connection_established",
            title="Connected",
            message="Real-time notifications enabled",
            data={"campaign_id": campaign_id},
            timestamp=datetime.utcnow()
        ))
    
    async def disconnect(self, websocket: WebSocket, user_id: str):
        """Disconnect a WebSocket"""
        if user_id in self.connections:
            self.connections[user_id].discard(websocket)
            if not self.connections[user_id]:
                del self.connections[user_id]
                # Clean up campaign subscriptions if no connections
                if user_id in self.campaign_subscriptions:
                    del self.campaign_subscriptions[user_id]
        
        logger.info(f"WebSocket disconnected for user {user_id}")
    
    async def send_to_user(self, user_id: str, notification: NotificationData):
        """Send notification to all connections for a specific user"""
        if user_id not in self.connections:
            return
        
        message = json.dumps(notification.to_dict())
        disconnected = set()
        
        for websocket in self.connections[user_id]:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.warning(f"Failed to send notification to user {user_id}: {e}")
                disconnected.add(websocket)
        
        # Clean up disconnected sockets
        for ws in disconnected:
            self.connections[user_id].discard(ws)
    
    async def send_to_campaign_subscribers(self, campaign_id: str, notification: NotificationData):
        """Send notification to all users subscribed to a campaign"""
        for user_id, subscriptions in self.campaign_subscriptions.items():
            if campaign_id in subscriptions:
                await self.send_to_user(user_id, notification)
    
    async def broadcast_to_all(self, notification: NotificationData):
        """Send notification to all connected users"""
        for user_id in self.connections.keys():
            await self.send_to_user(user_id, notification)

class NotificationService:
    """Service for creating and sending notifications based on system events"""
    
    def __init__(self):
        self.websocket_manager = WebSocketManager()
        self.event_bus = get_event_bus()
        self._setup_event_handlers()
        logger.info("NotificationService initialized")
    
    def _setup_event_handlers(self):
        """Subscribe to relevant events from the event bus"""
        # Discovery and pipeline events
        self.event_bus.subscribe(EventType.MEDIA_CREATED, self._handle_discovery_progress)
        self.event_bus.subscribe(EventType.ENRICHMENT_COMPLETED, self._handle_enrichment_completed)
        self.event_bus.subscribe(EventType.VETTING_COMPLETED, self._handle_vetting_completed)
        
        # Review events
        self.event_bus.subscribe(EventType.MATCH_APPROVED, self._handle_match_decision)
        self.event_bus.subscribe(EventType.MATCH_REJECTED, self._handle_match_decision)
        
        logger.info("Notification event handlers registered")
    
    async def _handle_discovery_progress(self, event: Event):
        """Handle discovery progress events"""
        try:
            campaign_id = event.data.get('campaign_id')
            if not campaign_id:
                return
            
            notification = NotificationData(
                id=str(uuid.uuid4()),
                type="discovery_progress",
                title="Discovery In Progress",
                message=f"New podcast discovered: {event.data.get('media_name', 'Unknown')}",
                data={
                    "media_id": event.entity_id,
                    "media_name": event.data.get('media_name'),
                    "campaign_id": campaign_id,
                    "step": "discovery"
                },
                timestamp=event.timestamp,
                campaign_id=str(campaign_id),
                priority="normal"
            )
            
            await self.websocket_manager.send_to_campaign_subscribers(str(campaign_id), notification)
            
        except Exception as e:
            logger.error(f"Error handling discovery progress notification: {e}")
    
    async def _handle_enrichment_completed(self, event: Event):
        """Handle enrichment completion events"""
        try:
            campaign_id = event.data.get('campaign_id')
            if not campaign_id:
                return
            
            notification = NotificationData(
                id=str(uuid.uuid4()),
                type="enrichment_completed",
                title="Podcast Analysis Complete",
                message=f"Enrichment completed for {event.data.get('media_name', 'podcast')}",
                data={
                    "media_id": event.entity_id,
                    "media_name": event.data.get('media_name'),
                    "campaign_id": campaign_id,
                    "quality_score": event.data.get('quality_score'),
                    "step": "enrichment"
                },
                timestamp=event.timestamp,
                campaign_id=str(campaign_id),
                priority="normal"
            )
            
            await self.websocket_manager.send_to_campaign_subscribers(str(campaign_id), notification)
            
        except Exception as e:
            logger.error(f"Error handling enrichment completed notification: {e}")
    
    async def _handle_vetting_completed(self, event: Event):
        """Handle vetting completion - creates review ready notifications"""
        try:
            campaign_id = event.data.get('campaign_id')
            vetting_score = event.data.get('vetting_score', 0)
            media_name = event.data.get('media_name', 'podcast')
            
            if not campaign_id:
                return
            
            # Determine notification type based on vetting score
            if vetting_score >= 50:
                notification = NotificationData(
                    id=str(uuid.uuid4()),
                    type="review_ready",
                    title="New Review Ready",
                    message=f"✨ {media_name} passed vetting (score: {vetting_score}/100) - Ready for your review!",
                    data={
                        "match_id": event.entity_id,
                        "media_name": media_name,
                        "campaign_id": campaign_id,
                        "vetting_score": vetting_score,
                        "step": "review_ready"
                    },
                    timestamp=event.timestamp,
                    campaign_id=str(campaign_id),
                    priority="high"
                )
            else:
                notification = NotificationData(
                    id=str(uuid.uuid4()),
                    type="vetting_failed",
                    title="Podcast Filtered Out",
                    message=f"{media_name} didn't meet criteria (score: {vetting_score}/100)",
                    data={
                        "match_id": event.entity_id,
                        "media_name": media_name,
                        "campaign_id": campaign_id,
                        "vetting_score": vetting_score,
                        "step": "filtered"
                    },
                    timestamp=event.timestamp,
                    campaign_id=str(campaign_id),
                    priority="low"
                )
            
            await self.websocket_manager.send_to_campaign_subscribers(str(campaign_id), notification)
            
        except Exception as e:
            logger.error(f"Error handling vetting completed notification: {e}")
    
    async def _handle_match_decision(self, event: Event):
        """Handle match approval/rejection decisions"""
        try:
            campaign_id = event.data.get('campaign_id')
            decision = "approved" if event.event_type == EventType.MATCH_APPROVED else "rejected"
            media_name = event.data.get('media_name', 'podcast')
            
            if not campaign_id:
                return
            
            title = f"Match {decision.title()}"
            message = f"✅ {media_name} {decision}" if decision == "approved" else f"❌ {media_name} {decision}"
            
            notification = NotificationData(
                id=str(uuid.uuid4()),
                type=f"match_{decision}",
                title=title,
                message=message,
                data={
                    "match_id": event.entity_id,
                    "media_name": media_name,
                    "campaign_id": campaign_id,
                    "decision": decision,
                    "notes": event.data.get('notes')
                },
                timestamp=event.timestamp,
                campaign_id=str(campaign_id),
                priority="normal"
            )
            
            await self.websocket_manager.send_to_campaign_subscribers(str(campaign_id), notification)
            
        except Exception as e:
            logger.error(f"Error handling match decision notification: {e}")
    
    async def send_discovery_started(self, campaign_id: str, estimated_completion: int):
        """Send notification when discovery pipeline starts"""
        notification = NotificationData(
            id=str(uuid.uuid4()),
            type="discovery_started",
            title="Discovery Started",
            message=f"🚀 Podcast discovery pipeline started (ETA: {estimated_completion} min)",
            data={
                "campaign_id": campaign_id,
                "estimated_completion": estimated_completion,
                "step": "started"
            },
            timestamp=datetime.utcnow(),
            campaign_id=campaign_id,
            priority="normal"
        )
        
        await self.websocket_manager.send_to_campaign_subscribers(campaign_id, notification)
    
    async def send_discovery_completed(self, campaign_id: str, total_discovered: int, reviews_ready: int):
        """Send notification when discovery pipeline completes"""
        notification = NotificationData(
            id=str(uuid.uuid4()),
            type="discovery_completed",
            title="Discovery Complete",
            message=f"🎉 Found {total_discovered} podcasts, {reviews_ready} ready for review",
            data={
                "campaign_id": campaign_id,
                "total_discovered": total_discovered,
                "reviews_ready": reviews_ready,
                "step": "completed"
            },
            timestamp=datetime.utcnow(),
            campaign_id=campaign_id,
            priority="high"
        )
        
        await self.websocket_manager.send_to_campaign_subscribers(campaign_id, notification)
    
    async def send_pipeline_progress(self, campaign_id: str, completed: int, total: int, in_progress: int):
        """Send progress update for pipeline processing"""
        percentage = (completed / total * 100) if total > 0 else 0
        
        notification = NotificationData(
            id=str(uuid.uuid4()),
            type="pipeline_progress",
            title="Processing Progress",
            message=f"📊 {completed}/{total} completed ({percentage:.0f}%)",
            data={
                "campaign_id": campaign_id,
                "completed": completed,
                "total": total,
                "in_progress": in_progress,
                "percentage": percentage,
                "step": "processing"
            },
            timestamp=datetime.utcnow(),
            campaign_id=campaign_id,
            priority="normal"
        )
        
        await self.websocket_manager.send_to_campaign_subscribers(campaign_id, notification)

# Global notification service instance
_notification_service: Optional[NotificationService] = None

def get_notification_service() -> NotificationService:
    """Get the global notification service instance"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service