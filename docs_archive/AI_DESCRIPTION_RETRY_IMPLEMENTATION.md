# AI Description Retry Mechanism Implementation

## Problem Solved
Previously, when a discovery completed enrichment but lacked an AI description, it would fail vetting and only retry:
- Every 15 minutes (vetting pipeline) - but would keep failing
- Once daily at 03:00 (enrichment pipeline) - creating up to 24-hour delays

## Solution Implemented

### 1. **New Query Added** (`campaign_media_discoveries.py`)
```python
async def get_discoveries_needing_ai_description(limit: int = 20) -> List[Dict[str, Any]]:
    """Get discoveries where enrichment is complete but AI description is missing."""
```
This query finds:
- Discoveries with `enrichment_status = 'completed'`
- `vetting_status = 'pending'`
- Media missing AI description
- Ordered by oldest first

### 2. **New Scheduled Task** (`task_scheduler.py`)
```python
# AI description completion - every 10 minutes
self.register_task(ScheduledTask(
    name="ai_description_completion",
    task_function=self._run_ai_description_completion,
    schedule_type=ScheduleType.INTERVAL,
    interval_seconds=10 * 60  # 10 minutes
))
```

### 3. **Task Implementation** (`manager.py`)
Added `run_ai_description_completion` method that:
- Fetches up to 20 discoveries needing AI descriptions
- Uses `EnhancedDiscoveryWorkflow._generate_podcast_ai_description`
- Updates media with generated AI description
- Logs progress and errors

## How It Works

### Automatic Flow:
1. **Discovery completes enrichment** but lacks AI description
2. **Every 10 minutes**: AI description completion task runs
3. **Generates missing AI descriptions** for up to 20 discoveries
4. **Next vetting cycle** (every 15 min) picks up these discoveries
5. **Vetting succeeds** and creates matches if score ≥ 6.0

### Benefits:
- ✅ **No 24-hour delays** - AI descriptions generated every 10 minutes
- ✅ **Automatic progression** - discoveries flow seamlessly through pipeline
- ✅ **Resource efficient** - processes in batches of 20
- ✅ **Fault tolerant** - continues on individual failures

## Current Scheduled Tasks Summary

| Task | Frequency | Purpose |
|------|-----------|---------|
| Transcription | 30 minutes | Process flagged episodes |
| Vetting | 15 minutes | Vet enriched discoveries |
| AI Description | **10 minutes** | Complete missing AI descriptions |
| Episode Sync | Daily 02:00 | Sync new episodes |
| Enrichment | Daily 03:00 | Full enrichment pipeline |
| Qualitative | 2 hours | Assess match quality |

## Monitoring

To check if discoveries are stuck waiting for AI descriptions:
```sql
SELECT COUNT(*) as stuck_discoveries
FROM campaign_media_discoveries cmd
JOIN media m ON cmd.media_id = m.media_id
WHERE cmd.enrichment_status = 'completed'
AND cmd.vetting_status = 'pending'
AND (m.ai_description IS NULL OR m.ai_description = '');
```

## Note on Implementation Choice

We chose **Solution 1** (dedicated AI description task) over modifying the vetting pipeline because:
1. Keeps concerns separated - vetting focuses on vetting
2. More frequent runs (10 min vs 15 min)
3. Easier to monitor and debug
4. Can be disabled/tuned independently

The system now ensures discoveries progress through the pipeline without long delays!