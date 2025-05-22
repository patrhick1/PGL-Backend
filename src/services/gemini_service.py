import os
import logging
import json
# import google.generativeai as genai # Replaced by LangChain
# from google.generativeai.types import Tool, GenerateContentResponse, GenerationConfig, Content, Part # Problematic imports
# from google.generativeai.types import HarmCategory, HarmBlockThreshold # HarmCategory and HarmBlockThreshold might be needed for Langchain config
# from google.ai.generativelanguage import Candidate # Replaced by LangChain's response handling

# LangChain imports
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage # For constructing prompts and handling responses
# from langchain_core.pydantic_v1 import BaseModel as LangchainBaseModel # No longer using the v1 shim directly here
from langchain_core.output_parsers import PydanticOutputParser # This might still be useful depending on how with_structured_output works
from langchain_core.exceptions import OutputParserException

from dotenv import load_dotenv
from typing import Optional, List, Dict, Type, TypeVar, Any
from pydantic import BaseModel, ValidationError, HttpUrl # Using pydantic.BaseModel directly
import asyncio

# Configure logging
logger = logging.getLogger(__name__)
# BasicConfig should ideally be in the main entry point of the application, not in a library module.
# Assuming it's set up elsewhere, or if this script is run directly, it will apply.
# logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), 
#                     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Constants
DEFAULT_MODEL_ID = "gemini-1.5-flash-latest" # Changed back from gemini-2.0-flash as per original user file

# Define a TypeVar for Pydantic models
T = TypeVar("T", bound=BaseModel) # Now bound to pydantic.BaseModel

# Safety settings might need to be passed to ChatGoogleGenerativeAI if supported, or are default
# from google.generativeai.types import HarmCategory, HarmBlockThreshold # Keep for safety settings if needed
# DEFAULT_SAFETY_SETTINGS = {
#     HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
#     HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
#     HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
#     HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
# }
# Langchain's ChatGoogleGenerativeAI handles safety settings by default.
# Specific configurations can be passed if necessary, consult LangChain documentation.

