# podcast_outreach/api/routers/chatbot.py

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, UUID4
from typing import Optional, List, Dict, Any
import json
import logging

from podcast_outreach.api.dependencies import get_current_user
from podcast_outreach.services.chatbot.conversation_engine import ConversationEngine
from podcast_outreach.database.queries import chatbot_conversations as conv_queries
from podcast_outreach.services.ai.tracker import tracker as ai_tracker
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/campaigns/{campaign_id}/chatbot", tags=["Chatbot"])

# Request/Response Models
class ChatbotStartRequest(BaseModel):
    pass

class ChatbotMessageRequest(BaseModel):
    conversation_id: UUID4
    message: str

class ChatbotCompleteRequest(BaseModel):
    conversation_id: UUID4

class ChatbotResumeRequest(BaseModel):
    conversation_id: Optional[UUID4] = None

class ChatbotStartResponse(BaseModel):
    conversation_id: str
    initial_message: str
    estimated_time: str

class ChatbotMessageResponse(BaseModel):
    bot_message: str
    extracted_data: Dict[str, Any]
    progress: int
    phase: str
    keywords_found: int
    quick_replies: Optional[List[str]] = []

class ConversationSummaryResponse(BaseModel):
    conversation_id: str
    status: str
    progress: int
    phase: str
    messages_count: int
    keywords_summary: Dict[str, int]
    stories_count: int
    achievements_count: int
    total_insights: int
    insight_types: Optional[List[str]]
    extracted_data: Dict[str, Any]

class ConversationHistoryItem(BaseModel):
    conversation_id: str
    status: str
    phase: str
    progress: int
    message_count: int
    started_at: Optional[str]
    completed_at: Optional[str]

# Initialize conversation engine as singleton
conversation_engine = None

def get_conversation_engine() -> ConversationEngine:
    global conversation_engine
    if conversation_engine is None:
        conversation_engine = ConversationEngine()
    return conversation_engine

@router.post("/start", response_model=ChatbotStartResponse, 
             summary="Start Chatbot Session",
             description="Initialize a new chatbot conversation session for questionnaire")
