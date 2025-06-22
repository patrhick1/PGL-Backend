# Workflow Self-Healing Mechanisms

## Overview

The podcast discovery workflow now includes automatic detection and correction of common issues, eliminating the need for manual intervention in most cases.

## Self-Healing Components

### 1. Workflow Health Checker (Every 30 Minutes)
Located in: `services/tasks/health_checker.py`

Automatically detects and fixes:
- **Missing Episode Summaries**: Compiles summaries when episodes are transcribed but compilation is missing
- **Stuck Enrichment Statuses**: Corrects discoveries marked as pending when enrichment is actually complete
- **Stale Processing Locks**: Clears locks older than 60 minutes that prevent retry
- **Failed Vetting**: Resets transient failures (timeouts, errors) for retry

### 2. AI Description Completion Task (Every 10 Minutes)
- Finds media missing AI descriptions after enrichment
- Uses atomic work acquisition to prevent race conditions
- Automatically releases locks on completion or failure

### 3. Lock Cleanup Mechanisms
- **AI Description Locks**: Cleaned up after 60 minutes
- **Vetting Locks**: Cleaned up after 60 minutes
- Prevents discoveries from being stuck indefinitely

### 4. Enhanced Error Recovery
- **404 Audio Files**: Marked as failed immediately without retry
- **Transient Failures**: Automatically retried after cooldown period
- **Race Condition Protection**: Atomic work acquisition prevents duplicate processing

## How It Works

### Discovery Workflow States
```
Discovery Created → Enrichment → AI Description → Vetting → Match Creation
                      ↓              ↓              ↓            ↓
                   [Health]      [Health]      [Health]    [Health Check]
                    Check]        Check]        Check]
```

### Health Check Process (Every 30 Minutes)
1. **Scan for Issues**
   - Queries database for stuck/incomplete records
   - Identifies missing data or wrong statuses

2. **Apply Fixes**
   - Compiles missing episode summaries
   - Updates incorrect statuses
   - Clears stale locks
   - Resets failed attempts for retry

3. **Log Results**
   - Reports number of issues found and fixed
   - Details specific corrections made

## Common Issues Auto-Fixed

### Issue 1: Episode Summaries Not Compiled
**Symptom**: Episodes transcribed but `episode_summaries_compiled` is null
**Auto-Fix**: Health checker compiles summaries using `update_media_quality_score()`

### Issue 2: Enrichment Stuck as "Pending"
**Symptom**: Media fully enriched but discovery shows enrichment_status='pending'
**Auto-Fix**: Health checker updates status to 'completed' when all enrichment criteria met

### Issue 3: Vetting Process Locked
**Symptom**: Vetting shows "PROCESSING:" lock in error field
**Auto-Fix**: Lock cleanup removes stale locks after 60 minutes

### Issue 4: AI Description Generation Failed
**Symptom**: Media enriched but ai_description is null
**Auto-Fix**: AI description task retries generation every 10 minutes

### Issue 5: Vetting Failed Due to Timeout
**Symptom**: Vetting marked as failed with timeout/error message
**Auto-Fix**: Health checker resets to pending for retry after 2 hours

## Manual Intervention

While most issues are auto-corrected, you can manually trigger corrections:

### Run Health Check Immediately
```python
from podcast_outreach.services.tasks.health_checker import run_workflow_health_check
results = await run_workflow_health_check()
```

### Fix Specific Media
```python
python fix_media_11.py  # Fix specific media ID
python fix_stuck_discoveries.py  # Fix all stuck discoveries
```

## Monitoring

Check health check results in logs:
```
grep "Health check completed" app.log
grep "issues found" app.log
```

## Configuration

Adjust timing in `services/scheduler/task_scheduler.py`:
- Health Check: Default 30 minutes
- AI Description: Default 10 minutes
- Lock Cleanup: Default 60 minutes stale threshold

## Benefits

1. **No Manual Scripts**: Issues are detected and fixed automatically
2. **Continuous Operation**: Workflow continues even with transient failures
3. **Race Condition Safe**: Atomic operations prevent conflicts
4. **Self-Documenting**: Health check logs show what was fixed
5. **Configurable**: Adjust thresholds and intervals as needed

## Future Improvements

1. **Metrics Dashboard**: Track health check performance over time
2. **Alerting**: Notify when issues exceed thresholds
3. **Predictive Fixes**: Detect patterns and prevent issues
4. **Custom Health Checks**: Add domain-specific validations