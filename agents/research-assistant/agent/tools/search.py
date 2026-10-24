"""Enterprise DuckDuckGo web search tool with error handling and sanitization."""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Performs a web search using DuckDuckGo and returns structured results.

    Args:
        query: The search keywords or question.
        max_results: The maximum number of search results to return (capped between 1 and 10).

    Returns:
        A list of dictionaries with 'title', 'href', and 'body' keys.
    """
    clean_query = str(query).strip() if query else ""
    if not clean_query:
        logger.warning("Empty search query provided.")
        return []

    safe_max_results = max(1, min(int(max_results or 5), 10))
    logger.info(f"Searching web for query: '{clean_query}' (max_results={safe_max_results})")

    try:
        from duckduckgo_search import DDGS
        
        results: List[Dict[str, Any]] = []
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(clean_query, max_results=safe_max_results))
            for item in raw_results:
                title = str(item.get("title", "")).strip()
                href = str(item.get("href", item.get("link", ""))).strip()
                body = str(item.get("body", item.get("snippet", ""))).strip()
                if href and title:
                    results.append({
                        "title": title,
                        "href": href,
                        "body": body,
                    })
        return results
    except ImportError:
        logger.warning("duckduckgo_search package not installed. Returning fallback indicator.")
        return [{
            "title": f"Search result for: {clean_query}",
            "href": "https://duckduckgo.com/?q=" + clean_query.replace(" ", "+"),
            "body": f"duckduckgo_search is not installed. To enable live web search, run `pip install duckduckgo-search`."
        }]
    except Exception as e:
        logger.error(f"Search failed for query '{clean_query}': {e}")
        return [{
            "title": f"Search fallback for: {clean_query}",
            "href": "https://duckduckgo.com/?q=" + clean_query.replace(" ", "+"),
            "body": f"Notice: Live search encountered an upstream error ({str(e)}). Proceeding with domain knowledge."
        }]
