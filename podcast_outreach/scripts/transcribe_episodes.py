# podcast_outreach/scripts/transcribe_episodes.py

import asyncio
import logging
import os

# Corrected imports to use the new service class and queries
from podcast_outreach.services.media.transcriber import MediaTranscriber, AudioNotFoundError
from podcast_outreach.services.media.analyzer import MediaAnalyzerService
from podcast_outreach.services.matches.match_creation import MatchCreationService
from podcast_outreach.database.queries import episodes as episode_queries, campaigns as campaign_queries, media as media_queries
from podcast_outreach.database.connection import init_db_pool, close_db_pool, reset_db_pool
from podcast_outreach.config import ORCHESTRATOR_CONFIG
from podcast_outreach.services.enrichment.quality_score import QualityService
from podcast_outreach.database.models.media_models import EnrichedPodcastProfile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 20

async def run_transcription_logic(db_service=None):
    """
    Core logic for the transcription and analysis process. Can accept a database service or use global pool.
    """
    # Determine which pool to use for database operations
    if db_service:
        pool_to_use = db_service.pool
    else:
        # For standalone runs, ensure we have the latest pool configuration
        await reset_db_pool()
        from podcast_outreach.database.connection import get_db_pool
        pool_to_use = await get_db_pool()
        
    try:
        transcriber = MediaTranscriber()
        analyzer = MediaAnalyzerService()
        match_creator = MatchCreationService()
        quality_service = QualityService()

        # Process episodes that need transcription
        to_transcribe = await episode_queries.fetch_episodes_for_transcription(BATCH_SIZE, pool_to_use)
        if to_transcribe:
            logger.info(f"Found {len(to_transcribe)} episodes to transcribe.")
            for ep in to_transcribe:
                episode_id = ep["episode_id"]
                media_id = ep["media_id"]
                success = await process_single_episode_with_retry(
                    ep, transcriber, analyzer, match_creator, quality_service, pool_to_use
                )
                if not success:
                    logger.error(f"Failed to process episode {episode_id} after all retries")
        else:
            logger.info("No episodes require transcription at this time.")
        
        # Process episodes that need embeddings (including Podscan episodes with existing content)
        to_embed = await episode_queries.fetch_episodes_for_embedding_generation(BATCH_SIZE, pool_to_use)
        if to_embed:
            logger.info(f"Found {len(to_embed)} episodes needing embeddings.")
            for ep in to_embed:
                episode_id = ep["episode_id"]
                success = await generate_embedding_for_existing_episode(ep, transcriber, pool_to_use)
                if success:
                    logger.info(f"Generated embedding for episode {episode_id}")
                else:
                    logger.warning(f"Failed to generate embedding for episode {episode_id}")
        else:
            logger.info("No episodes need embeddings at this time.")
        
        # Process episodes that need analysis (including Podscan episodes with existing transcripts)
        to_analyze = await episode_queries.fetch_episodes_for_analysis(BATCH_SIZE, pool_to_use)
        if to_analyze:
            logger.info(f"Found {len(to_analyze)} episodes to analyze.")
            media_ids_analyzed = set()
            
            for ep in to_analyze:
                episode_id = ep["episode_id"]
                media_id = ep["media_id"]
                
                # Analyze the episode
                analysis_result = await analyzer.analyze_episode(episode_id)
                if analysis_result.get("status") == "success":
                    logger.info(f"Episode {episode_id} analysis successful.")
                    media_ids_analyzed.add(media_id)
                else:
                    logger.warning(f"Episode {episode_id} analysis failed: {analysis_result.get('message')}")
            
            # Run podcast-level analysis for media that had episodes analyzed
            for media_id in media_ids_analyzed:
                logger.info(f"Running podcast-level analysis for media {media_id}")
                podcast_analysis_result = await analyzer.analyze_podcast_from_episodes(media_id)
                status = podcast_analysis_result.get("status")
                if status == "success":
                    logger.info(f"Podcast-level analysis successful for media {media_id}")
                elif status == "safety_blocked":
                    logger.warning(f"Podcast-level analysis blocked by safety filters for media {media_id}. Using fallback description.")
                else:
                    logger.warning(f"Podcast-level analysis failed for media {media_id}: {podcast_analysis_result.get('message')}")
        else:
            logger.info("No episodes require analysis at this time.")
    
    finally:
        # Clean up resources if needed
        pass

