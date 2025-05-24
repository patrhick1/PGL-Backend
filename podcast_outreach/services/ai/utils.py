"""Utility functions for AI services."""

import logging
from typing import Optional

from podcast_outreach.services.ai.openai_client import OpenAIService
from podcast_outreach.utils.file_manipulation import read_txt_file

logger = logging.getLogger(__name__)

# Load the genre ID prompt text
GENRE_ID_PROMPT = read_txt_file(
    r"prompts/podcast_search/listennotes_genre_id_prompt.txt"
)

def generate_genre_ids(openai_service: OpenAIService, run_keyword: str, record_id: Optional[str] = None):
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

    genre_ids = openai_service.create_chat_completion(
        system_prompt=GENRE_ID_PROMPT,
        prompt=prompt,
        workflow="generate_genre_ids",
        parse_json=True,
        json_key="ids",
        podcast_id=record_id,
    )
    logger.info("Genre IDs generated: %s", genre_ids)
    return genre_ids
