
# PGL Pitch System Documentation

This document provides a detailed overview of the pitch generation, sending, and tracking system.

## 1. Pitch Generation

The pitch generation process is designed to create highly personalized and effective pitches at scale.

### 1.1. Pitch Generator Service

*   **Service:** `services/pitches/generator.py`
*   **Function:** This service is the core of the pitch generation process. It uses a combination of AI models and predefined templates to create unique pitches for each podcast.
*   **Process:**
    1.  **Data Gathering:** The service gathers information about the client (from the `campaigns` table) and the target podcast (from the `podcasts` table).
    2.  **AI-Powered Content Creation:** It uses a large language model (LLM) to generate a personalized pitch body and subject line. The AI is prompted to highlight the client's expertise and explain why they would be a great guest for the specific podcast.
    3.  **Template Integration:** The generated content is then inserted into a pitch template, which provides the overall structure and formatting for the email.
    4.  **Draft Creation:** The final pitch is saved as a `draft` in the `pitches` table.

### 1.2. Pitch Templates

*   **API Endpoint:** `/api/pitch_templates/`
*   **Database Table:** `pitch_templates`
*   **Purpose:** Pitch templates allow for the creation of reusable pitch structures. This enables A/B testing of different pitch formats and ensures a consistent brand voice.

## 2. Pitch Sending

Once a pitch has been approved, it can be sent to the podcast.

### 2.1. Pitch Sender Service

*   **Service:** `services/pitches/sender.py`
*   **Function:** This service is responsible for sending the pitch to the podcast's contact person.
*   **Process:**
    1.  **Email Integration:** The service integrates with an external email provider (e.g., Nylas) to send the email.
    2.  **Personalization:** It uses the information from the `pitches` table to personalize the email with the recipient's name and other details.
    3.  **Status Update:** After the email is sent, the service updates the pitch's status to `sent` in the `pitches` table.

## 3. Pitch Tracking

The system provides comprehensive tracking for each pitch.

### 3.1. Pitch Status

*   **Database Field:** `pitches.status`
*   **Function:** This field tracks the current state of the pitch throughout its lifecycle.
*   **Statuses:**
    *   `draft`: The pitch has been generated but not yet approved.
    *   `approved`: The pitch has been approved and is ready to be sent.
    *   `sent`: The pitch has been sent to the podcast.
    *   `accepted`: The podcast has responded positively to the pitch.
    *   `rejected`: The podcast has declined the pitch.
    *   `archived`: The pitch is no longer active.

### 3.2. Response Tracking

*   **Service:** `services/inbox/booking_assistant.py`
*   **Function:** This service monitors the inbox for replies to sent pitches.
*   **Process:**
    1.  **Email Monitoring:** The service continuously checks for new emails in the connected email account.
    2.  **AI-Powered Analysis:** It uses natural language processing (NLP) to analyze the content of the replies and determine the sentiment (positive, negative, neutral).
    3.  **Status Updates:** Based on the analysis, the service automatically updates the pitch status. For example, if a reply is positive, the status is changed to `accepted`.

## 4. API Endpoints

The following API endpoints are used to manage pitches:

*   `POST /api/pitches/`: Create a new pitch.
*   `GET /api/pitches/`: Get a list of pitches.
*   `GET /api/pitches/{pitch_id}`: Get a specific pitch.
*   `PUT /api/pitches/{pitch_id}`: Update a pitch.
*   `DELETE /api/pitches/{pitch_id}`: Delete a pitch.
*   `POST /api/pitches/{pitch_id}/send`: Send a pitch.

This system provides a robust and automated solution for managing the entire pitch lifecycle, from creation to tracking and analysis.
