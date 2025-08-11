# Frontend API Documentation

## Authentication Endpoints (`/auth/`)

All auth endpoints are **PUBLIC** - no authentication required.

### 1. User Registration
```
POST /auth/register
Content-Type: application/json

Body:
{
  "full_name": "John Doe",      // Required, min 2 chars
  "email": "john@example.com",   // Required, valid email
  "password": "mypassword123",   // Required, min 8 chars
  
  // Optional - Only for converting lead magnet prospects
  "prospect_person_id": 123,     // Optional: ID of existing prospect
  "prospect_campaign_id": "uuid" // Optional: ID of prospect's campaign
}

Response 201:
{
  "message": "Registration successful",
  "person_id": 456,
  "campaign_id": "new-uuid-here"
}

Errors:
- 400: User already exists
- 400: Prospect conversion failed (mismatched email, etc.)
```

**For NEW users:** Only send `full_name`, `email`, `password`. The system will automatically create a default campaign.

**For lead magnet conversion:** Include `prospect_person_id` and `prospect_campaign_id` from the lead magnet submission.

### 2. Login
```
POST /auth/token
Content-Type: application/x-www-form-urlencoded

Body:
username=john@example.com&password=mypassword123

Response 200:
{
  "access_token": "session-token",
  "token_type": "bearer",
  "user_data": {
    "person_id": 456,
    "username": "john@example.com",
    "full_name": "John Doe",
    "role": "client"
  }
}

Errors:
- 401: Invalid credentials
```

### 3. Password Reset Request
```
POST /auth/request-password-reset
Content-Type: application/x-www-form-urlencoded

Body:
email=john@example.com

Response 202:
{
  "message": "If an account with this email exists, a password reset link has been sent."
}

// Always returns 202 for security (doesn't reveal if email exists)
```

### 4. Reset Password with Token
```
POST /auth/reset-password
Content-Type: application/x-www-form-urlencoded

Body:
token=reset-token-from-email&new_password=newpassword123

Response 200:
{
  "message": "Password has been reset successfully. You can now log in with your new password."
}

Errors:
- 400: Invalid or expired token
```

### 5. Logout
```
POST /auth/logout

Response 200:
{
  "message": "Logged out successfully"
}
```

### 6. Get Current User
```
GET /auth/me

Response 200:
{
  "person_id": 456,
  "username": "john@example.com", 
  "full_name": "John Doe",
  "role": "client"
}

Errors:
- 401: Not authenticated
```

## User Management Endpoints (`/users/`)

All user endpoints require **AUTHENTICATION**.

### 1. Change Password (Logged-in Users)
```
POST /users/me/change-password
Content-Type: application/x-www-form-urlencoded

Body:
current_password=oldpassword&new_password=newpassword123

Response 200:
{
  "message": "Password updated successfully."
}

Errors:
- 401: Current password incorrect
- 400: User account issue
```

### 2. Update Notification Settings
```
PATCH /users/me/notification-settings
Content-Type: application/json

Body:
{
  "email_notifications": true,
  "push_notifications": false
  // ... other notification settings
}

Response 200: Updated user object
```

### 3. Update Privacy Settings
```
PATCH /users/me/privacy-settings
Content-Type: application/json

Body:
{
  "profile_visibility": "private"
  // ... other privacy settings  
}

Response 200: Updated user object
```

## Admin Endpoints (`/people/`)

Admin-only endpoints for user management.

### Set User Password (Admin Only)
```
PUT /people/{person_id}/set-password
Content-Type: application/x-www-form-urlencoded

Body:
new_password=adminsetpassword123

Response 200:
{
  "message": "Password set successfully for user {person_id}."
}
```

## Frontend Implementation Notes

### 1. Registration Flow

**For new users (normal signup):**
```javascript
const registerNewUser = async (fullName, email, password) => {
  const response = await fetch('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      full_name: fullName,
      email: email,
      password: password
      // Don't include prospect fields for new users
    })
  });
  
  if (response.ok) {
    const data = await response.json();
    // User registered, can now login or auto-login
    console.log('New campaign created:', data.campaign_id);
  }
};
```

**For lead magnet conversion:**
```javascript
const convertProspect = async (fullName, email, password, prospectPersonId, prospectCampaignId) => {
  const response = await fetch('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      full_name: fullName,
      email: email,
      password: password,
      prospect_person_id: prospectPersonId,
      prospect_campaign_id: prospectCampaignId
    })
  });
  
  if (response.ok) {
    // Prospect converted to client
    console.log('Prospect converted successfully');
  }
};
```

