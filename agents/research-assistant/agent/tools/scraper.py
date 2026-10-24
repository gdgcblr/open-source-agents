"""Enterprise web scraping and text extraction tool with retry logic and sanitization."""

import logging
import re
import time
from typing import Any, Dict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
DEFAULT_TIMEOUT = 10
MAX_RETRIES = 2
BACKOFF_FACTOR = 0.5


def _is_valid_url(url: str) -> bool:
    """Validates URL structure and scheme."""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def scrape_webpage(url: str, max_chars: int = 4000, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Fetches a webpage, strips markup/scripts, and extracts readable text.
    Implements exponential backoff retry on transient network failures.

    Args:
        url: The web URL to fetch and parse.
        max_chars: Maximum characters of text content to extract.
        timeout: HTTP request timeout in seconds.

    Returns:
        Dictionary containing url, title, status, and clean text content.
    """
    clean_url = str(url).strip() if url else ""
    logger.info(f"Scraping webpage: {clean_url} (max_chars={max_chars})")

    if not _is_valid_url(clean_url):
        return {
            "status": "error",
            "url": clean_url,
            "title": "",
            "content": f"Invalid URL provided: '{clean_url}'. Must be a valid http:// or https:// URL."
        }

    html_content = None
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            import requests
            headers = {"User-Agent": USER_AGENT}
            response = requests.get(clean_url, headers=headers, timeout=timeout)
            response.raise_for_status()
            html_content = response.text
            break
        except ImportError:
            import urllib.request
            try:
                req = urllib.request.Request(clean_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    html_content = resp.read().decode("utf-8", errors="ignore")
                break
            except Exception as e:
                last_error = e
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                sleep_sec = BACKOFF_FACTOR * (2 ** attempt)
                logger.warning(f"Transient error fetching {clean_url}: {e}. Retrying in {sleep_sec:.1f}s...")
                time.sleep(sleep_sec)

    if html_content is None:
        logger.error(f"Failed to fetch {clean_url} after {MAX_RETRIES + 1} attempts: {last_error}")
        return {
            "status": "error",
            "url": clean_url,
            "title": "",
            "content": f"Fetch error after retries: {str(last_error)}"
        }

    title = ""
    clean_text = ""

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")

        # Strip noisy elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg", "iframe"]):
            element.decompose()

        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        text = soup.get_text(separator=" ")
        clean_text = re.sub(r"\s+", " ", text).strip()
    except ImportError:
        title_match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()

        text = re.sub(r"<(script|style).*?</\1>", "", html_content, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        clean_text = re.sub(r"\s+", " ", text).strip()

    if len(clean_text) > max_chars:
        clean_text = clean_text[:max_chars] + f"\n\n[... Truncated to {max_chars} characters for context conservation]"

    return {
        "status": "success",
        "url": clean_url,
        "title": title or "Untitled Web Page",
        "content": clean_text or "No readable text content found on this page.",
        "char_count": len(clean_text)
    }
