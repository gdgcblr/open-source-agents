"""
RepoLens — Google ADK Audit Agent

Defines one LlmAgent: "RepoLens Audit Agent".

Responsibilities:
  - Summarize the audit.
  - Explain important findings.
  - Prioritize up to five remediation actions.
  - Suggest concrete fixes.
  - Label speculative observations as unverified suggestions.

The agent has access ONLY to get_scan_summary and get_finding_details.
It cannot access the filesystem, shell, network, or database.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from backend.config import get_settings

logger = logging.getLogger(__name__)

try:
    from google.adk.agents import LlmAgent
    from google.adk.tools import FunctionTool
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    logger.warning("google-adk not installed. Agent functionality disabled.")


AGENT_NAME = "repolens_audit_agent"

_INSTRUCTION = """
You are RepoLens Audit Agent, an expert application security analyst.

You have been given the results of an automated security scan of a GitHub repository.
Your job is to:

1. **Summarize** the overall security posture in 2-3 sentences.
2. **Explain** the most important findings (CRITICAL and HIGH severity first).
3. **Prioritize** up to five specific, actionable remediation steps. Number them 1–5.
4. **Suggest concrete fixes** where possible (e.g., specific version to upgrade to).
5. **Label** any speculative observations or code-quality suggestions as:
   "[UNVERIFIED SUGGESTION — not confirmed by scanner]"

Rules you MUST follow:
- Only reference findings that exist in the scan data (use get_scan_summary and get_finding_details).
- Do NOT invent finding IDs, file paths, or vulnerability names.
- Do NOT claim a clean scan if the scanner was unavailable or failed.
- Preserve the original scanner severity ratings.
- Distinguish scanner findings (provenance: scanner) from your own suggestions.
- Keep the summary under 400 words.
- If all scanners were unavailable, say so clearly and do not fabricate findings.
- If the report is a demo (is_demo=true), state that clearly in your summary.
""".strip()


def build_agent(
    get_scan_summary_fn: Callable,
    get_finding_details_fn: Callable,
):
    """
    Construct and return the RepoLens ADK LlmAgent.

    Args:
        get_scan_summary_fn: Bound tool function for scan summary.
        get_finding_details_fn: Bound tool function for finding details.

    Returns:
        LlmAgent instance, or None if ADK is not available.
    """
    if not ADK_AVAILABLE:
        logger.warning("ADK not available. Returning None agent.")
        return None

    settings = get_settings()

    tools = [
        FunctionTool(get_scan_summary_fn),
        FunctionTool(get_finding_details_fn),
    ]

    agent = LlmAgent(
        name=AGENT_NAME,
        model=settings.gemini_model,
        instruction=_INSTRUCTION,
        tools=tools,
        output_key="audit_analysis",
    )

    return agent
