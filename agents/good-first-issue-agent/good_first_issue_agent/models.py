"""Small data structures shared by the sources, scoring, agent and output."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Issue:
    """An issue normalized from GitHub or from an error tracker."""

    source: str  # "github", "sentry" or "glitchtip"
    id: str  # GitHub issue number or error-tracker issue id, as text
    display_id: str  # "#123" for GitHub, short id (e.g. "WEB-1A") for trackers
    title: str
    url: str
    body: str = ""
    labels: list[str] = field(default_factory=list)
    state: str = "open"
    assignees: list[str] = field(default_factory=list)
    comments: int = 0
    created_at: str = ""
    updated_at: str = ""
    locked: bool = False
    # Error-tracker fields (empty for GitHub)
    level: str = ""
    culprit: str = ""
    event_count: int = 0
    user_count: int = 0
    error_type: str = ""
    error_value: str = ""
    stack_files: list[str] = field(default_factory=list)


@dataclass
class Reason:
    """One scoring signal: how many points it added or removed, and why."""

    signal: str
    points: int
    detail: str


@dataclass
class ScoredIssue:
    issue: Issue
    score: int
    reasons: list[Reason] = field(default_factory=list)
    uncertainties: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    # Files or paths that appear in the issue text or stack trace (evidence, not guesses)
    evidence_paths: list[str] = field(default_factory=list)
    # Guardrail flags, e.g. possible prompt injection in the issue text
    flags: list[str] = field(default_factory=list)


@dataclass
class AIResult:
    text: str
    model: str
    warnings: list[str] = field(default_factory=list)
    tool_calls: int = 0


@dataclass
class Report:
    source: str
    target: str  # "owner/repo" or "org/project"
    target_url: str
    fetched: int = 0
    excluded_pull_requests: int = 0
    ranked: list[ScoredIssue] = field(default_factory=list)
    selected: ScoredIssue | None = None
    ai: AIResult | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["disclaimer"] = (
            "Scores are heuristics based on issue text and labels, not a guarantee "
            "that an issue is beginner-friendly. AI analysis, when present, is a "
            "model-generated recommendation and may be wrong."
        )
        return data
