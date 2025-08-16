# Multiple Pitches Per Match - Detailed Implementation Plan

## Executive Summary

Enable users to create multiple pitch sequences (initial email, follow-ups) for the same campaign-media match. The solution uses campaign_id + media_id as the natural grouping key, with sequence numbers to track pitch order, eliminating the need for additional relationship fields.

## Current System Analysis

### Database Structure

#### Key Tables
1. **match_suggestions**: Links campaigns to media (podcasts)
   - Primary Key: `match_id`
   - Key Fields: `campaign_id`, `media_id`, `client_approved`
   - When `client_approved = TRUE`, the match is ready for pitch generation

2. **pitch_generations**: Stores pitch content
   - Primary Key: `pitch_gen_id`
   - Key Fields: `campaign_id`, `media_id`, `draft_text`, `final_text`, `send_ready_bool`
   - No direct link to `match_id` currently
   - Contains the actual email content

3. **pitches**: Tracks sending and engagement
   - Primary Key: `pitch_id`
   - Key Fields: `campaign_id`, `media_id`, `pitch_gen_id`, `attempt_no`, `pitch_state`
   - Links to pitch_generations via `pitch_gen_id`
   - Tracks: sent, opened, clicked, replied states

### Current Workflow
1. Match gets approved → `client_approved = TRUE`
2. User manually creates pitch generation (no auto-generation)
3. Pitch record created linking to pitch generation
4. Email sent and tracked

### Current Limitations
- No explicit relationship between matches and pitch generations
- No structured way to handle multiple pitches per match
- `attempt_no` field exists but is underutilized
- No sequence tracking for follow-ups

## Proposed Solution

### Core Concept
Use the natural composite key of `campaign_id + media_id` to group pitches, with a `sequence_number` to track order. The first pitch (sequence_number = 1) is the initial pitch, subsequent ones are follow-ups.

### Database Changes

#### 1. Add Fields to pitch_generations Table

```sql
-- Add match_id for explicit relationship
ALTER TABLE pitch_generations 
ADD COLUMN match_id INTEGER REFERENCES match_suggestions(match_id) ON DELETE RESTRICT;

-- Add sequence tracking
ALTER TABLE pitch_generations
ADD COLUMN sequence_number INTEGER DEFAULT 1 NOT NULL;

-- Add pitch type for clarity
ALTER TABLE pitch_generations
ADD COLUMN pitch_type VARCHAR(50) DEFAULT 'initial' 
CHECK (pitch_type IN ('initial', 'follow_up_1', 'follow_up_2', 'follow_up_3', 'custom', 're_engagement'));

-- Add metadata for tracking
ALTER TABLE pitch_generations
ADD COLUMN pitch_metadata JSONB DEFAULT '{}'::jsonb;

-- Create indexes for performance
CREATE INDEX idx_pitch_generations_match_id 
ON pitch_generations(match_id);

CREATE INDEX idx_pitch_generations_campaign_media 
ON pitch_generations(campaign_id, media_id);

CREATE INDEX idx_pitch_generations_sequence 
ON pitch_generations(campaign_id, media_id, sequence_number);

-- Add comment for documentation
COMMENT ON COLUMN pitch_generations.sequence_number IS 
'Order of pitch in sequence. 1 = initial, 2+ = follow-ups. Unique per campaign-media combination.';

COMMENT ON COLUMN pitch_generations.pitch_metadata IS 
'JSON metadata: days_since_last_pitch, template_variables, automation_trigger, etc.';
```

#### 2. Create Function to Get Next Sequence Number

```sql
CREATE OR REPLACE FUNCTION get_next_pitch_sequence_number(
    p_campaign_id UUID,
    p_media_id INTEGER
) RETURNS INTEGER AS $$
DECLARE
    v_max_sequence INTEGER;
BEGIN
    SELECT COALESCE(MAX(sequence_number), 0) + 1
    INTO v_max_sequence
    FROM pitch_generations
    WHERE campaign_id = p_campaign_id 
    AND media_id = p_media_id;
    
    RETURN v_max_sequence;
END;
$$ LANGUAGE plpgsql;
```

#### 3. Create Function to Determine Pitch Type

