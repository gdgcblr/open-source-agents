"""Plug the gate into any Google ADK agent through its model and tool callbacks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google.adk.models.llm_response import LlmResponse
from google.genai import types

from .gate import Decision, Evidence, Verdict, check_message, decide
from .handoff import build_handoff
from .policy import Policy, load_policy

# Marks responses the harness wrote instead of a real tool, so they never count as evidence.
BLOCKED_KEY = "harness_blocked"

_INSTRUCTIONS = {
    Decision.CLARIFY: "Do not guess. Ask the customer one short question that resolves this, then try again.",
    Decision.ESCALATE: "Do not retry. Tell the customer a human teammate will follow up on ticket {ticket_id} with full context.",
    Decision.REFUSE: "Do not retry. Politely tell the customer this cannot be done, and why.",
}


class EscalationHarness:
    """Decides act / clarify / escalate / refuse before every tool call an agent makes.

    Usage:
        harness = EscalationHarness("policy.yaml")
        agent = Agent(..., **harness.callbacks())
    """

    def __init__(self, policy: Policy | str | Path, handoff_dir: str | Path | None = None):
        self.policy = policy if isinstance(policy, Policy) else load_policy(policy)
        self.handoff_dir = Path(handoff_dir) if handoff_dir else None
        self.log: list[dict] = []  # one entry per decision, for evals and audits
        self.handoffs: list[dict] = []
        self._pending: dict[str, dict] = {}  # function_call_id -> packet awaiting the tool's ticket

    def callbacks(self) -> dict[str, Any]:
        return {
            "before_model_callback": self.before_model,
            "before_tool_callback": self.before_tool,
            "after_tool_callback": self.after_tool,
        }

    def decisions(self, session_id: str) -> list[dict]:
        return [entry for entry in self.log if entry["session_id"] == session_id]

    # --- ADK callbacks -------------------------------------------------------

    def before_model(self, callback_context, llm_request) -> LlmResponse | None:
        """Hand off before the model runs when a customer message must always reach a human."""
        last = llm_request.contents[-1] if llm_request.contents else None
        if last is None or last.role != "user" or not last.parts:
            return None
        if any(part.function_response for part in last.parts):
            return None
        text = " ".join(part.text for part in last.parts if part.text)
        verdict = check_message(self.policy, text)
        if verdict is None:
            return None
        session = callback_context.session
        packet = self._handoff(session, callback_context.state, verdict, proposed=None)
        self._record(
            session.id, None, {}, verdict, ticket_id=packet["ticket_id"], invocation_id=callback_context.invocation_id
        )
        reply = (
            f"I've passed this to a human teammate (ticket {packet['ticket_id']}). "
            "They'll see our full conversation, so you won't need to repeat anything."
        )
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=reply)]))

    def before_tool(self, tool, args: dict[str, Any], tool_context) -> dict | None:
        session = tool_context.session
        evidence = self._evidence(session)
        spec = self.policy.tools.get(tool.name)

        invocation_id = tool_context.invocation_id
        if spec is not None and spec.risk == "handoff":
            # One ticket per customer message: if this turn already escalated, reuse that ticket.
            earlier = [
                e for e in self.decisions(session.id) if e["invocation_id"] == invocation_id and e["ticket_id"]
            ]
            if earlier:
                ticket_id = earlier[-1]["ticket_id"]
                return {
                    BLOCKED_KEY: True,
                    "decision": Decision.ESCALATE.value,
                    "reason": "Already escalated for this message.",
                    "ticket_id": ticket_id,
                    "instruction": _INSTRUCTIONS[Decision.ESCALATE].format(ticket_id=ticket_id),
                }
            # The model chose to escalate: let the tool run, and give its ticket a full packet.
            verdict = Verdict(Decision.ESCALATE, "model:escalate", str(args.get("reason", "")))
            packet = self._handoff(session, tool_context.state, verdict, proposed=None)
            self._record(session.id, tool.name, args, verdict, packet["ticket_id"], invocation_id)
            self._pending[tool_context.function_call_id] = packet
            return None

        verdict = decide(self.policy, tool.name, args, evidence)
        if verdict.decision is Decision.ACT:
            self._record(session.id, tool.name, args, verdict, invocation_id=invocation_id)
            return None

        response = {
            BLOCKED_KEY: True,
            "decision": verdict.decision.value,
            "reason": verdict.reason,
        }
        if verdict.detail.get("candidates"):
            response["options"] = verdict.detail["candidates"]
        ticket_id = None
        if verdict.decision is Decision.ESCALATE:
            proposed = {"tool": tool.name, "args": dict(args)}
            ticket_id = self._handoff(session, tool_context.state, verdict, proposed)["ticket_id"]
            response["ticket_id"] = ticket_id
        response["instruction"] = _INSTRUCTIONS[verdict.decision].format(ticket_id=ticket_id)
        self._record(session.id, tool.name, args, verdict, ticket_id, invocation_id)
        return response

    def after_tool(self, tool, args: dict[str, Any], tool_context, tool_response) -> dict | None:
        """Give the packet the ticket ID the real escalation tool created, so both sides match."""
        packet = self._pending.pop(tool_context.function_call_id, None)
        new_id = tool_response.get("ticket_id") if isinstance(tool_response, dict) else None
        if packet and new_id and new_id != packet["ticket_id"]:
            old_id = packet["ticket_id"]
            packet["ticket_id"] = new_id
            for entry in self.log:
                if entry["ticket_id"] == old_id:
                    entry["ticket_id"] = new_id
            self._save(packet, replaces=old_id)
        return None

    # --- internals -----------------------------------------------------------

    def _evidence(self, session) -> Evidence:
        evidence = Evidence()
        for event in session.events:
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                if event.author == "user" and part.text:
                    evidence.user_texts.append(part.text)
                response = part.function_response.response if part.function_response else None
                if response and not response.get(BLOCKED_KEY):
                    evidence.tool_outputs.append(json.dumps(response, default=str))
        evidence.prior_actions = [
            (entry["tool"], entry["args"])
            for entry in self.decisions(session.id)
            if entry["decision"] == Decision.ACT.value
        ]
        return evidence

    def _handoff(self, session, state, verdict: Verdict, proposed: dict | None) -> dict:
        evidence = self._evidence(session)
        packet = build_handoff(
            customer_id=state.get("customer_id"),
            user_texts=evidence.user_texts,
            actions_taken=[{"tool": t, "args": a} for t, a in evidence.prior_actions],
            proposed_action=proposed,
            verdict=verdict,
        )
        self.handoffs.append(packet)
        self._save(packet)
        return packet

    def _save(self, packet: dict, replaces: str | None = None) -> None:
        if not self.handoff_dir:
            return
        self.handoff_dir.mkdir(parents=True, exist_ok=True)
        if replaces:
            (self.handoff_dir / f"{replaces}.json").unlink(missing_ok=True)
        path = self.handoff_dir / f"{packet['ticket_id']}.json"
        path.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")

    def _record(self, session_id, tool, args, verdict: Verdict, ticket_id=None, invocation_id=None) -> None:
        self.log.append(
            {
                "session_id": session_id,
                "invocation_id": invocation_id,
                "tool": tool,
                "args": dict(args),
                "decision": verdict.decision.value,
                "rule": verdict.rule,
                "reason": verdict.reason,
                "ticket_id": ticket_id,
            }
        )
