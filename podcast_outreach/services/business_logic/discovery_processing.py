# podcast_outreach/services/business_logic/discovery_processing.py

import logging
import uuid
import numpy as np
import json
import re
from typing import List, Dict, Any, Optional, Tuple

from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import review_tasks as review_task_queries
from podcast_outreach.services.matches.vetting_agent import VettingAgent
from podcast_outreach.services.enrichment.enrichment_orchestrator import EnrichmentOrchestrator
from podcast_outreach.services.events.event_bus import get_event_bus, Event, EventType

logger = logging.getLogger(__name__)

async def process_discovery_workflow(
    campaign_id: uuid.UUID,
    media_id: int,
    discovery_keyword: str
) -> Dict[str, Any]:
    """
    Main discovery workflow processor. Handles the complete pipeline:
    1. Create/get discovery record
    2. Check enrichment needs
    3. Run vetting when ready
    4. Create matches when approved
    """
    result = {
        "status": "success",
        "discovery_id": None,
        "steps_completed": [],
        "next_step": None
    }
    
    try:
        # Step 1: Create or get discovery record
        discovery = await cmd_queries.create_or_get_discovery(
            campaign_id, media_id, discovery_keyword
        )
        
        if not discovery:
            result["status"] = "error"
            result["message"] = "Failed to create discovery record"
            return result
        
        result["discovery_id"] = discovery["id"]
        result["steps_completed"].append("discovery_created")
        
        # Step 2: Check if enrichment is needed
        enrichment_needed = await _check_enrichment_needs(media_id)
        
        if enrichment_needed and discovery["enrichment_status"] == "pending":
            # Trigger enrichment
            await cmd_queries.update_enrichment_status(discovery["id"], "in_progress")
            
            enrichment_orchestrator = EnrichmentOrchestrator()
            enrichment_success = await enrichment_orchestrator.enrich_media(media_id)
            
            if enrichment_success:
                await cmd_queries.update_enrichment_status(discovery["id"], "completed")
                result["steps_completed"].append("enrichment_completed")
            else:
                await cmd_queries.update_enrichment_status(
                    discovery["id"], "failed", "Enrichment process failed"
                )
                result["status"] = "error"
                result["message"] = "Enrichment failed"
                return result
        elif discovery["enrichment_status"] == "completed":
            result["steps_completed"].append("enrichment_already_completed")
        
        # Step 3: Check if ready for vetting
        if discovery["enrichment_status"] == "completed" and discovery["vetting_status"] == "pending":
            vetting_result = await _run_vetting_for_discovery(discovery)
            
            if vetting_result["success"]:
                result["steps_completed"].append("vetting_completed")
                result["vetting_score"] = vetting_result["score"]
                
                # Step 4: Create match if score is high enough
                if vetting_result["score"] >= 5.0 and not discovery["match_created"]:
                    match_result = await _create_match_and_review_task(discovery)
                    if match_result["success"]:
                        result["steps_completed"].append("match_created")
                        result["match_suggestion_id"] = match_result["match_id"]
                        result["review_task_id"] = match_result["review_task_id"]
                    else:
                        result["status"] = "partial"
                        result["message"] = "Vetting succeeded but match creation failed"
            else:
                result["status"] = "error" 
                result["message"] = f"Vetting failed: {vetting_result['error']}"
                return result
        
        # Determine next step
        if discovery["review_task_created"]:
            result["next_step"] = "awaiting_client_review"
        elif discovery["match_created"]:
            result["next_step"] = "creating_review_task"
        elif discovery["vetting_status"] == "completed":
            if discovery["vetting_score"] >= 5.0:
                result["next_step"] = "creating_match"
            else:
                result["next_step"] = "vetting_score_too_low"
        elif discovery["enrichment_status"] == "completed":
            result["next_step"] = "ready_for_vetting"
        else:
            result["next_step"] = "enrichment_in_progress"
        
        return result
        
    except Exception as e:
        logger.error(f"Error in discovery workflow for campaign {campaign_id}, media {media_id}: {e}")
        return {
            "status": "error",
            "message": f"Discovery workflow failed: {str(e)}",
            "steps_completed": result.get("steps_completed", [])
        }

async def _check_enrichment_needs(media_id: int) -> bool:
    """Check if media needs enrichment."""
    media = await media_queries.get_media_by_id_from_db(media_id)
    if not media:
        return True
    
    # Check if we have basic enrichment
    needs_enrichment = (
        media.get("last_enriched_timestamp") is None or
        media.get("quality_score") is None or
        media.get("ai_description") is None
    )
    
    # Check if we have enough analyzed episodes
    transcribed_count = await media_queries.count_transcribed_episodes_for_media(media_id)
    if transcribed_count < 3:
        needs_enrichment = True
    
    return needs_enrichment