```sql
CREATE OR REPLACE FUNCTION determine_pitch_type(
    p_sequence_number INTEGER
) RETURNS VARCHAR AS $$
BEGIN
    RETURN CASE 
        WHEN p_sequence_number = 1 THEN 'initial'
        WHEN p_sequence_number = 2 THEN 'follow_up_1'
        WHEN p_sequence_number = 3 THEN 'follow_up_2'
        WHEN p_sequence_number = 4 THEN 'follow_up_3'
        ELSE 'custom'
    END;
END;
$$ LANGUAGE plpgsql;
```

#### 4. Add Constraint to Prevent Duplicate Sequences

```sql
-- Ensure unique sequence numbers per campaign-media combination
CREATE UNIQUE INDEX idx_unique_campaign_media_sequence 
ON pitch_generations(campaign_id, media_id, sequence_number);
```

#### 5. Data Migration for Existing Records

```sql
-- Populate match_id for existing pitch_generations
UPDATE pitch_generations pg
SET match_id = ms.match_id,
    sequence_number = 1,
    pitch_type = 'initial'
FROM match_suggestions ms
WHERE pg.campaign_id = ms.campaign_id 
AND pg.media_id = ms.media_id
AND pg.match_id IS NULL;

-- Update attempt_no in pitches table to match sequence_number
UPDATE pitches p
SET attempt_no = pg.sequence_number
FROM pitch_generations pg
WHERE p.pitch_gen_id = pg.pitch_gen_id
AND p.attempt_no != pg.sequence_number;
```

### API Implementation

#### 1. Update Database Queries

##### podcast_outreach/database/queries/pitch_generations.py

