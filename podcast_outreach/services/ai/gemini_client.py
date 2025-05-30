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

    async def get_structured_data(self, 
                                  prompt_template_str: str, # Renamed from prompt to reflect it's a template string
                                  user_query: str,          # Added: the actual content to process (e.g., GDoc text)
                                  output_model: Any, 
                                  temperature: float = 0.1,
                                  workflow: str = "structured_output",
                                  related_pitch_gen_id: Optional[int] = None,
                                  related_campaign_id: Optional[uuid.UUID] = None, 
                                  related_media_id: Optional[int] = None,
                                  max_retries: int = 3, 
                                  initial_retry_delay: int = 2) -> Optional[Any]:
        """
        Generates structured data using Gemini with a Pydantic-like output model.
        It now expects a prompt_template_str (which should include placeholders like {user_query} and {format_instructions})
        and a user_query (e.g., the GDoc content).
        """
        from langchain_google_genai import ChatGoogleGenerativeAI
        # Corrected import for PydanticOutputParser based on common Langchain usage
        from langchain_core.output_parsers import PydanticOutputParser 
        from langchain_core.prompts import PromptTemplate # Corrected import path

        parser = PydanticOutputParser(pydantic_object=output_model)
        format_instructions = parser.get_format_instructions()

        # The prompt_template_str IS the template string itself now.
        # It should contain placeholders for {format_instructions} and {user_query} (or whatever variable name you use for the GDoc content).
        # Example prompt_template_str might be:
        # """Please extract information from the following text: {user_query}
        # Comply with these format instructions: {format_instructions}"""
        
        # Assume prompt_template_str contains {user_query} and {format_instructions}
        # If your actual template uses a different placeholder for the GDoc content (e.g., {{gdoc_content}}),
        # you'll need to ensure your PromptTemplate reflects that, e.g. input_variables=["gdoc_content", "format_instructions"]
        # and then pass it in chain.invoke like {"gdoc_content": user_query}
        
        # For current implementation, let's assume the prompt_template_str expects 'user_query' and 'format_instructions'
        # and 'prompt_instructions' is part of the prompt_template_str directly.
        # The key is that the LangChain PromptTemplate needs to be constructed correctly.

        # Let's define input_variables based on what your prompt_template_str actually expects.
        # If your prompts (parse_bio_prompt.txt) use {{gdoc_content}}, then input_variables should reflect that.
        # For example, if prompt_template_str is "Extract from {{gdoc_content}}. Format: {format_instructions}"
        # then input_variables=["gdoc_content", "format_instructions"]
        # and chain.invoke would be chain.invoke({"gdoc_content": user_query})

        # For this adaptation, I will assume the prompt_template_str uses {user_query} and {format_instructions}.
        # If your actual template uses a different name for the content placeholder (like {{gdoc_content}}), 
        # then the `user_query` key in `chain.invoke` and `input_variables` must match that name.

        prompt_template = PromptTemplate(
            template=prompt_template_str, # This is the full template now
            input_variables=["user_query", "format_instructions"], # Assuming these are in your prompt_template_str
            partial_variables={"format_instructions": format_instructions}
        )

        # For logging, the fully formatted prompt before LLM call
        # This requires formatting with the actual user_query as well.
        # formatted_llm_prompt_for_logging = prompt_template.format(user_query=user_query) 
        # For a simpler token count, we can use the template + user_query length.
        approx_input_for_logging = prompt_template_str + user_query + format_instructions

        retry_count = 0
        retry_delay = initial_retry_delay
        last_exception = None

        while retry_count <= max_retries:
            try:
                start_time = time.time()

                llm_for_structured_output = ChatGoogleGenerativeAI(
                    model="gemini-1.5-flash-001", 
                    google_api_key=GEMINI_API_KEY,
                    temperature=temperature,
                    max_output_tokens=2048 
                )
                
                # The chain now correctly uses the PromptTemplate which has format_instructions partially filled.
                # It expects `user_query` to be provided during invoke.
                chain = prompt_template | llm_for_structured_output.with_structured_output(output_model)
                
                response_obj = await asyncio.to_thread(chain.invoke, {"user_query": user_query})

                execution_time = time.time() - start_time
                tokens_in = len(approx_input_for_logging) // 4 
                tokens_out = len(response_obj.model_dump_json()) // 4

                await ai_tracker.log_usage(
                    workflow=workflow,
                    model=llm_for_structured_output.model_name,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    execution_time=execution_time,
                    endpoint="gemini.structured_output_v2", # Updated endpoint name
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