# podcast_outreach/services/ai/openai_client.py

import os
import json
import logging
import time
import asyncio # Added for async operations
import functools # Added for asyncio.to_thread
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
import uuid # For UUID types

# Import our AI usage tracker from its new location
from podcast_outreach.services.ai.tracker import tracker as ai_tracker # Corrected import path
from podcast_outreach.logging_config import get_logger # Use new logging config
from podcast_outreach.utils.file_manipulation import read_txt_file # Use new utils path

# Load .env variables to access your OpenAI API key
load_dotenv()

# Configure logging
logger = get_logger(__name__)

# --- Pydantic Models (Moved from old openai_service.py) ---
# These models are still used by the methods below.
# If these models are used elsewhere, they should be in a shared `schemas` or `models` directory.
# For now, keeping them here as they are tightly coupled to this service's output parsing.

class get_host_guest_confirmation(BaseModel):
    status: str = Field(
        description=
        "provide your overall assessment by outputting either 'Both' for if both host and guest are identified, 'Host' or 'Guest'"
    )
    Host: str = Field(
        description=
        "Identify who the host of the show is and extract their names, it is usually one host though"
    )
    Guest: str = Field(
        description=
        "Identify who the guest is and extract their names as a string")

class get_validation(BaseModel):
    correct: str = Field(
        description=
        "the only response I need here is true or false, If the junior correctly labeled the host(s) and guest(s), the boolean variable 'correct' is 'true' or If the junior incorrectly labeled the host(s) and guest(s), the boolean variable 'correct' is 'false' "
    )

class get_answer_for_fit(BaseModel):
    Answer: str = Field(
        description=
        "ONLY provide your overall fit assessment by outputting either 'Fit' or 'Not a fit' (without quotes), using the JSON format specified "
    )

class get_episode_ID(BaseModel):
    ID: str = Field(
        description=
        "Give your output containing ONLY the selected Episode ID in JSON ")

class GetTopicDescriptions(BaseModel):
    topic_1: str = Field(...,
                         alias="Topic 1",
                         description="Title of the first topic.")
    description_1: str = Field(...,
                               alias="Description 1",
                               description="Description for the first topic.")
    topic_2: str = Field(...,
                         alias="Topic 2",
                         description="Title of the second topic.")
    description_2: str = Field(...,
                               alias="Description 2",
                               description="Description for the second topic.")
    topic_3: str = Field(...,
                         alias="Topic 3",
                         description="Title of the third topic.")
    description_3: str = Field(...,
                               alias="Description 3",
                               description="Description for the third topic.")

class getHostName(BaseModel):
    Host: str = Field(
        description=
        "Identify who the host of the show is and extract their names, it is usually one host though, only return the host name nothing more"
    )

class StructuredData(BaseModel):
    """
    This model defines the structure of the data that we expect from our
    OpenAI completion when generating bios and angles.
    """
    Bio: str = Field(description="""Client's bio.
            Include one main text but keep tabs and new lines indicating "Full Bio,"
            "Summary Bio," and "Short Bio" within the text.""")
    Angles: str = Field(description="""Client's angles.
            Each angle has three parts: Topic, Outcome, Description.
            Keep tabs and new lines to separate these parts.""")

# --- End Pydantic Models ---

