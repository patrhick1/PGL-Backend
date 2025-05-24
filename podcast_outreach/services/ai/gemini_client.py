# podcast_outreach/services/ai/gemini_client.py

import os
import time
import logging
import asyncio # Added for async operations
import functools # Added for asyncio.to_thread
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import google.generativeai as genai
import uuid

# Import our AI usage tracker from its new location
from podcast_outreach.services.ai.tracker import tracker as ai_tracker
from podcast_outreach.logging_config import get_logger # Use new logging config

# Load environment variables
load_dotenv()

# Fetch API Key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Set up logging
logger = get_logger(__name__)

class GeminiService: # Keeping original class name for compatibility with existing calls
    """
    A service that communicates with Google's Gemini API to generate text responses.
    """

    def __init__(self):
        """
        Initialize the Gemini client using the API key from environment variables.
        """
        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY environment variable not set.")
            raise ValueError("Please set the GEMINI_API_KEY environment variable.")
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            logger.info("GeminiService initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise

    async def create_message(self, prompt: str, model: str = 'gemini-1.5-flash-001',
                             workflow: str = "unknown", related_pitch_gen_id: Optional[int] = None,
                             related_campaign_id: Optional[uuid.UUID] = None, related_media_id: Optional[int] = None,
                             max_retries: int = 3, initial_retry_delay: int = 2) -> str:
        """
        Generate a response from Gemini based on the provided prompt.

        Args:
            prompt (str): The text prompt to send to the Gemini API
            model (str): The Gemini model to use
            workflow (str): The name of the workflow using this method
            related_pitch_gen_id (int, optional): ID of the pitch generation for tracking
            related_campaign_id (UUID, optional): ID of the campaign for tracking
            related_media_id (int, optional): ID of the media for tracking
            max_retries (int): Maximum number of retry attempts
            initial_retry_delay (int): Initial delay in seconds before first retry (doubles with each retry)

        Returns:
            str: The text response from Gemini
        """
        retry_count = 0
        retry_delay = initial_retry_delay
        last_exception = None

        while retry_count <= max_retries:
            try:
                start_time = time.time()

                generation_config = {
                    "temperature": 0.01,
                    "top_p": 0.1,
                    "top_k": 1,
                    "max_output_tokens": 2048,
                }

                model_instance = genai.GenerativeModel(
                    model_name=model,
                    generation_config=generation_config
                )

                # Use asyncio.to_thread for synchronous API call within async function
                response = await asyncio.to_thread(model_instance.generate_content, prompt)

                execution_time = time.time() - start_time
                content_text = response.text if hasattr(response, 'text') else str(response)

                tokens_in = len(prompt) // 4  # Rough approximation
                tokens_out = len(content_text) // 4  # Rough approximation

                await ai_tracker.log_usage( # Await the async log_usage call
                    workflow=workflow,
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    execution_time=execution_time,
                    endpoint="gemini.generate_content",
                    related_pitch_gen_id=related_pitch_gen_id,
                    related_campaign_id=related_campaign_id,
                    related_media_id=related_media_id
                )

                return content_text

            except Exception as e:
                last_exception = e
                retry_count += 1

                if retry_count <= max_retries:
                    logger.warning(f"Error in Gemini API call (attempt {retry_count}/{max_retries}): {e}. "
                                   f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Error in create_message after {max_retries} retries: {e}")
                    raise Exception("Failed to generate message using Gemini API.") from e

    async def create_chat_completion(self, system_prompt: str, prompt: str,
                                     workflow: str = "chat_completion",
                                     related_pitch_gen_id: Optional[int] = None,
                                     related_campaign_id: Optional[uuid.UUID] = None, related_media_id: Optional[int] = None,
                                     max_retries: int = 3, initial_retry_delay: int = 2) -> str:
        """
        Create a chat completion using the Gemini API.

        Args:
            system_prompt (str): The system role prompt for guidance.
            prompt (str): The user's main content/query.
            workflow (str): Name of the workflow using this method.
            related_pitch_gen_id (int, optional): ID of the pitch generation for tracking
            related_campaign_id (UUID, optional): ID of the campaign for tracking
            related_media_id (int, optional): ID of the media for tracking
            max_retries (int): Maximum number of retry attempts
            initial_retry_delay (int): Initial delay in seconds before first retry (doubles with each retry)

        Returns:
            str: The response text from Gemini
        """
        combined_prompt = f"System: {system_prompt}\n\nUser: {prompt}"

        return await self.create_message( # Await the async create_message call
            prompt=combined_prompt,
            model="gemini-1.5-pro-latest", # Using a more capable model for chat completion
            workflow=workflow,
            related_pitch_gen_id=related_pitch_gen_id,
            related_campaign_id=related_campaign_id,
            related_media_id=related_media_id,
            max_retries=max_retries,
            initial_retry_delay=initial_retry_delay
        )

    async def get_structured_data(self, prompt: str, output_model: Any, temperature: float = 0.1,
                                  workflow: str = "structured_output",
                                  related_pitch_gen_id: Optional[int] = None,
                                  related_campaign_id: Optional[uuid.UUID] = None, related_media_id: Optional[int] = None,
                                  max_retries: int = 3, initial_retry_delay: int = 2) -> Optional[Any]:
        """
        Generates structured data using Gemini with a Pydantic-like output model.
        This method is designed to be used with models that support structured output (e.g., Gemini 1.5 Flash/Pro).
        """
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain.output_parsers.pydantic import PydanticOutputParser
        from langchain.prompts import PromptTemplate

        parser = PydanticOutputParser(pydantic_object=output_model)
        format_instructions = parser.get_format_instructions()

        full_prompt_template = PromptTemplate(
            template="""{prompt_instructions}\n\n{format_instructions}\n\nUser query: {user_query}""",
            input_variables=["prompt_instructions", "format_instructions", "user_query"]
        )

        full_prompt = full_prompt_template.format(
            prompt_instructions=prompt,
            format_instructions=format_instructions,
            user_query="" # The main prompt is the instruction, no separate user query here
        )

        retry_count = 0
        retry_delay = initial_retry_delay
        last_exception = None

        while retry_count <= max_retries:
            try:
                start_time = time.time()

                # Re-initialize LLM for structured output if needed, or ensure it's configured for it
                llm_for_structured_output = ChatGoogleGenerativeAI(
                    model="gemini-1.5-flash-001", # Or a more capable model if needed for complex parsing
                    google_api_key=GEMINI_API_KEY,
                    temperature=temperature,
                    max_output_tokens=2048 # Ensure enough tokens for structured output
                )

                chain = (
                    full_prompt_template.partial(prompt_instructions=prompt, format_instructions=format_instructions)
                    | llm_for_structured_output.with_structured_output(output_model)
                )

                # Use asyncio.to_thread for synchronous LangChain call
                response_obj = await asyncio.to_thread(chain.invoke, {"user_query": ""})

                execution_time = time.time() - start_time

                # Estimate tokens for logging
                tokens_in = len(full_prompt) // 4
                tokens_out = len(response_obj.model_dump_json()) // 4

                await ai_tracker.log_usage(
                    workflow=workflow,
                    model=llm_for_structured_output.model_name,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    execution_time=execution_time,
                    endpoint="gemini.structured_output",
                    related_pitch_gen_id=related_pitch_gen_id,
                    related_campaign_id=related_campaign_id,
                    related_media_id=related_media_id
                )

                return response_obj

            except Exception as e:
                last_exception = e
                retry_count += 1

                if retry_count <= max_retries:
                    logger.warning(f"Error in Gemini structured output API call (attempt {retry_count}/{max_retries}): {e}. "
                                   f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Error in get_structured_data after {max_retries} retries: {e}")
                    raise Exception("Failed to get structured data using Gemini API.") from e