class GeminiService:
    """Service for interacting with the Google Gemini API using LangChain."""

    def __init__(self, api_key: Optional[str] = None, model_id: str = DEFAULT_MODEL_ID):
        """Initializes the LangChain Gemini client.

        Args:
            api_key: The Google API key. If None, attempts to load from GOOGLE_API_KEY or GEMINI_API_KEY env vars.
            model_id: The Gemini model ID to use.
        """
        effective_api_key = api_key
        if not effective_api_key:
            effective_api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

        if not effective_api_key:
            logger.error("Gemini API key not found. Please set GOOGLE_API_KEY or GEMINI_API_KEY.")
            raise ValueError("Gemini API key not provided and not found in environment variables.")
        
        # genai.configure(api_key=self.api_key) # Not needed for Langchain client
        self.model_id = model_id
        
        try:
            # Initialize LangChain ChatGoogleGenerativeAI client
            self.llm = ChatGoogleGenerativeAI(
                model=self.model_id,
                google_api_key=effective_api_key,
                temperature=0.1, # Default, can be overridden per call
                convert_system_message_to_human=True # Recommended for some Gemini models
            )
            logger.info(f"GeminiService (LangChain) initialized successfully with model: {self.model_id}")
        except Exception as e:
            logger.error(f"Failed to initialize LangChain ChatGoogleGenerativeAI '{self.model_id}': {e}", exc_info=True)
            raise
    
    def _parse_text_from_lc_response(self, response: AIMessage) -> Optional[str]:
        """Safely extracts text from a LangChain AIMessage."""
        if not isinstance(response, AIMessage):
            logger.warning(f"Expected AIMessage, got {type(response)}. Cannot extract text.")
            return None
        
        if isinstance(response.content, str):
            return response.content
        elif isinstance(response.content, list) and response.content:
            first_part = response.content[0]
            if isinstance(first_part, str):
                 return first_part 
            if isinstance(first_part, dict) and "text" in first_part:
                return first_part["text"]
        
        logger.warning("No straightforward text content found in LangChain AIMessage.")
        logger.debug(f"Full LangChain AIMessage for no-text case: {response}")
        return None

    async def query_text_with_google_search(self, query: str) -> Optional[str]:
        """Queries Gemini (via LangChain) and returns the text response.
        Google Search grounding is often an inherent capability of models like Gemini via LangChain,
        especially when it infers the need from the query, or it can be enabled via tools.
        For simplicity, we assume the model uses search if appropriate.

        Args:
            query: The user's query string.

        Returns:
            The main text response from the model, or None if an error occurs.
        """
        logger.info(f"Sending text query to LangChain Gemini ({self.model_id}): '{query[:100]}...'")
        try:
            # For simple text queries, Google Search might be used by the model if it's a "connect" model
            # or if the query implies it. Explicit tool usage might be needed for more control.
            # For ChatGoogleGenerativeAI, search is often enabled by default for capable models.
            response = await self.llm.ainvoke(query) # Use ainvoke for async
            return self._parse_text_from_lc_response(response)
        except Exception as e:
            logger.error(f"Error during LangChain Gemini call for text query: {e}", exc_info=True)
            return None

    async def query_with_grounding_details(self, query: str) -> Dict[str, Any]:
        """Queries Gemini with Google Search grounding (if available and used by model)
        and returns text and potentially other metadata.
        Retrieving explicit grounding chunks like in the previous version is more complex
        with LangChain's base ChatGoogleGenerativeAI and might require custom parsing of
        `response.response_metadata` or specific tool configurations not covered here.
        This version will focus on the text response.

        Args:
            query: The user's query string.

        Returns:
            A dictionary with 'text_response'. 'web_queries' and 'grounding_chunks' are
            not reliably available through this simplified Langchain interface.
        """
        response_payload = {
            "text_response": None,
            "web_queries": [], # Not directly available in this simplified setup
            "grounding_chunks": [] # Not directly available
        }
        logger.info(f"Sending query for (potential) grounding details to LangChain Gemini ({self.model_id}): '{query[:100]}...'")
        try:
            response = await self.llm.ainvoke(query)
            response_payload["text_response"] = self._parse_text_from_lc_response(response)
            
            # Extracting detailed grounding metadata like web_search_queries or grounding_chunks
            # from response.response_metadata would require knowing the specific structure
            # provided by ChatGoogleGenerativeAI, which can vary.
            # Example: if 'usage_metadata' in response.response_metadata:
            #    metadata = response.response_metadata['usage_metadata'] # or similar key
            #    if metadata and 'web_search_queries' in metadata: ...

            return response_payload
        except Exception as e:
            logger.error(f"Error during LangChain Gemini call for grounding details: {e}", exc_info=True)
            return response_payload

    async def get_structured_data(
        self,
        prompt: str,
        output_model: Type[T], # T is TypeVar("T", bound=BaseModel from pydantic)
        temperature: Optional[float] = 0.1
    ) -> Optional[T]:
        """Queries Gemini using LangChain for structured output (Pydantic v2 compatible).

        Args:
            prompt: The full prompt to send to Gemini.
            output_model: The Pydantic model class (inheriting from pydantic.BaseModel)
                          to validate and parse the JSON into.
            temperature: The generation temperature.

        Returns:
            An instance of the Pydantic model if successful, None otherwise.
        """
        if not issubclass(output_model, BaseModel): # Check against pydantic.BaseModel
             raise TypeError(f"Output model {output_model.__name__} must inherit from pydantic.BaseModel.")

        logger.info(f"Sending structured data query to LangChain Gemini ({self.model_id}) for {output_model.__name__}. Temp: {temperature}")
        logger.debug(f"Structured data prompt (first 200 chars): {prompt[:200]}...")
        
        try:
            # Create an LLM instance with the desired temperature for this specific call
            # .with_structured_output takes the Pydantic model directly (v2)
            structured_llm = self.llm.with_config({"temperature": temperature}) \
                                     .with_structured_output(output_model)
            
            ai_response = await structured_llm.ainvoke(prompt)

            if isinstance(ai_response, output_model):
                logger.info(f"Successfully received and parsed structured response as {output_model.__name__}.")
                return ai_response
            else:
                # This case should ideally be handled by LangChain's .with_structured_output
                logger.error(f"Structured output call did not return the expected Pydantic model type ({output_model.__name__}). Got type: {type(ai_response)}. Response: {ai_response}")
                # Attempt manual validation if the response is a dict (less likely if .with_structured_output is used correctly)
                if isinstance(ai_response, dict):
                    try:
                        validated_response = output_model(**ai_response)
                        logger.warning("Manual Pydantic validation succeeded after structured output type mismatch.")
                        return validated_response
                    except (ValidationError, TypeError) as manual_exc:
                        logger.error(f"Manual Pydantic validation also failed: {manual_exc}")
                        return None
                return None

        except ValidationError as ve: # This might catch errors if the LLM returns JSON that *almost* matches
            logger.error(f"Pydantic validation failed processing Gemini output for model {output_model.__name__}. Error: {ve}. Prompt: '{prompt[:50]}...'")
            return None
        except OutputParserException as ope: # Langchain's specific parsing error
            logger.error(f"LangChain OutputParserException for {output_model.__name__}: {ope}")
            logger.debug(f"Prompt causing OutputParserException: {prompt[:200]}...")
            return None
        except Exception as e:
            logger.error(f"Error getting structured output ({output_model.__name__}) from LangChain Gemini: {e}", exc_info=True)
            return None

