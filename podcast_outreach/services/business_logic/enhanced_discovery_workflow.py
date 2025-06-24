"""
Enhanced Discovery Workflow

This enhanced workflow includes:
1. Host name confidence verification
2. Batch transcription for improved performance
3. Better error handling for failed URLs
4. Cross-reference validation for host names
5. Smart batching based on episode duration
6. Exponential backoff for temporary failures
"""

import logging
import uuid
import asyncio
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import review_tasks as review_task_queries
from podcast_outreach.services.matches.enhanced_vetting_agent import EnhancedVettingAgent
from podcast_outreach.services.enrichment.enrichment_orchestrator import EnrichmentOrchestrator
from podcast_outreach.services.enrichment.host_confidence_verifier import HostConfidenceVerifier
from podcast_outreach.services.media.batch_transcriber import BatchTranscriptionService
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.services.enrichment.data_merger import DataMergerService
from podcast_outreach.services.enrichment.quality_score import QualityService
from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService
from podcast_outreach.services.enrichment.enrichment_agent import EnrichmentAgent
from podcast_outreach.services.media.analyzer import MediaAnalyzerService
from podcast_outreach.services.events.event_bus import get_event_bus, Event, EventType

logger = logging.getLogger(__name__)

class EnhancedDiscoveryWorkflow:
    """
    Enhanced discovery workflow with improved host verification and batch transcription.
    """
    
    def __init__(self):
        # Initialize all required services
        self.vetting_agent = EnhancedVettingAgent()
        self.batch_transcriber = BatchTranscriptionService()
        self.host_verifier = HostConfidenceVerifier()
        self.media_analyzer = MediaAnalyzerService()
        
        # Initialize enrichment orchestrator with dependencies
        gemini_service = GeminiService()
        social_discovery_service = SocialDiscoveryService()
        data_merger = DataMergerService()
        enrichment_agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger)
        quality_service = QualityService()
        self.enrichment_orchestrator = EnrichmentOrchestrator(
            enrichment_agent, quality_service, social_discovery_service
        )
        
        logger.info("EnhancedDiscoveryWorkflow initialized with all services")
    
    async def process_discovery(
        self,
        campaign_id: uuid.UUID,
        media_id: int,
        discovery_keyword: str
    ) -> Dict[str, Any]:
        """
        Process a single discovery through the enhanced workflow.
        """
        result = {
            "status": "success",
            "discovery_id": None,
            "steps_completed": [],
            "errors": [],
            "improvements": []  # Track improvements made
        }
        
        try:
            # Step 1: Create/get discovery record
            discovery = await cmd_queries.create_or_get_discovery(
                campaign_id, media_id, discovery_keyword
            )
            
            if not discovery:
                result["status"] = "error"
                result["errors"].append("Failed to create discovery record")
                return result
            
            result["discovery_id"] = discovery["id"]
            result["steps_completed"].append("discovery_tracked")
            
            # Step 2: Check and run enrichment if needed
            if discovery["enrichment_status"] != "completed":
                enrichment_result = await self._run_enhanced_enrichment_step(discovery)
                result["steps_completed"].extend(enrichment_result["steps_completed"])
                result["improvements"].extend(enrichment_result.get("improvements", []))
                if enrichment_result["status"] != "success":
                    result["errors"].extend(enrichment_result.get("errors", []))
                    if enrichment_result["status"] == "error":
                        result["status"] = "partial_failure"
                        return result
            
            # Step 3: Verify host names with confidence scoring
            host_verification_result = await self._verify_host_names(media_id)
            if host_verification_result:
                result["steps_completed"].append("host_verification")
                result["improvements"].append({
                    "type": "host_verification",
                    "details": host_verification_result
                })
            
            # Step 4: Check if vetting is needed and ready
            if discovery["enrichment_status"] == "completed" and discovery["vetting_status"] == "pending":
                media = await media_queries.get_media_by_id_from_db(media_id)
                if media and media.get("ai_description"):
                    vetting_result = await self._run_vetting_step(discovery)
                    result["steps_completed"].extend(vetting_result["steps_completed"])
                    if vetting_result["status"] != "success":
                        result["errors"].extend(vetting_result.get("errors", []))
                        result["status"] = "partial_failure"
                    else:
                        result["vetting_score"] = vetting_result.get("vetting_score", 0)
                else:
                    result["steps_completed"].append("waiting_for_ai_description")
            
            # Step 5: Create match if vetting score is high enough
            if discovery["vetting_status"] == "completed" and discovery["vetting_score"] >= 5.0:
                if not discovery["match_created"]:
                    match_result = await self._create_match_and_review_task(discovery)
                    result["steps_completed"].extend(match_result["steps_completed"])
                    if match_result["status"] == "success":
                        result["match_id"] = match_result.get("match_id")
                        result["review_task_id"] = match_result.get("review_task_id")
                    else:
                        result["errors"].extend(match_result.get("errors", []))
                else:
                    result["steps_completed"].append("match_already_created")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in enhanced discovery workflow: {e}", exc_info=True)
            result["status"] = "error"
            result["errors"].append(str(e))
            return result
    
    async def _run_enhanced_enrichment_step(self, discovery: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhanced enrichment step with batch transcription and better error handling.
        """
        result = {
            "status": "success",
            "steps_completed": [],
            "errors": [],
            "improvements": []
        }
        
        try:
            # Update status to in_progress
            await cmd_queries.update_enrichment_status(discovery["id"], "in_progress")
            
            media_id = discovery["media_id"]
            
            # Step 1: Basic enrichment (social data, etc)
            logger.info(f"Running basic enrichment for media {media_id}")
            enriched_profile = await self.enrichment_orchestrator.enrichment_agent.enrich_podcast_profile(
                {"media_id": media_id}
            )
            
            if enriched_profile:
                # Update media with enriched data
                update_data = enriched_profile.model_dump(exclude_none=True)
                # Clean up data as in original enrichment_processing.py
                fields_to_remove = ['unified_profile_id', 'recent_episodes', 'quality_score']
                for field in fields_to_remove:
                    if field in update_data:
                        del update_data[field]
                if 'primary_email' in update_data:
                    update_data['contact_email'] = update_data.pop('primary_email')
                
                # Convert HttpUrl objects to strings
                from pydantic import HttpUrl
                for key, value in update_data.items():
                    if isinstance(value, HttpUrl):
                        update_data[key] = str(value)
                    
                await media_queries.update_media_enrichment_data(media_id, update_data)
                result["steps_completed"].append("social_enrichment_completed")
            
            # Step 2: Enhanced batch transcription
            episodes = await episode_queries.get_episodes_for_media(media_id, limit=10)
            
            # Filter episodes needing transcription and check URL status
            episodes_to_transcribe = []
            for ep in episodes:
                if not ep.get('transcript') and ep.get('direct_audio_url'):
                    # Check if URL has failed before
                    url_status = ep.get('audio_url_status', 'available')
                    if url_status not in ['failed_404', 'failed_temp']:
                        episodes_to_transcribe.append(ep)
                    else:
                        logger.info(f"Skipping episode {ep['episode_id']} due to URL status: {url_status}")
            
            if episodes_to_transcribe:
                logger.info(f"Creating batch for {len(episodes_to_transcribe)} episodes")
                
                # Create transcription batch
                episode_ids = [ep['episode_id'] for ep in episodes_to_transcribe]
                batch_info = await self.batch_transcriber.create_transcription_batch(
                    episode_ids,
                    discovery["campaign_id"]
                )
                
                if batch_info['status'] == 'created':
                    # Process the batch
                    batch_results = await self.batch_transcriber.process_batch(
                        batch_info['batch_id']
                    )
                    
                    result["improvements"].append({
                        "type": "batch_transcription",
                        "batch_id": batch_info['batch_id'],
                        "episodes_processed": batch_results['summary']['total'],
                        "episodes_completed": batch_results['summary']['completed'],
                        "episodes_failed": batch_results['summary']['failed']
                    })
                    
                    # Analyze transcribed episodes
                    for episode_result in batch_results['results']:
                        if episode_result['status'] == 'completed':
                            try:
                                analysis_result = await self.media_analyzer.analyze_episode(
                                    episode_result['episode_id']
                                )
                                if analysis_result["status"] == "success":
                                    logger.info(f"Episode {episode_result['episode_id']} analyzed successfully")
                            except Exception as e:
                                logger.error(f"Error analyzing episode {episode_result['episode_id']}: {e}")
                    
                    result["steps_completed"].append("batch_transcription_completed")
            
            # Step 3: Generate AI description for podcast
            media_data = await media_queries.get_media_by_id_from_db(media_id)
            if media_data and not media_data.get('ai_description'):
                ai_description = await self._generate_podcast_ai_description(media_id)
                if ai_description:
                    await media_queries.update_media_ai_description(media_id, ai_description)
                    result["steps_completed"].append("ai_description_generated")
            
            # Step 4: Calculate quality score
            transcribed_count = await media_queries.count_transcribed_episodes_for_media(media_id)
            if transcribed_count >= 3:
                quality_score = await self.enrichment_orchestrator.quality_service.calculate_score(media_id)
                if quality_score:
                    await media_queries.update_media_quality_score(media_id, quality_score)
                    result["steps_completed"].append("quality_score_calculated")
            
            # Mark enrichment as completed
            await cmd_queries.update_enrichment_status(discovery["id"], "completed")
            result["steps_completed"].append("enrichment_completed")
            
        except Exception as e:
            logger.error(f"Error in enhanced enrichment step: {e}", exc_info=True)
            await cmd_queries.update_enrichment_status(
                discovery["id"], "failed", str(e)
            )
            result["status"] = "error"
            result["errors"].append(str(e))
        
        return result
    
    async def _verify_host_names(self, media_id: int) -> Optional[Dict[str, Any]]:
        """
        Verify host names and return verification results.
        """
        try:
            verification_result = await self.host_verifier.verify_host_names(media_id)
            
            if verification_result and verification_result.get("low_confidence_hosts"):
                logger.warning(f"Found {len(verification_result['low_confidence_hosts'])} "
                             f"low-confidence hosts for media {media_id}")
            
            return verification_result
            
        except Exception as e:
            logger.error(f"Error verifying host names for media {media_id}: {e}")
            return None
    
    async def _generate_podcast_ai_description(self, media_id: int) -> Optional[str]:
        """
        Generate AI description using episode summaries and podcast description.
        """
        try:
            media = await media_queries.get_media_by_id_from_db(media_id)
            episodes = await episode_queries.get_episodes_for_media_with_content(media_id, limit=3)
            
            if not media:
                return None
            
            # Compile information for AI description
            context_parts = [
                f"Podcast: {media.get('name') or 'Unknown'}",
                f"Original Description: {media.get('description') or 'No description available'}",
                f"Category: {media.get('category') or 'Uncategorized'}"
            ]
            
            # Use verified host names with confidence scores
            host_confidence = media.get('host_names_discovery_confidence', {})
            
            # Handle case where host_confidence might be a JSON string
            if isinstance(host_confidence, str):
                try:
                    host_confidence = json.loads(host_confidence)
                except:
                    host_confidence = {}
            
            if host_confidence and isinstance(host_confidence, dict):
                # Sort hosts by confidence
                sorted_hosts = sorted(
                    host_confidence.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                high_confidence_hosts = [
                    host for host, conf in sorted_hosts if conf >= 0.7
                ]
                if high_confidence_hosts:
                    context_parts.append(f"Hosts: {', '.join(high_confidence_hosts)}")
                else:
                    context_parts.append("Hosts: Unknown")
            elif media.get('host_names'):
                hosts_str = ', '.join(str(h) for h in media['host_names'] if h)
                context_parts.append(f"Hosts: {hosts_str or 'Unknown'}")
            else:
                context_parts.append("Hosts: Unknown")
            
            if episodes:
                context_parts.append("\nRecent Episodes:")
                for ep in episodes:
                    if ep.get('ai_episode_summary'):
                        title = ep.get('title') or 'Untitled Episode'
                        summary = ep.get('ai_episode_summary') or ''
                        context_parts.append(f"- {title}: {summary}")
            
            context = "\n".join(context_parts)
            
            # Use Gemini to generate comprehensive description
            gemini = GeminiService()
            prompt = """
            Based on the following podcast information and episode summaries, 
            create a comprehensive, engaging description of what this podcast is about.
            Focus on the main themes, target audience, and unique value proposition.
            Keep it under 200 words.
            
            {context}
            """
            
            ai_description = await gemini.create_message(
                prompt=prompt.format(context=context),
                workflow="podcast_description_generation",
                related_media_id=media_id
            )
            
            return ai_description
            
        except Exception as e:
            logger.error(f"Error generating AI description for media {media_id}: {e}", exc_info=True)
            return None
    
    async def _run_vetting_step(self, discovery: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run vetting using campaign_media_discoveries instead of match_suggestions.
        """
        result = {
            "status": "success", 
            "steps_completed": [],
            "errors": []
        }
        
        try:
            # Get campaign data with questionnaire responses
            campaign = await campaign_queries.get_campaign_by_id(discovery["campaign_id"])
            if not campaign:
                result["status"] = "error"
                result["errors"].append("Campaign not found")
                return result
            
            if not campaign.get("ideal_podcast_description"):
                result["status"] = "error"
                result["errors"].append("Campaign missing ideal_podcast_description")
                return result
            
            # Update vetting status
            await cmd_queries.update_enrichment_status(discovery["id"], "in_progress")
            
            # Run vetting
            vetting_result = await self.vetting_agent.vet_match(
                campaign, 
                discovery["media_id"]
            )
            
            if vetting_result:
                # Update discovery with vetting results
                await cmd_queries.update_vetting_results(
                    discovery["id"],
                    vetting_result["vetting_score"],
                    vetting_result.get("vetting_reasoning", ""),
                    vetting_result.get("vetting_checklist", {}),
                    "completed"
                )
                
                result["vetting_score"] = vetting_result["vetting_score"]
                result["steps_completed"].append("vetting_completed")
                
                # Publish event
                await self._publish_vetting_event(discovery, vetting_result)
                
            else:
                await cmd_queries.update_vetting_results(
                    discovery["id"],
                    0.0,
                    "Vetting failed to produce results",
                    {},
                    "failed"
                )
                result["status"] = "error"
                result["errors"].append("Vetting failed to produce results")
        
        except Exception as e:
            logger.error(f"Error in vetting step: {e}", exc_info=True)
            result["status"] = "error"
            result["errors"].append(str(e))
        
        return result
    
    async def _create_match_and_review_task(self, discovery: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create match suggestion and review task for high-scoring discoveries.
        """
        result = {
            "status": "success",
            "steps_completed": [],
            "errors": []
        }
        
        try:
            # Create match suggestion
            match_data = {
                "campaign_id": discovery["campaign_id"],
                "media_id": discovery["media_id"],
                "status": "pending_client_review",
                "match_score": discovery["vetting_score"],
                "matched_keywords": [discovery["discovery_keyword"]],
                "ai_reasoning": discovery["vetting_reasoning"],
                "vetting_score": discovery["vetting_score"],
                "vetting_reasoning": discovery["vetting_reasoning"]
            }
            
            match = await match_queries.create_match_suggestion_in_db(match_data)
            if not match:
                result["status"] = "error"
                result["errors"].append("Failed to create match suggestion")
                return result
            
            match_id = match["match_id"]
            result["match_id"] = match_id
            
            # Update discovery record
            await cmd_queries.mark_match_created(discovery["id"], match_id)
            result["steps_completed"].append("match_created")
            
            # Create review task
            review_task_data = {
                "task_type": "match_suggestion",
                "related_id": match_id,
                "campaign_id": discovery["campaign_id"],
                "status": "pending",
                "notes": f"AI-vetted match ready for review. Score: {discovery['vetting_score']:.1f}/10"
            }
            
            review_task = await review_task_queries.create_review_task_in_db(review_task_data)
            if review_task:
                result["review_task_id"] = review_task.get("review_task_id")
                await cmd_queries.mark_review_task_created(
                    discovery["id"], 
                    review_task["review_task_id"]
                )
                result["steps_completed"].append("review_task_created")
            
        except Exception as e:
            logger.error(f"Error creating match and review task: {e}", exc_info=True)
            result["status"] = "error"
            result["errors"].append(str(e))
        
        return result
    
    async def _publish_vetting_event(self, discovery: Dict[str, Any], vetting_result: Dict[str, Any]):
        """Publish vetting completed event."""
        try:
            event_bus = get_event_bus()
            media = await media_queries.get_media_by_id_from_db(discovery["media_id"])
            
            event = Event(
                event_type=EventType.VETTING_COMPLETED,
                entity_id=str(discovery["media_id"]),
                entity_type="media",
                data={
                    "campaign_id": str(discovery["campaign_id"]),
                    "media_id": discovery["media_id"],
                    "media_name": media.get("name", "Unknown") if media else "Unknown",
                    "vetting_score": vetting_result["vetting_score"],
                    "vetting_reasoning": vetting_result.get("vetting_reasoning", ""),
                    "discovery_keyword": discovery["discovery_keyword"]
                },
                source="enhanced_discovery_workflow"
            )
            await event_bus.publish(event)
            
        except Exception as e:
            logger.error(f"Error publishing vetting event: {e}")
    
    async def run_periodic_verifications(self):
        """
        Run periodic host name verifications for existing media.
        """
        logger.info("Starting periodic host name verifications")
        
        try:
            results = await self.host_verifier.run_verification_batch(batch_size=50)
            
            # Log summary
            successful = sum(1 for r in results if r["status"] == "success")
            low_confidence_total = sum(r.get("low_confidence_count", 0) for r in results)
            
            logger.info(f"Periodic verification completed: {successful} media verified, "
                       f"{low_confidence_total} low-confidence hosts found")
            
        except Exception as e:
            logger.error(f"Error in periodic verifications: {e}", exc_info=True)