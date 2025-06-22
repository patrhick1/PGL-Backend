# podcast_outreach/services/matches/match_creation.py
import asyncio
import logging
import uuid
import json
import re
from typing import Dict, Any, Optional, List, Tuple
import numpy as np
from datetime import timezone, datetime

# Database queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import review_tasks as review_task_queries

logger = logging.getLogger(__name__)

# Constants for scoring
WEIGHT_EMBEDDING = 0.7
WEIGHT_KEYWORD = 0.3
MIN_SCORE_FOR_VETTING = 0.5 # Threshold to create a review task

def convert_embedding_to_list(embedding) -> Optional[List[float]]:
    """Convert various embedding formats to a list of floats."""
    if embedding is None:
        return None
        
    # If it's already a list of numbers, return as is
    if isinstance(embedding, list) and all(isinstance(x, (int, float)) for x in embedding):
        return [float(x) for x in embedding]
    
    # If it's a numpy array, convert to list
    if isinstance(embedding, np.ndarray):
        return embedding.tolist()
    
    # If it's a string representation from PostgreSQL
    if isinstance(embedding, str):
        # Handle numpy string representation like np.str_('[-0.009, 0.015, ...]')
        if embedding.startswith("np.str_('") and embedding.endswith("')"):
            clean_embedding = embedding[9:-2]  # Remove np.str_(' and ')
            try:
                # Parse as JSON array
                return json.loads(clean_embedding)
            except json.JSONDecodeError:
                # Fall back to regex parsing
                numbers = re.findall(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?', clean_embedding)
                return [float(x) for x in numbers] if numbers else None
        
        # Handle direct JSON array string
        if embedding.startswith('[') and embedding.endswith(']'):
            try:
                return json.loads(embedding)
            except json.JSONDecodeError:
                # Fall back to regex parsing
                numbers = re.findall(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?', embedding)
                return [float(x) for x in numbers] if numbers else None
        
        # Handle comma-separated values
        if ',' in embedding:
            try:
                return [float(x.strip()) for x in embedding.split(',')]
            except ValueError:
                return None
    
    # If all else fails, try to extract numbers with regex
    if isinstance(embedding, str):
        numbers = re.findall(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?', str(embedding))
        return [float(x) for x in numbers] if numbers else None
    
    return None

def cosine_similarity(vec1, vec2) -> float:
    """Computes cosine similarity between two vectors."""
    # Convert embeddings to lists if needed
    vec1_list = convert_embedding_to_list(vec1)
    vec2_list = convert_embedding_to_list(vec2)
    
    if not vec1_list or not vec2_list:
        return 0.0
    
    try:
        v1 = np.array(vec1_list)
        v2 = np.array(vec2_list)
        norm_v1 = np.linalg.norm(v1)
        norm_v2 = np.linalg.norm(v2)
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        
        similarity = np.dot(v1, v2) / (norm_v1 * norm_v2)
        return float(similarity) if not np.isnan(similarity) else 0.0
    except Exception as e:
        logger.error(f"Error computing cosine similarity: {e}", exc_info=True)
        return 0.0

def jaccard_similarity(list1: List[str], list2: List[str]) -> float:
    """Computes Jaccard similarity between two lists of keywords."""
    if not list1 or not list2:
        return 0.0
    set1 = set(list1)
    set2 = set(list2)
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0


class MatchCreationService:
    """
    Service to create and score match suggestions between campaigns and media episodes.
    """

    async def create_and_score_match_suggestions_for_campaign(
        self, 
        campaign_id: uuid.UUID, 
        media_records: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Processes one campaign against multiple media records to create/update match suggestions.
        """
        processed_matches = []
        campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign or not campaign.get("embedding") or not campaign.get("campaign_keywords"):
            logger.warning(f"Campaign {campaign_id} has no embedding or keywords. Skipping match creation.")
            return []

        for media_data in media_records:
            media_id = media_data.get("media_id")
            if not media_id:
                continue
            
            match_result = await self._score_single_campaign_media_pair(campaign, media_data)
            if match_result:
                processed_matches.append(match_result)
        return processed_matches

    async def create_and_score_match_suggestions_for_media(
        self, 
        media_id: int, 
        campaign_records: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Processes one media record (and its episodes) against multiple campaigns.
        """
        processed_matches = []
        media_data = await media_queries.get_media_by_id_from_db(media_id)
        if not media_data:
            logger.warning(f"Media {media_id} not found. Skipping match creation.")
            return []

        episodes_with_embeddings = await episode_queries.get_episodes_for_media_with_embeddings(media_id, limit=10)
        if not episodes_with_embeddings:
            logger.info(f"Media {media_id} has no episodes with embeddings. Skipping match creation against campaigns.")
            return []
        
        media_data["episodes_with_embeddings"] = episodes_with_embeddings

        for campaign in campaign_records:
            if not campaign or not campaign.get("embedding") or not campaign.get("campaign_keywords"):
                logger.debug(f"Campaign {campaign.get('campaign_id')} missing embedding/keywords for media {media_id}. Skipping.")
                continue
            
            match_result = await self._score_single_campaign_media_pair(campaign, media_data)
            if match_result:
                processed_matches.append(match_result)
        return processed_matches

    async def _score_single_campaign_media_pair(
        self, 
        campaign: Dict[str, Any], 
        media: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        campaign_id = campaign["campaign_id"]
        media_id = media["media_id"]
        
        campaign_embedding = campaign.get("embedding")
        campaign_keywords = campaign.get("campaign_keywords", [])

        if not campaign_embedding:
            return None

        episodes_to_score = media.get("episodes_with_embeddings")
        if episodes_to_score is None:
            episodes_to_score = await episode_queries.get_episodes_for_media_with_embeddings(media_id, limit=5)

        if not episodes_to_score:
            return None

        best_embedding_score = -1.0
        best_matching_episode_id = None
        best_episode_keywords = []
        
        for episode in episodes_to_score:
            episode_embedding = episode.get("embedding")
            if episode_embedding:
                sim = cosine_similarity(campaign_embedding, episode_embedding)
                if sim > best_embedding_score:
                    best_embedding_score = sim
                    best_matching_episode_id = episode.get("episode_id")
                    best_episode_keywords = episode.get("episode_keywords", [])

        keyword_score = 0.0
        overlapping_keywords = []
        if campaign_keywords and best_episode_keywords:
            keyword_score = jaccard_similarity(campaign_keywords, best_episode_keywords)
            overlapping_keywords = list(set(campaign_keywords).intersection(set(best_episode_keywords)))
        
        final_quantitative_score = (best_embedding_score * WEIGHT_EMBEDDING) + (keyword_score * WEIGHT_KEYWORD)
        
        ai_reasoning = f"Quantitative match score: {final_quantitative_score:.3f}. Content similarity (max {best_embedding_score:.3f}). Keyword Jaccard score ({keyword_score:.3f})."

        match_suggestion_payload = {
            "campaign_id": campaign_id,
            "media_id": media_id,
            "match_score": final_quantitative_score,
            "matched_keywords": overlapping_keywords,
            "ai_reasoning": ai_reasoning,
            "status": "pending_vetting", # New initial status
            "best_matching_episode_id": best_matching_episode_id
        }
        
        existing_suggestion = await match_queries.get_match_suggestion_by_campaign_and_media_ids(campaign_id, media_id)
        
        if existing_suggestion:
            # Update if score changed significantly or if it was previously rejected and can be re-evaluated
            existing_score = existing_suggestion.get('match_score', 0)
            # Convert Decimal to float for arithmetic operations
            existing_score = float(existing_score) if existing_score is not None else 0.0
            significant_change = abs(existing_score - final_quantitative_score) > 0.01
            if significant_change:
                updated_suggestion = await match_queries.update_match_suggestion_in_db(existing_suggestion["match_id"], match_suggestion_payload)
                logger.info(f"Updated match suggestion for campaign {campaign_id} and media {media_id}. New score: {final_quantitative_score:.3f}")
                existing_suggestion = updated_suggestion
            else:
                logger.info(f"Match suggestion for campaign {campaign_id} and media {media_id} exists with similar score. Skipping.")
                return existing_suggestion
        else:
            new_suggestion = await match_queries.create_match_suggestion_in_db(match_suggestion_payload)
            if not new_suggestion:
                logger.error(f"Failed to create match suggestion for campaign {campaign_id} and media {media_id}.")
                return None
            logger.info(f"Created new match suggestion for campaign {campaign_id} and media {media_id}. Score: {final_quantitative_score:.3f}")
            existing_suggestion = new_suggestion
            
            # Publish match created event for new matches
            try:
                from podcast_outreach.services.events.event_bus import get_event_bus, Event, EventType
                event_bus = get_event_bus()
                event = Event(
                    event_type=EventType.MATCH_CREATED,
                    entity_id=str(new_suggestion['match_id']),
                    entity_type="match",
                    data={
                        "campaign_id": str(campaign_id),
                        "media_id": media_id,
                        "match_score": final_quantitative_score,
                        "matched_keywords": overlapping_keywords
                    },
                    source="match_creation"
                )
                await event_bus.publish(event)
                logger.info(f"Published MATCH_CREATED event for match {new_suggestion['match_id']}")
            except Exception as e:
                logger.error(f"Error publishing match created event: {e}")

        # *** NEW: TRIGGER VETTING TASK ***
        if existing_suggestion and final_quantitative_score >= MIN_SCORE_FOR_VETTING:
            match_id = existing_suggestion['match_id']
            # Check if a vetting task already exists and is pending
            already_pending_task = await review_task_queries.get_pending_review_task_by_related_id_and_type(
                related_id=match_id,
                task_type="match_suggestion_vetting"
            )
            if not already_pending_task:
                vetting_task_payload = {
                    "task_type": "match_suggestion_vetting",
                    "related_id": match_id,
                    "campaign_id": campaign_id,
                    "status": "pending",
                    "notes": f"Vetting required for match with quantitative score: {final_quantitative_score:.3f}"
                }
                await review_task_queries.create_review_task_in_db(vetting_task_payload)
                logger.info(f"Created 'match_suggestion_vetting' task for match_id {match_id}.")
            else:
                logger.info(f"A 'match_suggestion_vetting' task already exists for match_id {match_id}.")
        
        return existing_suggestion