```python
async def get_pitch_generations_by_match(match_id: int) -> List[Dict[str, Any]]:
    """Get all pitch generations for a specific match, ordered by sequence."""
    query = """
    SELECT pg.*, 
           p.pitch_state, 
           p.send_ts, 
           p.reply_bool,
           p.opened_ts,
           p.clicked_ts
    FROM pitch_generations pg
    LEFT JOIN pitches p ON pg.pitch_gen_id = p.pitch_gen_id
    WHERE pg.match_id = $1
    ORDER BY pg.sequence_number ASC;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, match_id)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching pitch generations for match {match_id}: {e}")
            return []

async def get_pitch_generations_by_campaign_media(
    campaign_id: uuid.UUID, 
    media_id: int
) -> List[Dict[str, Any]]:
    """Get all pitch generations for a campaign-media combination."""
    query = """
    SELECT pg.*, 
           p.pitch_state,
           p.send_ts,
           p.reply_bool
    FROM pitch_generations pg
    LEFT JOIN pitches p ON pg.pitch_gen_id = p.pitch_gen_id
    WHERE pg.campaign_id = $1 AND pg.media_id = $2
    ORDER BY pg.sequence_number ASC;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, campaign_id, media_id)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching pitches for campaign {campaign_id} and media {media_id}: {e}")
            return []

async def get_next_sequence_number(campaign_id: uuid.UUID, media_id: int) -> int:
    """Get the next sequence number for a campaign-media combination."""
    query = """
    SELECT COALESCE(MAX(sequence_number), 0) + 1 as next_seq
    FROM pitch_generations
    WHERE campaign_id = $1 AND media_id = $2;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id, media_id)
            return row['next_seq'] if row else 1
        except Exception as e:
            logger.exception(f"Error getting next sequence number: {e}")
            return 1

async def create_pitch_generation_in_db(pitch_gen_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Inserts a new pitch generation record with sequence tracking.
    """
    # Get next sequence number if not provided
    if 'sequence_number' not in pitch_gen_data:
        pitch_gen_data['sequence_number'] = await get_next_sequence_number(
            pitch_gen_data['campaign_id'],
            pitch_gen_data['media_id']
        )
    
    # Determine pitch type based on sequence number
    if 'pitch_type' not in pitch_gen_data:
        seq_num = pitch_gen_data['sequence_number']
        if seq_num == 1:
            pitch_gen_data['pitch_type'] = 'initial'
        elif seq_num == 2:
            pitch_gen_data['pitch_type'] = 'follow_up_1'
        elif seq_num == 3:
            pitch_gen_data['pitch_type'] = 'follow_up_2'
        elif seq_num == 4:
            pitch_gen_data['pitch_type'] = 'follow_up_3'
        else:
            pitch_gen_data['pitch_type'] = 'custom'
    
    query = """
    INSERT INTO pitch_generations (
        campaign_id, media_id, match_id, template_id, draft_text, 
        ai_model_used, pitch_topic, temperature, reviewer_id, 
        reviewed_at, final_text, send_ready_bool, generation_status,
        sequence_number, pitch_type, pitch_metadata
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
    ) RETURNING *;
    """
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                pitch_gen_data['campaign_id'],
                pitch_gen_data['media_id'],
                pitch_gen_data.get('match_id'),
                pitch_gen_data['template_id'],
                pitch_gen_data['draft_text'],
                pitch_gen_data.get('ai_model_used'),
                pitch_gen_data.get('pitch_topic'),
                pitch_gen_data.get('temperature'),
                pitch_gen_data.get('reviewer_id'),
                pitch_gen_data.get('reviewed_at'),
                pitch_gen_data.get('final_text'),
                pitch_gen_data.get('send_ready_bool', False),
                pitch_gen_data.get('generation_status', 'draft'),
                pitch_gen_data['sequence_number'],
                pitch_gen_data['pitch_type'],
                json.dumps(pitch_gen_data.get('pitch_metadata', {}))
            )
            if row:
                logger.info(f"Pitch generation created: {row['pitch_gen_id']} (sequence: {row['sequence_number']})")
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error creating pitch generation: {e}")
            raise

async def can_create_follow_up(campaign_id: uuid.UUID, media_id: int) -> Dict[str, Any]:
    """
    Check if a follow-up can be created for a campaign-media combination.
    Returns info about the last pitch and whether follow-up is allowed.
    """
    query = """
    WITH last_pitch AS (
        SELECT pg.*, p.send_ts, p.reply_bool, p.pitch_state
        FROM pitch_generations pg
        LEFT JOIN pitches p ON pg.pitch_gen_id = p.pitch_gen_id
        WHERE pg.campaign_id = $1 AND pg.media_id = $2
        ORDER BY pg.sequence_number DESC
        LIMIT 1
    )
    SELECT 
        *,
        CASE 
            WHEN reply_bool = TRUE THEN 'already_replied'
            WHEN pitch_state != 'sent' THEN 'not_sent'
            WHEN send_ts > NOW() - INTERVAL '7 days' THEN 'too_recent'
            WHEN sequence_number >= 4 THEN 'max_attempts_reached'
            ELSE 'can_follow_up'
        END as follow_up_status,
        EXTRACT(DAY FROM NOW() - send_ts) as days_since_sent
    FROM last_pitch;
    """
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id, media_id)
            if not row:
                return {
                    'can_follow_up': True,
                    'follow_up_status': 'no_pitches_yet',
                    'next_sequence_number': 1
                }
            
            result = dict(row)
            result['can_follow_up'] = result['follow_up_status'] == 'can_follow_up'
            result['next_sequence_number'] = result['sequence_number'] + 1
            return result
        except Exception as e:
            logger.exception(f"Error checking follow-up eligibility: {e}")
            return {'can_follow_up': False, 'error': str(e)}
```

#### 2. Update API Endpoints

##### podcast_outreach/api/routers/pitches.py

Add new endpoints for multiple pitch support:

```python
@router.get("/match/{match_id}/pitch-sequence", response_model=List[PitchSequenceItem])
async def get_pitch_sequence_for_match(
    match_id: int,
    user: dict = Depends(get_current_user)
):
    """
    Get all pitches in the sequence for a specific match.
    Shows initial pitch and all follow-ups with their status.
    """
    # Validate match ownership
    if not await validate_match_ownership(match_id, user):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    pitches = await pitch_gen_queries.get_pitch_generations_by_match(match_id)
    
    # Enhance with sequence information
    for idx, pitch in enumerate(pitches):
        pitch['sequence_position'] = f"{idx + 1} of {len(pitches)}"
        pitch['can_send'] = pitch.get('send_ready_bool', False) and not pitch.get('send_ts')
    
    return pitches

@router.post("/match/{match_id}/create-follow-up", response_model=PitchGenerationResponse)
async def create_follow_up_pitch(
    match_id: int,
    request: FollowUpPitchRequest,
    user: dict = Depends(get_current_user)
):
    """
    Create a follow-up pitch for an existing match.
    Automatically determines the sequence number and pitch type.
    """
    # Validate match ownership
    if not await validate_match_ownership(match_id, user):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get match details
    match = await match_queries.get_match_suggestion_by_id_from_db(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    
    campaign_id = match['campaign_id']
    media_id = match['media_id']
    
    # Check if follow-up is allowed
    follow_up_check = await pitch_gen_queries.can_create_follow_up(campaign_id, media_id)
    
    if not follow_up_check['can_follow_up']:
        reason = follow_up_check.get('follow_up_status', 'unknown')
        if reason == 'already_replied':
            raise HTTPException(400, "Cannot create follow-up: Recipient has already replied")
        elif reason == 'not_sent':
            raise HTTPException(400, "Cannot create follow-up: Previous pitch not sent yet")
        elif reason == 'too_recent':
            days = follow_up_check.get('days_since_sent', 0)
            raise HTTPException(400, f"Cannot create follow-up: Only {days} days since last pitch (minimum 7 days)")
        elif reason == 'max_attempts_reached':
            raise HTTPException(400, "Cannot create follow-up: Maximum follow-up attempts reached (3)")
        else:
            raise HTTPException(400, f"Cannot create follow-up: {reason}")
    
    # Determine if user can use AI or must create manually
    has_ai_access = await check_pitch_generation_access(user)
    
    if has_ai_access and request.use_ai:
        # AI generation for paid users
        generator_service = PitchGeneratorService()
        result = await generator_service.generate_follow_up_pitch(
            match_id=match_id,
            sequence_number=follow_up_check['next_sequence_number'],
            template_id=request.template_id or 'follow_up_template',
            context={
                'days_since_last': follow_up_check.get('days_since_sent', 0),
                'previous_subject': follow_up_check.get('subject_line'),
                'pitch_type': follow_up_check.get('pitch_type')
            }
        )
    else:
        # Manual creation for free users or by choice
        if not request.subject_line or not request.body_text:
            raise HTTPException(400, "Subject line and body text required for manual pitch creation")
        
        pitch_gen_data = {
            "campaign_id": campaign_id,
            "media_id": media_id,
            "match_id": match_id,
            "template_id": None,
            "draft_text": request.body_text,
            "ai_model_used": "manual",
            "generation_status": "manual",
            "send_ready_bool": True,
            "sequence_number": follow_up_check['next_sequence_number'],
            "pitch_metadata": {
                "manual_creation": True,
                "created_by": user.get('username'),
                "previous_pitch_gen_id": follow_up_check.get('pitch_gen_id')
            }
        }
        
        created_pitch_gen = await pitch_gen_queries.create_pitch_generation_in_db(pitch_gen_data)
        
        # Create pitch record
        pitch_data = {
            "campaign_id": campaign_id,
            "media_id": media_id,
            "attempt_no": follow_up_check['next_sequence_number'],
            "subject_line": request.subject_line,
            "body_snippet": request.body_text[:250],
            "pitch_gen_id": created_pitch_gen['pitch_gen_id'],
            "pitch_state": "ready_to_send",
            "client_approval_status": "approved",
            "created_by": f"user_{user.get('person_id')}"
        }
        
        await pitch_queries.create_pitch_in_db(pitch_data)
        
        result = {
            "pitch_gen_id": created_pitch_gen['pitch_gen_id'],
            "campaign_id": campaign_id,
            "media_id": media_id,
            "generated_at": created_pitch_gen['generated_at'],
            "status": "success",
            "message": f"Follow-up {follow_up_check['next_sequence_number']} created successfully"
        }
    
    return PitchGenerationResponse(**result)

@router.get("/campaign/{campaign_id}/media/{media_id}/pitches", response_model=List[PitchSequenceItem])
async def get_pitches_for_campaign_media(
    campaign_id: uuid.UUID,
    media_id: int,
    user: dict = Depends(get_current_user)
):
    """
    Get all pitches for a specific campaign-media combination.
    Useful when match_id is not available.
    """
    # Validate campaign ownership
    if not await validate_campaign_ownership(campaign_id, user):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    pitches = await pitch_gen_queries.get_pitch_generations_by_campaign_media(
        campaign_id, media_id
    )
    
    return pitches

@router.post("/bulk-follow-ups", response_model=BulkFollowUpResponse)
async def create_bulk_follow_ups(
    request: BulkFollowUpRequest,
    user: dict = Depends(get_current_user)
):
    """
    Create follow-ups for multiple matches at once.
    Only for matches that haven't received replies and meet timing criteria.
    Premium feature for paid users.
    """
    # Check premium access
    has_ai_access = await check_pitch_generation_access(user)
    if not has_ai_access:
        raise HTTPException(403, "Bulk follow-up generation is a Premium feature")
    
    results = {
        "successful": [],
        "failed": [],
        "skipped": []
    }
    
    for match_id in request.match_ids:
        try:
            # Validate ownership
            if not await validate_match_ownership(match_id, user):
                results["skipped"].append({
                    "match_id": match_id,
                    "reason": "Not authorized"
                })
                continue
            
            # Get match details
            match = await match_queries.get_match_suggestion_by_id_from_db(match_id)
            if not match:
                results["failed"].append({
                    "match_id": match_id,
                    "reason": "Match not found"
                })
                continue
            
            # Check if follow-up is allowed
            follow_up_check = await pitch_gen_queries.can_create_follow_up(
                match['campaign_id'], 
                match['media_id']
            )
            
            if not follow_up_check['can_follow_up']:
                results["skipped"].append({
                    "match_id": match_id,
                    "reason": follow_up_check.get('follow_up_status', 'unknown')
                })
                continue
            
            # Generate follow-up
            generator_service = PitchGeneratorService()
            result = await generator_service.generate_follow_up_pitch(
                match_id=match_id,
                sequence_number=follow_up_check['next_sequence_number'],
                template_id=request.template_id or 'follow_up_template'
            )
            
            results["successful"].append({
                "match_id": match_id,
                "pitch_gen_id": result['pitch_gen_id'],
                "sequence_number": follow_up_check['next_sequence_number']
            })
            
        except Exception as e:
            logger.exception(f"Error creating follow-up for match {match_id}: {e}")
            results["failed"].append({
                "match_id": match_id,
                "reason": str(e)
            })
    
    return results
```