### 2. Login Flow
```javascript
const login = async (email, password) => {
  const response = await fetch('/auth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `username=${encodeURIComponent(email)}&password=${encodeURIComponent(password)}`
  });
  
  if (response.ok) {
    const data = await response.json();
    // Store session token (usually handled by cookies)
    localStorage.setItem('user', JSON.stringify(data.user_data));
  }
};
```

### 3. Password Reset Flow
```javascript
// Step 1: Request reset
const requestPasswordReset = async (email) => {
  const response = await fetch('/auth/request-password-reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `email=${encodeURIComponent(email)}`
  });
  
  // Always shows success message for security
  alert('If an account exists, a reset link has been sent to your email.');
};

// Step 2: Reset with token (from email link)
const resetPassword = async (token, newPassword) => {
  const response = await fetch('/auth/reset-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `token=${encodeURIComponent(token)}&new_password=${encodeURIComponent(newPassword)}`
  });
  
  if (response.ok) {
    alert('Password reset successfully! You can now log in.');
    // Redirect to login page
  }
};
```

### 4. Change Password (Logged-in Users)
```javascript
const changePassword = async (currentPassword, newPassword) => {
  const response = await fetch('/users/me/change-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    credentials: 'include', // Include session cookies
    body: `current_password=${encodeURIComponent(currentPassword)}&new_password=${encodeURIComponent(newPassword)}`
  });
  
  if (response.ok) {
    alert('Password updated successfully!');
  } else if (response.status === 401) {
    alert('Current password is incorrect.');
  }
};
```

### 5. Session Management
```javascript
// Check if user is logged in
const getCurrentUser = async () => {
  const response = await fetch('/auth/me', {
    credentials: 'include'
  });
  
  if (response.ok) {
    return await response.json();
  }
  return null; // Not logged in
};

// Logout
const logout = async () => {
  await fetch('/auth/logout', {
    method: 'POST',
    credentials: 'include'
  });
  
  localStorage.removeItem('user');
  // Redirect to login page
};
```

## Error Handling

All endpoints return standard HTTP status codes:
- `200`: Success
- `201`: Created (registration)
- `202`: Accepted (async operations like email sending)
- `400`: Bad request (validation errors)
- `401`: Unauthorized (authentication required/failed)
- `403`: Forbidden (insufficient permissions)
- `404`: Not found
- `500`: Internal server error

Error responses include a `detail` field:
```json
{
  "detail": "Current password is incorrect."
}
```


## Pitch Management Endpoints (`/pitches/`)

All pitch endpoints require **AUTHENTICATION**.

### 1. Create a Pitch

`POST /api/pitches/`

*   **Description:** Creates a new pitch.
*   **Body:**

```json
{
  "client_id": 1,
  "podcast_id": 1,
  "subject": "Podcast Pitch: John Doe",
  "body": "I would like to be a guest on your podcast..."
}
```

### 2. Get Pitches

`GET /api/pitches/`

*   **Description:** Retrieves a list of pitches.

### 3. Get a Specific Pitch

`GET /api/pitches/{pitch_id}`

*   **Description:** Retrieves a specific pitch by its ID.

### 4. Update a Pitch

`PUT /api/pitches/{pitch_id}`

*   **Description:** Updates a pitch.

### 5. Delete a Pitch

`DELETE /api/pitches/{pitch_id}`

*   **Description:** Deletes a pitch.

### 6. Send a Pitch

`POST /api/pitches/{pitch_id}/send`

*   **Description:** Sends a pitch to the podcast.

## Placement Management Endpoints (`/placements/`)

All placement endpoints require **AUTHENTICATION**.

### 1. Create a Placement

`POST /api/placements/`

*   **Description:** Creates a new placement.
*   **Body:**

```json
{
  "pitch_id": 1,
  "booking_date": "2025-12-25T12:00:00Z"
}
```

### 2. Get Placements

`GET /api/placements/`

*   **Description:** Retrieves a list of placements.

### 3. Get a Specific Placement

`GET /api/placements/{placement_id}`

*   **Description:** Retrieves a specific placement by its ID.

### 4. Update a Placement

`PUT /api/placements/{placement_id}`

*   **Description:** Updates a placement.

### 5. Delete a Placement

`DELETE /api/placements/{placement_id}`

*   **Description:** Deletes a placement.

