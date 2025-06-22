# Episode Summaries Compilation Fix

## Problem Summary

We discovered a critical issue where:
1. Episodes were being transcribed and had `ai_episode_summary` values
2. But the `episode_summaries_compiled` field in the media table remained NULL
3. This caused `campaign_media_discoveries` to get stuck in "pending" status
4. The discovery workflow couldn't progress to vetting and match creation

## Root Causes

### 1. Missing EnrichmentOrchestrator.enrich_media() Method
- `discovery_processing.py` was calling `enrichment_orchestrator.enrich_media(media_id)`
- But this method didn't exist in `EnrichmentOrchestrator` class
- This caused enrichment to fail silently

### 2. Wrong Database Update Method
- Quality score updates were using `update_media_enrichment_data()` 
- Instead of `update_media_quality_score()`
- Only `update_media_quality_score()` compiles episode summaries
- See `media.py` lines 493-545 for the implementation

### 3. Workflow Dependencies
The discovery workflow expected:
- Media to be fully enriched (AI description, quality score, episode summaries)
- But episode summaries were never compiled due to the wrong update method
- This prevented discoveries from moving to "completed" status

## Fixes Applied

### 1. Added enrich_media() Method
Created the missing method in `enrichment_orchestrator.py`:
```python
async def enrich_media(self, media_id: int) -> bool:
    # 1. Run core enrichment (social data, contact info)
    # 2. Generate AI description if missing
    # 3. Update quality score AND compile episode summaries
    # Uses update_media_quality_score() to ensure summaries are compiled
```

### 2. Fixed Quality Score Updates
Changed all quality score updates to use the correct method:
```python
# OLD (wrong):
await media_queries.update_media_enrichment_data(media_id, score_components)

# NEW (correct):
await media_queries.update_media_quality_score(media_id, quality_score_val)
```

### 3. Created Fix Scripts
- `fix_stuck_discoveries.py` - Finds and fixes all stuck discoveries
- `fix_media_11.py` - Quick fix for specific media records

## How to Run the Fix

### For Specific Media (like media_id 11):
```bash
cd /mnt/c/Users/ebube/Documents/PGL - Postgres/podcast_outreach
python fix_media_11.py
```

### For All Stuck Discoveries:
```bash
cd /mnt/c/Users/ebube/Documents/PGL - Postgres/podcast_outreach
python fix_stuck_discoveries.py
```

## Prevention

1. **Always use `update_media_quality_score()`** when updating quality scores
2. **Test discovery workflow end-to-end** after any changes
3. **Monitor for stuck discoveries** with this query:
```sql
SELECT COUNT(*) as stuck_count
FROM campaign_media_discoveries cmd
JOIN media m ON cmd.media_id = m.media_id
WHERE cmd.enrichment_status = 'pending'
AND m.quality_score IS NOT NULL
AND EXISTS (
    SELECT 1 FROM episodes e 
    WHERE e.media_id = m.media_id 
    AND e.ai_episode_summary IS NOT NULL
);
```

## Affected Code Files

1. `/services/enrichment/enrichment_orchestrator.py`
   - Added `enrich_media()` method
   - Fixed `run_quality_score_updates()` to use correct update method
   - Fixed `_update_quality_score_for_media()` to use correct update method

2. `/services/business_logic/discovery_processing.py`
   - No changes needed (now calls the newly added method)

3. `/database/queries/media.py`
   - No changes (already had the correct implementation)

## Verification

After running the fix, verify:
1. `episode_summaries_compiled` is populated for affected media
2. `campaign_media_discoveries` status changes from "pending" to "completed"
3. Discoveries are now available for vetting

Query to check:
```sql
SELECT 
    m.media_id,
    m.name,
    m.episode_summaries_compiled IS NOT NULL as has_compiled_summaries,
    cmd.enrichment_status,
    COUNT(e.episode_id) as transcribed_episodes
FROM media m
JOIN campaign_media_discoveries cmd ON m.media_id = cmd.media_id
LEFT JOIN episodes e ON m.media_id = e.media_id AND e.ai_episode_summary IS NOT NULL
WHERE m.media_id = 11
GROUP BY m.media_id, m.name, m.episode_summaries_compiled, cmd.enrichment_status;
```