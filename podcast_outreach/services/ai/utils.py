# podcast_outreach/services/ai/utils.py

import logging
from typing import Optional
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
_PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'podcast_search', 'listennotes_genre_id_prompt.txt')
if os.path.exists(_PROMPT_FILE_PATH):
    GENRE_ID_PROMPT = read_txt_file(_PROMPT_FILE_PATH)
else:
    logger.warning(f"Genre ID prompt file not found at {_PROMPT_FILE_PATH}. Using a default prompt.")
    GENRE_ID_PROMPT = """
    You are an expert in podcast categorization. Given a user search query, identify relevant ListenNotes genre IDs.
    Here are some examples:
    - Query: "technology startups" -> {"ids": "139,144,157"}
    - Query: "business growth strategies" -> {"ids": "99,90,77"}
    - Query: "health and wellness" -> {"ids": "253,69,104"}
    - Query: "true crime stories" -> {"ids": "84"}
    """


async def generate_genre_ids(openai_service: OpenAIService, run_keyword: str, record_id: Optional[str] = None):
    """Generate ListenNotes genre IDs using OpenAI."""
    logger.info("Calling OpenAI to generate genre IDs...")

    prompt = f"""
    User Search Query:
    "{run_keyword}"

    Provide the list of genre IDs as per the example above.
    Return the response in JSON format with an 'ids' key containing an array of integers.
    Do not include backticks i.e ```json
    Example JSON Output Format: {{"ids": "139,144,157,99,90,77,253,69,104,84"}}
    """

    # Await the async create_chat_completion call
    genre_ids = await openai_service.create_chat_completion(
        system_prompt=GENRE_ID_PROMPT,
        prompt=prompt,
        workflow="generate_genre_ids",
        parse_json=True,
        json_key="ids",
        related_media_id=record_id, # Use related_media_id for tracking if applicable
        # If record_id is an Airtable ID, it won't map directly to PostgreSQL media_id.
        # You'll need to adjust tracking to use the new PostgreSQL IDs.
        # For now, keeping it as is, but be aware of the change.
    )
    logger.info("Genre IDs generated: %s", genre_ids)
    return genre_ids