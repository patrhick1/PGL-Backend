
# PGL Podcast Discovery, Enrichment, Vetting, and Matching Workflow

This document provides a detailed, verifiable breakdown of the automated workflow for identifying, enriching, vetting, and matching podcasts with clients.

## 1. Podcast Discovery

The discovery process is initiated by the `AutomatedDiscoveryService` and is responsible for finding new podcast opportunities for active campaigns.

*   **Trigger:** The `check_and_run_discoveries` method in `services/discovery/automated_discovery_service.py` is called periodically by a scheduler.
*   **Process:**
    1.  **Campaign Selection:** The service identifies campaigns that are ready for discovery. This is determined by the `get_campaigns_ready_for_auto_discovery` method, which selects campaigns that have `auto_discovery_enabled` set to `true`, have keywords, and have not exceeded their weekly match limits.
    2.  **Podcast Search:** For each selected campaign, the service iterates through the `campaign_keywords` and uses the `ListenNotesAPIClient` and `PodscanAPIClient` to search for relevant podcasts. This is handled by the `_fetch_podcasts_for_keywords` method.
        *   **Code Reference:** `integrations/listen_notes.py` and `integrations/podscan.py`.
    3.  **Discovery Tracking:** As new podcasts are found, they are added to the `media` table, and a record is created in the `campaign_media_discoveries` table to link the podcast to the campaign and the keyword that was used to find it.
        *   **Code Reference:** `database/queries/media.py` (specifically `track_campaign_media_discovery`).

## 2. Data Enrichment

Once a new podcast is discovered, it goes through an enrichment process to gather more information about it.

*   **Trigger:** The `EnrichmentOrchestrator` in `services/enrichment/enrichment_orchestrator.py` is responsible for enriching new and existing podcast records.
*   **Process:**
    1.  **Core Details Enrichment:** The `run_core_details_enrichment` method identifies new media records and uses the `EnrichmentAgent` to gather additional information, such as social media links, contact information, and a more detailed description.
        *   **Code Reference:** `services/enrichment/enrichment_agent.py`.
    2.  **Social Stats Refresh:** The `run_social_stats_refresh` method periodically updates the follower counts for social media accounts associated with the podcasts.
        *   **Code Reference:** `services/enrichment/social_scraper.py`.
    3.  **AI Description Generation:** If a podcast does not have a description, the system uses the content of its recent episodes to generate one using an AI model.
        *   **Code Reference:** `services/media/analyzer.py`.
    4.  **Quality Score Calculation:** The `run_quality_score_updates` method calculates a quality score for each podcast based on a variety of factors, including the number of episodes, the presence of social media links, and the estimated audience size. The `calculate_podcast_quality_score` method in the `QualityService` is responsible for this calculation.
        *   **Code Reference:** `services/enrichment/quality_score.py`.

## 3. Vetting

After a podcast has been enriched, it is vetted to determine if it is a good fit for a specific client's campaign.

*   **Trigger:** The `EnhancedVettingOrchestrator` in `services/matches/enhanced_vetting_orchestrator.py` identifies enriched podcasts that are ready for vetting.
*   **Process:**
    1.  **Vetting Agent:** The `vet_match` method of the `EnhancedVettingAgent` is called to perform the vetting. This agent uses an AI model to compare the podcast's profile with the client's campaign goals and ideal podcast description.
        *   **Code Reference:** `services/matches/enhanced_vetting_agent.py`.
    2.  **Vetting Score:** The agent generates a `vetting_score` between 0 and 100, along with a detailed `vetting_reasoning` that explains the score.
    3.  **Results Storage:** The vetting results are stored in the `campaign_media_discoveries` table.

## 4. Matching

If a podcast is successfully vetted and receives a high enough score, a match suggestion is created.

*   **Trigger:** The `_create_match_suggestion` method in the `EnhancedVettingOrchestrator` is called for podcasts that pass the vetting process.
*   **Process:**
    1.  **Episode Matching:** The `EpisodeMatcher` service is used to find the best episode from the podcast to showcase to the client. This is done by comparing the content of the episodes with the client's campaign information.
        *   **Code Reference:** `services/matches/episode_matcher.py`.
    2.  **Match Creation:** A new record is created in the `match_suggestions` table. This record includes the campaign, the podcast, the best matching episode, the vetting score, and the reasoning.
        *   **Code Reference:** `services/matches/match_creation.py`.
    3.  **Review Task:** A new review task is created for the client to review the match suggestion.

This comprehensive workflow ensures that only the most relevant and high-quality podcasts are presented to clients, with a detailed and verifiable paper trail for each step of the process.
