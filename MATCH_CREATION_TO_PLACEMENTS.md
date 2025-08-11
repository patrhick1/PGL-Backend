
# PGL Match Creation to Placements Workflow

This document provides a detailed, verifiable workflow from the moment a match is created between a client and a podcast to the final placement.

## 1. Match Creation

A match represents a potential opportunity for a client to be a guest on a podcast.

*   **Trigger:** The `_create_match_suggestion` method in the `EnhancedVettingOrchestrator` is called for podcasts that pass the vetting process.
*   **Process:**
    1.  **Scoring:** The `MatchCreationService` calculates a `match_score` based on the cosine similarity between the campaign's and the podcast's embeddings, as well as the Jaccard similarity of their keywords.
        *   **Code Reference:** `services/matches/match_creation.py` -> `_score_single_campaign_media_pair` function.
    2.  **Match Suggestion:** A new record is created in the `match_suggestions` table, containing the campaign, podcast, match score, and the best matching episode.
        *   **Code Reference:** `database/queries/match_suggestions.py` -> `create_match_suggestion_in_db` function.
    3.  **Client Review Task:** A review task is created for the client to approve or reject the match suggestion.

## 2. Client Approval

The client reviews the match suggestion and decides whether to proceed with the pitch.

*   **Trigger:** The client approves the match suggestion through the UI.
*   **Process:**
    1.  **Status Update:** The `client_approved` field in the `match_suggestions` table is set to `true`, and the `status` is updated to `approved`.
        *   **Code Reference:** `database/queries/match_suggestions.py` -> `approve_match_and_create_pitch_task` function.

## 3. Pitch Generation

Once a match is approved, a personalized pitch is generated.

*   **Trigger:** A staff member or admin initiates the pitch generation process via the `POST /api/pitches/generate` endpoint.
*   **Process:**
    1.  **Pitch Generation Service:** The `PitchGeneratorService` uses an AI model to create a personalized pitch email and subject line based on the selected pitch template, the client's campaign information, and the podcast's details.
        *   **Code Reference:** `services/pitches/generator.py` -> `generate_pitch_for_match` function.
    2.  **Pitch Record:** A new record is created in the `pitches` table to store the generated pitch.
        *   **Code Reference:** `database/queries/pitches.py` -> `create_pitch_in_db` function.
    3.  **Pitch Review Task:** A review task is created for a staff member to review and approve the generated pitch.

## 4. Pitch Sending

After the pitch is approved, it is sent to the podcast.

*   **Trigger:** A staff member or admin initiates the sending process via the `POST /api/pitches/{pitch_id}/send` endpoint.
*   **Process:**
    1.  **Pitch Sender Service:** The `PitchSenderService` sends the pitch to the podcast's contact email address using an integrated email service (e.g., Instantly.ai or Nylas).
        *   **Code Reference:** `services/pitches/sender.py` and `services/pitches/sender_v2.py`.
    2.  **Status Update:** The `pitch_state` in the `pitches` table is updated to `sent`.

## 5. Response Tracking and Booking

The system monitors for responses to the sent pitches and facilitates the booking process.

*   **Trigger:** An email reply is received from the podcast.
*   **Process:**
    1.  **Booking Assistant:** The `BookingAssistantService` processes the incoming email, using AI to classify the response (e.g., `accepted`, `rejected`, `question`).
        *   **Code Reference:** `services/inbox/booking_assistant.py`.
    2.  **Positive Response:** If the response is positive, the `pitch_state` is updated to `accepted`.

## 6. Placement

When a pitch is accepted, it is converted into a placement, representing a confirmed booking.

*   **Trigger:** A staff member manually creates a placement record via the `POST /api/placements/` endpoint after a booking is confirmed.
*   **Process:**
    1.  **Placement Creation:** A new record is created in the `placements` table, linking the placement to the original pitch, campaign, and media.
        *   **Code Reference:** `database/queries/placements.py` -> `create_placement_in_db` function.
    2.  **Status Tracking:** The placement's `current_status` is tracked through its lifecycle (e.g., `scheduled`, `completed`, `cancelled`).

This workflow provides a structured and semi-automated process for converting a potential match into a confirmed podcast placement.
