# Database Field Analysis: Pitches and Pitch Generations

## Schema Analysis

### pitch_generations Table
**Purpose**: Stores the AI-generated pitch content and metadata about the generation process.

**Fields in Schema**:
1. `pitch_gen_id` - Primary key
2. `campaign_id` - Links to campaign
3. `media_id` - Links to media (podcast)
4. `template_id` - Links to pitch template used
5. `draft_text` - The generated pitch email body
6. `ai_model_used` - Which AI model was used
7. `pitch_topic` - Topic/episode used for pitch
8. `temperature` - AI temperature setting
9. `generated_at` - When generated
10. `reviewer_id` - Who reviewed it
11. `reviewed_at` - When reviewed
12. `final_text` - Final edited version
13. `send_ready_bool` - Ready to send flag
14. `generation_status` - Status (draft, approved, etc.)

### pitches Table
**Purpose**: Represents actual pitch attempts/sends, links to pitch_generations for content.

**Fields in Schema**:
1. `pitch_id` - Primary key
2. `campaign_id` - Links to campaign
3. `media_id` - Links to media (podcast)
4. `attempt_no` - Attempt number
5. `match_score` - Score from match suggestion
6. `matched_keywords` - Keywords that matched
7. `score_evaluated_at` - When score was evaluated
8. `outreach_type` - Type of outreach (e.g., cold_email)
9. `subject_line` - Email subject line
10. `body_snippet` - Preview of body (250 chars)
11. `send_ts` - When sent
12. `reply_bool` - Did they reply?
13. `reply_ts` - When they replied
14. `instantly_lead_id` - Instantly.ai integration ID
15. `pitch_gen_id` - Links to pitch_generations
16. `placement_id` - Links to placements
17. `pitch_state` - State (generated, sent, etc.)
18. `client_approval_status` - Approval status
19. `created_by` - Who created it
20. `created_at` - When created

## Current Population Analysis

### What's Being Populated in pitch_generations:
✅ campaign_id
✅ media_id
✅ template_id
✅ draft_text
✅ ai_model_used
✅ pitch_topic (using episode title)
✅ temperature
✅ generation_status
✅ send_ready_bool
❌ generated_at (defaults to CURRENT_TIMESTAMP)
❌ reviewer_id (null until reviewed)
❌ reviewed_at (null until reviewed)
❌ final_text (null until edited)

### What's Being Populated in pitches:
✅ campaign_id
✅ media_id
✅ attempt_no
✅ match_score
✅ matched_keywords
✅ score_evaluated_at
✅ outreach_type
✅ subject_line
✅ body_snippet
✅ pitch_gen_id
✅ pitch_state
✅ client_approval_status
✅ created_by
❌ send_ts (null until sent)
❌ reply_bool (null until tracked)
❌ reply_ts (null until reply)
❌ instantly_lead_id (null until sent via Instantly)
❌ placement_id (null until placement created)
❌ created_at (defaults to CURRENT_TIMESTAMP)

## Issues Found

### 1. pitch_generations INSERT Issue
The INSERT statement explicitly includes `generated_at` but passes `datetime.utcnow()` which should be handled by the database default.

**Current**:
```sql
INSERT INTO pitch_generations (
    ..., generated_at, ...
) VALUES (
    ..., $8, ...
)
```

**Should be**: Remove `generated_at` from INSERT to use database default.

### 2. pitches INSERT Issue  
The INSERT includes `created_at` explicitly but should use database default.

**Current**:
```sql
INSERT INTO pitches (
    ..., created_at, ...
) VALUES (
    ..., $18, ...
)
```

**Should be**: Remove `created_at` from INSERT to use database default.

### 3. Missing Context Fields
Some fields that could be populated from the match suggestion aren't being used:
- `vetting_score` from match_suggestions could inform pitch generation
- `vetting_reasoning` could be referenced in pitch

## Recommendations

1. **Remove timestamp fields from INSERTs** - Let database handle defaults
2. **Add vetting context** - Include vetting score/reasoning in pitch generation metadata
3. **Track pitch versions** - Use `final_text` field when pitches are edited
4. **Link to original match** - Consider adding match_id reference to pitches table

## Workflow Verification

### From Match Approval to Pitch:
1. ✅ Match approved → pitch generator called
2. ✅ Pitch generator creates pitch_generations record
3. ✅ Pitch generator creates pitches record
4. ✅ Review task created with pitch_gen_id
5. ✅ All essential fields populated
6. ⚠️ Timestamp handling could be cleaner
7. ⚠️ Some contextual data not carried forward