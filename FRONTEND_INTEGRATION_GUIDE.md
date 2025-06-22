# 🚀 FRONTEND INTEGRATION GUIDE
**Complete API Documentation for React Vite Frontend**

---

## **📋 OVERVIEW**

Your automated podcast discovery system now provides these key user journeys:

1. **Discovery**: User triggers podcast discovery → Automated pipeline → Review tasks created
2. **Review**: User sees pending reviews → Detailed AI analysis → Approve/Reject decision  
3. **Tracking**: Real-time progress monitoring throughout the pipeline

---

## **🔗 KEY ENDPOINTS FOR FRONTEND**

### **1. TRIGGER DISCOVERY (Start the automated pipeline)**

```http
POST /match-suggestions/campaigns/{campaign_id}/discover
```

**Request:**
```json
{
  "max_matches": 50  // Optional: limit number of podcasts to discover
}
```

**Response (Immediate):**
```json
{
  "status": "success",
  "message": "Automated discovery pipeline started. Podcasts will be discovered → enriched → vetted → matched automatically.",
  "campaign_id": "123e4567-e89b-12d3-a456-426614174000",
  "discoveries_initiated": 0,
  "estimated_completion_minutes": 5,
  "track_endpoint": "/match-suggestions/campaigns/123e4567-e89b-12d3-a456-426614174000/discoveries/status"
}
```

**Frontend Usage:**
```javascript
// Trigger discovery
const response = await fetch(`/api/match-suggestions/campaigns/${campaignId}/discover`, {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${token}` },
  body: JSON.stringify({ max_matches: 50 })
});

const result = await response.json();
// Show success message + redirect to tracking page
```

---

### **2. TRACK DISCOVERY PROGRESS**

```http
GET /match-suggestions/campaigns/{campaign_id}/discoveries/status
```

**Query Parameters:**
- `status_filter` (optional): "pending", "in_progress", "completed", "failed"
- `limit` (optional): Number of results (default: 20)
- `offset` (optional): For pagination

**Response:**
```json
{
  "items": [
    {
      "discovery_id": 123,
      "campaign_id": "123e4567-e89b-12d3-a456-426614174000",
      "media_id": 456,
      "media_name": "Tech Talk Daily",
      "discovery_keyword": "marketing",
      "enrichment_status": "completed",
      "vetting_status": "completed", 
      "overall_status": "completed",
      "vetting_score": 8.5,
      "match_created": true,
      "review_task_created": true,
      "discovered_at": "2025-06-18T10:30:00Z",
      "updated_at": "2025-06-18T10:35:00Z",
      "enrichment_error": null,
      "vetting_error": null
    }
  ],
  "total": 15,
  "in_progress": 3,
  "completed": 10,
  "failed": 2
}
```

**Frontend Usage:**
```javascript
// Track progress (call every 10-30 seconds)
const trackProgress = async () => {
  const response = await fetch(`/api/match-suggestions/campaigns/${campaignId}/discoveries/status`);
  const status = await response.json();
  
  // Update progress UI
  updateProgressBar(status.completed, status.total);
  
  // Show completed discoveries
  showDiscoveryResults(status.items);
  
  // Stop polling when all completed
  if (status.in_progress === 0) {
    clearInterval(progressInterval);
    showCompletionMessage();
  }
};

