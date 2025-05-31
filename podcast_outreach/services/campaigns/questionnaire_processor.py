# podcast_outreach/services/campaigns/questionnaire_processor.py
import logging
import uuid
from typing import Dict, Any
from podcast_outreach.database.queries import campaigns as campaign_queries
import json # For storing as JSONB
from podcast_outreach.services.tasks.manager import task_manager # Corrected import path

logger = logging.getLogger(__name__)

def _construct_mock_interview_from_questionnaire(questionnaire_data: Dict[str, Any]) -> str:
    """
    Constructs a string for mock_interview_trancript from questionnaire responses.
    (This function can be expanded based on your questionnaire structure)
    """
    lines = []
    
    # Example: Iterate through top-level keys and their values
    for section_key, section_value in questionnaire_data.items():
        lines.append(f"--- {section_key.replace('_', ' ').title()} ---")
        if isinstance(section_value, dict):
            for item_key, item_value in section_value.items():
                if isinstance(item_value, list):
                    lines.append(f"{item_key.replace('_', ' ').title()}: {', '.join(map(str, item_value))}")
                else:
                    lines.append(f"{item_key.replace('_', ' ').title()}: {str(item_value)}")
        elif isinstance(section_value, list):
             lines.append(f"{section_key.replace('_', ' ').title()}: {', '.join(map(str, section_value))}")
        else:
            lines.append(f"{section_key.replace('_', ' ').title()}: {str(section_value)}")
        lines.append("") # Add a blank line for separation

    return "\n".join(lines)

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
            "questionnaire_responses": questionnaire_data, # Store the raw Python dict, asyncpg handles JSONB
            "mock_interview_trancript": mock_interview_text
        }

        # Extract keywords (example logic, adjust based on your questionnaire structure)
        # This assumes your questionnaire_data might have keys like 'expertise', 'preferredTopics' etc.
        questionnaire_keywords_set = set() 
        
        # Example: Extracting from a nested structure
        personal_info = questionnaire_data.get("personalInfo", {})
        if isinstance(personal_info, dict) and personal_info.get("expertise"):
            expertise_list = personal_info["expertise"]
            if isinstance(expertise_list, list):
                 questionnaire_keywords_set.update(kw for kw in expertise_list if isinstance(kw, str))

        preferences = questionnaire_data.get("preferences", {})
        if isinstance(preferences, dict) and preferences.get("preferredTopics"):
            topics_list = preferences["preferredTopics"]
            if isinstance(topics_list, list):
                questionnaire_keywords_set.update(topic for topic in topics_list if isinstance(topic, str))
        
        # Add more keyword extraction logic as needed from other parts of questionnaire_data

        if questionnaire_keywords_set: # Only update if new keywords were found
            update_payload["questionnaire_keywords"] = sorted(list(questionnaire_keywords_set))

        updated_campaign = await campaign_queries.update_campaign(campaign_id, update_payload)
        if updated_campaign:
            logger.info(f"Successfully processed questionnaire and updated campaign {campaign_id} with questionnaire_keywords.")
            # Enqueue the process_campaign_content task
            task_id = str(uuid.uuid4())
            task_manager.start_task(
                task_id,
                "process_campaign_content",
                args={"campaign_id": str(campaign_id)}
            )
            logger.info(f"Enqueued process_campaign_content task {task_id} for campaign {campaign_id}.")
            return True
        else:
            logger.error(f"Failed to update campaign {campaign_id} after processing questionnaire.")
            return False

    except Exception as e:
        logger.exception(f"Error processing questionnaire for campaign {campaign_id}: {e}")
        return False