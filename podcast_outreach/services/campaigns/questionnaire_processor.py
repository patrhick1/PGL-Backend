# podcast_outreach/services/campaigns/questionnaire_processor.py
import logging
import uuid
from typing import Dict, Any
from podcast_outreach.database.queries import campaigns as campaign_queries

logger = logging.getLogger(__name__)

def _construct_mock_interview_from_questionnaire(questionnaire_data: Dict[str, Any]) -> str:
    """
    Constructs a string for mock_interview_trancript from questionnaire responses.
    """
    lines = []
    
    # Personal Info
    pi = questionnaire_data.get("personalInfo", {})
    if pi.get("fullName"): lines.append(f"Full Name: {pi['fullName']}")
    if pi.get("jobTitle"): lines.append(f"Job Title: {pi['jobTitle']}")
    if pi.get("company"): lines.append(f"Company: {pi['company']}")
    if pi.get("bio"): lines.append(f"\nProfessional Bio:\n{pi['bio']}\n")
    if pi.get("expertise"): lines.append(f"Areas of Expertise: {', '.join(pi['expertise'])}")

    # Experience
    exp = questionnaire_data.get("experience", {})
    if exp.get("yearsOfExperience"): lines.append(f"\nYears of Experience: {exp['yearsOfExperience']}")
    if exp.get("previousPodcasts"): lines.append(f"Previous Podcast Appearances: {exp['previousPodcasts']}")
    if exp.get("speakingExperience"): lines.append(f"Other Speaking Experience: {', '.join(exp['speakingExperience'])}")
    if exp.get("achievements"): lines.append(f"\nKey Achievements:\n{exp['achievements']}\n")

    # Goals
    goals = questionnaire_data.get("goals", {})
    if goals.get("primaryGoals"): lines.append(f"Primary Goals for Podcast Appearances: {', '.join(goals['primaryGoals'])}")
    if goals.get("targetAudience"): lines.append(f"\nTarget Audience Description:\n{goals['targetAudience']}\n")
    if goals.get("keyMessages"): lines.append(f"\nKey Messages to Convey:\n{goals['keyMessages']}\n")
    
    # You might also iterate through the `interviewResponses` from PitchGenerator.tsx's form
    # if that data is also submitted here or if those questions are merged into Questionnaire.tsx.
    # For example, if `interviewResponses` is part of `questionnaire_data`:
    # interview_responses = questionnaire_data.get("interviewResponses", {})
    # if interview_responses:
    #     lines.append("\n--- Interview Insights ---")
    #     for q_id, answer in interview_responses.items():
    #         # You'd need a mapping from q_id to actual question text for readability
    #         lines.append(f"Q ({q_id}): {answer}")

    return "\n\n".join(lines)

async def process_campaign_questionnaire_submission(campaign_id: uuid.UUID, questionnaire_data: Dict[str, Any]) -> bool:
    """
    Processes submitted questionnaire data for a campaign.
    Updates the campaign record with questionnaire responses and a constructed mock interview transcript.
    """
    try:
        campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found for questionnaire submission.")
            return False

        mock_interview_text = _construct_mock_interview_from_questionnaire(questionnaire_data)
        
        update_payload: Dict[str, Any] = {
            "questionnaire_responses": questionnaire_data, # Store the raw JSON
            "mock_interview_trancript": mock_interview_text
        }

        # Extract keywords
        keywords = set(campaign.get("campaign_keywords", []) or []) # Start with existing keywords
        if questionnaire_data.get("personalInfo", {}).get("expertise"):
            keywords.update(questionnaire_data["personalInfo"]["expertise"])
        if questionnaire_data.get("preferences", {}).get("preferredTopics"):
            keywords.update(questionnaire_data["preferences"]["preferredTopics"])
        
        update_payload["campaign_keywords"] = sorted(list(keywords))

        updated_campaign = await campaign_queries.update_campaign(campaign_id, update_payload)
        if updated_campaign:
            logger.info(f"Successfully processed questionnaire and updated campaign {campaign_id}.")
            return True
        else:
            logger.error(f"Failed to update campaign {campaign_id} after processing questionnaire.")
            return False

    except Exception as e:
        logger.exception(f"Error processing questionnaire for campaign {campaign_id}: {e}")
        return False

# In your new API router (e.g., api/routers/campaigns.py):
# from podcast_outreach.services.campaigns.questionnaire_processor import process_campaign_questionnaire_submission
#
# @router.post("/{campaign_id}/submit-questionnaire-data")
# async def submit_questionnaire(campaign_id: uuid.UUID, questionnaire_data: YourQuestionnairePydanticModel):
#     success = await process_campaign_questionnaire_submission(campaign_id, questionnaire_data.model_dump())
#     if success:
#         return {"message": "Questionnaire data processed successfully."}
#     else:
#         raise HTTPException(status_code=500, detail="Failed to process questionnaire data.")