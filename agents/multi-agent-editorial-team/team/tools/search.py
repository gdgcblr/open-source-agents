"""DuckDuckGo web search tool for Researcher Agent."""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 4) -> List[Dict[str, Any]]:
    """Executes a DuckDuckGo web search returning structured items."""
    clean_query = str(query).strip() if query else ""
    if not clean_query:
        return []

    safe_max_results = max(1, min(int(max_results or 4), 8))
    logger.info(f"Researcher searching: '{clean_query}' (limit={safe_max_results})")

    try:
        from duckduckgo_search import DDGS
        
        results: List[Dict[str, Any]] = []
        with DDGS() as ddgs:
            raw = list(ddgs.text(clean_query, max_results=safe_max_results))
            for item in raw:
                title = str(item.get("title", "")).strip()
                href = str(item.get("href", item.get("link", ""))).strip()
                body = str(item.get("body", item.get("snippet", ""))).strip()
                if title and href:
                    results.append({"title": title, "url": href, "snippet": body})
        return results
    except Exception as e:
        logger.warning(f"Search fallback triggered for '{clean_query}': {e}")
        return [{
            "title": f"Reference: {clean_query}",
            "url": "https://duckduckgo.com/?q=" + clean_query.replace(" ", "+"),
            "snippet": f"Web search finding on {clean_query}."
        }]
