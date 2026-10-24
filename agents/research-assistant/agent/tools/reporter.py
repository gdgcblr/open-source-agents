"""Enterprise report exporter tool with path traversal protection and HTML dashboard generation."""

import datetime
import logging
import os
import re
from typing import Any, Dict, List, Optional

from .html_dashboard import generate_html_dashboard

logger = logging.getLogger(__name__)


def sanitize_filename(topic: str) -> str:
    """Sanitizes topic string to prevent path traversal or invalid filesystem characters."""
    clean = re.sub(r"[^a-zA-Z0-9_\-]+", "_", topic.strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean[:50] or "untitled_research"


def save_research_artifacts(
    topic: str,
    content: str,
    output_dir: str = "reports",
    metrics: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, str]:
    """Saves both formatted Markdown report and interactive HTML dashboard.

    Args:
        topic: The original research topic or question.
        content: The Markdown report body.
        output_dir: Target directory to save reports (created if missing).
        metrics: Optional telemetry metrics dictionary.
        history: Optional observation history for evidence cards.

    Returns:
        Dictionary containing 'markdown_path' and 'html_path'.
    """
    safe_dir = os.path.abspath(output_dir)
    os.makedirs(safe_dir, exist_ok=True)

    safe_slug = sanitize_filename(topic)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    md_filename = f"research_{safe_slug}_{timestamp}.md"
    html_filename = f"research_{safe_slug}_{timestamp}.html"

    md_filepath = os.path.join(safe_dir, md_filename)
    html_filepath = os.path.join(safe_dir, html_filename)

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Format optional metrics
    metrics_yaml = ""
    if metrics:
        metrics_yaml = f"""duration_seconds: {metrics.get('duration_seconds', 0.0)}
steps_taken: {metrics.get('steps_taken', 0)}
pages_scraped: {metrics.get('pages_scraped', 0)}
searches_performed: {metrics.get('searches_performed', 0)}
mock_mode: {metrics.get('mock_mode', False)}
"""

    header = f"""---
topic: "{topic.replace('"', '')}"
generated_at: "{now_str}"
agent: "open-source-ai / research-assistant"
{metrics_yaml}---

# Research Report: {topic.strip()}

*Generated on {now_str} by Research Assistant Agent.*

---

"""
    full_markdown = header + content.strip() + "\n"

    # Write Markdown file
    with open(md_filepath, "w", encoding="utf-8") as f:
        f.write(full_markdown)

    # Generate and write HTML Dashboard
    html_content = generate_html_dashboard(
        topic=topic,
        markdown_content=content,
        metrics=metrics,
        history=history,
    )
    with open(html_filepath, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"Saved Markdown report to: {md_filepath}")
    logger.info(f"Saved HTML dashboard to: {html_filepath}")

    return {
        "markdown_path": md_filepath,
        "html_path": html_filepath,
    }


def save_markdown_report(
    topic: str,
    content: str,
    output_dir: str = "reports",
    metrics: Optional[Dict[str, Any]] = None,
    history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Convenience wrapper returning markdown path for backwards compatibility."""
    artifacts = save_research_artifacts(
        topic=topic,
        content=content,
        output_dir=output_dir,
        metrics=metrics,
        history=history,
    )
    return artifacts["markdown_path"]
