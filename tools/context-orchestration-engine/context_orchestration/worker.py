"""The one worker class.

A worker is a configuration plus a gateway, with no memory between turns. It
sends exactly two messages, a system prompt and the compiled briefing, and
parses the reply into claims. It never sees another worker's output.
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from context_orchestration.contracts import ContextPackage, WorkerClaims, WorkerConfig
from context_orchestration.gateway import Gateway

SYSTEM_PROMPT = """\
You are one worker in a sequence of independent workers completing a single long task.
You have no memory of earlier turns. Everything known about the work so far is in the
briefing you are given, compiled by the engine. Do only your assigned task. Do not redo
completed work, do not repeat failed attempts, and keep earlier decisions unless you
record a new decision with a reason.

Reply with ONE JSON object and nothing else, with these keys:
{
  "summary": "string",
  "completed_task": "string, the task you completed",
  "decisions": [{"decision": "string", "reason": "string"}],
  "artifacts": [{"name": "string", "description": "string"}],
  "issues_opened": [{"description": "string", "severity": "low|medium|high"}],
  "issues_resolved": ["issue id or description"],
  "failed_attempts": [{"approach": "string", "reason": "string"}],
  "assumptions": [{"text": "string", "reason": "string"}],
  "progress": "string",
  "last_action": "string",
  "handoff": {
    "state_at_handoff": "string",
    "notes_for_next_worker": "string",
    "recommended_next_action": "string",
    "artifacts_mentioned": ["string"]
  }
}"""


class WorkerOutputError(RuntimeError):
    pass


def parse_claims(text: str) -> WorkerClaims:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise WorkerOutputError("reply contains no JSON object")
    try:
        return WorkerClaims.model_validate(json.loads(text[start : end + 1]))
    except (ValueError, ValidationError) as exc:
        raise WorkerOutputError(f"reply is not a valid claims object: {exc}") from exc


class UniversalWorker:
    def __init__(self, config: WorkerConfig, gateway: Gateway, attempts: int = 2) -> None:
        self.config = config
        self.gateway = gateway
        self.attempts = attempts

    def messages(self, package: ContextPackage) -> list[dict]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": package.rendered_text},
        ]

    def run(self, package: ContextPackage) -> tuple[WorkerClaims, str]:
        """Claims plus the raw reply. Malformed JSON is retried, not repaired."""
        error: WorkerOutputError | None = None
        for _ in range(self.attempts):
            raw = self.gateway.complete(self.config, self.messages(package))
            try:
                return parse_claims(raw), raw
            except WorkerOutputError as exc:
                error = exc
        raise WorkerOutputError(f"{self.config.id}: {error}")
