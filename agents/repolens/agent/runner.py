"""
RepoLens — ADK Agent Runner

Orchestrates:
  1. Prepare sanitized report snapshot for the agent.
  2. Build agent with bound tools.
  3. Run agent via ADK Runner/Session API.
  4. Validate and extract structured output.
  5. Return ai_summary and ai_prioritized_actions, or None on failure.

When GOOGLE_API_KEY is absent or the model call fails, returns (None, []).
The scanner-only workflow continues working without AI enrichment.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Optional

from backend.config import get_settings
from backend.models import AuditReport

logger = logging.getLogger(__name__)

try:
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai.types import Content, Part
    ADK_RUNNER_AVAILABLE = True
except ImportError:
    ADK_RUNNER_AVAILABLE = False


# Maximum number of findings to include in the agent context (to bound token usage)
_MAX_FINDINGS_FOR_AGENT = 30
# Maximum total characters sent to the agent
_MAX_CONTEXT_CHARS = 12_000


def _sanitize_report_for_agent(report: AuditReport) -> dict[str, Any]:
    """
    Create a safe, bounded snapshot of the report for the agent.
    - Limits finding count
    - Truncates evidence to max_snippet_bytes
    - Excludes full report_markdown (too long)
    """
    settings = get_settings()
    findings_data = []
    for f in report.findings[:_MAX_FINDINGS_FOR_AGENT]:
        fd = f.model_dump()
        # Evidence already redacted by normalizer, but apply size limit again
        if fd.get("evidence"):
            fd["evidence"] = fd["evidence"][: settings.max_snippet_bytes]
        findings_data.append(fd)

    return {
        "repository_url": report.repository_url,
        "repository_name": report.repository_name,
        "commit_sha": report.commit_sha,
        "tech_stack": report.tech_stack,
        "findings": findings_data,
        "scanner_status": {
            name: s.model_dump()
            for name, s in report.scanner_status.items()
        },
        "is_demo": report.is_demo,
    }


def _extract_prioritized_actions(text: str) -> list[str]:
    """
    Extract numbered action items (1. ...) from agent output text.
    Returns up to 5 items.
    """
    pattern = re.compile(r"^\s*(\d+)\.\s+(.+)", re.MULTILINE)
    actions = []
    for m in pattern.finditer(text):
        item = m.group(2).strip()
        if item:
            actions.append(item)
        if len(actions) >= 5:
            break
    return actions


def _validate_agent_output(raw_output: Any) -> str:
    """
    Validate that agent output is a non-empty string.
    Strips any potential prompt-injection preamble longer than 5000 chars.
    """
    if not raw_output:
        return ""
    if not isinstance(raw_output, str):
        try:
            raw_output = str(raw_output)
        except Exception:
            return ""
    # Truncate to a reasonable limit
    return raw_output[:5000]


async def run_agent_async(report: AuditReport) -> tuple[Optional[str], list[str]]:
    """
    Run the ADK agent asynchronously.

    Returns:
        (ai_summary, ai_prioritized_actions) or (None, []) on failure.
    """
    settings = get_settings()

    if not settings.gemini_available:
        logger.info("GOOGLE_API_KEY not set. Skipping AI enrichment.")
        return None, []

    if not ADK_RUNNER_AVAILABLE:
        logger.warning("ADK Runner not available. Skipping AI enrichment.")
        return None, []

    from agent.tools import make_tools
    from agent.audit_agent import build_agent, ADK_AVAILABLE

    if not ADK_AVAILABLE:
        return None, []

    try:
        # Set API key for google-genai
        os.environ["GOOGLE_API_KEY"] = settings.google_api_key

        snapshot = _sanitize_report_for_agent(report)
        get_scan_summary_fn, get_finding_details_fn = make_tools(snapshot)
        agent = build_agent(get_scan_summary_fn, get_finding_details_fn)

        if agent is None:
            return None, []

        session_service = InMemorySessionService()
        runner = Runner(
            agent=agent,
            app_name="repolens",
            session_service=session_service,
        )

        session = await session_service.create_session(
            app_name="repolens",
            user_id="system",
        )

        user_message = Content(
            role="user",
            parts=[Part(text=(
                f"Please analyze the security scan results for "
                f"{report.repository_name} and provide your audit summary."
            ))],
        )

        final_response_text = ""
        async for event in runner.run_async(
            user_id="system",
            session_id=session.id,
            new_message=user_message,
        ):
            if hasattr(event, "content") and event.content:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        final_response_text += part.text

        validated = _validate_agent_output(final_response_text)
        actions = _extract_prioritized_actions(validated)
        return validated, actions

    except Exception as exc:
        logger.error("Agent run failed: %s", exc, exc_info=True)
        return None, []


def run_agent_sync(report: AuditReport) -> tuple[Optional[str], list[str]]:
    """
    Synchronous wrapper for run_agent_async.
    Used by the FastAPI endpoint (which runs in AnyIO worker thread).
    """
    import asyncio
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, run_agent_async(report))
                return future.result(timeout=60)
        else:
            return asyncio.run(run_agent_async(report))
    except Exception as exc:
        logger.error("Sync agent wrapper failed: %s", exc)
        return None, []
