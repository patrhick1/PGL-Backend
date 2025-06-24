# Vetting Score Analysis

## 1. Where Vetting Scores are Generated

### Primary Generation: Enhanced Vetting Agent
- **File**: `/mnt/c/Users/ebube/Documents/PGL - Postgres/podcast_outreach/services/matches/enhanced_vetting_agent.py`
- **Main Method**: `vet_match_enhanced()` (line 355)
- **Score Calculation**: `_calculate_final_weighted_score()` (line 337)
- **Scale**: 0-10 with the following interpretation:
  - 0-2: No alignment or very poor fit
  - 3-4: Minimal alignment, significant gaps
  - 5-6: Moderate alignment, some relevant overlap
  - 7-8: Strong alignment, good fit with minor gaps
  - 9-10: Excellent alignment, near-perfect or perfect fit

The vetting agent:
1. Generates a dynamic checklist based on client profile
2. Gathers podcast evidence (description, episodes, themes, etc.)
3. Scores each criterion from 0-10
4. Calculates weighted average to get final score (normalized to 0-10)

## 2. Where Vetting Scores are Stored

### Database Tables

#### campaign_media_discoveries table
- **Field**: `vetting_score NUMERIC(4,2)` (line 616 in schema.py)
- Stores vetting results for discovered podcasts
- Also stores:
  - `vetting_reasoning TEXT`
  - `vetting_criteria_met JSONB`
  - `topic_match_analysis TEXT`
  - `vetting_criteria_scores JSONB`
  - `client_expertise_matched TEXT[]`
  - `vetted_at TIMESTAMP`

#### match_suggestions table  
- **Field**: `vetting_score NUMERIC` (line 380 in schema.py)
- Stores vetting results when matches are created
- Also stores:
  - `vetting_reasoning TEXT`
  - `vetting_checklist JSONB`
  - `last_vetted_at TIMESTAMPTZ`

## 3. Where Vetting Scores are Compared Against Thresholds

### Threshold Values Used:
- **5.0**: Minimum threshold for creating matches and showing as "ready"
- **6.0**: Used in match_processing.py for automated match creation

### Key Comparison Locations:

1. **Enhanced Discovery Workflow** (`services/business_logic/enhanced_discovery_workflow.py`)
   - Line 130: `if discovery["vetting_status"] == "completed" and discovery["vetting_score"] >= 5.0:`
   - Creates match if score meets threshold

2. **Discovery Processing** (`services/business_logic/discovery_processing.py`)
   - Line 107: `if discovery["vetting_score"] >= 5.0:`
   - Determines next step after vetting

3. **Match Processing** (`services/business_logic/match_processing.py`)
   - Line 102: `min_vetting_score = 6.0`
   - Line 104: `if vetting_score >= min_vetting_score:`
   - Higher threshold for automated match creation

4. **Campaign Media Discoveries Query** (`database/queries/campaign_media_discoveries.py`)
   - Line 232: `min_vetting_score: float = 5.0` (parameter)
   - Line 241: `AND cmd.vetting_score >= $1`
   - Line 411: `AND cmd.vetting_score >= 5.0` (for 'ready' status filter)

5. **Enhanced Vetting Orchestrator** (`services/matches/enhanced_vetting_orchestrator.py`)
   - Line 135: `if vetting_results['vetting_score'] >= 5.0:`
   - Automatically creates match suggestion

6. **Notification Service** (`services/events/notification_service.py`)
   - Line 202: `if vetting_score >= 5.0:`
   - Determines notification type based on score

## 4. UI/API Endpoints that Display/Use Vetting Scores

### API Endpoints:

1. **Review Tasks Endpoint** (`api/routers/review_tasks.py`)
   - GET `/review-tasks/enhanced` - Returns vetting scores in review tasks
   - Query parameter: `min_vetting_score` (0-10) for filtering
   - Score interpretation in UI:
     - >= 8.0: "Highly Recommended"
     - >= 6.5: "Good Match"
     - >= 5.0: "Acceptable Match"
     - < 5.0: "Below Threshold"

2. **Match Suggestions Endpoint** (`api/routers/matches.py`)
   - POST `/match-suggestions/campaigns/{campaign_id}/discover`
   - Mentions "vetting score ≥ 6.0" in documentation

### Schema Definitions:
- `ReviewTaskResponse`: Includes `vetting_score: Optional[float]` (0-10)
- `DiscoveryResponse`: Includes `vetting_score: Optional[float]` (0-10)
- `MatchSuggestionInDB`: Includes `vetting_score: Optional[float]` (0-10)

## 5. Other Business Logic Depending on Vetting Score Scale

1. **Check Vetting System Status** (`check_vetting_system_status.py`)
   - Line 72: `COUNT(CASE WHEN vetting_score >= 5.0 THEN 1 END) as high_score`
   - Used for system monitoring

2. **Test Files**
   - Multiple test files check for specific vetting scores
   - Edge case testing for score boundaries

## Summary of Key Thresholds:
- **< 5.0**: Below threshold, not ready for matches
- **>= 5.0**: Meets minimum criteria, can create match
- **>= 6.0**: Good enough for automated match creation  
- **>= 6.5**: Displayed as "Good Match" in UI
- **>= 8.0**: Displayed as "Highly Recommended" in UI

The vetting score is consistently used as a 0-10 scale throughout the system, with 5.0 being the primary threshold for match creation eligibility.