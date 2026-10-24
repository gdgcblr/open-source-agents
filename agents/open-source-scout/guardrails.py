"""Guardrail Enforcement Module.

Strictly verifies that any repository processed, summarized, or outputted
by the LLM exists in the pre-verified GitHub API search results (Step 1).
Prevents LLM hallucinations or unauthorized repository recommendations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set, Tuple

logger = logging.getLogger("Guardrails")


class GuardrailViolationError(Exception):
    """Raised when the LLM outputs a repository not present in the verified search results."""
    pass


class RepoGuardrail:
    """Enforces strict whitelisting and structural validation against GitHub search results."""

    def __init__(self, verified_repos: List[Dict[str, Any]]):
        self.verified_repos = verified_repos
        self.allowed_full_names: Set[str] = set()
        self.allowed_urls: Set[str] = set()
        self.repo_map: Dict[str, Dict[str, Any]] = {}

        for repo in verified_repos:
            fn = repo.get("full_name", "").strip().lower()
            url = repo.get("html_url", "").strip().lower().rstrip("/")
            if fn:
                self.allowed_full_names.add(fn)
                self.repo_map[fn] = repo
            if url:
                self.allowed_urls.add(url)
                # Map URL without trailing slash
                self.repo_map[url] = repo

    def is_verified_repo(self, identifier: str) -> bool:
        """Checks if a repository name or URL belongs to the verified whitelist."""
        clean_id = identifier.strip().lower().rstrip("/")
        # Extract owner/repo if full URL passed
        if clean_id.startswith("https://github.com/"):
            clean_id = clean_id.replace("https://github.com/", "")

        return (
            clean_id in self.allowed_full_names
            or f"https://github.com/{clean_id}" in self.allowed_urls
        )

    def validate_and_filter_summaries(
        self,
        llm_summaries: List[Dict[str, Any]],
        strict: bool = True
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Validates LLM summaries against the verified repository whitelist.

        Args:
            llm_summaries: List of repository summary dicts produced by the LLM.
            strict: If True, raises GuardrailViolationError when an unauthorized repo is detected.
                    If False, strips out unverified repos and returns them in a violations list.

        Returns:
            Tuple of (verified_summaries, rejected_violations)
        """
        verified_results = []
        violations = []

        for item in llm_summaries:
            target_name = (item.get("full_name") or item.get("name") or "").strip().lower()
            target_url = (item.get("html_url") or item.get("url") or "").strip().lower().rstrip("/")

            # Normalize name if user/model passed URL in full_name
            if target_name.startswith("https://github.com/"):
                target_name = target_name.replace("https://github.com/", "")

            # Check whitelist membership
            is_valid = (
                target_name in self.allowed_full_names
                or target_url in self.allowed_urls
            )

            if not is_valid:
                violation_record = {
                    "rejected_item": item,
                    "reason": (
                        f"Hallucination / Unauthorized Repo: '{target_name or target_url}' "
                        f"was NOT found in the verified Step 1 GitHub API search results."
                    )
                }
                violations.append(violation_record)
                logger.warning(
                    "[GUARDRAIL VIOLATION BLOCKED] Rejected unverified repository: %s",
                    target_name or target_url
                )
                if strict:
                    raise GuardrailViolationError(violation_record["reason"])
            else:
                # Merge verified GitHub metadata to ensure rank, metrics, and URLs remain 100% genuine
                matched_meta = self.repo_map.get(target_name) or self.repo_map.get(target_url) or {}
                merged_record = dict(matched_meta)
                merged_record.update({
                    "problem_statement": item.get("problem_statement") or matched_meta.get("description", "Open-source codebase."),
                    "what_you_will_learn": item.get("what_you_will_learn"),
                    "why_it_fits_complexity": item.get("why_it_fits_complexity"),
                    "suggested_first_step": item.get("suggested_first_step"),
                    "guardrail_status": "VERIFIED_GENUINE"
                })
                verified_results.append(merged_record)

        return verified_results, violations
