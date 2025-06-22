# PGL Podcast Outreach System - Complete Workflow Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Client Workflow](#client-workflow)
3. [Admin/Staff Workflow](#adminstafi-workflow)
4. [API Endpoints for Frontend](#api-endpoints-for-frontend)
5. [Database Schema Reference](#database-schema-reference)
6. [Event-Driven Background Processes](#event-driven-background-processes)
7. [Frontend Implementation Guide](#frontend-implementation-guide)

---

## System Overview

The PGL Podcast Outreach System is an AI-powered platform that automates the discovery, analysis, and vetting of podcast opportunities for client campaigns. The system uses event-driven architecture to minimize manual intervention while providing human oversight at critical decision points.

### Core Components
- **Campaign Management**: Client goals, keywords, and targeting criteria
- **Podcast Discovery**: Automated search via ListenNotes and PodScan APIs
- **Content Analysis**: AI transcription, summarization, and embedding generation
- **Quality Assessment**: Automated scoring based on audience, engagement, and content
- **AI Vetting**: Intelligent matching against campaign criteria with detailed reasoning
- **Human Review**: Final approval/rejection by staff with full AI context
- **Outreach Management**: Pitch generation and tracking

---

## Client Workflow

### Phase 1: Campaign Setup & Onboarding

#### 1.1 Client Profile Creation
**Frontend Screens Needed:**
- Client registration/login form
- Company profile setup
- Contact information management

**Key API Endpoints:**
```
POST /api/auth/register - Client registration
POST /api/auth/login - Client authentication
GET /api/client/profile - Get client profile
PUT /api/client/profile - Update client profile
```

**Data Required:**
- Company name, website, industry
- Primary contact details
- Billing information
- Campaign preferences

#### 1.2 Campaign Creation
**Frontend Screens Needed:**
- Campaign wizard/form
- Keyword management interface
- Target audience definition
- Campaign goals setting

**Key API Endpoints:**
```
POST /api/campaigns - Create new campaign
GET /api/campaigns/{id} - Get campaign details
PUT /api/campaigns/{id} - Update campaign
GET /api/campaigns/{id}/status - Get campaign progress
```

**Required Campaign Data:**
```json
{
  "campaign_name": "Q1 2024 Product Launch",
  "campaign_description": "Promoting our new AI-powered analytics tool",
  "campaign_keywords": ["analytics", "AI", "business intelligence", "data science"],
  "target_audience": "Business professionals, data analysts, CTOs",
  "campaign_goals": "Generate leads, increase brand awareness",
  "budget_range": "$5000-$10000",
  "timeline": "3 months",
  "preferred_podcast_categories": ["Business", "Technology", "Entrepreneurship"],
  "guest_bio": "CEO with 10 years experience in AI/ML",
  "key_talking_points": ["AI democratization", "Data-driven decisions"]
}
```

#### 1.3 Client Dashboard
**Frontend Components Needed:**
- Campaign overview cards
- Progress tracking charts
- Recent activity feed
- Quick action buttons

**Dashboard API Endpoints:**
```
GET /api/dashboard/overview - Campaign summary stats
GET /api/dashboard/recent-activity - Latest updates
GET /api/campaigns/{id}/metrics - Campaign-specific metrics
```

**Dashboard Data Structure:**
```json
{
  "campaigns": [
    {
      "campaign_id": "uuid",
      "name": "Q1 2024 Product Launch",
      "status": "active",
      "created_at": "2024-01-15T10:00:00Z",
      "metrics": {
        "podcasts_discovered": 156,
        "matches_pending_review": 23,
        "matches_approved": 8,
        "pitches_sent": 5,
        "interviews_scheduled": 2
      },
      "progress_percentage": 35
    }
  ],
  "overall_stats": {
    "total_campaigns": 3,
    "active_campaigns": 2,
    "total_matches_this_month": 45,
    "response_rate": "18%"
  }
}
```

### Phase 2: Podcast Discovery & Matching (Automated)

#### 2.1 Discovery Process (Behind the Scenes)
The system automatically discovers podcasts based on campaign keywords. Clients can monitor but don't directly control this process.

**Frontend Display:**
- Progress indicator showing discovery status
- Live counter of podcasts found
- Quality distribution charts

**Monitoring API:**
```
GET /api/campaigns/{id}/discovery-status
```

**Response:**
```json
{
  "status": "in_progress",
  "podcasts_discovered": 156,
  "last_discovery_run": "2024-01-15T14:30:00Z",
  "next_scheduled_run": "2024-01-16T02:00:00Z",
  "quality_distribution": {
    "high": 23,
    "medium": 89,
    "low": 44
  },
  "sources": {
    "ListenNotes": 98,
    "PodScan": 58
  }
}
```

#### 2.2 Match Review Interface
This is where clients see and review podcast opportunities that have been AI-vetted and are ready for approval.

**Frontend Components:**
- Match cards with podcast details
- AI vetting scores and reasoning display
- Approve/Reject buttons with required notes/reasons
- Filtering and sorting options (pending_client_review, client_approved, client_rejected)
- Detailed podcast profiles with vetting analysis

**Key API Endpoints:**
```
GET /api/match-suggestions/campaign/{campaign_id}?status=pending_client_review - Get matches pending client review
GET /api/match-suggestions/{match_id} - Get detailed match information with AI analysis
POST /api/match-suggestions/{match_id}/approve - Approve a vetted match (optional notes)
POST /api/match-suggestions/{match_id}/reject - Reject a vetted match (required reason)
```

**Match Data Structure:**
```json
{
  "match_id": "uuid",
  "campaign_id": "uuid",
  "status": "pending_client_review",
  "created_at": "2024-01-15T12:00:00Z",
  
  // AI Vetting Information
  "vetting_score": 8.5,
  "vetting_reasoning": "Strong alignment with AI/analytics focus. Host frequently discusses business technology. Audience demographics match target market (75% business professionals). High engagement rates (4.8/5 rating, 50K+ downloads per episode).",
  "vetting_checklist": {
    "audience_alignment": {"score": 9, "weight": 0.3, "reasoning": "Target audience matches campaign demographics"},
    "content_relevance": {"score": 8, "weight": 0.25, "reasoning": "Frequently covers AI and business analytics topics"},
    "host_credibility": {"score": 8, "weight": 0.2, "reasoning": "Industry expert with strong following"},
    "engagement_quality": {"score": 9, "weight": 0.15, "reasoning": "High listener engagement and interaction"},
    "production_quality": {"score": 7, "weight": 0.1, "reasoning": "Professional production, consistent publishing schedule"}
  },
  
  // Podcast Information
  "podcast": {
    "name": "The Business Intelligence Show",
    "description": "Weekly insights on data analytics and business intelligence",
    "host_name": "Sarah Johnson",
    "category": "Business",
    "image_url": "https://...",
    "website": "https://...",
    "contact_email": "sarah@bishow.com",
    "social_links": {
      "linkedin": "https://linkedin.com/in/sarahjohnson",
      "twitter": "https://twitter.com/sarahbi"
    },
    "statistics": {
      "total_episodes": 156,
      "average_downloads": 52000,
      "rating": 4.8,
      "review_count": 1240,
      "publishing_frequency": "Weekly"
    }
  },
  
  // Best Matching Content
  "best_matching_episode": {
    "title": "How AI is Transforming Business Decision Making",
    "description": "Deep dive into AI analytics tools and their impact",
    "published_date": "2024-01-10T00:00:00Z",
    "duration_minutes": 45,
    "download_count": 67000
  },
  
  // Match Scoring Details
  "match_score": 0.87,
  "matched_keywords": ["AI", "analytics", "business intelligence"],
  "ai_reasoning": "High content similarity score (0.91) based on episode transcripts. Strong keyword overlap with campaign focus."
}
```

#### 2.3 Client Review Actions
**Frontend Flow:**
1. Client views vetted matches with status "pending_client_review" in dashboard
2. Clicks on match to see detailed AI vetting analysis and scores
3. Reviews AI reasoning, scoring breakdown, and podcast details
4. Makes approve/reject decision with required notes/reasons
5. System updates match status to "client_approved" or "client_rejected"
6. Approved matches proceed to outreach phase automatically

**Client Action API Calls:**
```javascript
// Approve a match
const approvalResponse = await fetch(`/api/match-suggestions/${matchId}/approve`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ approval_notes: "Great fit for our campaign goals" })
});

// Reject a match
const rejectionResponse = await fetch(`/api/match-suggestions/${matchId}/reject`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ rejection_reason: "Audience doesn't align with our target market" })
});
```

**Match Status Flow:**
- `pending_vetting` → AI analysis in progress
- `pending_client_review` → Ready for client decision  
- `client_approved` → Client approved, ready for outreach
- `client_rejected` → Client rejected, no further action

---

## Admin/Staff Workflow

### Phase 1: System Management & Monitoring

#### 1.1 Admin Dashboard
**Frontend Components:**
- System health indicators
- Active campaigns overview
- Background task status
- Performance metrics
- User management

**Admin Dashboard API:**
```
GET /api/admin/dashboard - System overview
GET /api/admin/system-health - Background process status
GET /api/admin/metrics - Performance analytics
```

**Admin Dashboard Data:**
```json
{
  "system_status": {
    "discovery_pipeline": "running",
    "transcription_pipeline": "running",
    "vetting_pipeline": "running",
    "enrichment_pipeline": "running",
    "last_health_check": "2024-01-15T15:45:00Z"
  },
  "active_campaigns": 15,
  "pending_review_tasks": 47,
  "daily_metrics": {
    "podcasts_discovered": 234,
    "episodes_transcribed": 89,
    "matches_created": 67,
    "matches_vetted": 45
  },
  "pipeline_performance": {
    "discovery_success_rate": "94%",
    "transcription_success_rate": "89%",
    "vetting_completion_rate": "96%"
  }
}
```

#### 1.2 Review Task Management
This is the primary interface for staff to handle various review tasks in the system.

**Frontend Components:**
- Task queue interface
- Task filtering and prioritization
- Detailed task viewers
- Bulk actions
- Assignment management

**Review Tasks API:**
```
GET /api/admin/review-tasks - Get all review tasks
GET /api/admin/review-tasks/{id} - Get specific task
PUT /api/admin/review-tasks/{id}/assign - Assign task to staff member
PUT /api/admin/review-tasks/{id}/complete - Mark task complete
```

**Task Types and Data:**

**Match Suggestion Review Task:**
```json
{
  "review_task_id": "uuid",
  "task_type": "match_suggestion",
  "status": "pending",
  "priority": "high",
  "created_at": "2024-01-15T10:00:00Z",
  "assigned_to": "staff@pgl.com",
  "campaign_name": "Q1 2024 Product Launch",
  "client_name": "TechCorp Inc",
  
  // Match Information with AI Analysis
  "match_data": {
    "match_id": "uuid",
    "vetting_score": 8.5,
    "vetting_reasoning": "Detailed AI analysis of why this is a good match...",
    "vetting_checklist": {
      "audience_alignment": {"score": 9, "reasoning": "Perfect demographic match"},
      "content_relevance": {"score": 8, "reasoning": "Host covers AI topics frequently"}
    },
    "podcast_name": "The Business Intelligence Show",
    "host_name": "Sarah Johnson",
    "contact_email": "sarah@bishow.com",
    "match_score": 0.87,
    "matched_keywords": ["AI", "analytics"]
  },
  
  // Staff Action Required
  "required_action": "Review AI vetting and approve/reject for client presentation",
  "notes": "High-priority client, fast turnaround requested"
}
```

### Phase 2: Content & Quality Management

#### 2.1 Media Kit Generation Review
**Frontend Components:**
- Media kit preview interface
- Content editing capabilities
- Approval workflow
- Template management

**Media Kit API:**
```
GET /api/admin/media-kits/pending - Get kits awaiting review
GET /api/media-kits/{id} - Get specific media kit
PUT /api/media-kits/{id}/approve - Approve media kit
PUT /api/media-kits/{id}/request-changes - Request modifications
```

#### 2.2 Pitch Generation & Approval
**Frontend Components:**
- Pitch template management
- Generated pitch review
- Customization interface
- Send/schedule controls

**Pitch Management API:**
```
GET /api/admin/pitches/pending - Get pitches awaiting approval
GET /api/pitches/{id} - Get specific pitch
PUT /api/pitches/{id}/approve - Approve pitch for sending
PUT /api/pitches/{id}/edit - Modify pitch content
POST /api/pitches/{id}/send - Send approved pitch
```

### Phase 3: Campaign Monitoring & Optimization

#### 3.1 Campaign Performance Analysis
**Frontend Components:**
- Performance dashboards
- ROI tracking
- Success rate analytics
- Recommendation engine

**Analytics API:**
```
GET /api/admin/campaigns/{id}/analytics - Detailed campaign performance
GET /api/admin/analytics/trends - System-wide trends
GET /api/admin/analytics/optimization-suggestions - AI recommendations
```

#### 3.2 Quality Control & System Tuning
**Frontend Components:**
- AI model performance monitoring
- Quality score calibration
- Feedback incorporation
- System parameter adjustment

---

## API Endpoints for Frontend

### Authentication & User Management
```
POST /api/auth/register - User registration
POST /api/auth/login - User authentication
POST /api/auth/logout - User logout
GET /api/auth/verify-token - Token validation
PUT /api/auth/change-password - Password update

GET /api/users/profile - Get user profile
PUT /api/users/profile - Update user profile
GET /api/users/preferences - Get user preferences
PUT /api/users/preferences - Update preferences
```

### Campaign Management
```
GET /api/campaigns - List campaigns (paginated)
POST /api/campaigns - Create new campaign
GET /api/campaigns/{id} - Get campaign details
PUT /api/campaigns/{id} - Update campaign
DELETE /api/campaigns/{id} - Delete campaign
GET /api/campaigns/{id}/status - Get campaign status
GET /api/campaigns/{id}/metrics - Get campaign metrics
```

### Match & Review Management
```
GET /api/match-suggestions/campaign/{campaign_id} - Get matches for campaign (with status filter)
GET /api/match-suggestions/{match_id} - Get detailed match with AI vetting data
POST /api/match-suggestions/{match_id}/approve - Client approve vetted match
POST /api/match-suggestions/{match_id}/reject - Client reject vetted match (reason required)
PUT /api/match-suggestions/{match_id} - Admin update match (admin only)

GET /api/review-tasks - Get review tasks (with filters)
GET /api/review-tasks/{id} - Get specific review task
PUT /api/review-tasks/{id}/assign - Assign task
PUT /api/review-tasks/{id}/status - Update task status
```

### Media & Content Management
```
GET /api/media - Search/browse podcasts
GET /api/media/{id} - Get podcast details
GET /api/media/{id}/episodes - Get podcast episodes
POST /api/media/discover - Trigger manual discovery

GET /api/media-kits - List media kits
POST /api/media-kits - Create media kit
GET /api/media-kits/{id} - Get media kit
PUT /api/media-kits/{id} - Update media kit
```

### Pitch & Outreach Management
```
GET /api/pitches - List pitches
POST /api/pitches - Create pitch
GET /api/pitches/{id} - Get pitch details
PUT /api/pitches/{id} - Update pitch
POST /api/pitches/{id}/send - Send pitch

GET /api/pitch-templates - List templates
POST /api/pitch-templates - Create template
PUT /api/pitch-templates/{id} - Update template
```

### Dashboard & Analytics
```
GET /api/dashboard/overview - Dashboard summary
GET /api/dashboard/recent-activity - Recent activities
GET /api/analytics/campaigns - Campaign analytics
GET /api/analytics/performance - Performance metrics
GET /api/analytics/trends - Trend analysis
```

### Admin Endpoints
```
GET /api/admin/dashboard - Admin dashboard
GET /api/admin/system-health - System status
GET /api/admin/users - User management
GET /api/admin/campaigns - All campaigns overview
GET /api/admin/review-tasks - All review tasks
GET /api/admin/analytics - System analytics
```

---

## Database Schema Reference

### Key Tables and Relationships

#### Campaigns Table
```sql
campaigns (
  campaign_id UUID PRIMARY KEY,
  client_id UUID REFERENCES users(user_id),
  campaign_name VARCHAR(255),
  campaign_description TEXT,
  campaign_keywords TEXT[], -- Array of keywords
  target_audience TEXT,
  campaign_goals TEXT,
  budget_range VARCHAR(100),
  status VARCHAR(50) DEFAULT 'active',
  embedding VECTOR(1536), -- OpenAI embedding
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
)
```

#### Media Table
```sql
media (
  media_id SERIAL PRIMARY KEY,
  name VARCHAR(500),
  description TEXT,
  rss_url VARCHAR(1000),
  website VARCHAR(500),
  contact_email VARCHAR(255),
  source_api VARCHAR(50), -- 'ListenNotes' or 'PodscanFM'
  api_id VARCHAR(100),
  category VARCHAR(100),
  total_episodes INTEGER,
  quality_score DECIMAL(3,2),
  audience_size INTEGER,
  listen_score INTEGER,
  last_enriched_timestamp TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW()
)
```

#### Match Suggestions Table
```sql
match_suggestions (
  match_id UUID PRIMARY KEY,
  campaign_id UUID REFERENCES campaigns(campaign_id),
  media_id INTEGER REFERENCES media(media_id),
  match_score DECIMAL(5,4),
  matched_keywords TEXT[],
  status VARCHAR(50) DEFAULT 'pending_vetting',
  
  -- AI Vetting Fields
  vetting_score DECIMAL(3,1), -- 0-10 scale
  vetting_reasoning TEXT,
  vetting_checklist JSONB,
  last_vetted_at TIMESTAMP,
  
  -- Human Review
  human_review_status VARCHAR(50),
  human_review_notes TEXT,
  reviewed_by UUID REFERENCES users(user_id),
  reviewed_at TIMESTAMP,
  
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
)
```

#### Review Tasks Table
```sql
review_tasks (
  review_task_id UUID PRIMARY KEY,
  task_type VARCHAR(100), -- 'match_suggestion', 'media_kit', 'pitch'
  related_id UUID, -- ID of the item being reviewed
  campaign_id UUID REFERENCES campaigns(campaign_id),
  assigned_to UUID REFERENCES users(user_id),
  status VARCHAR(50) DEFAULT 'pending',
  priority VARCHAR(20) DEFAULT 'medium',
  notes TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  completed_at TIMESTAMP
)
```

---

## Event-Driven Background Processes

### Automated Workflow Sequence

1. **Media Discovery** (Every 4 hours for active campaigns)
   - System discovers new podcasts via APIs
   - Creates media records
   - Triggers enrichment process

2. **Content Enrichment** (Triggered by new media)
   - Fetches additional metadata
   - Calculates quality scores
   - Updates social media links
   - Triggers vetting process

3. **Episode Transcription** (Every 30 minutes)
   - Processes queued episodes
   - Generates transcripts and summaries
   - Creates embeddings for content matching

4. **AI Vetting** (Every 15 minutes)
   - Analyzes enriched media against campaigns
   - Generates vetting scores and reasoning
   - Creates review tasks for staff

5. **Match Creation** (Triggered by transcription)
   - Calculates similarity scores
   - Creates match suggestions
   - Queues for human review

### Background Task Status Monitoring

**Frontend Components Needed:**
- Real-time status indicators
- Process health monitoring
- Error reporting and alerting
- Manual trigger controls for admins

**Task Status API:**
```
GET /api/admin/tasks/status - Get all background task statuses
GET /api/admin/tasks/{type}/logs - Get logs for specific task type
POST /api/admin/tasks/{type}/trigger - Manually trigger task
POST /api/admin/tasks/{type}/pause - Pause task execution
POST /api/admin/tasks/{type}/resume - Resume task execution
```

---

## Frontend Implementation Guide

### State Management Recommendations

#### Client Dashboard State
```javascript
// Campaign State
const campaignState = {
  activeCampaigns: [],
  selectedCampaign: null,
  discoveryStatus: {},
  pendingMatches: [],
  approvedMatches: [],
  rejectedMatches: []
}

// Match Review State
const matchReviewState = {
  currentMatch: null,
  vettingDetails: {},
  userDecision: null,
  reviewNotes: '',
  isSubmitting: false
}
```

#### Admin Dashboard State
```javascript
// Admin State
const adminState = {
  systemHealth: {},
  pendingTasks: [],
  assignedTasks: [],
  completedTasks: [],
  selectedTask: null,
  performanceMetrics: {}
}

// Review Task State
const reviewTaskState = {
  currentTask: null,
  taskNotes: '',
  isProcessing: false,
  assignedStaff: null
}
```

### Key UI Components

#### 1. Match Review Card Component
```jsx
<MatchReviewCard 
  match={matchData}
  vettingScore={8.5}
  vettingReasoning="..."
  vettingChecklist={checklistData}
  onApprove={handleApprove}
  onReject={handleReject}
  showDetails={true}
/>
```

**Required Props:**
- match: Complete match object with podcast details
- vettingScore: AI-generated score (0-10)
- vettingReasoning: Detailed AI explanation
- vettingChecklist: Breakdown of scoring criteria
- Callback functions for approve/reject actions

#### 2. AI Vetting Display Component
```jsx
<VettingAnalysis 
  score={8.5}
  reasoning="Strong alignment with campaign goals..."
  checklist={vettingChecklist}
  confidence="high"
/>
```

**Checklist Data Structure:**
```javascript
const vettingChecklist = {
  audience_alignment: {
    score: 9,
    weight: 0.3,
    reasoning: "Target demographics match perfectly"
  },
  content_relevance: {
    score: 8,
    weight: 0.25,
    reasoning: "Host frequently discusses relevant topics"
  },
  // ... more criteria
}
```

#### 3. Review Task Management Component
```jsx
<ReviewTaskQueue 
  tasks={pendingTasks}
  filters={taskFilters}
  onTaskSelect={handleTaskSelect}
  onAssign={handleAssignment}
  onComplete={handleCompletion}
/>
```

### Data Flow Examples

#### Client Match Review Flow
```javascript
// 1. Fetch pending matches
const matches = await api.get(`/campaigns/${campaignId}/matches`);

// 2. Display match with AI analysis
const matchDetails = await api.get(`/matches/${matchId}`);

// 3. User makes decision
const decision = await api.post(`/matches/${matchId}/approve`, {
  notes: userNotes
});

// 4. Update UI state
setCampaignMatches(prevMatches => 
  prevMatches.filter(m => m.match_id !== matchId)
);
```

#### Admin Task Review Flow
```javascript
// 1. Fetch review tasks
const tasks = await api.get('/admin/review-tasks', {
  params: { status: 'pending', type: 'match_suggestion' }
});

// 2. Get detailed task information
const taskDetails = await api.get(`/review-tasks/${taskId}`);

// 3. Process task
const result = await api.put(`/review-tasks/${taskId}/complete`, {
  decision: 'approved',
  notes: staffNotes
});
```

### Error Handling & Loading States

#### API Error Handling
```javascript
const handleApiCall = async (apiCall) => {
  try {
    setLoading(true);
    const result = await apiCall();
    return result;
  } catch (error) {
    if (error.response?.status === 401) {
      // Handle authentication error
      redirectToLogin();
    } else if (error.response?.status === 403) {
      // Handle permission error
      showErrorMessage('You don\'t have permission for this action');
    } else {
      // Handle general error
      showErrorMessage('An error occurred. Please try again.');
    }
    console.error('API Error:', error);
  } finally {
    setLoading(false);
  }
};
```

#### Loading States for Long Operations
```jsx
// Match vetting in progress
<LoadingState 
  message="AI is analyzing this podcast match..."
  progress={vettingProgress}
  estimatedTime="2-3 minutes"
/>

// Discovery process
<DiscoveryProgress 
  discovered={156}
  processed={89}
  status="Enriching podcast profiles..."
/>
```

### Real-time Updates

#### WebSocket Integration for Live Updates
```javascript
// Connect to real-time updates
const socket = io('/dashboard');

socket.on('campaign_update', (data) => {
  updateCampaignMetrics(data.campaignId, data.metrics);
});

socket.on('new_match', (data) => {
  addNewMatch(data.match);
  showNotification('New podcast match found!');
});

socket.on('task_completed', (data) => {
  updateTaskStatus(data.taskId, 'completed');
});
```

### Mobile Responsiveness

#### Key Considerations
- Match cards should stack vertically on mobile
- AI vetting details should be collapsible
- Review actions should be easily accessible
- Dashboard metrics should reflow appropriately
- Task management should support swipe gestures

### Accessibility Requirements

- All interactive elements must be keyboard accessible
- Color-coding must be supplemented with text/icons
- Screen reader support for AI analysis content
- High contrast mode compatibility
- Focus management for modal dialogs

This documentation provides the complete foundation for frontend implementation. The backend APIs are designed to support all these workflows with proper data structures and real-time capabilities.