# podcast_outreach/database/queries/chatbot_conversations.py

import json
import logging
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool

logger = get_logger(__name__)

async def create_conversation(campaign_id: UUID, person_id: int, status: str = 'active', 
                            conversation_phase: str = 'introduction') -> Optional[Dict[str, Any]]:
    """Creates a new chatbot conversation."""
    query = """
    INSERT INTO chatbot_conversations 
    (campaign_id, person_id, status, conversation_phase)
    VALUES ($1, $2, $3, $4)
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id, person_id, status, conversation_phase)
            if row:
                logger.info(f"Created new conversation: {row['conversation_id']}")
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error creating conversation: {e}")
            raise

async def get_conversation_by_id(conversation_id: UUID) -> Optional[Dict[str, Any]]:
    """Fetches a conversation by ID."""
    query = "SELECT * FROM chatbot_conversations WHERE conversation_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, conversation_id)
            if not row:
                logger.debug(f"Conversation not found: {conversation_id}")
                return None
            return dict(row)
        except Exception as e:
            logger.exception(f"Error fetching conversation {conversation_id}: {e}")
            raise

async def get_conversation_with_campaign_data(conversation_id: UUID) -> Optional[Dict[str, Any]]:
    """Fetches a conversation with related campaign data."""
    query = """
    SELECT c.*, camp.campaign_keywords, camp.campaign_bio,
           p.full_name, p.email
    FROM chatbot_conversations c
    JOIN campaigns camp ON c.campaign_id = camp.campaign_id
    JOIN people p ON c.person_id = p.person_id
    WHERE c.conversation_id = $1 AND c.status = 'active';
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, conversation_id)
            if not row:
                logger.debug(f"Active conversation not found: {conversation_id}")
                return None
            return dict(row)
        except Exception as e:
            logger.exception(f"Error fetching conversation with campaign data: {e}")
            raise

async def update_conversation(conversation_id: UUID, messages: List[Dict], 
                            extracted_data: Dict, conversation_metadata: Dict, 
                            conversation_phase: str, progress: int) -> Optional[Dict[str, Any]]:
    """Updates a conversation with new messages and extracted data."""
    query = """
    UPDATE chatbot_conversations
    SET messages = $1,
        extracted_data = $2,
        conversation_metadata = $3,
        conversation_phase = $4,
        progress = $5,
        last_activity_at = CURRENT_TIMESTAMP
    WHERE conversation_id = $6
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query, 
                json.dumps(messages), 
                json.dumps(extracted_data),
                json.dumps(conversation_metadata),
                conversation_phase,
                progress,
                conversation_id
            )
            if row:
                logger.debug(f"Updated conversation {conversation_id}")
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error updating conversation {conversation_id}: {e}")
            raise

async def complete_conversation(conversation_id: UUID) -> Optional[Dict[str, Any]]:
    """Marks a conversation as completed."""
    query = """
    UPDATE chatbot_conversations
    SET status = 'completed',
        completed_at = CURRENT_TIMESTAMP
    WHERE conversation_id = $1
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, conversation_id)
            if row:
                logger.info(f"Completed conversation {conversation_id}")
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error completing conversation {conversation_id}: {e}")
            raise

async def pause_conversation(conversation_id: UUID) -> bool:
    """Pauses a conversation."""
    query = """
    UPDATE chatbot_conversations
    SET status = 'paused',
        last_activity_at = CURRENT_TIMESTAMP
    WHERE conversation_id = $1 AND status = 'active';
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, conversation_id)
            affected = int(result.split(" ")[1]) if result.startswith("UPDATE ") else 0
            if affected > 0:
                logger.info(f"Paused conversation {conversation_id}")
                return True
            return False
        except Exception as e:
            logger.exception(f"Error pausing conversation {conversation_id}: {e}")
            raise

async def resume_conversation(conversation_id: UUID) -> Optional[Dict[str, Any]]:
    """Resumes a paused conversation."""
    query = """
    UPDATE chatbot_conversations
    SET status = 'active',
        last_activity_at = CURRENT_TIMESTAMP
    WHERE conversation_id = $1 AND status = 'paused'
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, conversation_id)
            if row:
                logger.info(f"Resumed conversation {conversation_id}")
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error resuming conversation {conversation_id}: {e}")
            raise