const progressInterval = setInterval(trackProgress, 15000); // Every 15 seconds
```

---

### **3. GET PENDING REVIEWS (Main approval interface)**

```http
GET /review-tasks/enhanced
```

**Query Parameters:**
- `campaign_id` (optional): Filter by campaign
- `task_type` (optional): "match_suggestion", "pitch_review"  
- `status` (optional): "pending", "approved", "rejected" (default: "pending")
- `min_vetting_score` (optional): Minimum AI score (0-10)
- `limit` (optional): Results per page (default: 20)
- `offset` (optional): For pagination

**Response (Rich data for approval UI):**
```json
[
  {
    "review_task_id": 789,
    "task_type": "match_suggestion",
    "related_id": 456,
    "campaign_id": "123e4567-e89b-12d3-a456-426614174000",
    "status": "pending",
    "created_at": "2025-06-18T10:35:00Z",
    "completed_at": null,
    
    // Campaign context
    "campaign_name": "Marketing Expert Campaign",
    "client_name": "John Smith",
    
    // Podcast details
    "media_id": 456,
    "media_name": "Tech Talk Daily",
    "media_website": "https://techtalkdaily.com",
    "media_image_url": "https://example.com/podcast-cover.jpg",
    "media_description": "A daily podcast covering the latest in technology and business innovation...",
    
    // Discovery context
    "discovery_keyword": "marketing",
    "discovered_at": "2025-06-18T10:30:00Z",
    
    // AI Analysis Results
    "vetting_score": 8.5,
    "vetting_reasoning": "This podcast consistently features marketing professionals discussing growth strategies. The host asks thoughtful questions and the audience is highly engaged with business content. Perfect fit for marketing expertise positioning.",
    "vetting_criteria_met": {
      "audience_size": true,
      "topic_alignment": true,
      "host_style": true,
      "content_quality": true,
      "brand_safety": true
    },
    
    // Match details
    "match_score": 0.87,
    "matched_keywords": ["marketing", "growth", "business"],
    "best_matching_episode_id": 1234,
    
    // User-friendly summary
    "recommendation": "Highly Recommended",
    "key_highlights": [
      "Excellent vetting score (8.5/10)",
      "✓ audience_size",
      "✓ topic_alignment", 
      "✓ host_style",
      "✓ content_quality"
    ],
    "potential_concerns": []
  }
]
```

**Frontend Usage:**
```javascript
// Get pending reviews for approval interface
const getPendingReviews = async (campaignId = null) => {
  const params = new URLSearchParams({
    status: 'pending',
    limit: '20'
  });
  
  if (campaignId) params.append('campaign_id', campaignId);
  
  const response = await fetch(`/api/review-tasks/enhanced?${params}`);
  const reviews = await response.json();
  
  return reviews;
};

