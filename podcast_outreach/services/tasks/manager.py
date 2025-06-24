# podcast_outreach/services/tasks/manager.py

import threading
import uuid
import asyncpg
from typing import Dict, Optional, Any, List
import logging
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Database and service imports
from podcast_outreach.database.connection import get_background_task_pool, close_background_task_pool
from podcast_outreach.services.database_service import DatabaseService

# Business logic imports
from podcast_outreach.services.business_logic.campaign_processing import (
    process_campaign_content,
    generate_angles_and_bio
)
from podcast_outreach.services.business_logic.media_processing import (
    sync_episodes as sync_episodes_logic,
    transcribe_episodes as transcribe_episodes_logic
)
from podcast_outreach.services.business_logic.enrichment_processing import (
    run_enrichment_pipeline as run_enrichment_pipeline_logic,
    run_vetting_pipeline as run_vetting_pipeline_logic
)
from podcast_outreach.services.business_logic.match_processing import (
    run_qualitative_match_assessment as run_qualitative_match_assessment_logic,
    score_potential_matches as score_potential_matches_logic,
    create_matches_for_enriched_media as create_matches_for_enriched_media_logic
)
from podcast_outreach.services.business_logic.pitch_processing import (
    generate_pitches as generate_pitches_logic,
    send_pitches as send_pitches_logic
)

logger = logging.getLogger(__name__)

# --- Task Wrapper Functions ---

async def _run_async_background_task(coro):
    """Runs an async coroutine using the background task connection pool."""
    try:
        return await coro
    except Exception as e:
        logger.error(f"Error in background task: {e}", exc_info=True)
        return False










