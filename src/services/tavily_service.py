import os
import asyncio
import logging
from tavily import TavilyClient # Import the direct TavilyClient
from dotenv import load_dotenv
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)
# Basic config, assuming main application might set up more advanced logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Load environment variables from .env file
load_dotenv()

# Initialize the TavilyClient at module level
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
_tavily_client: Optional[TavilyClient] = None

if not TAVILY_API_KEY:
    logger.warning("TAVILY_API_KEY not found in environment variables. Tavily search will not be available.")
else:
    try:
        _tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
        logger.info("TavilyClient initialized successfully for tavily_service.")
    except Exception as e:
        logger.error(f"Failed to initialize TavilyClient in tavily_service: {e}")

async def async_tavily_search(
    query: str, 
    max_results: int = 3, 
    search_depth: str = "advanced", # "basic" or "advanced"
    include_answer: bool = False,
    include_raw_content: bool = False, # Whether to include raw content of websites
    include_images: bool = False # Whether to include image search results
) -> Optional[Dict[str, Any]]:
    """Async wrapper for Tavily search using the direct TavilyClient.

    Args:
        query: The search query.
        max_results: The maximum number of results to return.
        search_depth: The depth of the search ("basic" or "advanced").
        include_answer: Whether to include an LLM-generated answer based on the search results.
        include_raw_content: Whether to include raw content of scraped websites in results.
        include_images: Whether to include image search results.

    Returns:
        A dictionary containing the Tavily search response or None on error or if client not initialized.
    """
    if not _tavily_client:
        logger.error("TavilyClient is not initialized in tavily_service. Cannot perform search.")
        return None
        
    try:
        logger.info(
            f"Performing Tavily search: '{query[:50]}...' "
            f"(max_results={max_results}, depth={search_depth}, answer={include_answer}, raw_content={include_raw_content}, images={include_images})"
        )

        search_kwargs = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": include_answer,
            "include_raw_content": include_raw_content,
            "include_images": include_images
        }
        
        # The TavilyClient.search method is synchronous,
        # so run it in a thread pool to make it non-blocking for asyncio.
        response_data = await asyncio.to_thread(
            _tavily_client.search,
            **search_kwargs
        )
        
        answer_available = bool(response_data.get('answer'))
        results_count = len(response_data.get('results', []))
        images_count = len(response_data.get('images', []))
        logger.info(f"Tavily search returned. Answer: {answer_available}, Results: {results_count}, Images: {images_count}")
        return response_data
    except Exception as e:
        logger.error(f"Tavily search failed for query '{query}': {e}", exc_info=True)
        return None

# Example Usage (for direct testing of this service module)
if __name__ == "__main__":
    async def run_test():
        print("--- Testing Tavily Search Service --- ")
        if not TAVILY_API_KEY:
            print("TAVILY_API_KEY is not set. Please set it in your .env file to run the test.")
            return

        test_queries = [
            {"query": "Latest advancements in AI for 2024", "include_answer": True, "max_results": 2},
            {"query": "Who won the last F1 race?", "search_depth": "basic", "max_results": 1},
            {"query": "Images of golden retrievers", "include_images": True, "max_results": 3}
        ]

        for i, params in enumerate(test_queries):
            print(f"\n--- Test Query {i+1} --- ")
            print(f"Parameters: {params}")
            response = await async_tavily_search(**params)

            if response:
                print(f"Full Response (first 200 chars): {str(response)[:200]}...")
                if response.get("answer"):
                    print(f"  Answer: {response['answer']}")
                
                results = response.get("results", [])
                print(f"  Found {len(results)} web result snippets:")
                for res_idx, result in enumerate(results):
                    print(f"    Result {res_idx+1}: {result.get('title')} ({result.get('url')})")
                
                images = response.get("images", [])
                if images:
                    print(f"  Found {len(images)} image results:")
                    for img_idx, img in enumerate(images):
                        print(f"    Image {img_idx+1}: {img.get('url')}") 
            else:
                print("  No results found or an error occurred.")

    asyncio.run(run_test())
    print("\n--- Tavily Search Service Test Script Finished ---") 