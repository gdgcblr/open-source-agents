"""Data contracts.

Two families of types, kept deliberately apart:

* **Claims** (``WorkerClaims`` and its parts) are what a worker returns. They
  are parsed with ``extra="ignore"``, so a worker cannot self-report
  provenance such as who made a decision or whether an artifact is verified.
* **Canonical records** (``Decision``, ``Artifact``, ``Issue`` ...) live in
  ``ExecutionState`` and are written only by the ``StateReconciler``.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -- configuration -----------------------------------------------------------


class WorkerConfig(BaseModel):
    """One worker: a model string and where its credential comes from."""

    id: str
    model: str
    api_key_env: str | None = None
    # A literal key is allowed for local experiments but never serialised.
    api_key: str | None = Field(default=None, exclude=True, repr=False)
    api_base: str | None = None
    temperature: float = 0.2
    max_tokens: int = 1500
    max_retries: int = 3

    def resolve_key(self) -> str | None:
        if self.api_key:
            return self.api_key
        if self.api_key_env:
            return os.environ.get(self.api_key_env) or None
        return None


# -- canonical records (written by the reconciler only) ----------------------


class Decision(BaseModel):
    decision: str
    reason: str = ""
    made_by: str
    turn: int


class Artifact(BaseModel):
    name: str
    description: str = ""
    version: int = 1
    created_by: str
    modified_by: list[str] = Field(default_factory=list)
    # Nothing in this tool inspects artifact content, so this stays False.
    verified: bool = False
    turn: int


class Issue(BaseModel):
    id: str
    description: str
    severity: str = "medium"
    opened_by: str
    status: Literal["open", "closed"] = "open"
    resolution_claimed_by: str | None = None


class FailedAttempt(BaseModel):
    approach: str
    reason: str = ""
    recorded_by: str
    turn: int


class Assumption(BaseModel):
    text: str
    reason: str = ""
    recorded_by: str


class TurnRecord(BaseModel):
    turn: int
    worker_id: str
    model: str
    assigned_task: str
    summary: str = ""
    at: str = Field(default_factory=now)


class ExecutionState(BaseModel):
    """The canonical state of one task. Owned by the engine, not by a model."""

    task_id: str
    objective: str
    plan: list[str]
    turn: int = 0
    status: Literal["pending", "running", "completed"] = "pending"
    completed_tasks: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    failed_attempts: list[FailedAttempt] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    current_progress: str = ""
    last_action: str = ""
    next_action: str = ""
    previous_worker: str | None = None
    notes_from_previous: str = ""
    history: list[TurnRecord] = Field(default_factory=list)

    def open_issues(self) -> list[Issue]:
        return [i for i in self.issues if i.status == "open"]


# -- claims (what a worker returns) ------------------------------------------


class _Claim(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ClaimedDecision(_Claim):
    decision: str
    reason: str = ""


class ClaimedArtifact(_Claim):
    name: str
    description: str = ""


class ClaimedIssue(_Claim):
    description: str
    severity: str = "medium"


class ClaimedFailure(_Claim):
    approach: str
    reason: str = ""


class ClaimedAssumption(_Claim):
    text: str
    reason: str = ""


class HandoffReport(_Claim):
    """The worker's message to its successor."""

    state_at_handoff: str = ""
    notes_for_next_worker: str = ""
    recommended_next_action: str = ""
    artifacts_mentioned: list[str] = Field(default_factory=list)


class WorkerClaims(_Claim):
    summary: str = ""
    completed_task: str = ""
    decisions: list[ClaimedDecision] = Field(default_factory=list)
    artifacts: list[ClaimedArtifact] = Field(default_factory=list)
    issues_opened: list[ClaimedIssue] = Field(default_factory=list)
    issues_resolved: list[str] = Field(default_factory=list)
    failed_attempts: list[ClaimedFailure] = Field(default_factory=list)
    assumptions: list[ClaimedAssumption] = Field(default_factory=list)
    progress: str = ""
    last_action: str = ""
    handoff: HandoffReport = Field(default_factory=HandoffReport)


# -- engine outputs ------------------------------------------------------------


class ContextPackage(BaseModel):
    """The compiled briefing one worker receives. Never a transcript."""

    task_id: str
    turn: int
    target_worker_id: str
    assigned_task: str
    rendered_text: str
    estimated_tokens: int
    budget: int
    sections: list[str] = Field(default_factory=list)
    omitted_sections: list[str] = Field(default_factory=list)
    dropped_items: int = 0


class ReconciliationReport(BaseModel):
    worker_id: str
    turn: int
    decisions_added: int = 0
    decisions_duplicate: int = 0
    artifacts_created: list[str] = Field(default_factory=list)
    artifacts_versioned: list[str] = Field(default_factory=list)
    handoff_only_artifacts: list[str] = Field(default_factory=list)
    issues_opened: list[str] = Field(default_factory=list)
    rejected_resolutions: list[str] = Field(default_factory=list)
    failed_attempts_added: int = 0
    warnings: list[str] = Field(default_factory=list)
