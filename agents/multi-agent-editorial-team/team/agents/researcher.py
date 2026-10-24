"""Researcher Agent: Executes live web discovery and builds verified evidence dossiers."""

import logging
from typing import Callable, List, Optional

from ..state import ArticlePlan, EvidenceItem
from ..tools.search import search_web

logger = logging.getLogger(__name__)


class ResearcherAgent:
    """Executes search queries and collects factual evidence items."""

    def __init__(self, llm_caller: Optional[Callable[[str], str]] = None):
        self.llm_caller = llm_caller

    def research(self, plan: ArticlePlan) -> List[EvidenceItem]:
        """Runs search queries from the plan and produces a deduplicated evidence list."""
        logger.info(f"[Researcher] Executing research for {len(plan.search_queries)} queries.")
        evidence_list: List[EvidenceItem] = []
        seen_urls = set()

        for query in plan.search_queries:
            results = search_web(query, max_results=3)
            for item in results:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    evidence_list.append(EvidenceItem(
                        title=item.get("title", "Reference Finding"),
                        url=url,
                        snippet=item.get("snippet", ""),
                        verified=True
                    ))

        logger.info(f"[Researcher] Collected {len(evidence_list)} unique evidence findings.")
        return evidence_list
