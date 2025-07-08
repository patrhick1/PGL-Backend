# Critical Startup Fix for Memory Issues

## Problem Identified
Your logs show the service is restarting multiple times and each restart is trying to process the same episodes simultaneously. This is causing memory to spike immediately on startup.

## Immediate Fix Required

### 1. Add Startup Delay in main.py
This prevents all tasks from starting simultaneously:

```python
# In podcast_outreach/main.py, after task scheduler initialization:

# Find this section:
scheduler = initialize_scheduler(task_manager)
await scheduler.start()
logger.info("Task scheduler started.")

# Add this right after:
if IS_PRODUCTION and os.getenv("DISABLE_STARTUP_TASKS") != "true":
    startup_delay = int(os.getenv("STARTUP_DELAY_SECONDS", "30"))
    logger.info(f"Production mode: Delaying initial task execution by {startup_delay} seconds")
    await asyncio.sleep(startup_delay)
```

### 2. Stagger Task Execution
Update task_scheduler.py to stagger task starts:

```python
# In _scheduler_loop, when triggering tasks:
if self._should_run_task(scheduled_task, current_time):
    # Add stagger delay between tasks
    if tasks_triggered > 0:
        await asyncio.sleep(5)  # 5 second delay between task starts
    
    # ... rest of task triggering logic
    tasks_triggered += 1
```

### 3. Environment Variables to Add Immediately

```env
# Critical memory controls
MAX_CONCURRENT_DOWNLOADS=1
GLOBAL_TRANSCRIPTION_LIMIT=1
CHUNK_CONCURRENCY=1
GEMINI_API_CONCURRENCY=1
MAX_BATCH_SIZE=1
MAX_FILE_SIZE_MB=150

# Startup controls
STARTUP_DELAY_SECONDS=60
DISABLE_STARTUP_TASKS=false

# Memory thresholds
MEMORY_WARNING_PERCENT=40
MEMORY_ERROR_PERCENT=50
```

### 4. Single Episode Processing Mode
Add this environment check to transcribe_episodes.py:

```python
# At the top of run_transcription_logic:
SINGLE_EPISODE_MODE = os.getenv("SINGLE_EPISODE_MODE", "false").lower() == "true"
if SINGLE_EPISODE_MODE:
    BATCH_SIZE = 1
    logger.warning("SINGLE EPISODE MODE: Processing only 1 episode at a time")
```

## Why This Happens

1. Render restarts the service when memory is exceeded
2. Each restart triggers all scheduled tasks immediately
3. Multiple tasks try to process the same episodes
4. Memory spikes immediately, causing another restart
5. This creates a restart loop

## Testing the Fix

1. Set `DISABLE_STARTUP_TASKS=true` temporarily
2. Deploy and let the service stabilize
3. Manually trigger one task at a time via API
4. Monitor memory usage
5. Once stable, set `DISABLE_STARTUP_TASKS=false` with `STARTUP_DELAY_SECONDS=120`

## Long-term Solution

Consider implementing:
1. A distributed lock system (Redis) to prevent duplicate processing
2. Checkpoint system to track processed episodes
3. Move to a job queue system (Celery, RQ) instead of in-process scheduling
4. Use a separate worker service for heavy processing