async def process_single_episode_with_retry(
    ep, transcriber, analyzer, match_creator, quality_service, pool_to_use, max_retries=3
):
    """
    Process a single episode with retry mechanism for failed transcriptions.
    """
    episode_id = ep["episode_id"]
    media_id = ep["media_id"]
    local_audio_path = None
    
    # Check duration before processing
    from podcast_outreach.config import MAX_EPISODE_DURATION_SEC
    duration_sec = ep.get("duration_sec", 0)
    if duration_sec and duration_sec > MAX_EPISODE_DURATION_SEC:
        logger.warning(f"Skipping episode {episode_id} - duration {duration_sec}s exceeds max {MAX_EPISODE_DURATION_SEC}s")
        from podcast_outreach.database.queries.episodes import mark_episode_as_failed
        await mark_episode_as_failed(
            episode_id,
            error_type='failed_temp',
            error_message=f"Episode too long: {duration_sec}s (max: {MAX_EPISODE_DURATION_SEC}s)",
            pool=pool_to_use
        )
        return False
    
    for attempt in range(max_retries + 1):  # +1 because we want max_retries actual retries
        try:
            if attempt > 0:
                logger.info(f"--- RETRY {attempt}/{max_retries} for episode {episode_id}: '{ep.get('title')}' ---")
                # Exponential backoff: wait 2^attempt * 30 seconds
                wait_time = (2 ** attempt) * 30
                logger.info(f"Waiting {wait_time} seconds before retry...")
                await asyncio.sleep(wait_time)
            else:
                logger.info(f"--- Processing episode {episode_id}: '{ep.get('title')}' ---")
            
            # Use direct_audio_url if available, otherwise fall back to episode_url
            audio_url = ep.get("direct_audio_url") or ep["episode_url"]
            
            try:
                local_audio_path = await transcriber.download_audio(audio_url, episode_id=episode_id)
            except AudioNotFoundError as e:
                # 404 error - audio file doesn't exist, no point retrying
                logger.error(f"Audio not found (404) for episode {episode_id}: {e}")
                logger.warning(f"Marking episode {episode_id} as failed due to missing audio file")
                
                # Update episode to mark as failed with reason
                try:
                    await episode_queries.update_episode_transcription(
                        episode_id, 
                        "[AUDIO FILE NOT FOUND - 404 ERROR]", 
                        "Audio file no longer available at the provided URL", 
                        None, 
                        3,  # Mark as processed to avoid retrying
                        pool_to_use
                    )
                except Exception as db_e:
                    logger.error(f"Failed to update episode {episode_id} after 404 error: {db_e}")
                return False
            
            if not local_audio_path:
                if attempt < max_retries:
                    logger.warning(f"Failed to download audio for episode {episode_id}. Will retry.")
                    continue
                else:
                    logger.error(f"Failed to download audio for episode {episode_id} after {max_retries} retries.")
                    return False

            # Process transcription without holding database connections
            transcript, summary, embedding = await transcriber.transcribe_audio(
                local_audio_path, episode_id=episode_id, episode_title=ep.get("title")
            )
            
            if not transcript or "ERROR in chunk" in transcript:
                if attempt < max_retries:
                    logger.warning(f"Transcription failed for episode {episode_id}. Will retry.")
                    # Clean up the audio file before retry
                    if local_audio_path and os.path.exists(local_audio_path):
                        os.remove(local_audio_path)
                        local_audio_path = None
                    continue
                else:
                    logger.error(f"Transcription failed for episode {episode_id} after {max_retries} retries.")
                    # Retry database update once if it fails
                    for db_attempt in range(2):
                        try:
                            await episode_queries.update_episode_transcription(episode_id, transcript or "[TRANSCRIPTION FAILED]", summary, None, 3, pool_to_use)
                            break
                        except Exception as db_e:
                            if db_attempt == 0:
                                logger.warning(f"Database update failed for episode {episode_id}, retrying: {db_e}")
                                await asyncio.sleep(1)
                            else:
                                logger.error(f"Database update failed for episode {episode_id} after retry: {db_e}")
                    return False

            # Retry database update once if it fails
            updated_episode = None
            for db_attempt in range(2):
                try:
                    updated_episode = await episode_queries.update_episode_transcription(
                        episode_id, transcript, summary, embedding, 3, pool_to_use
                    )
                    break
                except Exception as db_e:
                    if db_attempt == 0:
                        logger.warning(f"Database update failed for episode {episode_id}, retrying: {db_e}")
                        await asyncio.sleep(1)
                    else:
                        logger.error(f"Database update failed for episode {episode_id} after retry: {db_e}")
                        return False
            logger.info(f"Episode {episode_id} transcribed and updated in DB.")
            
            # Publish episode transcribed event
            try:
                from podcast_outreach.services.events.event_bus import get_event_bus, Event, EventType
                event_bus = get_event_bus()
                event = Event(
                    event_type=EventType.EPISODE_TRANSCRIBED,
                    entity_id=str(episode_id),
                    entity_type="episode",
                    data={
                        "media_id": media_id,
                        "has_embedding": bool(embedding),
                        "transcript_length": len(transcript) if transcript else 0
                    },
                    source="transcribe_episodes"
                )
                await event_bus.publish(event)
                logger.info(f"Published EPISODE_TRANSCRIBED event for episode {episode_id}")
            except Exception as e:
                logger.error(f"Error publishing episode transcribed event: {e}")

            # --- Post-Transcription Pipeline ---
            if updated_episode:
                # 1. Analyze Content
                analysis_result = await analyzer.analyze_episode(episode_id)
                if analysis_result.get("status") == "success":
                    logger.info(f"Episode {episode_id} analysis successful.")
                else:
                    logger.warning(f"Episode {episode_id} analysis failed: {analysis_result.get('message')}")

                # 2. Match Creation Optimization: Removed automatic match creation
                # Matches are now created via enrichment pipeline after full enrichment is complete
                # This ensures higher quality matches with complete podcast data

                # 3. Update Quality Score
                transcribed_count = await media_queries.count_transcribed_episodes_for_media(media_id)
                min_episodes_needed = ORCHESTRATOR_CONFIG.get("quality_score_min_transcribed_episodes", 3)
                if transcribed_count >= min_episodes_needed:
                    logger.info(f"Media {media_id} has enough transcripts. Updating quality score.")
                    media_data = await media_queries.get_media_by_id_from_db(media_id)
                    if media_data:
                        profile = EnrichedPodcastProfile(**media_data)
                        score, components = quality_service.calculate_podcast_quality_score(profile)
                        if score is not None:
                            await media_queries.update_media_quality_score(media_id, score)
                            logger.info(f"Updated quality score for media {media_id} to {score}.")
            
            # Success - episode processed successfully
            return True

        except MemoryError as e:
            # Memory errors should not be retried - mark episode as failed
            logger.error(f"Memory error processing episode {episode_id}: {e}")
            from podcast_outreach.database.queries.episodes import mark_episode_as_failed
            await mark_episode_as_failed(
                episode_id, 
                error_type='failed_temp',
                error_message=f"Memory error: {str(e)}",
                pool=pool_to_use
            )
            return False  # Don't retry memory errors
        except ValueError as e:
            # Check if it's a file size error
            if "Audio file too large" in str(e):
                logger.warning(f"Episode {episode_id} file is too large: {e}")
                from podcast_outreach.database.queries.episodes import mark_episode_as_failed
                await mark_episode_as_failed(
                    episode_id,
                    error_type='failed_temp',
                    error_message=f"File too large: {str(e)}",
                    pool=pool_to_use
                )
                return False  # Don't retry file size errors
            else:
                # Re-raise other ValueErrors
                raise
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"Error processing episode {episode_id} (attempt {attempt + 1}): {e}. Will retry.")
            else:
                logger.exception(f"Error processing episode {episode_id} after {max_retries} retries: {e}")
                # Mark as failed after all retries exhausted
                from podcast_outreach.database.queries.episodes import mark_episode_as_failed
                await mark_episode_as_failed(
                    episode_id,
                    error_type='failed_temp',
                    error_message=f"Failed after {max_retries} retries: {str(e)}",
                    pool=pool_to_use
                )
                return False
        finally:
            if local_audio_path and os.path.exists(local_audio_path):
                try:
                    os.remove(local_audio_path)
                    logger.info(f"Cleaned up temporary audio file: {local_audio_path}")
                except OSError as e:
                    logger.error(f"Error removing temporary audio file {local_audio_path}: {e}")
                local_audio_path = None  # Reset for next attempt
    
    # If we get here, all retries failed
    logger.error(f"Episode {episode_id} failed after all {max_retries} retry attempts")
    return False

