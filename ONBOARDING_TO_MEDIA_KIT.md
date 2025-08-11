
# PGL Onboarding to Media Kit Creation Workflow

This document outlines the detailed, verifiable workflow from when a new client is onboarded to the system to the point where a professional media kit is generated for their campaign.

## 1. Client Onboarding

The process begins when a new client registers on the platform.

*   **Trigger:** A user submits their details to the `POST /api/auth/register` endpoint.
*   **Process:**
    1.  **User Creation:** A new record is created in the `people` table with the `role` set to `client`.
        *   **Code Reference:** `api/routers/auth.py` -> `register_user` function.
    2.  **Default Campaign:** A default campaign is created for the new client in the `campaigns` table. This campaign is named `[Client's Full Name]'s First Campaign`.
        *   **Code Reference:** `database/queries/campaigns.py` -> `create_campaign_in_db` function is called within the registration flow.
    3.  **Client Profile:** A corresponding profile is created in the `client_profiles` table, which stores plan details and usage allowances.
        *   **Code Reference:** `database/queries/client_profiles.py` -> `create_client_profile` function.
    4.  **Email Verification:** A verification email is sent to the client to confirm their email address.
        *   **Code Reference:** `services/email_service.py` -> `send_verification_email` function.

## 2. Campaign Questionnaire

Once the client is onboarded, they are prompted to fill out a detailed questionnaire to gather information for their campaign.

*   **Trigger:** The client accesses the questionnaire section of the application and submits their responses via the `POST /api/campaigns/{campaign_id}/submit-questionnaire` endpoint.
*   **Process:**
    1.  **Data Submission:** The frontend sends the questionnaire data, which includes the client's bio, expertise, target audience, and social media links.
    2.  **Data Processing:** The `QuestionnaireProcessor` service processes the submitted data.
        *   **Code Reference:** `services/campaigns/questionnaire_processor.py` -> `process_campaign_questionnaire_submission` function.
    3.  **AI-Powered Summary:** The system uses an AI model to generate a concise `ideal_podcast_description` based on the questionnaire responses. This summary is crucial for the vetting process later on.
    4.  **Database Update:** The `campaigns` table is updated with the `questionnaire_responses` and the generated `ideal_podcast_description`.
        *   **Code Reference:** `database/queries/campaigns.py` -> `update_campaign_questionnaire_data` function.

## 3. Media Kit Generation

With the campaign information in place, a professional media kit is automatically generated for the client.

*   **Trigger:** The `MediaKitService` is called to generate the media kit. This can be triggered automatically after the questionnaire is submitted or manually by the user.
*   **Process:**
    1.  **Data Aggregation:** The `MediaKitService` gathers all relevant information from the `campaigns` and `people` tables, including the questionnaire responses, AI-generated summary, and client's personal details.
        *   **Code Reference:** `services/media_kits/generator.py` -> `create_or_update_media_kit` function.
    2.  **AI Content Generation:** The service uses a large language model (LLM) to generate various sections of the media kit, including:
        *   A compelling **tagline**.
        *   A comprehensive **bio** in multiple lengths (full, summary, and short).
        *   A list of **talking points** and **sample interview questions**.
        *   A **testimonials** section.
    3.  **Social Media Integration:** The service uses the `SocialDiscoveryService` to fetch the latest follower counts from the client's social media profiles.
        *   **Code Reference:** `services/enrichment/social_scraper.py`.
    4.  **Media Kit Creation:** A new record is created in the `media_kits` table, storing all the generated content. A unique, URL-friendly `slug` is also generated for the media kit.
        *   **Code Reference:** `database/queries/media_kits.py` -> `create_media_kit_in_db` function.

This workflow ensures that every client has a comprehensive and professional media kit that can be used to effectively pitch them to podcasts, all with minimal manual intervention.