#### 3. Update Schemas

##### podcast_outreach/api/schemas/pitch_schemas.py

```python
class FollowUpPitchRequest(BaseModel):
    """Request for creating a follow-up pitch"""
    use_ai: bool = Field(True, description="Use AI generation (Premium) or manual creation")
    template_id: Optional[str] = Field(None, description="Template ID for AI generation")
    subject_line: Optional[str] = Field(None, description="Subject for manual creation")
    body_text: Optional[str] = Field(None, description="Body for manual creation")
    
class PitchSequenceItem(BaseModel):
    """Represents a pitch in a sequence"""
    pitch_gen_id: int
    sequence_number: int
    pitch_type: str
    generated_at: datetime
    send_ready_bool: bool
    pitch_state: Optional[str]
    send_ts: Optional[datetime]
    reply_bool: Optional[bool]
    opened_ts: Optional[datetime]
    clicked_ts: Optional[datetime]
    days_since_sent: Optional[int]
    sequence_position: str  # e.g., "2 of 3"
    can_send: bool
    
class BulkFollowUpRequest(BaseModel):
    """Request for bulk follow-up generation"""
    match_ids: List[int] = Field(..., min_items=1, max_items=50)
    template_id: Optional[str] = Field(None, description="Template to use for all follow-ups")
    min_days_since_last: int = Field(7, ge=3, le=30, description="Minimum days since last pitch")
    
class BulkFollowUpResponse(BaseModel):
    """Response for bulk follow-up generation"""
    successful: List[Dict[str, Any]]
    failed: List[Dict[str, Any]]
    skipped: List[Dict[str, Any]]
    summary: Dict[str, int]
```

### Frontend Implementation

#### 1. Pitch Sequence Component