async def _run_vetting_for_discovery(discovery: Dict[str, Any]) -> Dict[str, Any]:
    """Run vetting for a specific discovery."""
    try:
        # Get campaign and media data
        campaign_data = await campaign_queries.get_campaign_by_id(discovery["campaign_id"])
        if not campaign_data:
            return {"success": False, "error": "Campaign not found"}
        
        if not campaign_data.get("ideal_podcast_description"):
            return {"success": False, "error": "Campaign missing ideal_podcast_description"}
        
        # Run vetting
        vetting_agent = VettingAgent()
        vetting_result = await vetting_agent.vet_media_for_campaign(
            discovery["media_id"], campaign_data
        )
        
        if vetting_result.get("status") == "success":
            # Store vetting results
            await cmd_queries.update_vetting_results(
                discovery["id"],
                vetting_result["vetting_score"],
                vetting_result.get("vetting_reasoning", ""),
                vetting_result.get("vetting_criteria_met", {}),
                "completed"
            )
            
            # Emit vetting completed event for notifications
            try:
                event_bus = get_event_bus()
                media_data = await media_queries.get_media_by_id_from_db(discovery["media_id"])
                
                vetting_event = Event(
                    event_type=EventType.VETTING_COMPLETED,
                    entity_id=str(discovery["media_id"]),  # Use media_id as entity
                    entity_type="media",
                    data={
                        "campaign_id": str(discovery["campaign_id"]),
                        "media_id": discovery["media_id"],
                        "media_name": media_data.get("name", "Unknown") if media_data else "Unknown",
                        "vetting_score": vetting_result["vetting_score"],
                        "vetting_reasoning": vetting_result.get("vetting_reasoning", ""),
                        "discovery_keyword": discovery["discovery_keyword"]
                    },
                    source="discovery_workflow"
                )
                await event_bus.publish(vetting_event)
                logger.info(f"Published vetting completed event for media {discovery['media_id']}")
            except Exception as event_error:
                logger.error(f"Error publishing vetting completed event: {event_error}")
            
            return {
                "success": True,
                "score": vetting_result["vetting_score"],
                "reasoning": vetting_result.get("vetting_reasoning", "")
            }
        else:
            # Store failure
            await cmd_queries.update_vetting_results(
                discovery["id"],
                0.0,
                vetting_result.get("message", "Vetting failed"),
                {},
                "failed"
            )
            
            return {
                "success": False,
                "error": vetting_result.get("message", "Vetting failed")
            }
    
    except Exception as e:
        logger.error(f"Error vetting discovery {discovery['id']}: {e}")
        return {"success": False, "error": str(e)}

async def _create_match_and_review_task(discovery: Dict[str, Any]) -> Dict[str, Any]:
    """Create match suggestion and review task for approved discovery."""
    try:
        # First, find the best matching episode
        best_episode_id = await _find_best_matching_episode(
            discovery["campaign_id"], 
            discovery["media_id"]
        )
        
        # Create match suggestion
        match_payload = {
            "campaign_id": discovery["campaign_id"],
            "media_id": discovery["media_id"],
            "status": "pending_client_review",
            "quantitative_score": discovery["vetting_score"],
            "qualitative_assessment": discovery["vetting_reasoning"],
            "match_keywords": [discovery["discovery_keyword"]],
            "vetting_score": discovery["vetting_score"],
            "vetting_reasoning": discovery["vetting_reasoning"],
            "vetting_checklist": discovery.get("vetting_criteria_met", {}),
            "best_matching_episode_id": best_episode_id  # Include best episode
        }
        
        match_suggestion = await match_queries.create_match_suggestion_in_db(match_payload)
        if not match_suggestion:
            return {"success": False, "error": "Failed to create match suggestion"}
        
        match_id = match_suggestion["match_id"]
        
        # Mark match created in discovery
        await cmd_queries.mark_match_created(discovery["id"], match_id)
        
        # Create review task for client
        review_task_payload = {
            "task_type": "match_suggestion",
            "related_id": match_id,
            "campaign_id": discovery["campaign_id"],
            "status": "pending",
            "notes": f"Pre-vetted match ready for client review. Vetting Score: {discovery['vetting_score']}"
        }
        
        review_task = await review_task_queries.create_review_task_in_db(review_task_payload)
        if review_task:
            review_task_id = review_task.get("review_task_id")
            await cmd_queries.mark_review_task_created(discovery["id"], review_task_id)
        
        return {
            "success": True,
            "match_id": match_id,
            "review_task_id": review_task.get("review_task_id") if review_task else None
        }
        
    except Exception as e:
        logger.error(f"Error creating match and review task for discovery {discovery['id']}: {e}")
        return {"success": False, "error": str(e)}

async def run_enrichment_pipeline() -> bool:
    """Process discoveries that need enrichment."""
    try:
        discoveries = await cmd_queries.get_discoveries_needing_enrichment(limit=20)
        
        if not discoveries:
            logger.info("No discoveries need enrichment at this time")
            return True
        
        logger.info(f"Processing enrichment for {len(discoveries)} discoveries")
        
        enrichment_orchestrator = EnrichmentOrchestrator()
        
        for discovery in discoveries:
            try:
                await cmd_queries.update_enrichment_status(discovery["id"], "in_progress")
                
                success = await enrichment_orchestrator.enrich_media(discovery["media_id"])
                
                if success:
                    await cmd_queries.update_enrichment_status(discovery["id"], "completed")
                    logger.info(f"Enrichment completed for discovery {discovery['id']}")
                else:
                    await cmd_queries.update_enrichment_status(
                        discovery["id"], "failed", "Enrichment process failed"
                    )
                    logger.error(f"Enrichment failed for discovery {discovery['id']}")
                    
            except Exception as e:
                await cmd_queries.update_enrichment_status(
                    discovery["id"], "failed", str(e)
                )
                logger.error(f"Error enriching discovery {discovery['id']}: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error in enrichment pipeline: {e}")
        return False

