import os
import logging
import json
import google.generativeai as genai
from google.generativeai.types import Tool, GenerateContentResponse, GenerationConfig, Content, Part
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.ai.generativelanguage import Candidate

from dotenv import load_dotenv
from typing import Optional, List, Dict, Type, TypeVar, Any
from pydantic import BaseModel, ValidationError

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()

# Constants
DEFAULT_MODEL_ID = "gemini-1.5-flash-latest" # Use a generally available model

# Define a TypeVar for Pydantic models
T = TypeVar("T", bound=BaseModel)

# Safety settings to be less restrictive for general queries but still block harmful content
# Adjust these as needed based on observed behavior and requirements.
DEFAULT_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

class GeminiService:
    """Service for interacting with the Google Gemini API."""

    def __init__(self, api_key: Optional[str] = None, model_id: str = DEFAULT_MODEL_ID):
        """Initializes the Gemini client.

        Args:
            api_key: The Google API key. If None, attempts to load from GOOGLE_API_KEY or GEMINI_API_KEY env vars.
            model_id: The Gemini model ID to use.
        """
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

        if not self.api_key:
            logger.error("Gemini API key not found. Please set GOOGLE_API_KEY or GEMINI_API_KEY.")
            raise ValueError("Gemini API key not provided and not found in environment variables.")
        
        genai.configure(api_key=self.api_key)
        self.model_id = model_id
        # Get the model instance. This also validates the model_id to some extent.
        try:
            self.model = genai.GenerativeModel(self.model_id)
            logger.info(f"GeminiService initialized successfully with model: {self.model_id}")
        except Exception as e:
            logger.error(f"Failed to initialize GenerativeModel '{self.model_id}': {e}", exc_info=True)
            raise
    
    def _parse_text_from_response(self, response: GenerateContentResponse) -> Optional[str]:
        """Safely extracts text from a Gemini response."""
        try:
            if response and response.candidates:
                # Check for content policy violations first
                first_candidate = response.candidates[0]
                if first_candidate.finish_reason != Candidate.FinishReason.STOP:
                    logger.warning(f"Gemini response finish_reason indicates potential issue: {first_candidate.finish_reason.name}")
                    # Log safety ratings if available
                    if first_candidate.safety_ratings:
                        for rating in first_candidate.safety_ratings:
                            logger.warning(f"Safety Rating: {rating.category.name} - {rating.probability.name}")
                    if first_candidate.finish_reason == Candidate.FinishReason.SAFETY:
                         return "Error: Content blocked due to safety policies."
                    # For other non-STOP reasons, we might still have partial text or no text.

                if first_candidate.content and first_candidate.content.parts:
                    return first_candidate.content.parts[0].text
            logger.warning("No valid text content found in Gemini response.")
            logger.debug(f"Full Gemini response for no-text case: {response}")
            return None
        except Exception as e:
            logger.error(f"Error parsing text from Gemini response: {e}", exc_info=True)
            logger.debug(f"Gemini response causing parsing error: {response}")
            return None

    async def query_text_with_google_search(self, query: str) -> Optional[str]:
        """Queries Gemini with Google Search grounding and returns only the text response.

        Args:
            query: The user's query string.

        Returns:
            The main text response from the model, or None if an error occurs.
        """
        search_tool = Tool(google_search=genai.types.GoogleSearch()) # Corrected reference
        generation_config = GenerationConfig(tools=[search_tool])
        safety_settings = DEFAULT_SAFETY_SETTINGS

        logger.info(f"Sending text query with Google Search to Gemini ({self.model_id}): '{query[:100]}...'")
        try:
            response = await self.model.generate_content_async(
                query,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            return self._parse_text_from_response(response)
        except Exception as e:
            logger.error(f"Error during Gemini API call for text query: {e}", exc_info=True)
            return None

    async def query_with_grounding_details(self, query: str) -> Dict[str, Any]:
        """Queries Gemini with Google Search grounding and returns text, web queries, and grounding chunks.

        Args:
            query: The user's query string.

        Returns:
            A dictionary with 'text_response', 'web_queries', and 'grounding_chunks'.
            Values will be None or empty lists on error.
        """
        search_tool = Tool(google_search=genai.types.GoogleSearch())
        generation_config = GenerationConfig(tools=[search_tool])
        safety_settings = DEFAULT_SAFETY_SETTINGS
        
        response_payload = {
            "text_response": None,
            "web_queries": [],
            "grounding_chunks": []
        }

        logger.info(f"Sending query for grounding details to Gemini ({self.model_id}): '{query[:100]}...'")
        try:
            response = await self.model.generate_content_async(
                query,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            response_payload["text_response"] = self._parse_text_from_response(response)

            if response and response.candidates and response.candidates[0].grounding_metadata:
                metadata = response.candidates[0].grounding_metadata
                if metadata.web_search_queries:
                    response_payload["web_queries"] = list(metadata.web_search_queries)
                if metadata.grounding_chunks:
                    for chunk in metadata.grounding_chunks:
                        chunk_info = {"type": "Unknown", "title": None, "uri": None, "content": None}
                        if chunk.web:
                            chunk_info["type"] = "Web"
                            chunk_info["title"] = chunk.web.title
                            chunk_info["uri"] = chunk.web.uri
                            # Note: Gemini API typically doesn't return full web content in grounding_chunk directly
                        elif chunk.retrieved_context:
                            chunk_info["type"] = "RetrievedContext"
                            chunk_info["uri"] = chunk.retrieved_context.uri
                            chunk_info["title"] = chunk.retrieved_context.title
                        response_payload["grounding_chunks"].append(chunk_info)
            return response_payload
        except Exception as e:
            logger.error(f"Error during Gemini API call for grounding details: {e}", exc_info=True)
            return response_payload # Return payload with None/empty on error

    async def get_structured_data(
        self, 
        prompt: str, 
        output_model: Type[T],
        use_google_search: bool = True,
        temperature: Optional[float] = 0.1 # Default to low temp for structured output
    ) -> Optional[T]:
        """Queries Gemini and attempts to parse its response into a Pydantic model.

        Args:
            prompt: The full prompt to send to Gemini, including instructions for JSON output.
            output_model: The Pydantic model class to validate and parse the JSON into.
            use_google_search: Whether to enable Google Search grounding for this query.
            temperature: The generation temperature.

        Returns:
            An instance of the Pydantic model if successful, None otherwise.
        """
        tools = [Tool(google_search=genai.types.GoogleSearch())] if use_google_search else None
        # Forcing JSON output mode if available with the model
        generation_config = GenerationConfig(
            tools=tools,
            temperature=temperature,
            response_mime_type="application/json" # Request JSON output
        )
        safety_settings = DEFAULT_SAFETY_SETTINGS

        logger.info(f"Sending structured data query to Gemini ({self.model_id}) for {output_model.__name__}. Search: {use_google_search}, Temp: {temperature}")
        logger.debug(f"Structured data prompt (first 200 chars): {prompt[:200]}...")
        try:
            # Construct the Content object correctly
            # The prompt itself is the text part
            content_parts = [Part.from_text(prompt)]
            gemini_content = Content(parts=content_parts, role="user")

            response = await self.model.generate_content_async(
                gemini_content, # Pass the Content object
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            json_text_response = self._parse_text_from_response(response)
            if not json_text_response:
                logger.warning(f"Gemini returned no text for structured data for {output_model.__name__}.")
                return None
            
            if json_text_response.startswith("Error: Content blocked due to safety policies."):
                logger.error(f"Gemini content safety block for structured data query ({output_model.__name__}): {json_text_response}")
                return None
            
            # The response should be a JSON string if response_mime_type="application/json" worked.
            # Clean the response if it's wrapped in markdown triple backticks for JSON
            cleaned_json_text = json_text_response.strip()
            if cleaned_json_text.startswith("```json"):
                cleaned_json_text = cleaned_json_text[7:] # Remove ```json
            elif cleaned_json_text.startswith("```"):
                 cleaned_json_text = cleaned_json_text[3:] # Remove ```
            
            if cleaned_json_text.endswith("```"):
                cleaned_json_text = cleaned_json_text[:-3] # Remove ```
            cleaned_json_text = cleaned_json_text.strip()

            try:
                data = json.loads(cleaned_json_text)
                return output_model(**data)
            except json.JSONDecodeError as jde:
                logger.error(f"JSONDecodeError parsing Gemini response for {output_model.__name__}: {jde}")
                logger.debug(f"Invalid JSON string from Gemini: {cleaned_json_text}")
                return None
            except ValidationError as ve:
                logger.error(f"Pydantic ValidationError for {output_model.__name__}: {ve}")
                logger.debug(f"Data causing Pydantic error: {cleaned_json_text}")
                return None

        except Exception as e:
            logger.error(f"Error during Gemini API call for structured data ({output_model.__name__}): {e}", exc_info=True)
            return None

# Example Usage (for direct testing of this service module)
if __name__ == "__main__":
    from pydantic import HttpUrl # For example model

    # Define a simple Pydantic model for testing structured output
    class TestSocials(BaseModel):
        twitter_url: Optional[HttpUrl] = None
        website: Optional[HttpUrl] = None
        company_name: Optional[str] = None

    async def run_tests():
        print("--- Testing Gemini Service ---")
        try:
            gemini_service = GeminiService() # Uses default model_id
        except ValueError as e:
            print(f"Failed to initialize GeminiService: {e}")
            return

        # Test 1: Simple text query with Google Search
        print("\n--- Test 1: Text Query with Google Search ---")
        text_query = "What is the main website for OpenAI?"
        text_response = await gemini_service.query_text_with_google_search(text_query)
        print(f"Query: {text_query}")
        print(f"Response: {text_response}")

        # Test 2: Query with grounding details
        print("\n--- Test 2: Query with Grounding Details ---")
        grounding_query = "Latest news about Google Gemini model capabilities."
        grounding_response = await gemini_service.query_with_grounding_details(grounding_query)
        print(f"Query: {grounding_query}")
        print(f"Text Response: {grounding_response.get('text_response')}")
        print(f"Web Queries: {grounding_response.get('web_queries')}")
        # print(f"Grounding Chunks: {json.dumps(grounding_response.get('grounding_chunks'), indent=2)}")

        # Test 3: Structured data query
        print("\n--- Test 3: Structured Data Query ---")
        structured_prompt = f"""Please find the official Twitter URL and website for the company 'Tavily'.
        Return the information as a JSON object matching this schema: 
        {json.dumps(TestSocials.model_json_schema(), indent=2)}
        """
        structured_data = await gemini_service.get_structured_data(structured_prompt, TestSocials)
        if structured_data:
            print(f"Structured Data Parsed ({type(structured_data)}):")
            print(f"  Company Name: {structured_data.company_name}")
            print(f"  Twitter: {structured_data.twitter_url}")
            print(f"  Website: {structured_data.website}")
        else:
            print("Failed to get structured data or parse it.")
        
        # Test 4: Structured data query for potentially non-existent information (should return nulls)
        print("\n--- Test 4: Structured Data Query (Potentially Missing Info) ---")
        structured_prompt_missing = f"""Find the official Twitter and Website for a fictional company 'NonExistentCorp123XYZ'.
        Return the information as a JSON object matching this schema: 
        {json.dumps(TestSocials.model_json_schema(), indent=2)}
        Use null for fields if information is not found."""
        structured_data_missing = await gemini_service.get_structured_data(structured_prompt_missing, TestSocials)
        if structured_data_missing:
            print(f"Structured Data Parsed ({type(structured_data_missing)}):")
            print(f"  Company Name: {structured_data_missing.company_name}") # Expect None or what Gemini makes up
            print(f"  Twitter: {structured_data_missing.twitter_url}") # Expect None
            print(f"  Website: {structured_data_missing.website}") # Expect None
        else:
            print("Failed to get structured data or parse it for missing info test.")

    asyncio.run(run_tests())
    print("\n--- Gemini Service Test Script Finished ---") 