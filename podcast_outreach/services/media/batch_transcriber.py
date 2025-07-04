"""
Enhanced Batch Transcription Service

This service provides:
1. Batch transcription of multiple episodes concurrently
2. Smart batching based on episode duration
3. Better 404 handling with exponential backoff
4. Failed URL caching to prevent repeated attempts
"""

import logging
import asyncio
import uuid
import os
import tempfile
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
import aiohttp
import requests
from urllib.parse import urlparse

from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.services.media.transcriber import MediaTranscriber, AudioNotFoundError
from podcast_outreach.logging_config import get_logger
from podcast_outreach.utils.memory_monitor import get_memory_info

logger = get_logger(__name__)

class BatchTranscriptionService:
    """
    Enhanced transcription service with batch processing and improved error handling.
    """
    
    # Batch configuration
    MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "5"))  # Reduced from 10 to 5
    MAX_BATCH_DURATION_MINUTES = 180  # 3 hours total
    MAX_EPISODE_DURATION_MINUTES = 60  # Individual episode limit
    
    # Retry configuration with exponential backoff
    MAX_RETRIES = 3
    INITIAL_RETRY_DELAY = 5
    MAX_RETRY_DELAY = 300  # 5 minutes
    BACKOFF_FACTOR = 2
    
    # URL failure tracking
    PERMANENT_FAILURE_THRESHOLD = 3  # Mark as permanently failed after 3 attempts
    URL_RETRY_COOLDOWN_HOURS = 24    # Wait 24 hours before retrying a failed URL
    
    def __init__(self):
        self.transcriber = MediaTranscriber()
        self._active_batches: Dict[str, Dict[str, Any]] = {}
        self._failed_url_cache: Dict[str, Dict[str, Any]] = {}  # url -> {failure_count, last_attempt, error}
        self._cache_cleanup_task = None
        logger.info("BatchTranscriptionService initialized")
        # Start cache cleanup task
        self._start_cache_cleanup()
    
    def get_safe_batch_size(self) -> int:
        """
        Get memory-aware batch size based on current memory usage.
        Returns smaller batch sizes when memory is high.
        """
        memory_info = get_memory_info()
        process_percent = memory_info["process_percent"]
        
        if process_percent > 50:
            logger.warning(f"High memory usage ({process_percent:.1f}%), limiting batch size to 1")
            return 1
        elif process_percent > 30:
            logger.info(f"Moderate memory usage ({process_percent:.1f}%), limiting batch size to 2")
            return min(2, self.MAX_BATCH_SIZE)
        else:
            logger.debug(f"Normal memory usage ({process_percent:.1f}%), using full batch size")
            return self.MAX_BATCH_SIZE
    
    async def create_transcription_batch(
        self,
        episode_ids: List[int],
        campaign_id: Optional[uuid.UUID] = None
    ) -> Dict[str, Any]:
        """
        Create a batch of episodes for transcription with smart grouping.
        
        Returns:
            Dict containing batch information and status
        """
        batch_id = str(uuid.uuid4())
        logger.info(f"Creating transcription batch {batch_id} with {len(episode_ids)} episodes")
        
        try:
            # Get episode details
            episodes = []
            for episode_id in episode_ids:
                episode = await episode_queries.get_episode_by_id(episode_id)
                if episode:
                    episodes.append(episode)
            
            if not episodes:
                return {
                    "batch_id": batch_id,
                    "status": "error",
                    "error": "No valid episodes found"
                }
            
            # Smart batching based on duration
            batches = await self._create_smart_batches(episodes)
            
            # Store batch information
            self._active_batches[batch_id] = {
                "batches": batches,
                "campaign_id": campaign_id,
                "created_at": datetime.now(timezone.utc),
                "status": "pending",
                "total_episodes": len(episodes),
                "completed_episodes": 0,
                "failed_episodes": 0
            }
            
            return {
                "batch_id": batch_id,
                "status": "created",
                "total_batches": len(batches),
                "total_episodes": len(episodes),
                "estimated_duration_minutes": sum(b['total_duration'] for b in batches) / 60
            }
            
        except Exception as e:
            logger.error(f"Error creating transcription batch: {e}", exc_info=True)
            return {
                "batch_id": batch_id,
                "status": "error",
                "error": str(e)
            }
    
    async def _create_smart_batches(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Create smart batches based on episode duration, memory usage, and other factors.
        """
        batches = []
        current_batch = {
            "episodes": [],
            "total_duration": 0,
            "position": 0
        }
        
        # Sort episodes by duration to optimize batching
        sorted_episodes = sorted(
            episodes,
            key=lambda e: e.get('duration_sec', 0) or 0
        )
        
        # Get memory-aware batch size
        safe_batch_size = self.get_safe_batch_size()
        
        for episode in sorted_episodes:
            duration = episode.get('duration_sec', 0) or 0
            
            # Skip episodes that are too long
            if duration > self.MAX_EPISODE_DURATION_MINUTES * 60:
                logger.warning(f"Episode {episode['episode_id']} too long ({duration/60:.1f} min), skipping")
                continue
            
            # Check if adding this episode would exceed batch limits (using memory-aware batch size)
            if (current_batch['episodes'] and 
                (len(current_batch['episodes']) >= safe_batch_size or
                 current_batch['total_duration'] + duration > self.MAX_BATCH_DURATION_MINUTES * 60)):
                # Save current batch and start a new one
                batches.append(current_batch)
                current_batch = {
                    "episodes": [],
                    "total_duration": 0,
                    "position": len(batches)
                }
                # Re-check memory for new batch
                safe_batch_size = self.get_safe_batch_size()
            
            current_batch['episodes'].append(episode)
            current_batch['total_duration'] += duration
        
        # Add the last batch if it has episodes
        if current_batch['episodes']:
            batches.append(current_batch)
        
        logger.info(f"Created {len(batches)} smart batches from {len(episodes)} episodes (memory-aware batch size: {safe_batch_size})")
        return batches
    
    async def process_batch(self, batch_id: str) -> Dict[str, Any]:
        """
        Process a transcription batch with concurrent execution and error handling.
        """
        if batch_id not in self._active_batches:
            return {
                "status": "error",
                "error": "Batch not found"
            }
        
        batch_info = self._active_batches[batch_id]
        batch_info['status'] = 'processing'
        batch_info['started_at'] = datetime.now(timezone.utc)
        
        results = {
            "batch_id": batch_id,
            "status": "processing",
            "results": [],
            "summary": {
                "total": batch_info['total_episodes'],
                "completed": 0,
                "failed": 0,
                "skipped": 0
            }
        }
        
        try:
            # Process each sub-batch concurrently
            for sub_batch in batch_info['batches']:
                sub_batch_results = await self._process_sub_batch(
                    sub_batch,
                    batch_id,
                    batch_info.get('campaign_id')
                )
                results['results'].extend(sub_batch_results)
                
                # Update summary
                for result in sub_batch_results:
                    if result['status'] == 'completed':
                        results['summary']['completed'] += 1
                    elif result['status'] == 'failed':
                        results['summary']['failed'] += 1
                    elif result['status'] == 'skipped':
                        results['summary']['skipped'] += 1
            
            # Update batch status
            batch_info['status'] = 'completed'
            batch_info['completed_at'] = datetime.now(timezone.utc)
            batch_info['completed_episodes'] = results['summary']['completed']
            batch_info['failed_episodes'] = results['summary']['failed']
            
            results['status'] = 'completed'
            
            logger.info(f"Batch {batch_id} completed: {results['summary']}")
            
        except Exception as e:
            logger.error(f"Error processing batch {batch_id}: {e}", exc_info=True)
            batch_info['status'] = 'error'
            batch_info['error'] = str(e)
            results['status'] = 'error'
            results['error'] = str(e)
        
        return results
    
    async def _process_sub_batch(
        self,
        sub_batch: Dict[str, Any],
        batch_id: str,
        campaign_id: Optional[uuid.UUID]
    ) -> List[Dict[str, Any]]:
        """
        Process a sub-batch of episodes concurrently.
        """
        episodes = sub_batch['episodes']
        position = sub_batch['position']
        
        # Create tasks for concurrent processing
        tasks = []
        for i, episode in enumerate(episodes):
            task = self._process_single_episode(
                episode,
                batch_id,
                position * self.MAX_BATCH_SIZE + i,
                campaign_id
            )
            tasks.append(task)
        
        # Process concurrently with gather
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to error results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "episode_id": episodes[i]['episode_id'],
                    "status": "failed",
                    "error": str(result)
                })
            else:
                processed_results.append(result)
        
        return processed_results
    
    async def _process_single_episode(
        self,
        episode: Dict[str, Any],
        batch_id: str,
        position: int,
        campaign_id: Optional[uuid.UUID]
    ) -> Dict[str, Any]:
        """
        Process a single episode with retry logic and error handling.
        """
        episode_id = episode['episode_id']
        audio_url = episode.get('direct_audio_url')
        
        result = {
            "episode_id": episode_id,
            "batch_id": batch_id,
            "position": position,
            "status": "pending"
        }
        
        try:
            # Check if episode already has transcript
            if episode.get('transcript'):
                logger.info(f"Episode {episode_id} already has transcript, skipping")
                result['status'] = 'skipped'
                result['reason'] = 'already_transcribed'
                return result
            
            if not audio_url:
                logger.warning(f"Episode {episode_id} has no audio URL")
                result['status'] = 'failed'
                result['error'] = 'no_audio_url'
                await self._update_episode_url_status(episode_id, 'failed_404', 'No audio URL provided')
                return result
            
            # Check failed URL cache
            if await self._is_url_in_failure_cache(audio_url):
                logger.info(f"URL {audio_url} is in failure cache, skipping")
                result['status'] = 'skipped'
                result['reason'] = 'url_in_failure_cache'
                return result
            
            # Update batch tracking
            await episode_queries.update_episode_analysis_data(
                episode_id,
                transcription_batch_id=batch_id,
                transcription_batch_position=position
            )
            
            # Attempt transcription with retries
            transcript = await self._transcribe_with_retry(
                episode_id,
                audio_url,
                campaign_id
            )
            
            if transcript:
                # Update episode with transcript
                await episode_queries.update_episode_transcript(episode_id, transcript)
                
                # Update URL status as available
                await self._update_episode_url_status(episode_id, 'available')
                
                result['status'] = 'completed'
                result['transcript_length'] = len(transcript)
                
                logger.info(f"Successfully transcribed episode {episode_id}")
            else:
                result['status'] = 'failed'
                result['error'] = 'transcription_failed'
            
        except Exception as e:
            logger.error(f"Error processing episode {episode_id}: {e}", exc_info=True)
            result['status'] = 'failed'
            result['error'] = str(e)
        
        return result
    
    async def _transcribe_with_retry(
        self,
        episode_id: int,
        audio_url: str,
        campaign_id: Optional[uuid.UUID]
    ) -> Optional[str]:
        """
        Attempt to transcribe with exponential backoff retry logic.
        """
        retry_delay = self.INITIAL_RETRY_DELAY
        
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.info(f"Transcription attempt {attempt + 1}/{self.MAX_RETRIES} for episode {episode_id}")
                
                # Check URL status before attempting download
                url_check = await self._check_url_availability(audio_url)
                if url_check['status'] == 'not_found':
                    # Permanent failure - don't retry
                    await self._add_to_failure_cache(audio_url, 'not_found', permanent=True)
                    await self._update_episode_url_status(episode_id, 'failed_404', url_check['error'])
                    raise AudioNotFoundError(f"Audio not found: {audio_url}")
                
                # Download audio
                audio_file = await self.transcriber.download_audio(audio_url, episode_id)
                if not audio_file:
                    raise Exception("Failed to download audio file")
                
                try:
                    # Get episode details for transcription
                    episode = await episode_queries.get_episode_by_id(episode_id)
                    episode_title = episode.get('title') if episode else None
                    
                    # Transcribe - the transcribe_audio method will handle cleanup
                    transcript, summary, embedding = await self.transcriber.transcribe_audio(
                        audio_file, 
                        episode_id,
                        episode_title
                    )
                    
                    # Return just the transcript for backward compatibility
                    transcript_text = transcript if transcript else None
                    
                finally:
                    # Extra safety: ensure cleanup even if transcribe_audio didn't do it
                    if os.path.exists(audio_file):
                        try:
                            os.remove(audio_file)
                            logger.debug(f"Cleaned up audio file in batch transcriber: {audio_file}")
                        except Exception as e:
                            logger.error(f"Failed to clean up audio file {audio_file}: {e}")
                
                if transcript_text:
                    # Success - remove from failure cache if present
                    await self._remove_from_failure_cache(audio_url)
                    return transcript_text
                
            except AudioNotFoundError:
                # Don't retry 404 errors
                logger.error(f"Audio not found (404) for episode {episode_id}, not retrying")
                await self._update_episode_url_status(episode_id, 'failed_404', 'Audio file not found (404)')
                return None
                
            except Exception as e:
                logger.warning(f"Transcription attempt {attempt + 1} failed for episode {episode_id}: {e}")
                
                if attempt < self.MAX_RETRIES - 1:
                    # Exponential backoff
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * self.BACKOFF_FACTOR, self.MAX_RETRY_DELAY)
                else:
                    # Final failure
                    await self._add_to_failure_cache(audio_url, str(e))
                    await self._update_episode_url_status(
                        episode_id, 
                        'failed_temp', 
                        f"Failed after {self.MAX_RETRIES} attempts: {e}"
                    )
        
        return None
    
    async def _check_url_availability(self, url: str) -> Dict[str, Any]:
        """
        Check if a URL is available without downloading the full file.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(url, allow_redirects=True, timeout=30) as response:
                    if response.status == 404:
                        return {"status": "not_found", "error": "404 Not Found"}
                    elif response.status >= 400:
                        return {"status": "error", "error": f"HTTP {response.status}"}
                    else:
                        return {"status": "available", "content_type": response.headers.get('content-type')}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _is_url_in_failure_cache(self, url: str) -> bool:
        """
        Check if URL is in failure cache and should be skipped.
        """
        if url not in self._failed_url_cache:
            return False
        
        cache_entry = self._failed_url_cache[url]
        
        # Check if permanent failure
        if cache_entry.get('permanent'):
            return True
        
        # Check cooldown period
        last_attempt = cache_entry.get('last_attempt')
        if last_attempt:
            cooldown_end = last_attempt + timedelta(hours=self.URL_RETRY_COOLDOWN_HOURS)
            if datetime.now(timezone.utc) < cooldown_end:
                return True
        
        # Check failure threshold
        if cache_entry.get('failure_count', 0) >= self.PERMANENT_FAILURE_THRESHOLD:
            return True
        
        return False
    
    async def _add_to_failure_cache(self, url: str, error: str, permanent: bool = False):
        """
        Add URL to failure cache.
        """
        if url not in self._failed_url_cache:
            self._failed_url_cache[url] = {
                "failure_count": 0,
                "first_failure": datetime.now(timezone.utc)
            }
        
        cache_entry = self._failed_url_cache[url]
        cache_entry['failure_count'] += 1
        cache_entry['last_attempt'] = datetime.now(timezone.utc)
        cache_entry['last_error'] = error
        cache_entry['permanent'] = permanent
        
        logger.info(f"Added URL to failure cache: {url} (count: {cache_entry['failure_count']})")
    
    async def _remove_from_failure_cache(self, url: str):
        """
        Remove URL from failure cache.
        """
        if url in self._failed_url_cache:
            del self._failed_url_cache[url]
            logger.info(f"Removed URL from failure cache: {url}")
    
    async def _update_episode_url_status(
        self,
        episode_id: int,
        status: str,
        error: Optional[str] = None
    ):
        """
        Update episode URL status in database.
        """
        try:
            from podcast_outreach.database.connection import get_db_pool
            pool = await get_db_pool()
            
            update_data = {
                "audio_url_status": status,
                "audio_url_last_checked": datetime.now(timezone.utc)
            }
            
            if error:
                update_data["audio_url_last_error"] = error[:500]  # Limit error message length
            
            if status.startswith('failed'):
                # Increment failure count
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE episodes
                        SET audio_url_status = $1,
                            audio_url_last_checked = $2,
                            audio_url_last_error = $3,
                            audio_url_failure_count = COALESCE(audio_url_failure_count, 0) + 1
                        WHERE episode_id = $4
                    """, status, update_data["audio_url_last_checked"], error, episode_id)
            else:
                # Reset failure count on success
                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE episodes
                        SET audio_url_status = $1,
                            audio_url_last_checked = $2,
                            audio_url_last_error = NULL,
                            audio_url_failure_count = 0
                        WHERE episode_id = $3
                    """, status, update_data["audio_url_last_checked"], episode_id)
            
            logger.debug(f"Updated episode {episode_id} URL status to {status}")
            
        except Exception as e:
            logger.error(f"Error updating episode URL status: {e}", exc_info=True)
    
    async def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """
        Get the current status of a transcription batch.
        """
        if batch_id not in self._active_batches:
            return {
                "status": "not_found",
                "error": "Batch not found"
            }
        
        batch_info = self._active_batches[batch_id]
        
        return {
            "batch_id": batch_id,
            "status": batch_info['status'],
            "total_episodes": batch_info['total_episodes'],
            "completed_episodes": batch_info['completed_episodes'],
            "failed_episodes": batch_info['failed_episodes'],
            "created_at": batch_info['created_at'],
            "started_at": batch_info.get('started_at'),
            "completed_at": batch_info.get('completed_at'),
            "error": batch_info.get('error')
        }
    
    async def cleanup_old_batches(self, hours: int = 24):
        """
        Clean up old batch information from memory.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        to_remove = []
        for batch_id, batch_info in self._active_batches.items():
            if batch_info.get('created_at', datetime.now(timezone.utc)) < cutoff:
                to_remove.append(batch_id)
        
        for batch_id in to_remove:
            del self._active_batches[batch_id]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old batches")
    
    def _start_cache_cleanup(self):
        """Start the periodic cache cleanup task."""
        if self._cache_cleanup_task is None:
            self._cache_cleanup_task = asyncio.create_task(self._periodic_cache_cleanup())
            logger.info("Started cache cleanup task")
    
    async def _periodic_cache_cleanup(self):
        """Periodically clean up in-memory caches to prevent memory leaks."""
        while True:
            try:
                # Clean old batches (older than 24 hours)
                batch_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
                old_batches = [k for k, v in self._active_batches.items() 
                              if v.get('created_at', datetime.now(timezone.utc)) < batch_cutoff]
                for batch_id in old_batches:
                    del self._active_batches[batch_id]
                if old_batches:
                    logger.info(f"Cleaned up {len(old_batches)} old batches from memory")
                
                # Clean old failed URLs (older than 7 days)
                url_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
                old_urls = [k for k, v in self._failed_url_cache.items()
                           if v.get('last_attempt', datetime.now(timezone.utc)) < url_cutoff]
                for url in old_urls:
                    del self._failed_url_cache[url]
                if old_urls:
                    logger.info(f"Cleaned up {len(old_urls)} old failed URLs from cache")
                
                # Log current cache sizes
                logger.debug(f"Cache sizes - Active batches: {len(self._active_batches)}, Failed URLs: {len(self._failed_url_cache)}")
                
                # Run every hour
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"Error in cache cleanup task: {e}", exc_info=True)
                # Continue running even if there's an error
                await asyncio.sleep(3600)
    
    def __del__(self):
        """Cleanup when service is destroyed."""
        if self._cache_cleanup_task and not self._cache_cleanup_task.done():
            self._cache_cleanup_task.cancel()