async def start_chatbot_session(
    campaign_id: UUID4,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Initialize a new chatbot conversation session"""
    try:
        engine = get_conversation_engine()
        
        # For clients, use their person_id. For admin/staff, might need different logic
        person_id = user.get("person_id")
        if not person_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User profile incomplete - missing person_id"
            )
        
        result = await engine.create_conversation(
            str(campaign_id), 
            person_id
        )
        
        # Analytics tracking removed - ai_tracker is for AI usage, not general events
        
        return ChatbotStartResponse(**result)
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception(f"Error starting chatbot session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to start conversation: {str(e)}"
        )

@router.post("/message", response_model=ChatbotMessageResponse,
             summary="Send Chatbot Message",
             description="Process a user message and return bot response")
async def send_chatbot_message(
    campaign_id: UUID4,
    body: ChatbotMessageRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Process a user message and return bot response"""
    try:
        # Verify user owns this conversation
        conv = await conv_queries.get_conversation_by_id(body.conversation_id)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        if conv['person_id'] != user.get("person_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        if str(conv['campaign_id']) != str(campaign_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Campaign ID mismatch"
            )
        
        engine = get_conversation_engine()
        response = await engine.process_message(
            str(body.conversation_id), 
            body.message
        )
        
        # Message analytics tracking removed - ai_tracker is for AI usage, not general events
        
        return ChatbotMessageResponse(**response)
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception(f"Error processing chatbot message: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}"
        )

@router.get("/summary", response_model=ConversationSummaryResponse,
            summary="Get Conversation Summary",
            description="Get summary of extracted data from conversation")
async def get_conversation_summary(
    campaign_id: UUID4,
    conversation_id: UUID4,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get summary of extracted data from conversation"""
    try:
        # Get conversation with insights
        conv_summary = await conv_queries.get_conversation_summary(conversation_id)
        if not conv_summary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        # Verify ownership
        if conv_summary['person_id'] != user.get("person_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Parse extracted data
        extracted_data = json.loads(conv_summary['extracted_data'])
        messages = json.loads(conv_summary['messages'])
        
        # Get keyword counts by type
        keywords_summary = {}
        if 'keywords' in extracted_data:
            for ktype, keywords in extracted_data['keywords'].items():
                keywords_summary[ktype] = len(keywords)
        
        return ConversationSummaryResponse(
            conversation_id=str(conversation_id),
            status=conv_summary['status'],
            progress=conv_summary['progress'],
            phase=conv_summary['conversation_phase'],
            messages_count=len(messages),
            keywords_summary=keywords_summary,
            stories_count=len(extracted_data.get('stories', [])),
            achievements_count=len(extracted_data.get('achievements', [])),
            total_insights=conv_summary['total_insights'] or 0,
            insight_types=conv_summary['insight_types'],
            extracted_data=extracted_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting conversation summary: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get summary: {str(e)}"
        )

@router.post("/complete", 
             summary="Complete Chatbot Session",
             description="Complete the chatbot session and trigger processing")
async def complete_chatbot_session(
    campaign_id: UUID4,
    body: ChatbotCompleteRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Complete the chatbot session and trigger processing"""
    try:
        # Verify ownership
        conv = await conv_queries.get_conversation_by_id(body.conversation_id)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        if conv['person_id'] != user.get("person_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        engine = get_conversation_engine()
        result = await engine.complete_conversation(str(body.conversation_id))
        
        # Completion analytics tracking removed - ai_tracker is for AI usage, not general events
        
        # Trigger angle generation if needed
        # This could be done via event bus or task queue
        # await trigger_angle_generation(campaign_id)
        
        return result
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.exception(f"Error completing chatbot session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete conversation: {str(e)}"
        )

@router.get("/history", response_model=List[ConversationHistoryItem],
            summary="Get Conversation History",
            description="Get all conversations for a campaign")
async def get_conversation_history(
    campaign_id: UUID4,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get all conversations for a campaign"""
    try:
        conversations = await conv_queries.get_conversations_by_campaign(campaign_id)
        logger.info(f"Found {len(conversations)} total conversations for campaign {campaign_id}")
        
        # Filter by person_id for clients
        if user.get("role") == "client":
            person_id = user.get("person_id")
            filtered_conversations = [
                conv for conv in conversations 
                if conv.get('person_id') == person_id
            ]
            logger.info(f"After filtering for person_id {person_id}, found {len(filtered_conversations)} conversations")
            conversations = filtered_conversations
        
        return [
            ConversationHistoryItem(
                conversation_id=str(conv['conversation_id']),
                status=conv['status'],
                phase=conv['conversation_phase'],
                progress=conv['progress'],
                message_count=conv['message_count'],
                started_at=conv['started_at'].isoformat() if conv['started_at'] else None,
                completed_at=conv['completed_at'].isoformat() if conv['completed_at'] else None
            )
            for conv in conversations
        ]
        
    except Exception as e:
        logger.exception(f"Error getting conversation history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get history: {str(e)}"
        )

@router.post("/resume",
             summary="Resume Conversation",
             description="Resume the latest active or paused conversation for the campaign")
async def resume_conversation(
    campaign_id: UUID4,
    request: Request,
    body: ChatbotResumeRequest = ChatbotResumeRequest(),
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Resume a conversation - either a specific one or the latest resumable one"""
    try:
        person_id = user.get("person_id")
        if not person_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User profile incomplete - missing person_id"
            )
        
        # If no conversation_id provided, find the latest resumable one
        conversation_id = body.conversation_id
        if not conversation_id:
            conv = await conv_queries.get_latest_resumable_conversation(campaign_id, person_id)
            if not conv:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active or paused conversations found for this campaign"
                )
            conversation_id = conv['conversation_id']
        else:
            # Verify ownership if specific conversation_id provided
            conv = await conv_queries.get_conversation_by_id(conversation_id)
            if not conv:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Conversation not found"
                )
            
            if conv['person_id'] != person_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
            
            if str(conv['campaign_id']) != str(campaign_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Conversation does not belong to this campaign"
                )
        
        # If conversation is already active, just return it
        if conv['status'] == 'active':
            messages = json.loads(conv['messages'])
            last_bot_message = None
            for msg in reversed(messages):
                if msg['type'] == 'bot':
                    last_bot_message = msg['content']
                    break
            
            return {
                "conversation_id": str(conversation_id),
                "status": "active",
                "already_active": True,
                "last_message": last_bot_message or "Let's continue where we left off...",
                "message_count": len(messages),
                "phase": conv['conversation_phase'],
                "progress": conv['progress'],
                "messages": messages,
                "extracted_data": json.loads(conv.get('extracted_data', '{}'))
            }
        
        # Resume if paused
        if conv['status'] == 'paused':
            result = await conv_queries.resume_conversation(conversation_id)
            if not result:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to resume conversation"
                )
            conv = result
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot resume conversation with status: {conv['status']}"
            )
        
        # Get last bot message
        messages = json.loads(conv['messages'])
        last_bot_message = None
        for msg in reversed(messages):
            if msg['type'] == 'bot':
                last_bot_message = msg['content']
                break
        
        return {
            "conversation_id": str(conversation_id),
            "status": "active",
            "already_active": False,
            "last_message": last_bot_message or "Let's continue where we left off...",
            "message_count": len(messages),
            "phase": conv['conversation_phase'],
            "progress": conv['progress'],
            "messages": messages,
            "extracted_data": json.loads(conv.get('extracted_data', '{}'))
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error resuming conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume conversation: {str(e)}"
        )

