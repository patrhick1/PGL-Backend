# podcast_outreach/services/events/event_bus.py

import asyncio
import logging
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

class EventType(Enum):
    # Discovery events
    MEDIA_CREATED = "media_created"
    EPISODES_FETCHED = "episodes_fetched"
    
    # Enrichment events
    ENRICHMENT_COMPLETED = "enrichment_completed"
    QUALITY_SCORE_UPDATED = "quality_score_updated"
    
    # Transcription events
    EPISODE_TRANSCRIBED = "episode_transcribed"
    TRANSCRIPTION_FAILED = "transcription_failed"
    
    # Matching events
    MATCH_CREATED = "match_created"
    VETTING_COMPLETED = "vetting_completed"
    
    # Review events
    MATCH_APPROVED = "match_approved"
    MATCH_REJECTED = "match_rejected"

@dataclass
class Event:
    event_type: EventType
    entity_id: str  # Could be media_id, episode_id, match_id, etc.
    entity_type: str  # "media", "episode", "match", "campaign"
    data: Dict[str, Any]
    timestamp: datetime = None
    source: str = "system"
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

class EventBus:
    """
    Central event bus for coordinating workflow steps through event-driven architecture.
    Allows decoupled communication between different parts of the system.
    """
    
    def __init__(self):
        self.handlers: Dict[EventType, List[Callable]] = {}
        self.event_history: List[Event] = []
        self.max_history = 1000  # Keep last 1000 events for debugging
        logger.info("EventBus initialized")
    
    def subscribe(self, event_type: EventType, handler: Callable[[Event], Any]):
        """Subscribe a handler to an event type"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)
        logger.info(f"Registered handler for event type: {event_type.value}")
    
    def unsubscribe(self, event_type: EventType, handler: Callable[[Event], Any]):
        """Unsubscribe a handler from an event type"""
        if event_type in self.handlers:
            try:
                self.handlers[event_type].remove(handler)
                logger.info(f"Unregistered handler for event type: {event_type.value}")
            except ValueError:
                logger.warning(f"Handler not found for event type: {event_type.value}")
    
    async def publish(self, event: Event):
        """Publish an event to all subscribed handlers"""
        logger.info(f"Publishing event: {event.event_type.value} for {event.entity_type} {event.entity_id}")
        
        # Add to history
        self.event_history.append(event)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)
        
        # Get handlers for this event type
        handlers = self.handlers.get(event.event_type, [])
        
        if not handlers:
            logger.debug(f"No handlers registered for event type: {event.event_type.value}")
            return
        
        # Execute all handlers concurrently
        tasks = []
        for handler in handlers:
            try:
                # Get the current event loop safely
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    logger.warning("No running event loop, executing handlers sequentially")
                    # If no event loop, execute sequentially
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        await asyncio.to_thread(handler, event)
                    continue
                
                if asyncio.iscoroutinefunction(handler):
                    task = loop.create_task(handler(event))
                else:
                    # Wrap sync handlers in asyncio
                    task = loop.create_task(asyncio.to_thread(handler, event))
                tasks.append(task)
            except Exception as e:
                logger.error(f"Error creating task for handler {handler.__name__}: {e}")
        
        # Wait for all handlers to complete, but don't let one failure stop others
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    handler_name = handlers[i].__name__ if i < len(handlers) else "unknown"
                    logger.error(f"Handler {handler_name} failed for event {event.event_type.value}: {result}")
    
    def get_event_history(self, limit: int = 100, event_type: Optional[EventType] = None) -> List[Event]:
        """Get recent event history, optionally filtered by event type"""
        events = self.event_history
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return events[-limit:]
    
    def get_events_for_entity(self, entity_id: str, entity_type: str = None) -> List[Event]:
        """Get all events for a specific entity"""
        events = [e for e in self.event_history if e.entity_id == entity_id]
        if entity_type:
            events = [e for e in events if e.entity_type == entity_type]
        return events

# Global event bus instance
_event_bus: Optional[EventBus] = None

def get_event_bus() -> EventBus:
    """Get the global event bus instance"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus

def initialize_event_handlers():
    """Initialize default event handlers for workflow orchestration"""
    bus = get_event_bus()
    
    # Register workflow orchestration handlers
    bus.subscribe(EventType.MEDIA_CREATED, handle_media_created)
    bus.subscribe(EventType.EPISODES_FETCHED, handle_episodes_fetched)
    bus.subscribe(EventType.ENRICHMENT_COMPLETED, handle_enrichment_completed)
    bus.subscribe(EventType.EPISODE_TRANSCRIBED, handle_episode_transcribed)
    bus.subscribe(EventType.MATCH_CREATED, handle_match_created)
    bus.subscribe(EventType.VETTING_COMPLETED, handle_vetting_completed)
    
    logger.info("Default event handlers initialized")

