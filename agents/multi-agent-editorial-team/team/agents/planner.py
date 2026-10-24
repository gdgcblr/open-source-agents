"""Planner Agent: Decomposes topics into structured outlines and search blueprints."""

import json
import logging
import re
from typing import Any, Callable, Dict, Optional

from ..state import ArticlePlan

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are the Senior Editorial Planner Agent.
Your responsibility is to analyze a topic, define the target audience, outline key sections, and formulate 3 targeted web search queries.

Output ONLY valid JSON matching this schema:
{
  "title": "Working Title of Article",
  "target_audience": "e.g. AI Engineers, Developers, Researchers",
  "key_sections": [
    "Introduction & Problem Statement",
    "Technical Architecture & Key Patterns",
    "Comparative Trade-offs & Benchmarks",
    "Production Best Practices & Caveats"
  ],
  "search_queries": [
    "primary concept architecture and overview",
    "technical trade-offs and performance benchmarks",
    "real-world production implementation guide"
  ]
}
"""


class PlannerAgent:
    """Plans topic structure and research strategy."""

    def __init__(self, llm_caller: Optional[Callable[[str], str]] = None):
        self.llm_caller = llm_caller

    def plan(self, topic: str) -> ArticlePlan:
        """Generates an ArticlePlan for the given topic."""
        logger.info(f"[Planner] Formulating editorial plan for '{topic}'")
        if not self.llm_caller:
            # Fallback default plan
            return ArticlePlan(
                title=f"Comprehensive Guide to {topic}",
                target_audience="Developers and AI Practitioners",
                key_sections=[
                    "Executive Overview",
                    "Core Concepts & Architecture",
                    "Comparative Analysis & Trade-offs",
                    "Practical Implementation & Takeaways"
                ],
                search_queries=[
                    f"{topic} architecture overview",
                    f"{topic} best practices and benchmarks",
                    f"{topic} real world guide"
                ]
            )

        prompt = f"{PLANNER_SYSTEM_PROMPT}\n\nTopic: \"{topic}\"\nGenerate JSON plan:"
        raw_response = self.llm_caller(prompt)

        # Parse JSON
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_response.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

        try:
            data = json.loads(cleaned)
            return ArticlePlan(**data)
        except Exception as e:
            logger.warning(f"[Planner] JSON parse error: {e}. Using structured fallback.")
            return ArticlePlan(
                title=f"Analysis of {topic}",
                target_audience="Software Engineers",
                key_sections=["Introduction", "Architecture", "Practical Guidelines"],
                search_queries=[f"{topic} overview", f"{topic} guide"]
            )