```typescript
// components/PitchSequence.tsx

interface PitchSequence {
  match_id: number;
  pitches: PitchGeneration[];
  canCreateFollowUp: boolean;
  nextSequenceNumber: number;
}

const PitchSequenceView: React.FC<{matchId: number}> = ({matchId}) => {
  const [sequence, setSequence] = useState<PitchSequence | null>(null);
  const [creating, setCreating] = useState(false);
  
  const loadSequence = async () => {
    const response = await api.get(`/pitches/match/${matchId}/pitch-sequence`);
    setSequence(response.data);
  };
  
  const createFollowUp = async (useAI: boolean) => {
    setCreating(true);
    try {
      if (useAI && user.plan === 'paid') {
        await api.post(`/pitches/match/${matchId}/create-follow-up`, {
          use_ai: true,
          template_id: 'follow_up_template'
        });
      } else {
        // Show manual creation modal
        showManualPitchModal(matchId, sequence.nextSequenceNumber);
      }
      await loadSequence();
    } finally {
      setCreating(false);
    }
  };
  
  return (
    <div className="pitch-sequence-container">
      <h3>Pitch Sequence</h3>
      
      <div className="sequence-timeline">
        {sequence?.pitches.map((pitch, idx) => (
          <PitchTimelineItem 
            key={pitch.pitch_gen_id}
            pitch={pitch}
            isLast={idx === sequence.pitches.length - 1}
          />
        ))}
      </div>
      
      {sequence?.canCreateFollowUp && (
        <div className="follow-up-actions">
          <h4>Create Follow-up #{sequence.nextSequenceNumber}</h4>
          
          {user.plan === 'paid' ? (
            <>
              <button 
                onClick={() => createFollowUp(true)}
                disabled={creating}
                className="btn-primary"
              >
                Generate with AI
              </button>
              <button 
                onClick={() => createFollowUp(false)}
                disabled={creating}
                className="btn-secondary"
              >
                Write Manually
              </button>
            </>
          ) : (
            <button 
              onClick={() => createFollowUp(false)}
              disabled={creating}
              className="btn-primary"
            >
              Create Manual Follow-up
            </button>
          )}
        </div>
      )}
    </div>
  );
};
```

#### 2. Manual Pitch Creation Modal

```typescript
// components/ManualFollowUpModal.tsx

const ManualFollowUpModal: React.FC<{
  matchId: number;
  sequenceNumber: number;
  onClose: () => void;
  onSuccess: () => void;
}> = ({matchId, sequenceNumber, onClose, onSuccess}) => {
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [saving, setSaving] = useState(false);
  
  // Load previous pitch for context
  useEffect(() => {
    if (sequenceNumber > 1) {
      loadPreviousPitch();
    }
  }, [matchId, sequenceNumber]);
  
  const getFollowUpTemplate = () => {
    if (sequenceNumber === 2) {
      return {
        subject: "Following up: [Previous Subject]",
        body: "Hi [Name],\n\nI wanted to follow up on my previous email about..."
      };
    } else if (sequenceNumber === 3) {
      return {
        subject: "Quick follow-up",
        body: "Hi [Name],\n\nI know you're busy, so I'll keep this brief..."
      };
    }
    return {subject: '', body: ''};
  };
  
  const handleSave = async () => {
    setSaving(true);
    try {
      await api.post(`/pitches/match/${matchId}/create-follow-up`, {
        use_ai: false,
        subject_line: subject,
        body_text: body
      });
      onSuccess();
      onClose();
    } catch (error) {
      alert('Failed to create follow-up');
    } finally {
      setSaving(false);
    }
  };
  
  return (
    <Modal>
      <h2>Create Follow-up #{sequenceNumber}</h2>
      
      <div className="template-suggestions">
        <button onClick={() => {
          const template = getFollowUpTemplate();
          setSubject(template.subject);
          setBody(template.body);
        }}>
          Use Template
        </button>
      </div>
      
      <input
        type="text"
        placeholder="Subject line"
        value={subject}
        onChange={(e) => setSubject(e.target.value)}
      />
      
      <textarea
        placeholder="Email body"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={15}
      />
      
      <div className="modal-actions">
        <button onClick={onClose}>Cancel</button>
        <button 
          onClick={handleSave}
          disabled={!subject || !body || saving}
        >
          Create Follow-up
        </button>
      </div>
    </Modal>
  );
};
```

### Automation Features (Premium)