// Display in approval UI
const reviews = await getPendingReviews();
renderApprovalCards(reviews);
```

---

### **4. APPROVE/REJECT REVIEWS**

```http
POST /review-tasks/{review_task_id}/approve
```

**Request:**
```json
{
  "status": "approved",  // or "rejected"
  "notes": "Great podcast for our target audience"  // Optional
}
```

**Response (Updated review task):**
```json
{
  // Same structure as GET /review-tasks/enhanced
  "review_task_id": 789,
  "status": "approved",
  "completed_at": "2025-06-18T11:00:00Z",
  // ... rest of the enhanced data
}
```

**Frontend Usage:**
```javascript
// Approve a review
const approveReview = async (reviewTaskId, decision, notes = '') => {
  const response = await fetch(`/api/review-tasks/${reviewTaskId}/approve`, {
    method: 'POST',
    headers: { 
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}` 
    },
    body: JSON.stringify({
      status: decision, // 'approved' or 'rejected'
      notes: notes
    })
  });
  
  const updatedTask = await response.json();
  
  // Update UI to show approval
  updateReviewCard(reviewTaskId, updatedTask);
  showSuccessMessage(`Review ${decision}!`);
};
```

---

## **🎨 RECOMMENDED UI COMPONENTS**

### **1. Discovery Dashboard**
```jsx
function DiscoveryDashboard({ campaignId }) {
  const [discoveryStatus, setDiscoveryStatus] = useState(null);
  const [isRunning, setIsRunning] = useState(false);
  
  const startDiscovery = async () => {
    setIsRunning(true);
    const result = await triggerDiscovery(campaignId);
    // Start progress tracking
    startProgressTracking(campaignId);
  };
  
  return (
    <div className="discovery-dashboard">
      <button onClick={startDiscovery} disabled={isRunning}>
        {isRunning ? 'Discovery Running...' : 'Discover Podcasts'}
      </button>
      
      {discoveryStatus && (
        <ProgressTracker 
          completed={discoveryStatus.completed}
          total={discoveryStatus.total}
          inProgress={discoveryStatus.in_progress}
        />
      )}
    </div>
  );
}
```

### **2. Review Approval Card**
```jsx
function ReviewApprovalCard({ review, onApprove, onReject }) {
  return (
    <div className="review-card">
      <div className="podcast-header">
        <img src={review.media_image_url} alt={review.media_name} />
        <div>
          <h3>{review.media_name}</h3>
          <p>{review.discovery_keyword} • {review.recommendation}</p>
        </div>
      </div>
      
      <div className="ai-analysis">
        <div className="vetting-score">
          <span className="score">{review.vetting_score}/10</span>
          <StarRating score={review.vetting_score} />
        </div>
        
        <div className="highlights">
          {review.key_highlights.map(highlight => (
            <span key={highlight} className="highlight">{highlight}</span>
          ))}
        </div>
        
        <div className="reasoning">
          <p>{review.vetting_reasoning}</p>
        </div>
      </div>
      
      <div className="actions">
        <button 
          className="approve-btn" 
          onClick={() => onApprove(review.review_task_id)}
        >
          ✅ Approve
        </button>
        <button 
          className="reject-btn" 
          onClick={() => onReject(review.review_task_id)}
        >
          ❌ Reject
        </button>
        <button className="details-btn">
          📖 View Details
        </button>
      </div>
    </div>
  );
}
```

### **3. Real-time Progress Tracker**
```jsx
function ProgressTracker({ completed, total, inProgress }) {
  const percentage = total > 0 ? (completed / total) * 100 : 0;
  
  return (
    <div className="progress-tracker">
      <div className="progress-bar">
        <div 
          className="progress-fill" 
          style={{ width: `${percentage}%` }}
        />
      </div>
      
      <div className="progress-stats">
        <span>✅ {completed} Completed</span>
        <span>⏳ {inProgress} Processing</span>
        <span>📊 {total} Total</span>
      </div>
    </div>
  );
}
```

---

## **📱 REAL-TIME NOTIFICATION SYSTEM**

**🚀 NEW: WebSocket-based real-time notifications for instant updates!**

### **WebSocket Connection**
```javascript
class NotificationManager {
  constructor(authToken, campaignId = null) {
    this.authToken = authToken;
    this.campaignId = campaignId;
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
  }
  
  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const params = new URLSearchParams({
      token: this.authToken,
      ...(this.campaignId && { campaign_id: this.campaignId })
    });
    
    this.ws = new WebSocket(`${protocol}//${host}/notifications/ws?${params}`);
    
    this.ws.onopen = () => {
      console.log('🔗 Real-time notifications connected');
      this.reconnectAttempts = 0;
      this.onConnectionEstablished();
    };
    
    this.ws.onmessage = (event) => {
      const notification = JSON.parse(event.data);
      this.handleNotification(notification);
    };
    
    this.ws.onclose = () => {
      console.log('🔌 Notification connection closed');
      this.attemptReconnect();
    };
    
    this.ws.onerror = (error) => {
      console.error('❌ Notification connection error:', error);
    };
  }
  
  handleNotification(notification) {
    console.log('📢 Received notification:', notification);
    
    switch (notification.type) {
      case 'discovery_started':
        this.showToast('🚀 Discovery pipeline started', 'info');
        this.updateDiscoveryStatus('started');
        break;
        
      case 'discovery_progress':
        this.showToast(`📡 Discovered: ${notification.data.media_name}`, 'info');
        this.updateProgressCount();
        break;
        
      case 'enrichment_completed':
        this.showToast(`✨ Analysis complete: ${notification.data.media_name}`, 'success');
        break;
        
      case 'review_ready':
        this.showToast(notification.message, 'success');
        this.updateReviewCount();
        this.showBrowserNotification(notification);
        break;
        
      case 'discovery_completed':
        this.showToast(notification.message, 'success');
        this.onDiscoveryComplete(notification.data);
        this.showBrowserNotification(notification);
        break;
        
      case 'pipeline_progress':
        this.updateProgressBar(notification.data);
        break;
        
      case 'match_approved':
      case 'match_rejected':
        this.showToast(notification.message, 'info');
        this.updateMatchStatus(notification.data);
        break;
    }
  }
  
  // Send ping to keep connection alive
  sendPing() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'ping' }));
    }
  }
  
  // Subscribe to additional campaign
  subscribeToCampaign(campaignId) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'subscribe_campaign',
        campaign_id: campaignId
      }));
    }
  }
  
  attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++;
      const delay = Math.pow(2, this.reconnectAttempts) * 1000; // Exponential backoff
      console.log(`🔄 Reconnecting in ${delay/1000}s...`);
      setTimeout(() => this.connect(), delay);
    }
  }
  
  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// Usage in your React app
