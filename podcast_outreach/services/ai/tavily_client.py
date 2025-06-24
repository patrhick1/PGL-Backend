"""Async Tavily search client."""

import os
import asyncio
import logging
from typing import Dict, Any, Optional

from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
_client: Optional[TavilyClient] = None
if _TAVILY_API_KEY:
    try:
        _client = TavilyClient(api_key=_TAVILY_API_KEY)
        logger.info("TavilyClient initialized")
    except Exception as e:  # pragma: no cover - initialization errors
        logger.error("Failed to initialize TavilyClient: %s", e)
else:
    logger.warning("TAVILY_API_KEY not set; Tavily search disabled")

async def async_tavily_search(
    query: str,
    max_results: int = 3,
    search_depth: str = "advanced",
    include_answer: bool = False,
    include_raw_content: bool = False,
    include_images: bool = False,
) -> Optional[Dict[str, Any]]:
    """Perform an asynchronous Tavily search using TavilyClient."""
    if not _client:
        logger.error("TavilyClient not initialized")
        return None

    kwargs = {
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_answer": include_answer,
        "include_raw_content": include_raw_content,
        "include_images": include_images,
    }
    max_retries = 3
    base_delay = 2  # Start with 2 seconds
    
    for attempt in range(max_retries + 1):
        try:
            response = await asyncio.to_thread(_client.search, **kwargs)
            return response
        except Exception as e:  # pragma: no cover - runtime errors
            error_str = str(e).lower()
            
            # Check if it's a rate limiting error
            if "rate" in error_str or "blocked" in error_str or "excessive" in error_str:
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Tavily rate limited. Waiting {delay}s before retry {attempt + 1}/{max_retries}")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Tavily search failed after {max_retries} retries due to rate limiting: {e}")
            else:
                logger.error(f"Tavily search failed: {e}")
            
            return None