# Event Handlers for Workflow Orchestration

async def handle_media_created(event: Event):
    """Handle new media creation - trigger enrichment"""
    try:
        media_id = int(event.entity_id)
        logger.info(f"Handling media created event for media_id: {media_id}")
        
        # Trigger enrichment for new media
        from podcast_outreach.services.tasks.manager import task_manager
        import time
        
        task_id = f"event_enrichment_{media_id}_{int(time.time())}"
        task_manager.start_task(task_id, f"event_driven_enrichment_media_{media_id}")
        task_manager.run_enrichment_pipeline(task_id, media_id=media_id)
        
        logger.info(f"Triggered enrichment for new media_id: {media_id}")
        
    except Exception as e:
        logger.error(f"Error handling media created event: {e}", exc_info=True)

async def handle_episodes_fetched(event: Event):
    """Handle episodes fetched - potentially trigger transcription prioritization"""
    try:
        media_id = int(event.entity_id)
        episode_count = event.data.get('episode_count', 0)
        
        logger.info(f"Handling episodes fetched event for media_id: {media_id}, episodes: {episode_count}")
        
        # Could trigger immediate transcription for high-priority media
        # For now, just log the event
        
    except Exception as e:
        logger.error(f"Error handling episodes fetched event: {e}", exc_info=True)

async def handle_enrichment_completed(event: Event):
    """Handle enrichment completion - trigger vetting for related matches"""
    try:
        media_id = int(event.entity_id)
        logger.info(f"Handling enrichment completed event for media_id: {media_id}")
        
        # The enrichment process already triggers vetting via trigger_vetting_for_media
        # This handler could be used for additional downstream actions
        
        # Publish a quality score update event if enrichment included quality scoring
        if event.data.get('quality_score_updated'):
            quality_event = Event(
                event_type=EventType.QUALITY_SCORE_UPDATED,
                entity_id=str(media_id),
                entity_type="media",
                data={"quality_score": event.data.get('quality_score')},
                source="enrichment_handler"
            )
            await get_event_bus().publish(quality_event)
        
    except Exception as e:
        logger.error(f"Error handling enrichment completed event: {e}", exc_info=True)

async def handle_episode_transcribed(event: Event):
    """Handle episode transcription completion - trigger match creation"""
    try:
        episode_id = int(event.entity_id)
        media_id = event.data.get('media_id')
        
        logger.info(f"Handling episode transcribed event for episode_id: {episode_id}, media_id: {media_id}")
        
        # Trigger match creation for campaigns
        if media_id:
            from podcast_outreach.services.tasks.manager import task_manager
            import time
            
            task_id = f"event_match_creation_{media_id}_{int(time.time())}"
            task_manager.start_task(task_id, f"event_driven_match_creation_media_{media_id}")
            # This would need a new method in TaskManager for media-specific match creation
            logger.info(f"Would trigger match creation for media_id: {media_id} after episode transcription")
        
    except Exception as e:
        logger.error(f"Error handling episode transcribed event: {e}", exc_info=True)

async def handle_match_created(event: Event):
    """Handle match creation - potentially trigger immediate vetting for high-score matches"""
    try:
        match_id = int(event.entity_id)
        match_score = event.data.get('match_score', 0)
        
        logger.info(f"Handling match created event for match_id: {match_id}, score: {match_score}")
        
        # For high-scoring matches, we could trigger immediate vetting
        if match_score > 0.8:  # High confidence matches
            logger.info(f"High-score match {match_id} created - immediate vetting recommended")
        
    except Exception as e:
        logger.error(f"Error handling match created event: {e}", exc_info=True)

async def handle_vetting_completed(event: Event):
    """Handle vetting completion - create human review task"""
    try:
        match_id = int(event.entity_id)
        vetting_score = event.data.get('vetting_score', 0)
        
        logger.info(f"Handling vetting completed event for match_id: {match_id}, vetting_score: {vetting_score}")
        
        # The vetting orchestrator already creates review tasks
        # This handler could be used for notifications or other downstream actions
        
    except Exception as e:
        logger.error(f"Error handling vetting completed event: {e}", exc_info=True)