async def generate_embedding_for_existing_episode(ep, transcriber, pool_to_use) -> bool:
    """
    Generate embedding for an episode that already has content but missing embedding.
    Used for Podscan episodes and other pre-existing content.
    """
    episode_id = ep["episode_id"]
    title = ep.get("title", "")
    transcript = ep.get("transcript", "")
    ai_episode_summary = ep.get("ai_episode_summary", "")
    episode_summary = ep.get("episode_summary", "")
    
    try:
        # Use the best available content for embedding
        summary_for_embedding = ai_episode_summary or episode_summary or ""
        
        if not transcript and not summary_for_embedding:
            logger.warning(f"Episode {episode_id} has no content for embedding generation")
            return False
        
        # Generate embedding using AI summary only (no transcript truncation)
        from podcast_outreach.services.ai.openai_client import OpenAIService
        openai_service = OpenAIService()
        
        # Use only title + AI summary for embeddings (semantic-focused)
        if summary_for_embedding:
            embedding_text = f"Title: {title}\nSummary: {summary_for_embedding}"
        else:
            # Fallback: create summary from transcript if no summary exists
            logger.info(f"No summary available for episode {episode_id}, creating one from transcript")
            if transcript:
                # Use transcriber to create summary for embedding
                from podcast_outreach.services.media.transcriber import MediaTranscriber
                transcriber_service = MediaTranscriber()
                generated_summary = await transcriber_service.summarize_transcript(
                    transcript=transcript,
                    episode_title=title,
                    podcast_name="",  # Could fetch from media table if needed
                    episode_summary=""
                )
                embedding_text = f"Title: {title}\nSummary: {generated_summary}"
            else:
                embedding_text = f"Title: {title}"
        
        embedding = await openai_service.get_embedding(
            text=embedding_text, 
            workflow="episode_embedding", 
            related_ids={"episode_id": episode_id}
        )
        
        if not embedding:
            logger.error(f"Failed to generate embedding for episode {episode_id}")
            return False
        
        # Update episode with embedding
        updated_episode = await episode_queries.update_episode_transcription(
            episode_id, 
            transcript or "[NO_TRANSCRIPT]",  # Keep existing transcript or mark as none
            ai_episode_summary,  # Keep existing AI summary
            embedding,
            3,  # max_retries
            pool_to_use
        )
        
        if updated_episode:
            logger.info(f"Successfully generated embedding for episode {episode_id}")
            return True
        else:
            logger.error(f"Failed to update episode {episode_id} with embedding")
            return False
            
    except Exception as e:
        logger.error(f"Error generating embedding for episode {episode_id}: {e}")
        return False

async def main():
    """Main entry point for running the script directly."""
    await init_db_pool()
    try:
        await run_transcription_logic()
    finally:
        await close_db_pool()

if __name__ == "__main__":
    asyncio.run(main())