class OpenAIService: # Keeping original class name for compatibility
    """
    A service that communicates with OpenAI's API to perform various text-related tasks.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the OpenAI client using the API key from your environment variables.
        """
        if api_key is None:
            api_key = os.getenv('OPENAI_API')
            if not api_key:
                logger.error("OPENAI_API environment variable not set.")
                raise ValueError("Please set the OPENAI_API environment variable.")
        try:
            self.client = OpenAI(api_key=api_key)
            logger.info("OpenAIService initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")
            raise

    async def transform_text_to_structured_data(self, prompt: str, raw_text: str, data_type: str,
                                               workflow: str = "transform_structured_data",
                                               related_pitch_gen_id: Optional[int] = None,
                                               related_campaign_id: Optional[uuid.UUID] = None, related_media_id: Optional[int] = None,
                                               max_retries: int = 3, initial_retry_delay: int = 2) -> Optional[Dict[str, Any]]:
        """
        Use the OpenAI API to parse raw text into a structured JSON format.

        Args:
            prompt (str): Instructions for what we want from the raw text.
            raw_text (str): The text to be transformed.
            data_type (str): Type of structured data to parse.
            workflow (str): Name of the workflow using this method.
            related_pitch_gen_id (int, optional): ID of the pitch generation for tracking
            related_campaign_id (UUID, optional): ID of the campaign for tracking
            related_media_id (int, optional): ID of the media for tracking
            max_retries (int): Maximum number of retry attempts
            initial_retry_delay (int): Initial delay in seconds before first retry (doubles with each retry)

        Returns:
            dict: A dictionary that fits the specified Pydantic model.
        """
        retry_count = 0
        retry_delay = initial_retry_delay
        last_exception = None

        while retry_count <= max_retries:
            try:
                start_time = time.time()

                # Determine response format based on data_type
                response_format_model = None
                if data_type == 'Structured':
                    response_format_model = StructuredData
                elif data_type == 'confirmation':
                    response_format_model = get_host_guest_confirmation
                elif data_type == 'validation':
                    response_format_model = get_validation
                elif data_type == 'fit':
                    response_format_model = get_answer_for_fit
                elif data_type == 'episode_ID':
                    response_format_model = get_episode_ID
                elif data_type == 'topic_descriptions':
                    response_format_model = GetTopicDescriptions
                elif data_type == 'host_name':
                    response_format_model = getHostName
                else:
                    raise ValueError(f"Unsupported data_type for structured parsing: {data_type}")

                model = "gpt-4o-2024-08-06"

                # Use asyncio.to_thread for synchronous API call within async function
                completion = await asyncio.to_thread(
                    self.client.beta.chat.completions.parse,
                    model=model,
                    messages=[{
                        "role": "system",
                        "content": f"{prompt} Please provide the response in JSON format."
                    }, {
                        "role": "user",
                        "content": raw_text
                    }],
                    response_format=response_format_model,
                )

                execution_time = time.time() - start_time
                response_content = completion.choices[0].message.parsed

                tokens_in = completion.usage.prompt_tokens
                tokens_out = completion.usage.completion_tokens

                await ai_tracker.log_usage( # Await the async log_usage call
                    workflow=workflow,
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    execution_time=execution_time,
                    endpoint="openai.beta.chat.completions.parse",
                    related_pitch_gen_id=related_pitch_gen_id,
                    related_campaign_id=related_campaign_id,
                    related_media_id=related_media_id
                )

                return response_content.model_dump()

            except Exception as e:
                last_exception = e
                retry_count += 1

                if retry_count <= max_retries:
                    logger.warning(f"Error in OpenAI API call (attempt {retry_count}/{max_retries}): {e}. "
                                   f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay) # Await the sleep
                    retry_delay *= 2
                else:
                    logger.error(f"Error during text-to-structured-data transformation after {max_retries} retries: {e}")
                    raise Exception(f"Failed to transform text to structured data: {e}") from last_exception

    async def create_chat_completion(self, system_prompt: str, prompt: str,
                                     workflow: str = "chat_completion",
                                     related_pitch_gen_id: Optional[int] = None,
                                     related_campaign_id: Optional[uuid.UUID] = None, related_media_id: Optional[int] = None,
                                     parse_json: bool = False, json_key: Optional[str] = None,
                                     max_retries: int = 3, initial_retry_delay: int = 2) -> Any:
        """
        Create a chat completion using the OpenAI API.

        Args:
            system_prompt (str): The system role prompt for guidance.
            prompt (str): The user's main content/query.
            workflow (str): Name of the workflow using this method.
            related_pitch_gen_id (int, optional): ID of the pitch generation for tracking
            related_campaign_id (UUID, optional): ID of the campaign for tracking
            related_media_id (int, optional): ID of the media for tracking
            parse_json (bool, optional): Whether to parse the response as JSON.
            json_key (str, optional): If parse_json is True, extract this key from the JSON.
            max_retries (int): Maximum number of retry attempts
            initial_retry_delay (int): Initial delay in seconds before first retry (doubles with each retry)

        Returns:
            str: The raw text (JSON or otherwise) from the assistant's message, or
                 the value of the specified json_key if parse_json is True.
        """
        retry_count = 0
        retry_delay = initial_retry_delay
        last_exception = None

        while retry_count <= max_retries:
            try:
                start_time = time.time()

                model = "gpt-4o-2024-08-06"

                # Use asyncio.to_thread for synchronous API call within async function
                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    model=model,
                    messages=[{
                        "role": "system",
                        "content": system_prompt
                    }, {
                        "role": "user",
                        "content": prompt
                    }],
                    temperature=0.1,
                )

                execution_time = time.time() - start_time
                assistant_message = response.choices[0].message.content

                tokens_in = response.usage.prompt_tokens
                tokens_out = response.usage.completion_tokens

                await ai_tracker.log_usage( # Await the async log_usage call
                    workflow=workflow,
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    execution_time=execution_time,
                    endpoint="openai.chat.completions.create",
                    related_pitch_gen_id=related_pitch_gen_id,
                    related_campaign_id=related_campaign_id,
                    related_media_id=related_media_id
                )

                if parse_json:
                    try:
                        if "```" in assistant_message:
                            assistant_message = assistant_message.split("```")[1]
                            if assistant_message.startswith("json"):
                                assistant_message = assistant_message[4:]

                        result = json.loads(assistant_message.strip())
                        if json_key is not None:
                            if json_key not in result:
                                raise ValueError(f"Response JSON is missing '{json_key}' field.")
                            return result[json_key]
                        return result

                    except json.JSONDecodeError as e:
                        logger.error(f"Error parsing JSON from response: {e}")
                        logger.error(f"Raw response: {assistant_message}")
                        raise ValueError(f"OpenAI response was not valid JSON. Check logs.")
                
                return assistant_message

            except Exception as e:
                last_exception = e
                retry_count += 1

                if retry_count <= max_retries:
                    logger.warning(f"Error in OpenAI API call (attempt {retry_count}/{max_retries}): {e}. "
                                   f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay) # Await the sleep
                    retry_delay *= 2
                else:
                    logger.error(f"Error in create_chat_completion after {max_retries} retries: {e}")
                    raise Exception(f"Failed to generate chat completion using OpenAI API: {e}") from last_exception

    async def get_embedding(self, text: str, model: str = "text-embedding-ada-002", workflow: str = "embedding", **kwargs) -> Optional[List[float]]:
        start_time = time.time()
        try:
            text = text.replace("\n", " ") # OpenAI recommends replacing newlines
            response = await asyncio.to_thread(
                self.client.embeddings.create, input=[text], model=model
            )
            embedding = response.data[0].embedding
            
            # Estimate tokens for embeddings (input only)
            # OpenAI's ada-002 counts tokens differently, but this is a rough estimate for logging
            tokens_in = len(text) // 4 
            
            await ai_tracker.log_usage(
                workflow=workflow,
                model=model,
                tokens_in=tokens_in, 
                tokens_out=0, # Embeddings don't have "output tokens" in the same way
                execution_time=(time.time() - start_time),
                endpoint="openai.embeddings.create",
                **kwargs # Pass related_ids
            )
            return embedding
        except Exception as e:
            logger.error(f"Error getting embedding for text (first 100 chars): '{text[:100]}...': {e}", exc_info=True)
            return None