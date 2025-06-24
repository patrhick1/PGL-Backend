# Enhanced MediaFetcher - Discovery Tracking Fix

## Overview

This document describes the fix implemented to ensure that **all discovered podcasts** (both new and existing) are properly tracked in the `campaign_media_discoveries` table when running podcast discovery for a campaign.

## The Problem

Previously, when the podcast discovery process found podcasts that already existed in the database (from previous campaigns), it would:
1. Skip adding them to the media table (correct behavior to avoid duplicates)
2. **BUT** also skip creating a `campaign_media_discoveries` record (incorrect behavior)

This meant that existing podcasts weren't being considered as "discoveries" for new campaigns, preventing match creation between existing media and new campaigns.

## The Solution

Enhanced the existing MediaFetcher (`podcast_fetcher.py`) that:
1. Updates the `fetch_podcasts_for_campaign` method
2. Tracks whether each discovered podcast is new or existing
3. Creates `campaign_media_discoveries` records for ALL discovered podcasts (up to max_matches limit)
4. Only publishes MEDIA_CREATED events for podcasts with new discovery records

## Implementation Details

### Key Changes

1. **Enhanced Discovery Tracking**
   ```python
   # In _search_listennotes_with_tracking and _search_podscan_with_tracking
   
   # Check if media exists
   existing_media_in_db = await self._get_existing_media_by_identifiers(item, source)
   is_new = existing_media_in_db is None
   
   # Upsert media (updates existing or creates new)
   media_id = await self.merge_and_upsert_media(
       enriched, source, campaign_uuid, keyword,
       skip_discovery_tracking=True  # We handle discovery separately
   )
   
   # Track both new and existing media
   media_results.append((media_id, is_new))
   ```

2. **Discovery Record Creation**
   ```python
   # Create discovery records for ALL media (new and existing)
   for media_id, keyword, is_new_media in unique_discovered_media:
       if new_discoveries_count >= max_matches:
           break
       
       # Check if discovery already exists
       exists = await media_queries.check_campaign_media_discovery_exists(
           campaign_uuid, media_id
       )
       
       if not exists:
           # Create new discovery record
           discovery_created = await media_queries.track_campaign_media_discovery(
               campaign_uuid, media_id, keyword
           )
   ```

### Files Updated

1. **Updated**: `podcast_outreach/services/media/podcast_fetcher.py`
   - Enhanced the existing MediaFetcher with new discovery tracking logic
   - Added helper methods for tracking whether media is new or existing
   - Modified to create discovery records for ALL discovered podcasts

## Testing

Run the test script to verify the fix:

```bash
python test_enhanced_media_fetcher.py
```

The test will:
1. Select a campaign with keywords
2. Run discovery with a small limit (5 matches)
3. Show which discoveries are for NEW vs EXISTING podcasts
4. Verify that discovery records are created for both

## Expected Behavior

After this fix, when discovering podcasts for a campaign:

1. **New Podcasts**: 
   - Added to media table ✓
   - Discovery record created ✓
   - Episodes fetched ✓
   - MEDIA_CREATED event published ✓

2. **Existing Podcasts**:
   - Media record updated (if needed) ✓
   - Discovery record created ✓
   - Episodes NOT re-fetched (already have them) ✓
   - MEDIA_CREATED event published ✓

## Migration Notes

No database migration required. The fix only changes the application logic to properly use the existing `campaign_media_discoveries` table.

## Monitoring

To monitor the fix effectiveness:

```sql
-- Check recent discoveries showing new vs existing media
SELECT 
    cmd.discovery_id,
    cmd.discovered_at,
    m.name as podcast_name,
    CASE 
        WHEN m.created_at > cmd.discovered_at - INTERVAL '1 minute' 
        THEN 'NEW' 
        ELSE 'EXISTING' 
    END as media_status,
    cmd.discovery_keyword,
    c.campaign_name
FROM campaign_media_discoveries cmd
JOIN media m ON m.media_id = cmd.media_id
JOIN campaigns c ON c.campaign_id = cmd.campaign_id
ORDER BY cmd.discovered_at DESC
LIMIT 20;
```

## Rollback

If needed, to rollback to the original behavior:

1. Remove the new helper methods: `_search_and_track_discoveries`, `_search_listennotes_with_tracking`, `_search_podscan_with_tracking`
2. Revert the `fetch_podcasts_for_campaign` method to its previous implementation

However, this is not recommended as it will reintroduce the bug where existing podcasts aren't tracked as discoveries for new campaigns.