#### 1. Automatic Follow-up Scheduler

```python
# podcast_outreach/services/automation/follow_up_scheduler.py

class FollowUpScheduler:
    """Handles automatic follow-up generation for premium users"""
    
    async def schedule_follow_ups_for_campaign(
        self, 
        campaign_id: uuid.UUID,
        follow_up_rules: Dict[str, Any]
    ):
        """
        Schedule automatic follow-ups based on rules.
        
        Rules example:
        {
            "follow_up_1": {"days_after": 7, "template": "follow_up_1"},
            "follow_up_2": {"days_after": 14, "template": "follow_up_2"},
            "follow_up_3": {"days_after": 21, "template": "follow_up_3"}
        }
        """
        query = """
        SELECT DISTINCT ON (p.media_id) 
            p.*, 
            pg.sequence_number,
            ms.match_id
        FROM pitches p
        JOIN pitch_generations pg ON p.pitch_gen_id = pg.pitch_gen_id
        JOIN match_suggestions ms ON pg.match_id = ms.match_id
        WHERE p.campaign_id = $1
        AND p.pitch_state = 'sent'
        AND p.reply_bool = FALSE
        AND pg.sequence_number < 4
        ORDER BY p.media_id, pg.sequence_number DESC;
        """
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            pitches = await conn.fetch(query, campaign_id)
            
            for pitch in pitches:
                await self._check_and_create_follow_up(
                    pitch, 
                    follow_up_rules
                )
    
    async def _check_and_create_follow_up(
        self,
        pitch: Dict[str, Any],
        rules: Dict[str, Any]
    ):
        """Check if a follow-up should be created based on rules"""
        days_since_sent = (datetime.now() - pitch['send_ts']).days
        next_sequence = pitch['sequence_number'] + 1
        
        rule_key = f"follow_up_{next_sequence - 1}"
        if rule_key not in rules:
            return
        
        rule = rules[rule_key]
        if days_since_sent >= rule['days_after']:
            # Create follow-up
            generator = PitchGeneratorService()
            await generator.generate_follow_up_pitch(
                match_id=pitch['match_id'],
                sequence_number=next_sequence,
                template_id=rule['template']
            )
```

### Analytics and Reporting

#### 1. Sequence Performance Queries

```sql
-- Get pitch sequence performance metrics
CREATE OR REPLACE VIEW pitch_sequence_metrics AS
SELECT 
    pg.campaign_id,
    pg.media_id,
    pg.sequence_number,
    pg.pitch_type,
    COUNT(*) as total_sent,
    SUM(CASE WHEN p.reply_bool THEN 1 ELSE 0 END) as replies,
    SUM(CASE WHEN p.opened_ts IS NOT NULL THEN 1 ELSE 0 END) as opens,
    SUM(CASE WHEN p.clicked_ts IS NOT NULL THEN 1 ELSE 0 END) as clicks,
    AVG(EXTRACT(DAY FROM p.reply_ts - p.send_ts)) as avg_reply_time_days,
    ROUND(AVG(CASE WHEN p.reply_bool THEN 1.0 ELSE 0.0 END) * 100, 2) as reply_rate
FROM pitch_generations pg
JOIN pitches p ON pg.pitch_gen_id = p.pitch_gen_id
WHERE p.send_ts IS NOT NULL
GROUP BY pg.campaign_id, pg.media_id, pg.sequence_number, pg.pitch_type;

-- Get optimal follow-up timing
CREATE OR REPLACE VIEW optimal_follow_up_timing AS
SELECT 
    pg.pitch_type,
    EXTRACT(DAY FROM p.send_ts - lag_p.send_ts) as days_between,
    COUNT(*) as total_attempts,
    SUM(CASE WHEN p.reply_bool THEN 1 ELSE 0 END) as successful_replies,
    ROUND(AVG(CASE WHEN p.reply_bool THEN 1.0 ELSE 0.0 END) * 100, 2) as success_rate
FROM pitch_generations pg
JOIN pitches p ON pg.pitch_gen_id = p.pitch_gen_id
JOIN LATERAL (
    SELECT send_ts 
    FROM pitches p2
    JOIN pitch_generations pg2 ON p2.pitch_gen_id = pg2.pitch_gen_id
    WHERE pg2.campaign_id = pg.campaign_id 
    AND pg2.media_id = pg.media_id
    AND pg2.sequence_number = pg.sequence_number - 1
) lag_p ON true
WHERE pg.sequence_number > 1
GROUP BY pg.pitch_type, days_between
ORDER BY pg.pitch_type, days_between;
```

