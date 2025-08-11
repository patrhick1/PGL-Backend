# Podcast Revetting System Guide

## Overview

The Revetting System is designed to carefully re-evaluate podcasts that previously scored below 50 (the threshold for match creation) using an updated `ideal_podcast_description`. This system ensures that improved campaign criteria can surface previously overlooked podcast opportunities without breaking the existing pipeline.

## Background

### The Pipeline Flow
1. **Discovery** → Podcasts are discovered and added to `campaign_media_discoveries`
2. **Enrichment** → Podcast data is enhanced with AI descriptions, episode analysis, etc.
3. **Vetting** → Podcasts are scored (0-100) using the `EnhancedVettingAgent`
4. **Match Creation** → Only podcasts scoring ≥50 get match suggestions and review tasks

### The Problem
When campaign criteria are updated (e.g., more flexible `ideal_podcast_description`), previously low-scoring podcasts may now be viable matches, but they remain stuck in the system with `vetting_status='completed'` but `match_created=FALSE`.

### The Solution
The Revetting System:
- Identifies low-scoring podcasts for a specific campaign
- Re-runs vetting with the current campaign criteria
- Creates matches for newly qualifying podcasts
- Maintains full pipeline integrity and safety

## Architecture

### Key Components

1. **RevettingSystem Class** (`scripts/revetting_system.py`)
   - Main orchestrator for the revetting process
   - Handles campaign validation, podcast identification, and processing
   - Includes comprehensive safety checks and dry-run mode

2. **Database Integration**
   - Uses existing `campaign_media_discoveries` table
   - Leverages current `EnhancedVettingAgent`
   - Maintains compatibility with `discovery_processing.py` pipeline

3. **Safety Features**
   - Dry-run mode by default
   - Comprehensive validation and error handling
   - Pipeline integrity preservation
   - Detailed logging and reporting

### Database Schema Understanding

```sql
-- Key table: campaign_media_discoveries
SELECT 
    id,                    -- Discovery record ID
    campaign_id,          -- Links to campaigns table
    media_id,             -- Links to media table  
    vetting_status,       -- 'completed' for vetted podcasts
    vetting_score,        -- Score (0-100), <50 means no match created
    match_created,        -- FALSE for low-scoring podcasts
    vetting_reasoning     -- AI explanation of score
FROM campaign_media_discoveries
WHERE vetting_status = 'completed' 
  AND vetting_score < 50 
  AND match_created = FALSE;
```

## Usage

### Prerequisites
- Updated `ideal_podcast_description` in the campaign
- Access to the database and AI services
- Python environment with required dependencies

### Testing First (REQUIRED)

Always start with testing to ensure system integrity:

```bash
# Run comprehensive tests
cd /path/to/podcast_outreach
python scripts/test_revetting_system.py
```

This will verify:
- Database connectivity
- Campaign existence and validation
- Low-scoring podcast identification
- Safety mechanisms
- Dry-run execution

### Running the Revetting Process

#### Step 1: Dry Run (Recommended)
```bash
python scripts/revetting_system.py \
  --campaign-id 33c5adcd-10b9-4488-9241-f73b7f841e88 \
  --dry-run \
  --limit 10
```

This will:
- Identify low-scoring podcasts
- Simulate the revetting process
- Show what would happen without making changes
- Generate a detailed report

#### Step 2: Actual Execution
```bash
python scripts/revetting_system.py \
  --campaign-id 33c5adcd-10b9-4488-9241-f73b7f841e88 \
  --limit 20
```

**Important**: The `--limit` parameter is a safety feature. Start small (10-20 podcasts) for the first run.

### Command Line Options

```bash
--campaign-id CAMPAIGN_ID   # Required: UUID of the campaign to process
--dry-run                   # Optional: Run without making changes (RECOMMENDED)
--limit N                   # Optional: Limit number of podcasts to process
--verbose                   # Optional: Enable detailed logging
```

### Safety Mechanisms

1. **Dry Run Default**: The system encourages dry-run testing
2. **Automatic Limits**: Without explicit limits, the system applies safety constraints
3. **Validation**: Comprehensive campaign and database validation before processing
4. **Error Handling**: Graceful error handling with detailed logging
5. **Pipeline Integrity**: Uses existing workflow components to maintain consistency

## Expected Results