async def run_vetting_pipeline() -> bool:
    """Process discoveries ready for vetting."""
    try:
        discoveries = await cmd_queries.get_discoveries_ready_for_vetting(limit=20)
        
        if not discoveries:
            logger.info("No discoveries ready for vetting at this time")
            return True
        
        logger.info(f"Processing vetting for {len(discoveries)} discoveries")
        
        for discovery in discoveries:
            try:
                await cmd_queries.update_enrichment_status(discovery["id"], "in_progress")
                
                vetting_result = await _run_vetting_for_discovery(discovery)
                
                if vetting_result["success"]:
                    logger.info(f"Vetting completed for discovery {discovery['id']}: score {vetting_result['score']}")
                    
                    # Auto-create matches for high scores
                    if vetting_result["score"] >= 5.0:
                        match_result = await _create_match_and_review_task(discovery)
                        if match_result["success"]:
                            logger.info(f"Match created for discovery {discovery['id']}: match {match_result['match_id']}")
                else:
                    logger.info(f"Vetting failed for discovery {discovery['id']}: {vetting_result['error']}")
                    
            except Exception as e:
                logger.error(f"Error vetting discovery {discovery['id']}: {e}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error in vetting pipeline: {e}")
        return False

def parse_embedding(embedding: Any) -> Optional[np.ndarray]:
    """Convert various embedding formats to numpy array."""
    if embedding is None:
        return None
        
    # If it's already a numpy array
    if isinstance(embedding, np.ndarray):
        return embedding
    
    # If it's a list of numbers
    if isinstance(embedding, list) and all(isinstance(x, (int, float)) for x in embedding):
        return np.array(embedding)
    
    # If it's a string representation from PostgreSQL
    if isinstance(embedding, str):
        # Handle PostgreSQL vector format '[0.1, 0.2, ...]'
        if embedding.startswith('[') and embedding.endswith(']'):
            try:
                # Remove brackets and split by comma
                values = embedding[1:-1].split(',')
                return np.array([float(v.strip()) for v in values])
            except:
                pass
        
        # Handle numpy string representation like np.str_('[-0.009, 0.015, ...]')
        if embedding.startswith("np.str_('") and embedding.endswith("')"):
            clean_embedding = embedding[9:-2]  # Remove np.str_(' and ')
            try:
                return np.array(json.loads(clean_embedding))
            except:
                # Try regex parsing
                numbers = re.findall(r'-?\d+\.?\d*(?:[eE][+-]?\d+)?', clean_embedding)
                if numbers:
                    return np.array([float(x) for x in numbers])
    
    logger.warning(f"Could not parse embedding of type {type(embedding)}")
    return None

def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors."""
    try:
        norm_v1 = np.linalg.norm(vec1)
        norm_v2 = np.linalg.norm(vec2)
        
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        
        similarity = np.dot(vec1, vec2) / (norm_v1 * norm_v2)
        return float(similarity) if not np.isnan(similarity) else 0.0
    except Exception as e:
        logger.error(f"Error calculating cosine similarity: {e}")
        return 0.0

async def _find_best_matching_episode(
    campaign_id: uuid.UUID, 
    media_id: int
) -> Optional[int]:
    """Find the best matching episode for a campaign and media pair."""
    try:
        # Get campaign embedding
        campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign or not campaign.get('embedding'):
            logger.warning(f"Campaign {campaign_id} has no embedding")
            return None
        
        campaign_embedding = parse_embedding(campaign['embedding'])
        if campaign_embedding is None:
            logger.warning(f"Could not parse campaign embedding for {campaign_id}")
            return None
        
        # Get episodes with embeddings for this media
        episodes = await episode_queries.get_episodes_for_media_with_embeddings(media_id, limit=20)
        
        if not episodes:
            logger.info(f"No episodes with embeddings found for media {media_id}")
            return None
        
        # Find best match
        best_episode_id = None
        best_similarity = -1.0
        
        for episode in episodes:
            episode_embedding_raw = episode.get('embedding')
            if episode_embedding_raw is not None:
                episode_embedding = parse_embedding(episode_embedding_raw)
                if episode_embedding is not None:
                    similarity = cosine_similarity(campaign_embedding, episode_embedding)
                    
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_episode_id = episode['episode_id']
        
        if best_episode_id and best_similarity > 0:
            logger.info(f"Found best episode {best_episode_id} for campaign {campaign_id} and media {media_id} with similarity {best_similarity:.3f}")
        
        return best_episode_id
        
    except Exception as e:
        logger.error(f"Error finding best episode: {e}", exc_info=True)
        return None