### Migration Plan

#### Phase 1: Database Changes (Week 1)
1. Create migration script
2. Test on staging database
3. Deploy to production with rollback plan
4. Run data migration for existing records

#### Phase 2: Backend API (Week 2)
1. Update query functions
2. Add new endpoints
3. Update existing endpoints for backward compatibility
4. Deploy API changes

#### Phase 3: Frontend Basic (Week 3)
1. Add pitch sequence view component
2. Add manual follow-up creation
3. Update existing pitch views
4. Deploy frontend changes

#### Phase 4: Premium Features (Week 4)
1. Add AI follow-up generation
2. Add bulk follow-up creation
3. Add automation scheduler
4. Deploy premium features

#### Phase 5: Analytics (Week 5)
1. Create analytics views
2. Add reporting endpoints
3. Create dashboard components
4. Deploy analytics features

### Testing Strategy

#### Unit Tests
```python
# tests/test_pitch_sequences.py

async def test_sequence_number_increment():
    """Test that sequence numbers increment correctly"""
    # Create initial pitch
    pitch1 = await create_pitch_generation({
        'campaign_id': test_campaign_id,
        'media_id': test_media_id,
        'draft_text': 'Initial pitch'
    })
    assert pitch1['sequence_number'] == 1
    assert pitch1['pitch_type'] == 'initial'
    
    # Create follow-up
    pitch2 = await create_pitch_generation({
        'campaign_id': test_campaign_id,
        'media_id': test_media_id,
        'draft_text': 'Follow-up 1'
    })
    assert pitch2['sequence_number'] == 2
    assert pitch2['pitch_type'] == 'follow_up_1'

async def test_follow_up_restrictions():
    """Test that follow-up creation respects business rules"""
    # Test can't create follow-up too soon
    result = await can_create_follow_up(campaign_id, media_id)
    assert result['follow_up_status'] == 'too_recent'
    
    # Test can't create follow-up after reply
    # ... etc
```

### Rollback Plan

If issues arise, rollback strategy:

```sql
-- Remove new columns
ALTER TABLE pitch_generations 
DROP COLUMN IF EXISTS match_id,
DROP COLUMN IF EXISTS sequence_number,
DROP COLUMN IF EXISTS pitch_type,
DROP COLUMN IF EXISTS pitch_metadata;

-- Drop new indexes
DROP INDEX IF EXISTS idx_pitch_generations_match_id;
DROP INDEX IF EXISTS idx_pitch_generations_campaign_media;
DROP INDEX IF EXISTS idx_pitch_generations_sequence;
DROP INDEX IF EXISTS idx_unique_campaign_media_sequence;

-- Drop new functions
DROP FUNCTION IF EXISTS get_next_pitch_sequence_number;
DROP FUNCTION IF EXISTS determine_pitch_type;
```

### Success Metrics

1. **Adoption Rate**: % of users creating follow-ups
2. **Reply Rate Improvement**: Compare single vs multiple pitch sequences
3. **Optimal Timing**: Identify best days between follow-ups
4. **Sequence Completion**: % of sequences that reach 3+ pitches
5. **Premium Conversion**: Free users upgrading for automation

### Documentation

Update API documentation with new endpoints:
- GET `/pitches/match/{match_id}/pitch-sequence`
- POST `/pitches/match/{match_id}/create-follow-up`
- GET `/pitches/campaign/{campaign_id}/media/{media_id}/pitches`
- POST `/pitches/bulk-follow-ups`

### Security Considerations

1. **Rate Limiting**: Limit follow-up creation to prevent spam
2. **Ownership Validation**: Ensure users can only create follow-ups for their matches
3. **Sequence Limits**: Max 4 pitches per match to prevent harassment
4. **Time Restrictions**: Minimum 7 days between pitches

This implementation provides a robust, scalable solution for multiple pitches per match while maintaining backward compatibility and clear upgrade paths for premium features.