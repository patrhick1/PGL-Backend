# Race Condition Protection Implementation

## Overview
We've implemented multi-layer protection against race conditions in the discovery → enrichment → vetting → matching pipeline.

## 1. Database-Level Locking (Primary Protection)

### AI Description Completion
- **New Functions Added** to `campaign_media_discoveries.py`:
  - `acquire_ai_description_work_batch()` - Atomically acquires work using `FOR UPDATE SKIP LOCKED`
  - `release_ai_description_lock()` - Releases lock after processing
  - `cleanup_stale_ai_description_locks()` - Cleans up expired locks

### Vetting Pipeline
- **New Function Added**:
  - `acquire_vetting_work_batch()` - Atomically acquires vetting work with row-level locking

### How It Works:
```sql
-- Atomic work acquisition pattern
WITH candidates AS (
    SELECT id FROM campaign_media_discoveries
    WHERE status = 'pending'
    AND (lock_field IS NULL OR lock_field NOT LIKE 'PROCESSING:%')
    LIMIT 20
    FOR UPDATE SKIP LOCKED  -- Key: Skip rows locked by other workers
)
UPDATE campaign_media_discoveries
SET lock_field = 'PROCESSING:TYPE:UUID:TIMESTAMP'
FROM candidates
WHERE campaign_media_discoveries.id = candidates.id
RETURNING *;
```

## 2. Application-Level Concurrency Controls

### Task Scheduler Enhancements (`task_scheduler.py`)
- **Running Task Tracking**: Prevents duplicate task starts
- **Semaphore Controls**: Limits concurrent executions per task type
  ```python
  self.task_semaphores = {
      'ai_description_completion': asyncio.Semaphore(1),  # Only 1 concurrent
      'vetting_pipeline': asyncio.Semaphore(1),           # Only 1 concurrent
      'enrichment_pipeline': asyncio.Semaphore(1),        # Only 1 concurrent
      'transcription_pipeline': asyncio.Semaphore(2),     # Max 2 concurrent
  }
  ```

### Task Manager Updates (`manager.py`)
- **AI Description Task**: 
  - Uses atomic work acquisition
  - Processes with controlled concurrency (max 3 concurrent AI calls)
  - Always releases locks (success or failure)
  - 45-minute timeout protection

## 3. Lock Management Strategy

### Lock Storage
- Uses existing `enrichment_error` and `vetting_error` fields temporarily for locks
- Lock format: `PROCESSING:TYPE:UUID:TIMESTAMP`
- No schema changes required

### Lock Lifecycle
1. **Acquisition**: Atomic SELECT + UPDATE in single transaction
2. **Processing**: Work performed with lock held
3. **Release**: Lock cleared on completion (success or failure)
4. **Cleanup**: Stale locks cleaned up after 60 minutes

## 4. Resource Protection

### API Rate Limiting
```python
# In AI description completion task
semaphore = asyncio.Semaphore(3)  # Max 3 concurrent AI calls

async def process_discovery(discovery):
    async with semaphore:  # Enforces concurrency limit
        # Generate AI description
```

### Timeout Protection
```python
await asyncio.wait_for(
    asyncio.gather(*tasks, return_exceptions=True),
    timeout=45 * 60  # 45 minutes max
)
```

## 5. Benefits of This Implementation

### ✅ Prevents Race Conditions
- **Database locks** prevent multiple workers from processing same record
- **Skip locked** ensures workers find available work efficiently
- **Atomic operations** guarantee consistency

### ✅ Resource Efficiency
- **Controlled concurrency** prevents API overload
- **Batch processing** reduces overhead
- **Smart retries** via lock cleanup

### ✅ Fault Tolerance
- **Always release locks** even on errors
- **Automatic cleanup** of stale locks
- **Graceful degradation** if one worker fails

### ✅ No Schema Changes
- Uses existing error fields for locks
- Fully backward compatible
- Easy to deploy

## 6. Monitoring & Debugging

### Check for Stuck Locks
```sql
-- AI description locks
SELECT COUNT(*) as stuck_ai_locks
FROM campaign_media_discoveries
WHERE enrichment_error LIKE 'PROCESSING:AI_DESC:%'
AND updated_at < NOW() - INTERVAL '60 minutes';

-- Vetting locks
SELECT COUNT(*) as stuck_vetting_locks
FROM campaign_media_discoveries
WHERE vetting_error LIKE 'PROCESSING:VETTING:%'
AND updated_at < NOW() - INTERVAL '60 minutes';
```

### View Active Processing
```sql
-- Currently processing AI descriptions
SELECT id, media_id, enrichment_error, updated_at
FROM campaign_media_discoveries
WHERE enrichment_error LIKE 'PROCESSING:AI_DESC:%'
ORDER BY updated_at DESC;
```

## 7. Deployment Notes

1. **No database migrations needed** - uses existing columns
2. **Backward compatible** - old tasks continue working
3. **Gradual rollout possible** - can run alongside existing code
4. **Self-healing** - stale locks cleaned automatically

## 8. Future Improvements

If needed, we could add:
1. Dedicated `processing_lock` and `processing_started_at` columns
2. Redis-based distributed locks for multi-instance deployments
3. Metrics tracking for lock contention
4. Advisory locks for long-running operations

The current implementation provides robust protection against race conditions while being simple to deploy and maintain.