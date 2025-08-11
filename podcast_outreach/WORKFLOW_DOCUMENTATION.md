
# PGL Podcast Outreach Workflow Documentation

This document outlines the end-to-end workflow of the PGL Podcast Outreach Automation System, from client onboarding to successful podcast placement.

## 1. Client Onboarding

The first step is to onboard a new client to the platform.

*   **Action:** A new client is registered in the system.
*   **Process:**
    *   A new `client` record is created in the database.
    *   A default `campaign` is created for the client.
    *   The client is prompted to fill out a questionnaire to provide information about their goals, expertise, and target audience.
*   **Key Components:**
    *   **API Endpoint:** `POST /api/auth/register`
    *   **Database Tables:** `clients`, `campaigns`

## 2. Campaign Configuration

Once the client is onboarded, the campaign needs to be configured.

*   **Action:** The client or an account manager configures the campaign settings.
*   **Process:**
    *   The client provides details about their campaign, such as the target audience, key talking points, and desired outcomes.
    *   This information is used to generate a `campaign_summary` using AI.
*   **Key Components:**
    *   **API Endpoint:** `PATCH /api/campaigns/me/{campaign_id}`
    *   **Service:** `summary_builder.py`
    *   **Database Table:** `campaigns`

## 3. Podcast Discovery

The system automatically discovers relevant podcasts based on the campaign configuration.

*   **Action:** The system searches for podcasts that match the client's profile and campaign goals.
*   **Process:**
    *   The system uses the ListenNotes and Podscan APIs to search for podcasts based on keywords, categories, and other criteria.
    *   The results are filtered and scored based on relevance, audience size, and other factors.
*   **Key Components:**
    *   **Integrations:** `ListenNotes`, `Podscan`
    *   **Service:** `automated_discovery_service.py`
    *   **Database Table:** `podcasts`

## 4. Pitch Generation

Once a list of target podcasts has been identified, the system generates personalized pitches for each one.

*   **Action:** The system creates a unique pitch for each podcast.
*   **Process:**
    *   The AI-powered pitch generator uses the client's information, the podcast's details, and a variety of pitch templates to create a personalized and compelling pitch.
    *   The generated pitches are saved as drafts for review.
*   **Key Components:**
    *   **API Endpoint:** `POST /api/pitches/`
    *   **Service:** `generator.py` (in `services/pitches`)
    *   **Database Table:** `pitches`

## 5. Pitch Review and Approval

All generated pitches must be reviewed and approved before they are sent.

*   **Action:** An account manager or the client reviews the generated pitches.
*   **Process:**
    *   The reviewer can approve, reject, or edit the pitches.
    *   If a pitch is rejected, it is sent back to the generation step with feedback for improvement.
*   **Key Components:**
    *   **API Endpoint:** `PUT /api/pitches/{pitch_id}`
    *   **UI:** The frontend provides an interface for reviewing and approving pitches.

## 6. Pitch Sending

Once a pitch is approved, it is sent to the podcast.

*   **Action:** The system sends the pitch to the podcast's contact person.
*   **Process:**
    *   The pitch is sent via email using an integrated email service.
    *   The status of the pitch is updated to `sent`.
*   **Key Components:**
    *   **API Endpoint:** `POST /api/pitches/{pitch_id}/send`
    *   **Service:** `sender.py` (in `services/pitches`)
    *   **Database Table:** `pitches`

## 7. Response Tracking and Booking

The system tracks responses to the pitches and manages the booking process.

*   **Action:** The system monitors the inbox for replies to the pitches.
*   **Process:**
    *   When a positive response is received, the system automatically creates a `placement` record and updates the pitch status to `accepted`.
    *   The booking assistant helps to schedule the podcast recording.
*   **Key Components:**
    *   **Service:** `booking_assistant.py`
    *   **Database Tables:** `placements`, `pitches`

## 8. Placement Management

Once a booking is confirmed, it is managed as a placement.

*   **Action:** The system tracks the status of the placement.
*   **Process:**
    *   The placement status is updated as the recording is scheduled, completed, or cancelled.
*   **Key Components:**
    *   **API Endpoint:** `PUT /api/placements/{placement_id}`
    *   **Database Table:** `placements`

This workflow provides a seamless and automated process for podcast outreach, from start to finish.
