# Multiple Pitches Per Match - Implementation Plan

## Current System Analysis

### Database Relationships
```
match_suggestions (1) → (many) pitch_generations → (1) pitches
```

**Current Issues:**
- No explicit link between `match_suggestions` and `pitch_generations`
- `attempt_no` field in `pitches` table is underutilized
- No structured way to track pitch sequences (initial, follow-up 1, follow-up 2, etc.)

### Key Tables and Their Roles

1. **match_suggestions**: The approved match between campaign and media
2. **pitch_generations**: The content (what we're saying)
3. **pitches**: The sending record (when/how we sent it and tracking)

## Proposed Solution

### Option 1: Add match_id to pitch_generations (RECOMMENDED)

This is the cleanest solution that maintains data integrity and enables multiple pitches per match.

#### Database Changes

```sql
-- 1. Add match_id column to pitch_generations table
ALTER TABLE pitch_generations 
ADD COLUMN match_id INTEGER REFERENCES match_suggestions(match_id) ON DELETE RESTRICT;

-- 2. Create index for performance
CREATE INDEX IF NOT EXISTS idx_pitch_generations_match_id 
ON pitch_generations(match_id);

-- 3. Add pitch_type to track the type of pitch
ALTER TABLE pitch_generations
ADD COLUMN pitch_type VARCHAR(50) DEFAULT 'initial' 
CHECK (pitch_type IN ('initial', 'follow_up_1', 'follow_up_2', 'follow_up_3', 'custom'));

-- 4. Add sequence_number for ordering
ALTER TABLE pitch_generations
ADD COLUMN sequence_number INTEGER DEFAULT 1;

-- 5. Add parent_pitch_gen_id for tracking follow-up chains
ALTER TABLE pitch_generations
ADD COLUMN parent_pitch_gen_id INTEGER REFERENCES pitch_generations(pitch_gen_id) ON DELETE SET NULL;

-- 6. Create a unique constraint to prevent duplicate pitch types for the same match
CREATE UNIQUE INDEX idx_unique_match_pitch_type 
ON pitch_generations(match_id, pitch_type) 
WHERE pitch_type != 'custom';

-- 7. Migrate existing data (link existing pitch_generations to matches)
UPDATE pitch_generations pg
SET match_id = ms.match_id
FROM match_suggestions ms
WHERE pg.campaign_id = ms.campaign_id 
AND pg.media_id = ms.media_id
AND pg.match_id IS NULL;
```

### Benefits of This Approach

1. **Clear Relationship**: Direct link between matches and pitch generations
2. **Multiple Pitches**: Can create multiple pitch_generations for one match
3. **Pitch Sequencing**: Track initial vs follow-ups with `pitch_type` and `sequence_number`
4. **Chain Tracking**: `parent_pitch_gen_id` allows tracking conversation threads
5. **Data Integrity**: Foreign key ensures pitches are tied to valid matches
6. **Backward Compatible**: Existing code continues to work

### Implementation Steps

#### Step 1: Database Migration
```python
# podcast_outreach/database/migrations/add_match_id_to_pitch_generations.py

async def upgrade():
    """Add match_id and pitch sequencing fields to pitch_generations"""
    conn = await get_db_connection()
    
    # Add new columns
    await conn.execute("""
        ALTER TABLE pitch_generations 
        ADD COLUMN IF NOT EXISTS match_id INTEGER REFERENCES match_suggestions(match_id) ON DELETE RESTRICT,
        ADD COLUMN IF NOT EXISTS pitch_type VARCHAR(50) DEFAULT 'initial',
        ADD COLUMN IF NOT EXISTS sequence_number INTEGER DEFAULT 1,
        ADD COLUMN IF NOT EXISTS parent_pitch_gen_id INTEGER REFERENCES pitch_generations(pitch_gen_id) ON DELETE SET NULL;
    """)
    
    # Add constraints
    await conn.execute("""
        ALTER TABLE pitch_generations
        ADD CONSTRAINT check_pitch_type 
        CHECK (pitch_type IN ('initial', 'follow_up_1', 'follow_up_2', 'follow_up_3', 'custom'));
    """)
    
    # Create indexes
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pitch_generations_match_id ON pitch_generations(match_id);
        CREATE INDEX IF NOT EXISTS idx_pitch_generations_parent ON pitch_generations(parent_pitch_gen_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_match_pitch_type 
        ON pitch_generations(match_id, pitch_type) 
        WHERE pitch_type != 'custom';
    """)
    
    # Migrate existing data
    await conn.execute("""
        UPDATE pitch_generations pg
        SET match_id = ms.match_id
        FROM match_suggestions ms
        WHERE pg.campaign_id = ms.campaign_id 
        AND pg.media_id = ms.media_id
        AND pg.match_id IS NULL;
    """)
```

#### Step 2: Update API Schemas
```python
# podcast_outreach/api/schemas/pitch_schemas.py

class PitchGenerationRequest(BaseModel):
    match_id: int = Field(..., description="The ID of the approved match suggestion")
    pitch_type: str = Field("initial", description="Type of pitch: initial, follow_up_1, follow_up_2, etc.")
    parent_pitch_gen_id: Optional[int] = Field(None, description="ID of parent pitch for follow-ups")
    pitch_template_id: str = Field(..., description="ID of the pitch template to use")
    custom_subject: Optional[str] = None
    custom_body: Optional[str] = None

class ManualPitchCreateRequest(BaseModel):
    match_id: int
    pitch_type: str = "initial"
    parent_pitch_gen_id: Optional[int] = None
    subject_line: str
    body_text: str
```

#### Step 3: Update Pitch Generation Service
```python
# podcast_outreach/services/pitches/generator.py

async def generate_pitch_for_match(
    match_id: int,
    pitch_type: str = "initial",
    parent_pitch_gen_id: Optional[int] = None,
    template_id: str = None
) -> Dict[str, Any]:
    """Generate a pitch for a specific match and type"""
    
    # Get the match
    match = await match_queries.get_match_suggestion_by_id_from_db(match_id)
    if not match:
        raise ValueError(f"Match {match_id} not found")
    
    # Check if this pitch type already exists for this match
    existing = await pitch_gen_queries.get_pitch_generation_by_match_and_type(
        match_id, pitch_type
    )
    if existing and pitch_type != 'custom':
        raise ValueError(f"A {pitch_type} pitch already exists for match {match_id}")
    
    # Get sequence number
    sequence_number = await pitch_gen_queries.get_next_sequence_number(match_id)
    
    # Generate the pitch content
    # ... existing generation logic ...
    
    # Save to database with match_id
    pitch_gen_data = {
        "campaign_id": match["campaign_id"],
        "media_id": match["media_id"],
        "match_id": match_id,  # NEW
        "pitch_type": pitch_type,  # NEW
        "sequence_number": sequence_number,  # NEW
        "parent_pitch_gen_id": parent_pitch_gen_id,  # NEW
        "template_id": template_id,
        "draft_text": generated_text,
        # ... other fields ...
    }
    
    return await pitch_gen_queries.create_pitch_generation_in_db(pitch_gen_data)
```

#### Step 4: Update API Endpoints
```python
# podcast_outreach/api/routers/pitches.py

@router.get("/match/{match_id}/pitches", response_model=List[PitchGenerationInDB])
async def get_pitches_for_match(
    match_id: int,
    user: dict = Depends(get_current_user)
):
    """Get all pitch generations for a specific match"""
    # Verify user owns the match
    if not await validate_match_ownership(match_id, user):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    pitches = await pitch_gen_queries.get_pitch_generations_by_match(match_id)
    return pitches

@router.post("/match/{match_id}/generate-followup")
async def generate_followup_pitch(
    match_id: int,
    request: FollowUpPitchRequest,
    user: dict = Depends(get_current_user)
):
    """Generate a follow-up pitch for a match"""
    # Verify user owns the match
    if not await validate_match_ownership(match_id, user):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Determine pitch type based on existing pitches
    existing_pitches = await pitch_gen_queries.get_pitch_generations_by_match(match_id)
    
    if not existing_pitches:
        raise HTTPException(400, "No initial pitch found for this match")
    
    # Find the last pitch
    last_pitch = max(existing_pitches, key=lambda x: x['sequence_number'])
    
    # Determine next pitch type
    if last_pitch['pitch_type'] == 'initial':
        next_type = 'follow_up_1'
    elif last_pitch['pitch_type'] == 'follow_up_1':
        next_type = 'follow_up_2'
    elif last_pitch['pitch_type'] == 'follow_up_2':
        next_type = 'follow_up_3'
    else:
        next_type = 'custom'
    
    # Generate the follow-up
    result = await generate_pitch_for_match(
        match_id=match_id,
        pitch_type=next_type,
        parent_pitch_gen_id=last_pitch['pitch_gen_id'],
        template_id=request.template_id
    )
    
    return result
```

#### Step 5: Update Frontend Components
```typescript
// Frontend component to display multiple pitches per match

interface MatchPitches {
  match_id: number;
  pitches: PitchGeneration[];
}

const PitchSequenceView: React.FC<{matchId: number}> = ({matchId}) => {
  const [pitches, setPitches] = useState<PitchGeneration[]>([]);
  
  useEffect(() => {
    fetchPitchesForMatch(matchId).then(setPitches);
  }, [matchId]);
  
  return (
    <div className="pitch-sequence">
      <h3>Pitch Sequence</h3>
      {pitches.map((pitch, idx) => (
        <div key={pitch.pitch_gen_id} className="pitch-item">
          <div className="pitch-header">
            <span className="pitch-type">{pitch.pitch_type}</span>
            <span className="pitch-date">{pitch.generated_at}</span>
          </div>
          <div className="pitch-subject">{pitch.subject_line}</div>
          <div className="pitch-status">
            Status: {pitch.send_ready_bool ? 'Ready' : 'Draft'}
          </div>
          {pitch.pitch_type === 'initial' && idx === pitches.length - 1 && (
            <button onClick={() => generateFollowUp(matchId)}>
              Generate Follow-up
            </button>
          )}
        </div>
      ))}
    </div>
  );
};
```

### Use Cases Enabled

1. **Initial Pitch**: First outreach to a podcast
2. **Follow-up 1**: Sent 7 days after initial if no response
3. **Follow-up 2**: Sent 14 days after initial if no response
4. **Follow-up 3**: Final attempt after 21 days
5. **Custom Pitches**: For special situations or re-engagement

### Benefits for Users

1. **Better Response Rates**: Multiple touchpoints increase response probability
2. **Automated Sequences**: Set up follow-up campaigns that run automatically
3. **A/B Testing**: Test different pitch approaches for the same match
4. **Re-engagement**: Ability to re-pitch to podcasts after some time
5. **Campaign Management**: Track all pitches for a match in one place

### Migration Path

1. **Phase 1**: Add database columns (backward compatible)
2. **Phase 2**: Update API to support match_id in pitch generations
3. **Phase 3**: Add UI for creating follow-ups
4. **Phase 4**: Add automation for follow-up sequences
5. **Phase 5**: Analytics and reporting on pitch sequences

### Tracking and Analytics

With this structure, you can easily query:
- How many follow-ups were sent per match
- Response rates by pitch type (initial vs follow-ups)
- Optimal follow-up timing
- Which pitch templates work best for follow-ups

### Example Queries

```sql
-- Get all pitches for a match
SELECT * FROM pitch_generations 
WHERE match_id = 123 
ORDER BY sequence_number;

-- Get matches that need follow-ups
SELECT ms.* 
FROM match_suggestions ms
LEFT JOIN pitch_generations pg ON ms.match_id = pg.match_id
LEFT JOIN pitches p ON pg.pitch_gen_id = p.pitch_gen_id
WHERE ms.client_approved = TRUE
AND pg.pitch_type = 'initial'
AND p.reply_bool = FALSE
AND p.send_ts < NOW() - INTERVAL '7 days';

-- Get pitch sequence performance
SELECT 
    pitch_type,
    COUNT(*) as total_sent,
    SUM(CASE WHEN p.reply_bool THEN 1 ELSE 0 END) as replies,
    AVG(CASE WHEN p.reply_bool THEN 1.0 ELSE 0.0 END) * 100 as reply_rate
FROM pitch_generations pg
JOIN pitches p ON pg.pitch_gen_id = p.pitch_gen_id
GROUP BY pitch_type
ORDER BY 
    CASE pitch_type
        WHEN 'initial' THEN 1
        WHEN 'follow_up_1' THEN 2
        WHEN 'follow_up_2' THEN 3
        WHEN 'follow_up_3' THEN 4
        ELSE 5
    END;
```

## Implementation Priority

1. **High Priority**: Database changes and basic multiple pitch support
2. **Medium Priority**: UI for creating and viewing follow-ups
3. **Low Priority**: Automation and advanced analytics

This solution provides a robust foundation for multiple pitches per match while maintaining backward compatibility and data integrity.