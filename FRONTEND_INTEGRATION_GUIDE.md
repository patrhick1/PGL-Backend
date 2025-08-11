
# PGL Frontend Integration Guide

This guide provides instructions for frontend developers on how to integrate with the PGL Podcast Outreach Automation System API.

## 1. Authentication

Before making any other API calls, the user must be authenticated. The authentication process is described in detail in the [API Documentation](API_DOCUMENTATION.md).

## 2. Campaign Management

Once authenticated, the user can manage their campaigns.

### 2.1. Fetching Campaigns

*   **Endpoint:** `GET /api/campaigns/`
*   **Description:** This endpoint retrieves a list of all campaigns associated with the current user.
*   **Usage:**

```javascript
async function getCampaigns() {
  const response = await fetch('/api/campaigns/');
  const campaigns = await response.json();
  return campaigns;
}
```

### 2.2. Updating a Campaign

*   **Endpoint:** `PATCH /api/campaigns/me/{campaign_id}`
*   **Description:** This endpoint updates the details of a specific campaign.
*   **Usage:**

```javascript
async function updateCampaign(campaignId, data) {
  const response = await fetch(`/api/campaigns/me/${campaignId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });
  const updatedCampaign = await response.json();
  return updatedCampaign;
}
```

## 3. Pitch Generation

The frontend can integrate with the pitch generation system to create and manage pitches.

### 3.1. Creating a Pitch

*   **Endpoint:** `POST /api/pitches/`
*   **Description:** This endpoint creates a new pitch.
*   **Usage:**

```javascript
async function createPitch(pitchData) {
  const response = await fetch('/api/pitches/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(pitchData),
  });
  const newPitch = await response.json();
  return newPitch;
}
```

### 3.2. Generating a Pitch with AI

To generate a pitch using AI, you first need to create a pitch with some basic information (e.g., the client and the podcast). Then, you can call the AI pitch generator to populate the pitch content.

*   **Endpoint:** `POST /api/pitches/{pitch_id}/generate`
*   **Description:** This endpoint uses AI to generate the content of a pitch.
*   **Usage:**

```javascript
async function generatePitchContent(pitchId) {
  const response = await fetch(`/api/pitches/${pitchId}/generate`, {
    method: 'POST',
  });
  const generatedPitch = await response.json();
  return generatedPitch;
}
```

## 4. Pitch Review

The frontend should provide an interface for users to review and approve or reject pitches.

### 4.1. Fetching Review Tasks

*   **Endpoint:** `GET /api/review_tasks/`
*   **Description:** This endpoint retrieves a list of all review tasks assigned to the current user.
*   **Usage:**

```javascript
async function getReviewTasks() {
  const response = await fetch('/api/review_tasks/');
  const reviewTasks = await response.json();
  return reviewTasks;
}
```

### 4.2. Approving or Rejecting a Pitch

*   **Endpoint:** `PUT /api/review_tasks/{task_id}`
*   **Description:** This endpoint updates the status of a review task to `approved` or `rejected`.
*   **Usage:**

```javascript
async function updateReviewTask(taskId, status, feedback) {
  const response = await fetch(`/api/review_tasks/${taskId}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ status, feedback }),
  });
  const updatedTask = await response.json();
  return updatedTask;
}
```

## 5. Placements

The frontend can also be used to view and manage placements.

### 5.1. Fetching Placements

*   **Endpoint:** `GET /api/placements/`
*   **Description:** This endpoint retrieves a list of all placements.
*   **Usage:**

```javascript
async function getPlacements() {
  const response = await fetch('/api/placements/');
  const placements = await response.json();
  return placements;
}
```

This guide provides a starting point for integrating a frontend application with the PGL API. For more detailed information about the available endpoints and their parameters, please refer to the [API Documentation](API_DOCUMENTATION.md).
