# podcast_outreach/services/scheduler/task_scheduler.py

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Callable, Optional, Any
from dataclasses import dataclass
from enum import Enum

from podcast_outreach.services.tasks.manager import TaskManager
from podcast_outreach.services.database_service import DatabaseService

logger = logging.getLogger(__name__)

class ScheduleType(Enum):
    INTERVAL = "interval"
    DAILY = "daily"
    WEEKLY = "weekly"

@dataclass
class ScheduledTask:
    name: str
    task_function: Callable
    schedule_type: ScheduleType
    interval_seconds: Optional[int] = None
    time_of_day: Optional[str] = None  # Format: "HH:MM"
    day_of_week: Optional[int] = None  # 0=Monday, 6=Sunday
    last_run: Optional[datetime] = None
    enabled: bool = True

class TaskScheduler:
    """
    Centralized scheduler for background tasks with different scheduling patterns.
    Provides automated execution of periodic processes without manual triggers.
    """
    
    def __init__(self, task_manager: TaskManager):
        self.task_manager = task_manager
        self.scheduled_tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self.scheduler_task: Optional[asyncio.Task] = None
        
        # Track running tasks to prevent concurrent execution
        self.running_tasks: Dict[str, asyncio.Task] = {}
        
        # Semaphores for controlling concurrent execution per task type
        self.task_semaphores: Dict[str, asyncio.Semaphore] = {
            'ai_description_completion': asyncio.Semaphore(1),  # Only 1 concurrent
            'vetting_pipeline': asyncio.Semaphore(1),           # Only 1 concurrent
            'enrichment_pipeline': asyncio.Semaphore(1),        # Only 1 concurrent
            'transcription_pipeline': asyncio.Semaphore(2),     # Max 2 concurrent
            'episode_sync': asyncio.Semaphore(1),               # Only 1 concurrent
            'qualitative_assessment': asyncio.Semaphore(1),     # Only 1 concurrent
            'workflow_health_check': asyncio.Semaphore(1)       # Only 1 concurrent
        }
        
        logger.info("TaskScheduler initialized with concurrency controls")
    
    def register_task(self, scheduled_task: ScheduledTask):
        """Register a task for automated scheduling"""
        self.scheduled_tasks[scheduled_task.name] = scheduled_task
        logger.info(f"Registered scheduled task: {scheduled_task.name}")
    
    def register_default_tasks(self):
        """Register the default set of automated background tasks"""
        
        # Transcription pipeline - every 30 minutes
        self.register_task(ScheduledTask(
            name="transcription_pipeline",
            task_function=self._run_transcription_pipeline,
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=30 * 60  # 30 minutes
        ))
        
        # Vetting pipeline - every 15 minutes  
        self.register_task(ScheduledTask(
            name="vetting_pipeline",
            task_function=self._run_vetting_pipeline,
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=15 * 60  # 15 minutes
        ))
        
        # Episode sync - daily at 02:00
        self.register_task(ScheduledTask(
            name="episode_sync",
            task_function=self._run_episode_sync,
            schedule_type=ScheduleType.DAILY,
            time_of_day="02:00"
        ))
        
        # Full enrichment pipeline - daily at 03:00
        self.register_task(ScheduledTask(
            name="enrichment_pipeline",
            task_function=self._run_enrichment_pipeline,
            schedule_type=ScheduleType.DAILY,
            time_of_day="03:00"
        ))
        
        # Qualitative match assessment - every 2 hours
        self.register_task(ScheduledTask(
            name="qualitative_assessment",
            task_function=self._run_qualitative_assessment,
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=2 * 60 * 60  # 2 hours
        ))
        
        # AI description completion - every 10 minutes
        self.register_task(ScheduledTask(
            name="ai_description_completion",
            task_function=self._run_ai_description_completion,
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=10 * 60  # 10 minutes
        ))
        
        # Workflow health check - every 30 minutes
        self.register_task(ScheduledTask(
            name="workflow_health_check",
            task_function=self._run_workflow_health_check,
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=30 * 60  # 30 minutes
        ))
        
        # Automated campaign discovery - every 30 minutes
        self.register_task(ScheduledTask(
            name="automated_campaign_discovery",
            task_function=self._run_automated_discovery,
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=30 * 60  # 30 minutes
        ))
        
        # Weekly reset of ALL counts (free and paid users) - Mondays at 00:00
        self.register_task(ScheduledTask(
            name="reset_all_weekly_counts",
            task_function=self._reset_all_weekly_counts,
            schedule_type=ScheduleType.WEEKLY,
            day_of_week=0,  # Monday
            time_of_day="00:00"
        ))
        
        # Daily health check for weekly reset system
        self.register_task(ScheduledTask(
            name="weekly_reset_health_check",
            task_function=self._check_weekly_reset_health,
            schedule_type=ScheduleType.DAILY,
            time_of_day="10:00"  # 10 AM UTC daily
        ))
        
        logger.info(f"Registered {len(self.scheduled_tasks)} default background tasks")
    
    async def start(self):
        """Start the scheduler"""
        if self.running:
            logger.warning("TaskScheduler is already running")
            return
        
        self.running = True
        try:
            loop = asyncio.get_running_loop()
            self.scheduler_task = loop.create_task(self._scheduler_loop())
        except RuntimeError:
            logger.error("No running event loop to start scheduler")
            self.running = False
            return
        logger.info("TaskScheduler started")
    
    async def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("TaskScheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop with concurrency controls"""
        while self.running:
            try:
                current_time = datetime.now()
                
                for task_name, scheduled_task in self.scheduled_tasks.items():
                    if not scheduled_task.enabled:
                        continue
                    
                    if self._should_run_task(scheduled_task, current_time):
                        # Check if task is already running
                        if task_name in self.running_tasks and not self.running_tasks[task_name].done():
                            logger.info(f"Task {task_name} is already running, skipping this cycle")
                            continue
                        
                        # Check semaphore availability
                        semaphore = self.task_semaphores.get(task_name)
                        if semaphore and semaphore.locked():
                            logger.info(f"Max concurrent {task_name} tasks reached, skipping")
                            continue
                        
                        logger.info(f"Triggering scheduled task: {task_name}")
                        
                        # Create task with semaphore protection
                        if semaphore:
                            self.running_tasks[task_name] = asyncio.create_task(
                                self._run_task_with_semaphore(scheduled_task, semaphore, current_time)
                            )
                        else:
                            self.running_tasks[task_name] = asyncio.create_task(
                                self._run_task(scheduled_task, current_time)
                            )
                
                # Sleep for 60 seconds before next check
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    async def _run_task_with_semaphore(self, scheduled_task: ScheduledTask, semaphore: asyncio.Semaphore, current_time: datetime):
        """Run a task with semaphore protection"""
        async with semaphore:
            await self._run_task(scheduled_task, current_time)
    
    async def _run_task(self, scheduled_task: ScheduledTask, current_time: datetime):
        """Run a scheduled task"""
        try:
            await scheduled_task.task_function()
            scheduled_task.last_run = current_time
        except Exception as e:
            logger.error(f"Error running scheduled task {scheduled_task.name}: {e}", exc_info=True)
    
    def _should_run_task(self, task: ScheduledTask, current_time: datetime) -> bool:
        """Determine if a task should run based on its schedule"""
        if task.schedule_type == ScheduleType.INTERVAL:
            if task.last_run is None:
                return True
            
            elapsed = (current_time - task.last_run).total_seconds()
            return elapsed >= task.interval_seconds
        
        elif task.schedule_type == ScheduleType.DAILY:
            if task.last_run is None:
                return self._is_time_to_run_daily(task, current_time)
            
            # Check if it's a new day and the right time
            if current_time.date() > task.last_run.date():
                return self._is_time_to_run_daily(task, current_time)
            
            return False
        
        elif task.schedule_type == ScheduleType.WEEKLY:
            if task.last_run is None:
                return self._is_time_to_run_weekly(task, current_time)
            
            # Check if it's the right day and time, and hasn't run this week
            days_since_last = (current_time - task.last_run).days
            if days_since_last >= 7:
                return self._is_time_to_run_weekly(task, current_time)
            
            return False
        
        return False
    
    def _is_time_to_run_daily(self, task: ScheduledTask, current_time: datetime) -> bool:
        """Check if it's the right time of day to run a daily task"""
        if not task.time_of_day:
            return False
        
        target_hour, target_minute = map(int, task.time_of_day.split(':'))
        return (current_time.hour == target_hour and 
                current_time.minute == target_minute)
    
    def _is_time_to_run_weekly(self, task: ScheduledTask, current_time: datetime) -> bool:
        """Check if it's the right day and time to run a weekly task"""
        if task.day_of_week is None or not task.time_of_day:
            return False
        
        # Check day of week (0=Monday, 6=Sunday)
        if current_time.weekday() != task.day_of_week:
            return False
        
        return self._is_time_to_run_daily(task, current_time)
    
    # Task execution methods that interface with TaskManager
    
    async def _run_transcription_pipeline(self):
        """Run transcription pipeline"""
        task_id = f"scheduled_transcription_{int(datetime.now().timestamp())}"
        self.task_manager.start_task(task_id, "scheduled_transcription_pipeline")
        self.task_manager.run_transcription(task_id)
    
    async def _run_vetting_pipeline(self):
        """Run vetting pipeline"""
        task_id = f"scheduled_vetting_{int(datetime.now().timestamp())}"
        self.task_manager.start_task(task_id, "scheduled_vetting_pipeline")
        self.task_manager.run_vetting_pipeline(task_id)
    
    async def _run_episode_sync(self):
        """Run episode sync"""
        task_id = f"scheduled_episode_sync_{int(datetime.now().timestamp())}"
        self.task_manager.start_task(task_id, "scheduled_episode_sync")
        self.task_manager.run_episode_sync(task_id)
    
    async def _run_enrichment_pipeline(self):
        """Run enrichment pipeline"""
        task_id = f"scheduled_enrichment_{int(datetime.now().timestamp())}"
        self.task_manager.start_task(task_id, "scheduled_enrichment_pipeline")
        self.task_manager.run_enrichment_pipeline(task_id)
    
    async def _run_qualitative_assessment(self):
        """Run qualitative match assessment"""
        task_id = f"scheduled_qualitative_{int(datetime.now().timestamp())}"
        self.task_manager.start_task(task_id, "scheduled_qualitative_assessment")
        self.task_manager.run_qualitative_match_assessment(task_id)
    
    async def _run_ai_description_completion(self):
        """Complete AI descriptions for enriched media."""
        task_id = f"scheduled_ai_description_{int(datetime.now().timestamp())}"
        self.task_manager.start_task(task_id, "scheduled_ai_description_completion")
        self.task_manager.run_ai_description_completion(task_id)
    
    async def _run_workflow_health_check(self):
        """Run workflow health check to detect and fix common issues."""
        task_id = f"scheduled_health_check_{int(datetime.now().timestamp())}"
        self.task_manager.start_task(task_id, "scheduled_workflow_health_check")
        self.task_manager.run_workflow_health_check(task_id)
    
    async def _run_automated_discovery(self):
        """Run automated campaign discovery check"""
        task_id = f"scheduled_auto_discovery_{int(datetime.now().timestamp())}"
        self.task_manager.start_task(task_id, "scheduled_automated_discovery")
        self.task_manager.run_automated_discovery(task_id)
    
    async def _reset_all_weekly_counts(self):
        """Reset weekly counts for ALL users (free and paid)"""
        task_id = f"scheduled_weekly_reset_{int(datetime.now().timestamp())}"
        self.task_manager.start_task(task_id, "scheduled_weekly_reset")
        self.task_manager.reset_all_weekly_counts(task_id)
    
    async def _check_weekly_reset_health(self):
        """Check health of weekly reset system"""
        task_id = f"scheduled_reset_health_{int(datetime.now().timestamp())}"
        self.task_manager.start_task(task_id, "scheduled_reset_health_check")
        self.task_manager.check_weekly_reset_health(task_id)
    
    def get_task_status(self) -> Dict[str, Any]:
        """Get status of all scheduled tasks"""
        return {
            "scheduler_running": self.running,
            "tasks": {
                name: {
                    "enabled": task.enabled,
                    "schedule_type": task.schedule_type.value,
                    "last_run": task.last_run.isoformat() if task.last_run else None,
                    "interval_seconds": task.interval_seconds,
                    "time_of_day": task.time_of_day,
                    "day_of_week": task.day_of_week
                }
                for name, task in self.scheduled_tasks.items()
            }
        }
    
    def enable_task(self, task_name: str):
        """Enable a specific scheduled task"""
        if task_name in self.scheduled_tasks:
            self.scheduled_tasks[task_name].enabled = True
            logger.info(f"Enabled scheduled task: {task_name}")
    
    def disable_task(self, task_name: str):
        """Disable a specific scheduled task"""
        if task_name in self.scheduled_tasks:
            self.scheduled_tasks[task_name].enabled = False
            logger.info(f"Disabled scheduled task: {task_name}")

# Global scheduler instance
scheduler: Optional[TaskScheduler] = None

def get_scheduler() -> Optional[TaskScheduler]:
    """Get the global scheduler instance"""
    return scheduler

def initialize_scheduler(task_manager: TaskManager) -> TaskScheduler:
    """Initialize the global scheduler"""
    global scheduler
    scheduler = TaskScheduler(task_manager)
    # Register default tasks including AI description completion
    scheduler.register_default_tasks()
    return scheduler