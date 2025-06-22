# Orchestrator and Agent Analysis

## Current Architecture

### Vetting Components

#### 1. VettingOrchestrator (Original)
**Purpose**: Processes review tasks of type 'match_suggestion_vetting'
**Key Features**:
- Works with review_tasks table
- Finds pending vetting tasks
- Updates match_suggestions table
- Creates client review tasks after vetting
- Publishes VETTING_COMPLETED events

**Workflow**:
1. Looks for review tasks with type 'match_suggestion_vetting'
2. Gets match suggestion and campaign data
3. Runs vetting agent
4. Updates match status to 'pending_client_review'
5. Creates new review task for client

**Current Usage**: Not currently used after we switched to EnhancedVettingOrchestrator

#### 2. EnhancedVettingOrchestrator
**Purpose**: Processes campaign_media_discoveries records directly
**Key Features**:
- Works with campaign_media_discoveries table
- Uses atomic locking (FOR UPDATE SKIP LOCKED)
- Cleans up stale locks
- Automatically creates match suggestions for high scores
- No dependency on review_tasks for triggering

**Workflow**:
1. Acquires discoveries where enrichment is complete and vetting is pending
2. Runs vetting agent
3. Updates discovery with vetting results
4. Creates match suggestion if score >= 6.0
5. Creates review task for client review
6. Publishes VETTING_COMPLETED events

**Current Usage**: Active - used in enrichment_processing.py

#### 3. VettingAgent (Regular)
**Purpose**: Core vetting logic using AI
**Key Features**:
- Uses Gemini AI for analysis
- Extracts client profile from questionnaire
- Creates vetting checklist
- Scores podcasts against criteria
- Generates detailed analysis

**Current Usage**: Used by BOTH orchestrators

#### 4. EnhancedVettingAgent
**Purpose**: Extended vetting with more comprehensive questionnaire data
**Key Features**:
- More detailed client profile extraction
- Uses additional questionnaire fields
- (Code appears similar to regular VettingAgent)

**Current Usage**: NOT USED ANYWHERE

### Enrichment Components

#### 1. EnrichmentOrchestrator
**Purpose**: Main enrichment pipeline
**Key Features**:
- Runs core details enrichment for new media
- Refreshes social stats
- Updates quality scores
- Manages transcription flags
- Triggers match creation

**Current Usage**: Active - primary enrichment orchestrator

#### 2. EnrichmentAgent
**Purpose**: Core enrichment logic
**Key Features**:
- Enriches podcast profiles
- Discovers social media links
- Handles RSS feed enrichment
- Uses Gemini for discovery
- Merges data from multiple sources

**Current Usage**: Active - used by EnrichmentOrchestrator

#### 3. EnhancedDiscoveryWorkflow
**Purpose**: New discovery-based workflow
**Key Features**:
- Generates AI descriptions for podcasts
- Works with campaign_media_discoveries
- Used in AI description completion task

**Current Usage**: Active - used in task manager for AI descriptions

## Key Differences

### VettingOrchestrator vs EnhancedVettingOrchestrator

| Feature | VettingOrchestrator | EnhancedVettingOrchestrator |
|---------|-------------------|---------------------------|
| Trigger | Review tasks | Discovery records |
| Table | review_tasks | campaign_media_discoveries |
| Locking | None | Atomic with FOR UPDATE SKIP LOCKED |
| Match Creation | No | Yes (automatic for score >= 6.0) |
| Workflow | Reactive (waits for tasks) | Proactive (processes discoveries) |
| Race Protection | No | Yes |

### VettingAgent vs EnhancedVettingAgent

The EnhancedVettingAgent appears to be an incomplete implementation that's not being used. Both the regular and enhanced vetting orchestrators use the regular VettingAgent.

## Dependencies

### Files Using VettingOrchestrator
- None (after our update)

### Files Using EnhancedVettingOrchestrator
- services/business_logic/enrichment_processing.py

### Files Using VettingAgent
- services/matches/vetting_orchestrator.py
- services/matches/enhanced_vetting_orchestrator.py

### Files Using EnhancedVettingAgent
- None

## Recommendations

### 1. Safe to Delete
- **VettingOrchestrator**: No longer used, replaced by EnhancedVettingOrchestrator
- **EnhancedVettingAgent**: Never implemented/used, incomplete

### 2. Keep and Improve
- **EnhancedVettingOrchestrator**: Active and working with new workflow
- **VettingAgent**: Core vetting logic used by enhanced orchestrator
- **EnrichmentOrchestrator**: Main enrichment pipeline
- **EnrichmentAgent**: Core enrichment logic

### 3. Consider Merging
The EnhancedVettingOrchestrator could potentially use an improved version of VettingAgent that extracts more questionnaire data, but the current VettingAgent seems sufficient.

## Migration Notes

If we want to use EnhancedVettingAgent features:
1. Update EnhancedVettingOrchestrator to import EnhancedVettingAgent
2. Ensure EnhancedVettingAgent is complete and tested
3. Or merge the enhanced extraction logic into VettingAgent

## Conclusion

The "Enhanced" versions represent the new discovery-based workflow that:
- Works with campaign_media_discoveries table
- Has race condition protection
- Automates the full pipeline from discovery to match creation

The original orchestrators worked with a task-based system that required manual creation of review tasks. The enhanced versions are more automated and robust.