async def get_conversations_by_campaign(campaign_id: UUID) -> List[Dict[str, Any]]:
    """Gets all conversations for a campaign."""
    query = """
    SELECT conversation_id, status, conversation_phase, progress,
           started_at, completed_at, person_id,
           jsonb_array_length(messages) as message_count
    FROM chatbot_conversations
    WHERE campaign_id = $1
    ORDER BY started_at DESC;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, campaign_id)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching conversations for campaign {campaign_id}: {e}")
            raise

async def get_conversation_summary(conversation_id: UUID) -> Optional[Dict[str, Any]]:
    """Gets a summary of conversation insights."""
    query = """
    SELECT c.*, 
           COUNT(DISTINCT ci.insight_id) as total_insights,
           array_agg(DISTINCT ci.insight_type) as insight_types
    FROM chatbot_conversations c
    LEFT JOIN conversation_insights ci ON c.conversation_id = ci.conversation_id
    WHERE c.conversation_id = $1
    GROUP BY c.conversation_id;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, conversation_id)
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error fetching conversation summary: {e}")
            raise

async def save_conversation_insights(conversation_id: UUID, insights: List[Dict[str, Any]]) -> bool:
    """Saves multiple insights for a conversation."""
    if not insights:
        return True
        
    query = """
    INSERT INTO conversation_insights 
    (conversation_id, insight_type, content, confidence_score)
    VALUES ($1, $2, $3, $4);
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # Prepare data for bulk insert
            data = [
                (conversation_id, insight['type'], json.dumps(insight['content']), 
                 insight.get('confidence', 0.8))
                for insight in insights
            ]
            
            await conn.executemany(query, data)
            logger.info(f"Saved {len(insights)} insights for conversation {conversation_id}")
            return True
        except Exception as e:
            logger.exception(f"Error saving conversation insights: {e}")
            raise

async def get_abandoned_conversations(hours_inactive: int = 24) -> List[Dict[str, Any]]:
    """Gets conversations that have been inactive for specified hours."""
    query = """
    SELECT * FROM chatbot_conversations
    WHERE status = 'active' 
    AND last_activity_at < NOW() - INTERVAL '%s hours'
    ORDER BY last_activity_at ASC;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, hours_inactive)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching abandoned conversations: {e}")
            raise

async def update_conversation_to_abandoned(conversation_id: UUID) -> bool:
    """Marks an inactive conversation as abandoned."""
    query = """
    UPDATE chatbot_conversations
    SET status = 'abandoned'
    WHERE conversation_id = $1 AND status IN ('active', 'paused');
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, conversation_id)
            affected = int(result.split(" ")[1]) if result.startswith("UPDATE ") else 0
            if affected > 0:
                logger.info(f"Marked conversation {conversation_id} as abandoned")
                return True
            return False
        except Exception as e:
            logger.exception(f"Error marking conversation as abandoned: {e}")
            raise

async def get_latest_resumable_conversation(campaign_id: UUID, person_id: int) -> Optional[Dict[str, Any]]:
    """Gets the most recent active or paused conversation for a campaign and person."""
    query = """
    SELECT * FROM chatbot_conversations
    WHERE campaign_id = $1 
    AND person_id = $2
    AND status IN ('active', 'paused')
    ORDER BY last_activity_at DESC
    LIMIT 1;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id, person_id)
            if row:
                logger.info(f"Found resumable conversation: {row['conversation_id']}")
                return dict(row)
            logger.debug(f"No resumable conversation found for campaign {campaign_id} and person {person_id}")
            return None
        except Exception as e:
            logger.exception(f"Error fetching latest resumable conversation: {e}")
            raise