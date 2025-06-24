# podcast_outreach/services/ai/utils.py

import logging
from typing import Optional, List # Added List
import asyncio # Added for async operations
import os # Added for path manipulation

from podcast_outreach.services.ai.openai_client import OpenAIService # Corrected import path
from podcast_outreach.utils.file_manipulation import read_txt_file # Corrected import path

logger = logging.getLogger(__name__)

# Load the genre ID prompt text - adjust path to be relative to this file
# or ensure it's loaded from a central prompt management system.
# For now, let's make it relative to the project root as it was in src/
# A more robust solution would be to use services.ai.templates.load_prompt
# or pass the prompt content as an argument.
# For direct file access, ensure the path is correct relative to where the script is run
# or relative to this module.
# Assuming the prompt is now at podcast_outreach/services/ai/prompts/podcast_search/listennotes_genre_id_prompt.txt
# (This file was not provided in the directory listing, so assuming it's a conceptual file)
# For now, let's put a placeholder prompt if the file is truly missing or hardcode it.
# If the file exists in the old src/prompts path, you'd need to move it.

# Let's assume the prompt is now in the new prompts structure or hardcode for now.
# If you have a file like `podcast_outreach/services/ai/prompts/podcast_search/listennotes_genre_id_prompt.txt`
# then the path should be:
_LISTENNOTES_PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'podcast_search', 'listennotes_genre_id_prompt.txt')
if os.path.exists(_LISTENNOTES_PROMPT_FILE_PATH):
    LISTENNOTES_GENRE_ID_SYSTEM_PROMPT = read_txt_file(_LISTENNOTES_PROMPT_FILE_PATH)
else:
    logger.warning(f"ListenNotes genre ID prompt file not found at {_LISTENNOTES_PROMPT_FILE_PATH}. Using a default prompt.")
    LISTENNOTES_GENRE_ID_SYSTEM_PROMPT = """
    You are an expert in podcast categorization for ListenNotes. Given a user search query, identify relevant ListenNotes genre IDs.
    Return IDs as a comma-separated string within a JSON object: {"ids": "139,144,157"}
    """

async def generate_genre_ids(openai_service: OpenAIService, run_keyword: str, record_id: Optional[str] = None) -> Optional[str]:
    """Generate ListenNotes genre IDs using OpenAI. Returns a comma-separated string of IDs or None."""
    logger.info(f"Calling OpenAI to generate ListenNotes genre IDs for keyword: '{run_keyword}'.")

    prompt = f"""
    User Search Query:
    "{run_keyword}"

    Based on the user query and your knowledge of ListenNotes genres, provide the list of relevant ListenNotes genre IDs.
    Return the response in JSON format with an 'ids' key containing a comma-separated STRING of genre IDs.
    Example JSON Output Format: {{"ids": "139,144,157,99,90,77,253,69,104,84"}}
    Do not include backticks like ```json ... ``` in your output.
    """
    genre_ids_str = await openai_service.create_chat_completion(
        system_prompt=LISTENNOTES_GENRE_ID_SYSTEM_PROMPT,
        prompt=prompt,
        workflow="generate_listennotes_genre_ids",
        parse_json=True,
        json_key="ids",
        related_campaign_id=record_id,
        related_media_id=None
    )
    if isinstance(genre_ids_str, str):
        logger.info(f"ListenNotes genre IDs generated for '{run_keyword}': {genre_ids_str}")
        return genre_ids_str
    logger.warning(f"Failed to generate valid string of ListenNotes genre IDs for '{run_keyword}'. Received: {genre_ids_str}")
    return None

# --- Podscan Category ID Generation --- 
_PODSCAN_PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'podcast_search', 'podscan_category_id_prompt.txt')
if os.path.exists(_PODSCAN_PROMPT_FILE_PATH):
    PODSCAN_CATEGORY_ID_SYSTEM_PROMPT = read_txt_file(_PODSCAN_PROMPT_FILE_PATH)
else:
    logger.warning(f"Podscan category ID prompt file not found at {_PODSCAN_PROMPT_FILE_PATH}. Using a default prompt.")
    PODSCAN_CATEGORY_ID_SYSTEM_PROMPT = """
    You are a content moderator for Podscan.fm. Given a user search query, find the 10 most relevant category IDs.
    The list of categories will be provided in the prompt. 
    Return a comma-delimited string of these 10 category IDs within a JSON object: {"ids": "ct_id1,ct_id2,ct_id3,..."}
    """

async def generate_podscan_category_ids(openai_service: OpenAIService, run_keyword: str, record_id: Optional[str] = None) -> Optional[str]:
    """Generate Podscan category IDs using OpenAI. Returns a comma-separated string of IDs or None."""
    logger.info(f"Calling OpenAI to generate Podscan category IDs for keyword: '{run_keyword}'.")

    # The PODSCAN_CATEGORY_ID_SYSTEM_PROMPT itself contains the full list of categories and instructions.
    # We just need to append the specific user keyword to it or ensure the prompt is structured for that.
    # The current podscan_category_id_prompt.txt seems to be a complete prompt that includes the list.
    # We will pass the keyword as the main prompt, and the loaded file content as the system prompt.

    prompt_for_podscan = f"""
    User Search Query:
    "{run_keyword}"

    Based on the user query and the list of Podscan categories provided in the system instructions, identify the 10 most relevant category IDs.
    Return the response in JSON format with an 'ids' key containing a comma-separated STRING of these 10 category IDs.
    Example JSON Output Format: {{"ids": "ct_zqbe76njpnyjx432,ct_akrev35b4w4ypql9,ct_vy2zbpn3eg5q3m7g,ct_rzemq35l4jn9x27d,ct_vy2zbpn39mnq3m7g"}}
    Do not include backticks like ```json ... ``` in your output.
    """

    category_ids_str = await openai_service.create_chat_completion(
        system_prompt=PODSCAN_CATEGORY_ID_SYSTEM_PROMPT,
        prompt=prompt_for_podscan,
        workflow="generate_podscan_category_ids",
        parse_json=True,
        json_key="ids",
        related_campaign_id=record_id,
        related_media_id=None
    )
    if isinstance(category_ids_str, str):
        logger.info(f"Podscan category IDs generated for '{run_keyword}': {category_ids_str}")
        return category_ids_str
    logger.warning(f"Failed to generate valid string of Podscan category IDs for '{run_keyword}'. Received: {category_ids_str}")
    return None