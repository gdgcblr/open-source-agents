"""Shared data structures.

These typed records are the single source of truth that flows through the whole
pipeline: the GitHub tool produces them, the agent is only allowed to reference
them, and the eval harness checks the digest against them. Every ``event_id`` is
stable and traceable so a claim in the final digest can always be mapped back to
a concrete piece of activity (or flagged as unsupported).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Literal

EventKind = Literal[
    "commit", "pull_request", "issue", "review", "create", "delete"
]


@dataclass(frozen=True)
class ActivityEvent:
    """A single, verifiable unit of work pulled from GitHub."""

    event_id: str          # e.g. "commit:abc1234", "pr:owner/repo#42"
    kind: EventKind
    repo: str              # "owner/repo"
    title: str             # commit message subject / PR or issue title
    url: str
    timestamp: datetime
    state: str = ""        # open/closed/merged for PRs & issues; "" for commits
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    def as_evidence_line(self) -> str:
        """Compact, LLM-facing representation. The ``event_id`` prefix is what
        the model must cite, which is how we later verify groundedness."""
        tag = f"[{self.event_id}]"
        state = f" ({self.state})" if self.state else ""
        return f"{tag} {self.kind} in {self.repo}{state}: {self.title}"


@dataclass
class ActivityLog:
    """All activity fetched for one user on one day."""

    username: str
    date: str                       # ISO date, e.g. "2026-10-24"
    events: list[ActivityEvent] = field(default_factory=list)
    # Populated when a data source failed; drives escalation downstream.
    fetch_warnings: list[str] = field(default_factory=list)
    partial: bool = False           # True if any source failed to return

    @property
    def event_ids(self) -> set[str]:
        return {e.event_id for e in self.events}

    def is_empty(self) -> bool:
        return len(self.events) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "date": self.date,
            "partial": self.partial,
            "fetch_warnings": self.fetch_warnings,
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class Digest:
    """The agent's output plus the signals a human needs to trust it."""

    text: str
    escalate: bool = False
    escalation_reasons: list[str] = field(default_factory=list)
    needs_confirmation: list[str] = field(default_factory=list)  # [confirm ...] items
    referenced_event_ids: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "escalate": self.escalate,
            "escalation_reasons": self.escalation_reasons,
            "needs_confirmation": self.needs_confirmation,
            "referenced_event_ids": sorted(self.referenced_event_ids),
        }