const notificationManager = new NotificationManager(authToken, campaignId);
notificationManager.connect();

// Keep connection alive
setInterval(() => notificationManager.sendPing(), 30000);
```

### **React Hook for Notifications**
```javascript
import { useState, useEffect, useRef } from 'react';

const useNotifications = (authToken, campaignId) => {
  const [notifications, setNotifications] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const managerRef = useRef(null);
  
  useEffect(() => {
    const manager = new NotificationManager(authToken, campaignId);
    managerRef.current = manager;
    
    // Override handler methods
    manager.onConnectionEstablished = () => setIsConnected(true);
    manager.handleNotification = (notification) => {
      setNotifications(prev => [notification, ...prev.slice(0, 49)]); // Keep last 50
      // Handle specific notification types
      handleNotificationUI(notification);
    };
    
    manager.connect();
    
    return () => {
      manager.disconnect();
    };
  }, [authToken, campaignId]);
  
  const subscribeToCampaign = (newCampaignId) => {
    if (managerRef.current) {
      managerRef.current.subscribeToCampaign(newCampaignId);
    }
  };
  
  return {
    notifications,
    isConnected,
    subscribeToCampaign
  };
};
```

### **Browser Notifications**
```javascript
// Enhanced browser notifications
const requestNotificationPermission = async () => {
  if ('Notification' in window) {
    const permission = await Notification.requestPermission();
    return permission === 'granted';
  }
  return false;
};

