"""Run an investigation and stream progress events (used by both the CLI and the web UI)."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from collections.abc import AsyncIterator

from google.adk.agents.run_config import RunConfig
from google.adk.runners import InMemoryRunner
from google.genai import types

from .agent import build_root_agent
from .guardrails import QUARANTINE, review_report
from .schema import RCAReport
from .tools import load_incident

APP_NAME = "ishikawa"

# Hard ceiling on model calls per investigation (normal runs use ~15-25).
MAX_LLM_CALLS = int(os.getenv("ISHIKAWA_MAX_LLM_CALLS", "40"))
# Business-value assumptions, all overridable. Defaults are conservative estimates, not measurements.
MANUAL_RCA_MINUTES = float(os.getenv("ISHIKAWA_MANUAL_RCA_MINUTES", "45"))
ENGINEER_COST_PER_HOUR = float(os.getenv("ISHIKAWA_ENGINEER_COST_PER_HOUR", "60"))
PRICE_IN_PER_M = float(os.getenv("ISHIKAWA_PRICE_IN_PER_M", "0.50"))
PRICE_OUT_PER_M = float(os.getenv("ISHIKAWA_PRICE_OUT_PER_M", "3.00"))

_REDACTED = re.compile(r"\[REDACTED:([a-z0-9_]+)\]")


def _stage(author: str) -> str:
    if author.endswith("_investigator"):
        return author.removesuffix("_investigator")
    return author


def business_metrics(elapsed_s: float, tokens_in: int, tokens_out: int, llm_calls: int, tool_calls: int) -> dict:
    cost = tokens_in / 1e6 * PRICE_IN_PER_M + tokens_out / 1e6 * PRICE_OUT_PER_M
    saved_min = max(MANUAL_RCA_MINUTES - elapsed_s / 60, 0)
    return {
        "elapsed_s": round(elapsed_s, 1),
        "llm_calls": llm_calls,
        "tool_calls": tool_calls,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "est_cost_usd": round(cost, 4),
        "manual_baseline_min": MANUAL_RCA_MINUTES,
        "minutes_saved": round(saved_min, 1),
        "value_saved_usd": round(saved_min / 60 * ENGINEER_COST_PER_HOUR, 2),
    }


async def investigate(incident_id: str, repo_path: str | None = None, model: str | None = None) -> AsyncIterator[dict]:
    """Yield dict events: tool_call, guardrail, finding, report, done."""
    incident = load_incident(incident_id)
    agent = build_root_agent(model) if model else build_root_agent()
    runner = InMemoryRunner(agent=agent, app_name=APP_NAME)
    state = {"incident_id": incident_id}
    if repo_path:
        state["repo_path"] = repo_path
    session = await runner.session_service.create_session(
        app_name=APP_NAME, user_id="oncall", session_id=str(uuid.uuid4()), state=state
    )
    started = time.monotonic()
    message = types.Content(role="user", parts=[types.Part(text=f"Investigate incident {incident_id}.")])
    tokens_in = tokens_out = llm_calls = tool_calls = 0

    async for event in runner.run_async(
        user_id="oncall", session_id=session.id, new_message=message,
        run_config=RunConfig(max_llm_calls=MAX_LLM_CALLS),
    ):
        stage = _stage(event.author)
        if event.usage_metadata:
            llm_calls += 1
            tokens_in += event.usage_metadata.prompt_token_count or 0
            tokens_out += (event.usage_metadata.candidates_token_count or 0) + (event.usage_metadata.thoughts_token_count or 0)
        for call in event.get_function_calls():
            tool_calls += 1
            yield {"type": "tool_call", "stage": stage, "tool": call.name, "args": dict(call.args or {})}
        for resp in event.get_function_responses():
            text = json.dumps(resp.response, default=str)
            kinds = sorted(set(_REDACTED.findall(text)))
            if kinds:
                yield {"type": "guardrail", "stage": stage, "kind": "redaction", "tool": resp.name,
                       "detail": f"redacted {', '.join(kinds)} before the model saw it"}
            if QUARANTINE in text:
                yield {"type": "guardrail", "stage": stage, "kind": "injection", "tool": resp.name,
                       "detail": "quarantined text that tried to instruct the AI"}
            if '"error": "Tool budget' in text:
                yield {"type": "guardrail", "stage": stage, "kind": "budget", "tool": resp.name,
                       "detail": "tool-call budget reached"}
        if event.is_final_response() and event.content and event.content.parts:
            text = "".join(p.text or "" for p in event.content.parts if not p.thought).strip()
            if text and stage != "scribe":  # the scribe's report is read, validated, from state below
                yield {"type": "finding", "stage": stage, "text": text, "t": round(time.monotonic() - started, 1)}

    final = await runner.session_service.get_session(app_name=APP_NAME, user_id="oncall", session_id=session.id)
    raw = final.state.get("report")
    elapsed = time.monotonic() - started
    if raw:
        report = RCAReport.model_validate(raw) if isinstance(raw, dict) else RCAReport.model_validate_json(_strip_fences(raw))
        report, guard = review_report(report, incident, final.state)
        yield {"type": "report", "report": report.model_dump(), "guardrails": guard,
               "metrics": business_metrics(elapsed, tokens_in, tokens_out, llm_calls, tool_calls),
               "t": round(elapsed, 1)}
    yield {"type": "done", "elapsed_s": round(elapsed, 1)}


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text


def to_sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"
