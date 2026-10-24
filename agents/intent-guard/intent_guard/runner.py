"""Programmatic runner for IntentGuard.

This module provides a simple async function to execute a review
outside of the ADK CLI, used by both the FastAPI server and the CLI.
"""

from __future__ import annotations

import asyncio
import json
import os

from pathlib import Path

from dotenv import load_dotenv

_project_dir = Path(__file__).resolve().parent.parent
load_dotenv(_project_dir / ".env")
load_dotenv()

if os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
    os.environ["GEMINI_API_KEY"] = os.environ["GOOGLE_API_KEY"]
elif os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import root_agent
from .guardrails import (
    attach_guardrail_issues,
    build_hardened_user_message,
    scan_for_prompt_injection,
    validate_request_bounds,
)
from .models import ReviewRequest, ReviewVerdict

load_dotenv()

# Shared session service — in-memory is fine for a stateless review tool.
_session_service = InMemorySessionService()
_runner = Runner(
    agent=root_agent,
    app_name="agents",
    session_service=_session_service,
)

_session_counter = 0


async def run_review(request: ReviewRequest, max_retries: int = 2) -> ReviewVerdict:
    """Execute a full correctness review with active security guardrails.

    Args:
        request: The review request containing intent context and code diff.
        max_retries: Number of retries on transient server errors (503/429).

    Returns:
        A ReviewVerdict with the structured assessment.
    """
    global _session_counter
    _session_counter += 1

    # Guardrail 1: Enforce input bounds and size limits (DoS protection)
    validate_request_bounds(request)

    # Guardrail 2: Scan for prompt injection and adversarial manipulation
    combined_untrusted = f"{request.intent_context}\n{request.code_diff}"
    if request.repo_context:
        combined_untrusted += f"\n{request.repo_context}"
    injection_warnings = scan_for_prompt_injection(combined_untrusted)

    user_id = "reviewer_user"
    session_id = f"review_session_{_session_counter}"

    # Guardrail 3: Build hardened prompt with untrusted data isolation
    user_message = build_hardened_user_message(request, injection_warnings)

    last_error = None
    events = []
    for attempt in range(max_retries + 1):
        try:
            # Run the agent using ADK's run_debug helper.
            events = await _runner.run_debug(
                user_message,
                user_id=user_id,
                session_id=session_id,
                quiet=True,
            )
            break
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                await asyncio.sleep(2 * (attempt + 1))
            else:
                return ReviewVerdict(
                    verdict="needs_revision",
                    confidence=0.0,
                    requirements=[],
                    unmatched_changes=[],
                    issues=[],
                    summary=f"[API ERROR] Model service temporarily unavailable: {exc}. Please retry in a few moments.",
                )

    final_response_text = ""
    for event in events:
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_response_text += part.text

    # If final_response_text is empty, check any event with text content.
    if not final_response_text:
        for event in reversed(events):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        final_response_text += part.text
                if final_response_text:
                    break

    # Parse the agent's JSON response into our Pydantic model.
    verdict = _parse_verdict(final_response_text)

    # Guardrail 4: Attach detected prompt injection issues to final verdict
    return attach_guardrail_issues(verdict, injection_warnings)


def _build_user_message(request: ReviewRequest) -> str:
    """Construct the user message for the agent from a ReviewRequest."""
    parts = [
        "Please review the following AI-generated code for correctness "
        "against the original requirements.\n",
        "=" * 72,
        "INTENT CONTEXT (JIRA ticket / HLD / meeting notes):",
        "=" * 72,
        request.intent_context,
        "",
        "=" * 72,
        f"CODE CHANGES ({request.language}):",
        "=" * 72,
        request.code_diff,
    ]

    if request.repo_context:
        parts.extend([
            "",
            "=" * 72,
            "EXISTING REPO CONTEXT:",
            "=" * 72,
            request.repo_context,
        ])

    return "\n".join(parts)


def _parse_verdict(raw_text: str) -> ReviewVerdict:
    """Parse the agent's raw text response into a ReviewVerdict.

    Handles cases where the agent wraps JSON in markdown fences or
    adds preamble text.
    """
    text = raw_text.strip()

    # Strip markdown JSON fences if present.
    if "```json" in text:
        text = text.split("```json", 1)[1]
        text = text.split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1]
        text = text.split("```", 1)[0]

    # Try to find a JSON object in the text.
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]

    try:
        data = json.loads(text)
        return ReviewVerdict(**data)
    except (json.JSONDecodeError, Exception) as e:
        # Fallback: return a verdict indicating the agent's response
        # couldn't be parsed, but include the raw text.
        return ReviewVerdict(
            verdict="needs_revision",
            confidence=0.0,
            requirements=[],
            unmatched_changes=[],
            issues=[],
            summary=(
                f"[PARSE ERROR] Could not parse agent response into "
                f"structured verdict. Raw response:\n\n{raw_text[:2000]}"
            ),
        )