## Review Task Management Endpoints (`/review_tasks/`)

All review task endpoints require **AUTHENTICATION**.

### 1. Get Review Tasks

`GET /api/review_tasks/`

*   **Description:** Retrieves a list of review tasks.

### 2. Get a Specific Review Task

`GET /api/review_tasks/{task_id}`

*   **Description:** Retrieves a specific review task by its ID.

### 3. Update a Review Task

`PUT /api/review_tasks/{task_id}`

*   **Description:** Updates a review task (e.g., to approve or reject it).

## Campaign Management Endpoints (`/campaigns/`)


All campaign endpoints require **AUTHENTICATION**.

### 1. List My Campaigns
```
GET /campaigns/
Authorization: Required (Client, Staff, Admin)

Query Parameters:
- skip: int = 0 (pagination offset)
- limit: int = 100 (max 500, min 10)

Response 200:
[
  {
    "campaign_id": "uuid-here",
    "campaign_name": "John's First Campaign",
    "campaign_type": "general",
    "person_id": 123,
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "goal_note": "Increase brand awareness",
    // ... other campaign fields
  }
]

Note: Clients automatically see only their own campaigns
```

### 2. Get Specific Campaign
```
GET /campaigns/{campaign_id}
Authorization: Required (Client sees own, Staff/Admin see any)

Response 200: Campaign object (same structure as above)

Errors:
- 403: Cannot access campaign (not yours)
- 404: Campaign not found
```

### 3. Update My Campaign
```
PATCH /campaigns/me/{campaign_id}
Content-Type: application/json

Body (all fields optional):
{
  "campaign_name": "Updated Campaign Name",
  "campaign_type": "lead_generation",
  "goal_note": "Updated goals...",
  "start_date": "2024-02-01",
  "end_date": "2024-11-30",
  "campaign_keywords": ["podcast", "marketing", "growth"],
  "compiled_social_posts": "Social media content...",
  "podcast_transcript_link": "https://...",
  "compiled_articles_link": "https://...",
  "media_kit_url": "https://..."
}

Response 200: Updated campaign object

Errors:
- 403: Cannot edit campaign (not yours)
- 404: Campaign not found
- 400: No update data provided

Note: Clients cannot modify person_id or attio_client_id
```

### 4. Submit Questionnaire for Campaign
```
POST /campaigns/{campaign_id}/submit-questionnaire
Content-Type: application/json

Body:
{
  "questionnaire_data": {
    "personal_bio": "Your background...",
    "achievements": ["Achievement 1", "Achievement 2"],
    "expertise_areas": ["area1", "area2"],
    "target_audience": "Target demographic...",
    // ... other questionnaire fields
  }
}

Response 200: Updated campaign with questionnaire data

Errors:
- 403: Cannot submit questionnaire (not your campaign)
- 404: Campaign not found
```

## Frontend Implementation Examples

### 1. List User's Campaigns
```javascript
const getUserCampaigns = async () => {
  const response = await fetch('/campaigns/', {
    credentials: 'include'
  });
  
  if (response.ok) {
    const campaigns = await response.json();
    return campaigns;
  }
  throw new Error('Failed to fetch campaigns');
};
```

### 2. Get Specific Campaign
```javascript
const getCampaign = async (campaignId) => {
  const response = await fetch(`/campaigns/${campaignId}`, {
    credentials: 'include'
  });
  
  if (response.ok) {
    return await response.json();
  } else if (response.status === 403) {
    throw new Error('You can only view your own campaigns');
  }
  throw new Error('Campaign not found');
};
```

### 3. Update Campaign
```javascript
const updateCampaign = async (campaignId, updateData) => {
  const response = await fetch(`/campaigns/me/${campaignId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(updateData)
  });
  
  if (response.ok) {
    return await response.json();
  } else if (response.status === 403) {
    throw new Error('You can only edit your own campaigns');
  }
  throw new Error('Failed to update campaign');
};

// Example usage:
await updateCampaign('campaign-uuid', {
  campaign_name: 'New Campaign Name',
  goal_note: 'Updated goals and objectives'
});
```

### 4. Submit Questionnaire
```javascript
const submitQuestionnaire = async (campaignId, questionnaireData) => {
  const response = await fetch(`/campaigns/${campaignId}/submit-questionnaire`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({
      questionnaire_data: questionnaireData
    })
  });
  
  if (response.ok) {
    return await response.json();
  }
  throw new Error('Failed to submit questionnaire');
};
``` 