const showBrowserNotification = (notification) => {
  if ('Notification' in window && Notification.permission === 'granted') {
    const title = notification.title;
    const options = {
      body: notification.message,
      icon: '/podcast-icon.png',
      badge: '/notification-badge.png',
      tag: notification.type, // Prevent duplicate notifications
      data: notification.data,
      actions: notification.type === 'review_ready' ? [
        { action: 'view', title: 'View Review' },
        { action: 'dismiss', title: 'Dismiss' }
      ] : []
    };
    
    const notif = new Notification(title, options);
    
    notif.onclick = () => {
      window.focus();
      // Navigate to relevant page
      if (notification.type === 'review_ready') {
        window.location.href = `/reviews?campaign=${notification.campaign_id}`;
      }
      notif.close();
    };
    
    // Auto-close after 5 seconds for non-critical notifications
    if (notification.priority !== 'high') {
      setTimeout(() => notif.close(), 5000);
    }
  }
};
```

### **Toast Notifications Integration**
```javascript
// Enhanced toast notifications with notification data
const showToast = (message, type = 'info', notificationData = null) => {
  const toastConfig = {
    message,
    type,
    duration: type === 'error' ? 8000 : 4000,
    action: notificationData?.type === 'review_ready' ? {
      label: 'View Review',
      onClick: () => navigateToReview(notificationData.data.campaign_id)
    } : null
  };
  
  // Your toast library implementation
  toast(toastConfig);
};
```

---

## **🔄 POLLING & REAL-TIME UPDATES**

### **Discovery Progress Polling**
```javascript
const useDiscoveryProgress = (campaignId) => {
  const [status, setStatus] = useState(null);
  const [isPolling, setIsPolling] = useState(false);
  
  const startPolling = () => {
    setIsPolling(true);
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`/api/match-suggestions/campaigns/${campaignId}/discoveries/status`);
        const newStatus = await response.json();
        setStatus(newStatus);
        
        // Stop polling when complete
        if (newStatus.in_progress === 0) {
          setIsPolling(false);
          clearInterval(interval);
          showCompletionNotification(newStatus.completed);
        }
      } catch (error) {
        console.error('Polling error:', error);
      }
    }, 15000); // Poll every 15 seconds
    
    return () => clearInterval(interval);
  };
  
  return { status, isPolling, startPolling };
};
```

### **Review List Auto-refresh**
```javascript
const useReviewTasks = () => {
  const [reviews, setReviews] = useState([]);
  
  const refreshReviews = async () => {
    const response = await fetch('/api/review-tasks/enhanced?status=pending');
    const newReviews = await response.json();
    setReviews(newReviews);
  };
  
  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(refreshReviews, 30000);
    return () => clearInterval(interval);
  }, []);
  
  return { reviews, refreshReviews };
};
```

---

## **📊 FILTERING & SEARCH**

### **Advanced Filtering**
```javascript
const ReviewFilters = ({ onFiltersChange }) => {
  const [filters, setFilters] = useState({
    campaign_id: '',
    min_vetting_score: '',
    status: 'pending'
  });
  
  const handleFilterChange = (key, value) => {
    const newFilters = { ...filters, [key]: value };
    setFilters(newFilters);
    onFiltersChange(newFilters);
  };
  
  return (
    <div className="review-filters">
      <select 
        value={filters.status} 
        onChange={(e) => handleFilterChange('status', e.target.value)}
      >
        <option value="pending">Pending Review</option>
        <option value="approved">Approved</option>
        <option value="rejected">Rejected</option>
      </select>
      
      <input
        type="number"
        placeholder="Min Vetting Score (0-10)"
        value={filters.min_vetting_score}
        onChange={(e) => handleFilterChange('min_vetting_score', e.target.value)}
        min="0"
        max="10"
        step="0.1"
      />
    </div>
  );
};
```

---

## **🚨 ERROR HANDLING**

```javascript
const ApiService = {
  async request(url, options = {}) {
    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`,
          ...options.headers
        }
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'API request failed');
      }
      
      return await response.json();
    } catch (error) {
      console.error('API Error:', error);
      showToast(error.message, 'error');
      throw error;
    }
  },
  
  // Specific methods
  triggerDiscovery: (campaignId, maxMatches = 50) => 
    ApiService.request(`/api/match-suggestions/campaigns/${campaignId}/discover`, {
      method: 'POST',
      body: JSON.stringify({ max_matches: maxMatches })
    }),
    
  getDiscoveryStatus: (campaignId) =>
    ApiService.request(`/api/match-suggestions/campaigns/${campaignId}/discoveries/status`),
    
  getPendingReviews: (filters = {}) => {
    const params = new URLSearchParams(filters);
    return ApiService.request(`/api/review-tasks/enhanced?${params}`);
  },
  
  approveReview: (reviewTaskId, status, notes = '') =>
    ApiService.request(`/api/review-tasks/${reviewTaskId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ status, notes })
    })
};
```

---

## **✅ IMPLEMENTATION CHECKLIST**

**For your frontend colleague:**

1. **Discovery Flow**
   - [ ] Trigger discovery button with campaign selection
   - [ ] Progress tracking with real-time updates  
   - [ ] Completion notifications
   
2. **Review Interface**
   - [ ] Pending reviews dashboard
   - [ ] Detailed review cards with AI analysis
   - [ ] Approve/reject buttons with confirmation
   - [ ] Filtering and search capabilities
   
3. **Real-time Features**
   - [ ] Polling for discovery progress
   - [ ] Auto-refresh review lists
   - [ ] Browser notifications
   - [ ] Toast notifications for actions
   
4. **Error Handling**
   - [ ] API error handling and user-friendly messages
   - [ ] Loading states and spinners
   - [ ] Retry mechanisms for failed requests

**This system provides a complete automated SaaS experience - users trigger discovery and get intelligent review tasks automatically created with rich AI insights for easy approval decisions!** 🚀