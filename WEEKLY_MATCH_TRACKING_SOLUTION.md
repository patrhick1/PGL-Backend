# Weekly Match Tracking Solution

## Problem
The system has a `weekly_match_allowance` field in the `client_profiles` table but wasn't enforcing it. This led to campaign "01e8da81-b8e6-419b-a8a6-4ad15d549343" creating over 150 matches when it should have been limited by the weekly allowance.

## Root Cause
When discoveries with `vetting_score >= 50` were automatically converted to match_suggestions, the system was:
1. Not checking if the weekly limit had been reached
2. Not incrementing the `current_weekly_matches` counter

## Solution Components

### 1. Database Functions (Run Migration)
```bash
pgl_env/Scripts/python.exe podcast_outreach/migrations/add_match_tracking_functions.py
```

This creates:
- `check_and_increment_weekly_matches(person_id, increment)` - Atomically checks limit and increments counter
- `reset_weekly_matches()` - Resets all weekly counters (for scheduler)
- `get_match_allowance_status(person_id)` - Gets current status
- `get_person_id_from_campaign(campaign_id)` - Helper function

### 2. Discovery Processing Update
Updated `_create_match_and_review_task` in `discovery_processing.py` to:
1. Get the person_id from the campaign
2. Call `check_and_increment_weekly_matches` before creating a match
3. If limit is reached, mark discovery as "limit_reached" and skip match creation
4. Only create match if within limits

### 3. Weekly Reset
Add to scheduler to run weekly (e.g., Monday at midnight):
```sql
SELECT reset_weekly_matches();
```

## How It Works

### Match Creation Flow:
1. Discovery gets vetted with score >= 50
2. System attempts to create match
3. **NEW**: Check weekly limit using `check_and_increment_weekly_matches`
4. If allowed: Create match and increment counter atomically
5. If not allowed: Mark discovery as "limit_reached" and log warning

### Weekly Limits:
- Stored in `client_profiles.weekly_match_allowance`
- Counter in `client_profiles.current_weekly_matches`
- Reset tracked by `client_profiles.last_weekly_match_reset`

### Atomic Operation:
The PostgreSQL function ensures:
- No race conditions (uses row locking)
- Automatic weekly reset if needed
- Returns clear status (allowed/denied with counts)

## Benefits

1. **Enforces Limits**: No more unlimited match creation
2. **Atomic Checks**: Thread-safe counter updates
3. **Automatic Resets**: Handles weekly reset logic
4. **Clear Feedback**: Shows current count vs limit
5. **Retroactive Fix**: Migration counts existing matches for the current week

## Monitoring

Check current status for any person:
```sql
SELECT * FROM get_match_allowance_status(person_id);
```

See discoveries that hit the limit:
```sql
SELECT * FROM campaign_media_discoveries 
WHERE vetting_status = 'limit_reached'
AND updated_at > CURRENT_DATE - INTERVAL '7 days';
```

## Future Improvements

1. Add UI to show match allowance status
2. Send notifications when approaching limit
3. Allow manual limit increases for special cases
4. Track limit hits in analytics