class TaskManager:
    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        self.db_pool: Optional[asyncpg.Pool] = None
        self.db_service: Optional[DatabaseService] = None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="TaskManager")
        logger.info("TaskManager initialized.")
    
    async def initialize(self):
        """Initialize the background task database pool and services"""
        if self.db_pool is None or self.db_pool._closed:
            self.db_pool = await get_background_task_pool()
            self.db_service = DatabaseService(self.db_pool)
            logger.info("TaskManager background task database resources initialized.")
    
    async def cleanup_resources(self):
        """Cleanup database resources"""
        if self.db_pool and not self.db_pool._closed:
            await close_background_task_pool()
            self.db_pool = None
            self.db_service = None
            logger.info("TaskManager background task database resources cleaned up.")
    
    async def _run_business_logic_task(self, task_func, *args, **kwargs):
        """Run a business logic function using the background task connection pool"""
        try:
            # Ensure the background task pool is initialized
            if self.db_pool is None or self.db_pool._closed:
                await self.initialize()
            
            logger.info(f"Starting background task: {task_func.__name__}")
            result = await task_func(self.db_service, *args, **kwargs)
            logger.info(f"Background task completed: {task_func.__name__}")
            return result
                
        except Exception as e:
            logger.error(f"Error in business logic task {task_func.__name__}: {e}", exc_info=True)
            return False
    
    
    def run_angles_bio_generation(self, task_id: str, campaign_id_str: str):
        """Run angles and bio generation task"""
        async def _cleanup_wrapper():
            try:
                await self._run_business_logic_task(generate_angles_and_bio, campaign_id_str)
            finally:
                self.cleanup_task(task_id)
        
        # Create asyncio task
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for angles_bio_generation")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_episode_sync(self, task_id: str):
        """Run episode sync task"""
        async def _cleanup_wrapper():
            try:
                await self._run_business_logic_task(sync_episodes_logic)
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for episode_sync")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_transcription(self, task_id: str):
        """Run transcription task"""
        async def _cleanup_wrapper():
            try:
                await self._run_business_logic_task(transcribe_episodes_logic)
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for transcription")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_enrichment_pipeline(self, task_id: str, media_id: int = None):
        """Run enrichment pipeline task"""
        async def _cleanup_wrapper():
            try:
                await self._run_business_logic_task(run_enrichment_pipeline_logic, media_id=media_id)
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for enrichment_pipeline")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_vetting_pipeline(self, task_id: str):
        """Run vetting pipeline task"""
        async def _cleanup_wrapper():
            try:
                await self._run_business_logic_task(run_vetting_pipeline_logic)
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for vetting_pipeline")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_pitch_generation(self, task_id: str):
        """Run pitch generation task"""
        async def _cleanup_wrapper():
            try:
                await self._run_business_logic_task(generate_pitches_logic)
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for pitch_generation")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_pitch_sending(self, task_id: str):
        """Run pitch sending task"""
        async def _cleanup_wrapper():
            try:
                await self._run_business_logic_task(send_pitches_logic)
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for pitch_sending")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_campaign_content_processing(self, task_id: str, campaign_id_str: str):
        """Run campaign content processing task"""
        async def _cleanup_wrapper():
            try:
                campaign_id = uuid.UUID(campaign_id_str)
                await self._run_business_logic_task(process_campaign_content, campaign_id)
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for campaign_content_processing")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_qualitative_match_assessment(self, task_id: str):
        """Run qualitative match assessment task"""
        async def _cleanup_wrapper():
            try:
                await self._run_business_logic_task(run_qualitative_match_assessment_logic)
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for qualitative_match_assessment")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_score_potential_matches(self, task_id: str, campaign_id_str: Optional[str] = None, media_id_int: Optional[int] = None):
        """Run score potential matches task"""
        async def _cleanup_wrapper():
            try:
                await self._run_business_logic_task(score_potential_matches_logic, campaign_id_str, media_id_int)
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for score_potential_matches")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_create_matches_for_enriched_media(self, task_id: str):
        """Run create matches for enriched media task"""
        async def _cleanup_wrapper():
            try:
                await self._run_business_logic_task(create_matches_for_enriched_media_logic)
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for create_matches_for_enriched_media")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_workflow_health_check(self, task_id: str):
        """Run workflow health check to detect and fix common issues"""
        self.start_task(task_id, "workflow_health_check")
        
        async def health_check_logic():
            from podcast_outreach.services.tasks.health_checker import run_workflow_health_check
            try:
                results = await run_workflow_health_check()
                
                # Log results
                logger.info(f"Health check completed: {results['issues_found']} issues found, {results['issues_fixed']} fixed")
                for detail in results['details']:
                    if detail.get('found', 0) > 0:
                        logger.info(f"  - {detail['check']}: {detail['found']} found, {detail['fixed']} fixed")
                
                return results
                
            except Exception as e:
                logger.error(f"Error in workflow health check: {e}", exc_info=True)
                return None
        
        async def _cleanup_wrapper():
            try:
                await health_check_logic()
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for workflow_health_check")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_ai_description_completion(self, task_id: str):
        """Run AI description completion for discoveries missing AI descriptions"""
        async def ai_description_completion_logic():
            """Complete AI descriptions for enriched media with race condition protection."""
            from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
            from podcast_outreach.database.queries import media as media_queries
            from podcast_outreach.services.business_logic.enhanced_discovery_workflow import EnhancedDiscoveryWorkflow
            import asyncio
            
            try:
                # First, clean up any stale locks from previous runs
                cleaned = await cmd_queries.cleanup_stale_ai_description_locks(stale_minutes=60)
                if cleaned > 0:
                    logger.info(f"Cleaned up {cleaned} stale AI description locks")
                
                # Atomically acquire a batch of work
                discoveries = await cmd_queries.acquire_ai_description_work_batch(limit=20)
                if not discoveries:
                    logger.info("No discoveries available for AI description completion")
                    return
                
                logger.info(f"Acquired {len(discoveries)} discoveries for AI description generation")
                
                # Initialize workflow
                workflow = EnhancedDiscoveryWorkflow()
                
                # Process with controlled concurrency (max 3 concurrent AI calls)
                semaphore = asyncio.Semaphore(3)
                
                async def process_discovery(discovery):
                    async with semaphore:
                        discovery_id = discovery['id']
                        media_id = discovery['media_id']
                        media_name = discovery.get('media_name', 'Unknown')
                        
                        try:
                            logger.info(f"Generating AI description for media {media_id} ({media_name})")
                            
                            # Generate AI description
                            ai_desc = await workflow._generate_podcast_ai_description(media_id)
                            
                            if ai_desc:
                                # Update media with AI description
                                await media_queries.update_media_ai_description(media_id, ai_desc)
                                logger.info(f"Generated AI description for media {media_id}")
                                
                                # Release lock with success
                                await cmd_queries.release_ai_description_lock(discovery_id, success=True)
                            else:
                                logger.warning(f"Failed to generate AI description for media {media_id}")
                                # Release lock with failure
                                await cmd_queries.release_ai_description_lock(discovery_id, success=False)
                                
                        except Exception as e:
                            logger.error(f"Error generating AI description for discovery {discovery_id}: {e}")
                            # Always release lock on error
                            await cmd_queries.release_ai_description_lock(discovery_id, success=False)
                
                # Process all discoveries with timeout
                tasks = [process_discovery(discovery) for discovery in discoveries]
                
                # Wait for all with timeout (45 minutes max)
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=45 * 60  # 45 minutes
                    )
                except asyncio.TimeoutError:
                    logger.error("AI description completion timed out after 45 minutes")
                    # Locks will be cleaned up in next run
                        
            except Exception as e:
                logger.error(f"Error in AI description completion task: {e}", exc_info=True)
        
        async def _cleanup_wrapper():
            try:
                await ai_description_completion_logic()
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for ai_description_completion")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def run_workflow_health_check(self, task_id: str):
        """Run workflow health check to detect and fix common issues"""
        async def _cleanup_wrapper():
            try:
                from podcast_outreach.services.tasks.health_checker import WorkflowHealthChecker
                health_checker = WorkflowHealthChecker()
                result = await health_checker.run_health_check()
                logger.info(f"Health check completed: {result['issues_found']} issues found, {result['issues_fixed']} fixed")
                return result
            finally:
                self.cleanup_task(task_id)
        
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(_cleanup_wrapper())
            return task
        except RuntimeError:
            logger.warning("No event loop running for workflow_health_check")
            return self._executor.submit(asyncio.run, _cleanup_wrapper())
    
    def start_task(self, task_id: str, action: str) -> None:
        with self._lock:
            self.tasks[task_id] = {
                'action': action,
                'start_time': time.time(),
                'stop_flag': threading.Event(),
                'status': 'running'
            }
            logger.info(f"Task {task_id} for action '{action}' started.")
    
    def stop_task(self, task_id: str) -> bool:
        with self._lock:
            if task_id not in self.tasks:
                return False
            self.tasks[task_id]['stop_flag'].set()
            self.tasks[task_id]['status'] = 'stopping'
            logger.info(f"Task {task_id} for action '{self.tasks[task_id]['action']}' signaled to stop.")
            return True
    
    def get_stop_flag(self, task_id: str) -> Optional[threading.Event]:
        with self._lock:
            if task_id not in self.tasks:
                return None
            return self.tasks[task_id]['stop_flag']
    
    def cleanup_task(self, task_id: str) -> None:
        with self._lock:
            if task_id in self.tasks:
                action = self.tasks[task_id]['action']
                del self.tasks[task_id]
                logger.info(f"Task {task_id} for action '{action}' cleaned up.")
    
    def get_task_status(self, task_id: str) -> Optional[dict]:
        with self._lock:
            if task_id not in self.tasks:
                return None
            task = self.tasks[task_id]
            return {
                'task_id': task_id,
                'action': task['action'],
                'status': task['status'],
                'runtime': time.time() - task['start_time']
            }
    
    def list_tasks(self) -> Dict[str, dict]:
        with self._lock:
            return {
                task_id: {
                    'task_id': task_id,
                    'action': info['action'],
                    'status': info['status'],
                    'runtime': time.time() - info['start_time']
                }
                for task_id, info in self.tasks.items()
            }
    
    async def cleanup(self) -> None:
        logger.info("Cleaning up all tasks during application shutdown.")
        with self._lock:
            task_ids = list(self.tasks.keys())
            for task_id in task_ids:
                try:
                    self.tasks[task_id]['stop_flag'].set()
                    self.tasks[task_id]['status'] = 'stopped'
                    logger.info(f"Signaled task {task_id} to stop during shutdown.")
                except Exception as e:
                    logger.error(f"Error signaling task {task_id} to stop during shutdown: {e}")
            self.tasks.clear()
            logger.info(f"All {len(task_ids)} tasks cleared from manager.")
        
        # Shutdown executor
        self._executor.shutdown(wait=True)
        
        # Cleanup database resources
        await self.cleanup_resources()

# Global task manager instance
task_manager = TaskManager()