# podcast_outreach/services/ai/gemini_client.py

import os
import time
import logging
import asyncio # Added for async operations
# import functools # No longer explicitly needed with asyncio.to_thread if other changes are made
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import google.generativeai as genai
import uuid

# Import enums for safety settings
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Import our AI usage tracker from its new location
from podcast_outreach.services.ai.tracker import tracker as ai_tracker
from podcast_outreach.logging_config import get_logger # Use new logging config

# Load environment variables
load_dotenv()

# Fetch API Key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Set up logging
logger = get_logger(__name__)

class GeminiService:
    DEFAULT_SAFETY_SETTINGS = [
        {
            "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
            "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        },
        {
            "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        },
        {
            "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        },
        {
            "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        },
    ]

    def __init__(self):
        if not GEMINI_API_KEY:
            logger.error("GEMINI_API_KEY environment variable not set.")
            raise ValueError("Please set the GEMINI_API_KEY environment variable.")
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            logger.info("GeminiService initialized successfully.") # Simplified log message
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise

    async def create_message(self, prompt: str, model: str = 'gemini-2.0-flash',
                             workflow: str = "unknown", related_pitch_gen_id: Optional[int] = None,
                             related_campaign_id: Optional[uuid.UUID] = None, related_media_id: Optional[int] = None,
                             max_retries: int = 3, initial_retry_delay: int = 2) -> str:
        retry_count = 0
        retry_delay = initial_retry_delay
        last_exception = None
        response_obj = None # To store response object for logging in case of error

        while retry_count <= max_retries:
            try:
                start_time = time.time()

                generation_config = {
                    "temperature": 0.01,
                    "top_p": 0.1,
                    "top_k": 1,
                    "max_output_tokens": 10000, # Consider if this should be higher for some tasks
                }

                model_instance = genai.GenerativeModel(
                    model_name=model,
                    generation_config=generation_config,
                    safety_settings=self.DEFAULT_SAFETY_SETTINGS # Apply safety settings
                )
                
                # Assuming model_instance.generate_content is blocking and needs to_thread
                response_obj = await asyncio.to_thread(model_instance.generate_content, prompt)

                # Enhanced check for valid content before accessing .text
                if not response_obj.candidates or \
                   not hasattr(response_obj.candidates[0], 'content') or \
                   not response_obj.candidates[0].content.parts:
                    
                    candidate_info = "No candidates in response."
                    if response_obj.candidates: # Check if candidates list is not empty
                        candidate = response_obj.candidates[0]
                        candidate_info = f"Candidate finish_reason: {candidate.finish_reason} ({candidate.finish_reason.name if hasattr(candidate.finish_reason, 'name') else 'Unknown Name'})."
                        if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                            candidate_info += f" Safety ratings: {candidate.safety_ratings}."
                    
                    prompt_feedback_info = ""
                    if hasattr(response_obj, 'prompt_feedback') and response_obj.prompt_feedback:
                         prompt_feedback_info = f" Prompt feedback: {response_obj.prompt_feedback}."

                    error_message = f"Gemini response has no valid content parts. {candidate_info}{prompt_feedback_info}"
                    logger.error(error_message)
                    # Raise a specific error or re-raise if that's better for retry logic
                    # For now, let this be caught by the generic Exception and retried
                    raise ValueError(error_message)

                content_text = response_obj.text # Access .text only after validation

                execution_time = time.time() - start_time
                
                tokens_in = len(prompt) // 4 
                tokens_out = len(content_text) // 4

                await ai_tracker.log_usage(
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
                
                log_suffix = ""
                if response_obj:
                    if hasattr(response_obj, 'prompt_feedback') and response_obj.prompt_feedback:
                        log_suffix += f" PromptFeedback: {response_obj.prompt_feedback}."
                    if response_obj.candidates and len(response_obj.candidates) > 0: # Check if candidates list is not empty
                        candidate = response_obj.candidates[0]
                        if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                            log_suffix += f" SafetyRatings: {candidate.safety_ratings}."
                        if hasattr(candidate, 'finish_reason'):
                             log_suffix += f" FinishReason: {candidate.finish_reason} ({candidate.finish_reason.name if hasattr(candidate.finish_reason, 'name') else 'Unknown Name'})."
                
                retry_count += 1
                if retry_count <= max_retries:
                    logger.warning(f"Error in Gemini API call (attempt {retry_count}/{max_retries}): {e}.{log_suffix} "
                                   f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Error in create_message after {max_retries} retries: {e}.{log_suffix}")
                    # Ensure the original exception 'e' is chained for full context
                    raise Exception(f"Failed to generate message using Gemini API after {max_retries} retries. Last error: {str(e)}{log_suffix}") from e


    async def create_chat_completion(self, system_prompt: str, prompt: str,
                                     workflow: str = "chat_completion",
                                     related_pitch_gen_id: Optional[int] = None,
                                     related_campaign_id: Optional[uuid.UUID] = None, related_media_id: Optional[int] = None,
                                     max_retries: int = 3, initial_retry_delay: int = 2) -> str:
        # The model used here is 'gemini-2.0-flash-exp' which might have different safety defaults/behaviors
        # than 'gemini-2.5-flash-preview-04-17' used in create_message.
        # The advice to add DEFAULT_SAFETY_SETTINGS to create_message's model_instance is key.
        # For create_chat_completion, if it directly constructs its own model or uses a different one,
        # it too would need safety_settings applied if it's not inheriting from create_message's model_instance.
        # The provided code modification shows create_chat_completion calling create_message, so it will inherit.
        
        combined_prompt = f"System: {system_prompt}\n\nUser: {prompt}"
        
        # The model is 'gemini-2.5-flash-preview-04-17' if create_message default is used.
        # The Google AI Studio advice mentioned 'gemini-2.0-flash-exp' for create_chat_completion,
        # this seems to be hardcoded in the AI Studio's suggestion for this method.
        # If we want create_chat_completion to use 'gemini-2.0-flash-exp' and also have the new safety settings,
        # create_message would need to accept model parameter and apply safety settings to it.
        # The current structure of calling create_message means it will use the model passed to it.
        # The provided code from AI studio for create_chat_completion passes 'gemini-2.0-flash-exp'.
        
        return await self.create_message(
            prompt=combined_prompt,
            model='gemini-2.0-flash-exp', # As per AI Studio's suggestion for this specific method
            workflow=workflow,
            related_pitch_gen_id=related_pitch_gen_id,
            related_campaign_id=related_campaign_id,
            related_media_id=related_media_id,
            max_retries=max_retries,
            initial_retry_delay=initial_retry_delay
        )

    async def get_structured_data(self, 
                                  prompt_template_str: str,
                                  user_query: str,
                                  output_model: Any, 
                                  temperature: float = 0.1,
                                  workflow: str = "structured_output",
                                  related_pitch_gen_id: Optional[int] = None,
                                  related_campaign_id: Optional[uuid.UUID] = None, 
                                  related_media_id: Optional[int] = None,
                                  max_retries: int = 3, 
                                  initial_retry_delay: int = 2) -> Optional[Any]:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.output_parsers import PydanticOutputParser 
        from langchain_core.prompts import PromptTemplate

        parser = PydanticOutputParser(pydantic_object=output_model)
        format_instructions = parser.get_format_instructions()
        
        # Assuming the prompt_template_str will have {user_query} and {format_instructions}
        # If your actual template files are different, this PromptTemplate needs to match.
        prompt_template = PromptTemplate(
            template=prompt_template_str, 
            input_variables=["user_query"], # Only user_query is dynamic per call here
            partial_variables={"format_instructions": format_instructions}
        )
        
        approx_input_for_logging = prompt_template_str + user_query + format_instructions

        retry_count = 0
        retry_delay = initial_retry_delay
        last_exception = None

        while retry_count <= max_retries:
            try:
                start_time = time.time()

                # Convert the list of safety settings into the dictionary format LangChain expects
                safety_settings_dict = {
                    item["category"]: item["threshold"] for item in self.DEFAULT_SAFETY_SETTINGS
                }

                llm_for_structured_output = ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    google_api_key=GEMINI_API_KEY,
                    temperature=temperature,
                    max_output_tokens=2048, # Consider if this should be higher
                    safety_settings=safety_settings_dict # <-- Pass the correctly formatted dictionary
                )
                
                chain = prompt_template | llm_for_structured_output.with_structured_output(output_model)
                
                # The input to invoke should match the input_variables of the prompt_template
                response_obj = await asyncio.to_thread(chain.invoke, {"input_text": user_query})

                execution_time = time.time() - start_time
                tokens_in = len(approx_input_for_logging) // 4 
                tokens_out = len(response_obj.model_dump_json()) // 4 # Requires output_model to have model_dump_json

                await ai_tracker.log_usage(
                    workflow=workflow,
                    model=llm_for_structured_output.model, # Use the correct attribute 'model'
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    execution_time=execution_time,
                    endpoint="gemini.structured_output_v2",
                    related_pitch_gen_id=related_pitch_gen_id,
                    related_campaign_id=related_campaign_id,
                    related_media_id=related_media_id
                )
                return response_obj
            except Exception as e:
                last_exception = e
                retry_count += 1
                log_suffix = "" # Placeholder for potential future detailed error info from Langchain
                if retry_count <= max_retries:
                    logger.warning(f"Error in Gemini structured output API call (attempt {retry_count}/{max_retries}): {e}.{log_suffix} "
                                   f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Error in get_structured_data after {max_retries} retries: {e}.{log_suffix}")
                    raise Exception("Failed to get structured data using Gemini API after {max_retries} retries.") from e