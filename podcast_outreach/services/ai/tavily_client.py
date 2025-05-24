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
    try:
        response = await asyncio.to_thread(_client.search, **kwargs)
        return response
    except Exception as e:  # pragma: no cover - runtime errors
        logger.error("Tavily search failed: %s", e)
        return None