@router.post("/pause",
             summary="Pause Conversation",
             description="Pause an active conversation")
async def pause_conversation(
    campaign_id: UUID4,
    conversation_id: UUID4,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Pause an active conversation"""
    try:
        # Verify ownership
        conv = await conv_queries.get_conversation_by_id(conversation_id)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )
        
        if conv['person_id'] != user.get("person_id"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Pause conversation
        success = await conv_queries.pause_conversation(conversation_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to pause conversation"
            )
        
        return {
            "conversation_id": str(conversation_id),
            "status": "paused",
            "message": "Conversation paused. You can resume anytime."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error pausing conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause conversation: {str(e)}"
        )

@router.get("/latest",
            summary="Get Latest Conversation",
            description="Get the latest active or paused conversation for the campaign")
async def get_latest_conversation(
    campaign_id: UUID4,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user)
):
    """Get the latest resumable conversation for a campaign"""
    try:
        person_id = user.get("person_id")
        if not person_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User profile incomplete - missing person_id"
            )
        
        # Find the latest resumable conversation
        conv = await conv_queries.get_latest_resumable_conversation(campaign_id, person_id)
        if not conv:
            return {
                "found": False,
                "message": "No active or paused conversations found for this campaign"
            }
        
        # Get last bot message
        messages = json.loads(conv['messages'])
        last_bot_message = None
        for msg in reversed(messages):
            if msg['type'] == 'bot':
                last_bot_message = msg['content']
                break
        
        return {
            "found": True,
            "conversation_id": str(conv['conversation_id']),
            "status": conv['status'],
            "phase": conv['conversation_phase'],
            "progress": conv['progress'],
            "message_count": len(messages),
            "last_message": last_bot_message,
            "last_activity_at": conv['last_activity_at'].isoformat() if conv['last_activity_at'] else None,
            "messages": messages,
            "extracted_data": json.loads(conv.get('extracted_data', '{}'))
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting latest conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get latest conversation: {str(e)}"
        )