# Example Usage (for direct testing of this service module)
# Note: Pydantic models used for structured output here should inherit from pydantic.BaseModel
if __name__ == "__main__":
    # Ensure logging is configured for standalone run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')

    # Define a simple Pydantic model for testing structured output
    # Inherits from pydantic.BaseModel
    class TestSocials(BaseModel): 
        twitter_url: Optional[HttpUrl] = None
        website: Optional[HttpUrl] = None
        company_name: Optional[str] = None

    async def run_tests():
        print("--- Testing Gemini Service (LangChain Pydantic v2 alignment) ---")
        try:
            # Ensure GOOGLE_API_KEY or GEMINI_API_KEY is in your .env file or environment
            gemini_service = GeminiService() 
        except ValueError as e:
            print(f"Failed to initialize GeminiService: {e}")
            return
        except Exception as e_init:
            print(f"An unexpected error occurred during GeminiService initialization: {e_init}")
            return


        # Test 1: Simple text query
        print("\n--- Test 1: Text Query ---")
        text_query = "What is the main website for OpenAI?"
        text_response = await gemini_service.query_text_with_google_search(text_query)
        print(f"Query: {text_query}")
        print(f"Response: {text_response}")

        # Test 2: Query with "grounding details" (simplified)
        print("\n--- Test 2: Query with (Simplified) Grounding Details ---")
        grounding_query = "Latest news about Google Gemini model capabilities."
        grounding_response_payload = await gemini_service.query_with_grounding_details(grounding_query)
        print(f"Query: {grounding_query}")
        print(f"Text Response: {grounding_response_payload.get('text_response')}")
        # Web queries and grounding chunks are not populated by this simplified method

        # Test 3: Structured data query
        print("\n--- Test 3: Structured Data Query ---")
        # The prompt should guide the LLM to fill the fields of TestSocials
        structured_prompt = f"""Please find the official Twitter URL and website for the company 'Tavily'.
        Also, provide their company name.
        Respond with a JSON object that ONLY contains these fields: 'twitter_url', 'website', 'company_name'.
        """
        # It's crucial that TestSocials (the output_model) is a pydantic.BaseModel
        structured_data = await gemini_service.get_structured_data(
            structured_prompt, 
            TestSocials, # TestSocials now inherits from pydantic.BaseModel
            temperature=0.2 
        )
        if structured_data:
            print(f"Structured Data Parsed ({type(structured_data)}):")
            print(f"  Company Name: {structured_data.company_name}")
            print(f"  Twitter: {structured_data.twitter_url}")
            print(f"  Website: {structured_data.website}")
        else:
            print("Failed to get structured data or parse it.")
        
        # Test 4: Structured data query for potentially non-existent information
        print("\n--- Test 4: Structured Data Query (Potentially Missing Info) ---")
        structured_prompt_missing = f"""Find the official Twitter and Website for a fictional company 'NonExistentCorp123XYZ'.
        Also, provide their company name if known.
        Respond with a JSON object that ONLY contains these fields: 'twitter_url', 'website', 'company_name'.
        Use null for fields if information is not found."""
        structured_data_missing = await gemini_service.get_structured_data(
            structured_prompt_missing, 
            TestSocials,
            temperature=0.1
        )
        if structured_data_missing:
            print(f"Structured Data Parsed ({type(structured_data_missing)}):")
            print(f"  Company Name: {structured_data_missing.company_name}") 
            print(f"  Twitter: {structured_data_missing.twitter_url}") 
            print(f"  Website: {structured_data_missing.website}") 
        else:
            print("Failed to get structured data or parse it for missing info test.")

    asyncio.run(run_tests())
    print("\n--- Gemini Service (LangChain Pydantic v2 alignment) Test Script Finished ---") 