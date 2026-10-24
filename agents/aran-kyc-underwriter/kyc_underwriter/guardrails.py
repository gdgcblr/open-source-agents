"""Guardrails for the KYC underwriter. Each one is independent; any one can stop a leak.

G1 input guard    PII typed or pasted by the user is masked before Gemini sees it.
G2 egress guard   Every request to Gemini (user text AND tool results) is checked against the
                  session vault and the detectors. On a hit, the request is NOT sent.
G3 tool guard     Only Aran's read-only tools, only the "kyc" profile. Anything else is refused.
G4 output guard   Gemini's reply is checked for real values (should be impossible) before display.
G5 budget         run.py caps LLM calls per case (RunConfig.max_llm_calls).
G6 human review   REFER/DECLINE verdicts are flagged for a human underwriter (see INSTRUCTION).

Raw values are never logged: blocks are written to the Aran audit log as types only.
"""

from __future__ import annotations

import json
from typing import Any

from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

import aran
from aran import audit, guard

ALLOWED_TOOLS = {"list_documents", "redact_document", "privacy_summary"}
PROFILE = "kyc"

# Local-only record of every request text that would leave the machine. Used by the agent
# evals to prove nothing raw was ever sent; never written to disk by the agent itself.
EGRESS_LOG: list[str] = []


class Guardrails:
    def __init__(self, session_id: str):
        self.session_id = session_id

    def _block(self, event: str, leaks: list[guard.Leak]) -> LlmResponse:
        audit.record_event(session_id=self.session_id, event=event,
                           types=[l.type for l in leaks], channel="agent")
        msg = (f"[Aran guardrail] {event}: personal data detected ({guard.describe(leaks)}). "
               "The request was stopped on this machine and nothing was sent.")
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=msg)]))

    # G1 + G2
    def before_model(self, callback_context: Any, llm_request: LlmRequest) -> LlmResponse | None:
        outgoing: list[str] = []
        for content in llm_request.contents or []:
            for part in content.parts or []:
                if part.text and content.role == "user":
                    part.text = aran.redact_text(
                        part.text, PROFILE, self.session_id, use_llm=False, channel="agent-input"
                    ).redacted
                if part.text:
                    outgoing.append(part.text)
                if part.function_response:
                    outgoing.append(json.dumps(part.function_response.response, ensure_ascii=False))
                if part.function_call:
                    outgoing.append(json.dumps(part.function_call.args or {}, ensure_ascii=False))
        text = "\n".join(outgoing)
        EGRESS_LOG.append(text)
        leaks = guard.find_leaks(text, self.session_id, PROFILE)
        return self._block("egress blocked", leaks) if leaks else None

    # G3
    def before_tool(self, tool: Any, args: dict[str, Any], tool_context: Any) -> dict | None:
        if tool.name not in ALLOWED_TOOLS:
            return {"error": f"Tool {tool.name!r} is not allowed for this agent."}
        if "profile" in args and args["profile"] != PROFILE:
            return {"error": f"Only the {PROFILE!r} privacy profile is allowed."}
        return None

    # G4
    def after_model(self, callback_context: Any, llm_response: LlmResponse) -> LlmResponse | None:
        parts = (llm_response.content.parts if llm_response.content else None) or []
        text = "\n".join(p.text for p in parts if p.text)
        leaks = guard.find_leaks(text, self.session_id, PROFILE)
        return self._block("output blocked", leaks) if leaks else None