### Typical Output
```
==========================================
REVETTING PROCESS COMPLETE
==========================================
Low-scoring podcasts found: 15
Successfully re-vetted: 14
Scores improved: 8
New matches created: 5
Errors encountered: 1

✅ Process completed successfully!
💡 5 new podcast opportunities are now available for review
==========================================
```

### What Happens to Improved Podcasts
1. **Score Updated**: `vetting_score` updated with new score
2. **Match Created**: If score ≥50, creates `match_suggestion` record
3. **Review Task**: Creates `review_task` for client evaluation
4. **Pipeline Integration**: Podcast enters normal review workflow

## Database Changes

### Records Modified

1. **campaign_media_discoveries**
   - `vetting_score` updated with new score
   - `vetting_reasoning` updated with new explanation
   - `vetting_criteria_met` updated with new criteria analysis
   - `match_created` set to TRUE if qualifying
   - `match_suggestion_id` populated if match created

2. **match_suggestions** (new records for qualifying podcasts)
   - Complete match suggestion with vetting details
   - Status set to 'pending_client_review'
   - Includes best matching episode

3. **review_tasks** (new records for qualifying podcasts)
   - Task created for client review
   - Links to the new match suggestion

### No Data Loss
- Original vetting data is replaced with new data
- All other discovery tracking remains intact
- Pipeline state is preserved

## Monitoring and Troubleshooting

### Logs to Monitor
- **INFO**: Normal processing steps and results
- **WARNING**: Non-fatal issues (e.g., vetting failures)
- **ERROR**: Problems that need attention

### Common Issues

1. **Campaign Not Found**
   ```
   ValueError: Campaign {id} not found
   ```
   **Solution**: Verify campaign ID is correct

2. **Missing ideal_podcast_description**
   ```
   ValueError: Campaign {id} is missing ideal_podcast_description
   ```
   **Solution**: Update campaign with proper description

3. **No Low-Scoring Podcasts**
   ```
   No low-scoring podcasts found. Process complete.
   ```
   **Solution**: Normal - all podcasts already properly scored

4. **Vetting Failures**
   ```
   WARNING: Vetting failed for {podcast}: {reason}
   ```
   **Solution**: Check AI service availability and campaign data

### Performance Considerations
- Process includes 1-second delays between podcasts to avoid overwhelming services
- Use `--limit` to control batch sizes
- Monitor AI service quotas and limits

## Integration with Existing System

### Workflow Compatibility
The revetting system integrates seamlessly with existing workflows:

1. **Discovery Processing**: Uses same vetting agent and match creation logic
2. **Client Review**: New matches appear in normal client dashboard
3. **Pitch Generation**: Works with existing pitch generation system
4. **Status Tracking**: Maintains all existing status tracking

### API Compatibility
- New matches appear in existing API endpoints
- Client dashboard shows new opportunities
- Review task system handles new tasks normally

## Best Practices

### Before Running
1. **Test thoroughly** with `test_revetting_system.py`
2. **Backup database** (recommended for first use)
3. **Update campaign description** before revetting
4. **Start with small limits** (10-20 podcasts)

### During Execution
1. **Monitor logs** for errors or unexpected behavior
2. **Check system resources** (database, AI services)
3. **Validate results** in dry-run mode first

### After Running
1. **Review new matches** in client dashboard
2. **Check quality** of newly created matches
3. **Monitor client feedback** on new opportunities
4. **Adjust campaign criteria** if needed for future discoveries

## Maintenance

### Regular Tasks
- Monitor revetting system logs
- Clean up old discovery records if needed
- Update documentation with lessons learned

### Updates Required
- If vetting agent logic changes
- If match creation process changes
- If database schema changes

## Security Considerations

### Database Safety
- Uses existing connection pooling and security
- No direct SQL injection risks (uses parameterized queries)
- Respects existing access controls

### Operational Safety
- Dry-run mode prevents accidental changes
- Comprehensive validation before execution
- Graceful error handling and recovery

---

## Quick Start Summary

For the specific campaign mentioned in the request:

```bash
# 1. Test the system
python scripts/test_revetting_system.py

# 2. Run dry-run to see what would happen
python scripts/revetting_system.py \
  --campaign-id 33c5adcd-10b9-4488-9241-f73b7f841e88 \
  --dry-run --limit 10

# 3. Execute actual revetting (start small)
python scripts/revetting_system.py \
  --campaign-id 33c5adcd-10b9-4488-9241-f73b7f841e88 \
  --limit 20
```

This will safely process the updated campaign and surface any previously overlooked podcast opportunities while maintaining full system integrity.