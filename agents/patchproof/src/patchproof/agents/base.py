"""Base agent contracts, typed role outputs, and untrusted input sanitization."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from patchproof.core.enums import AgentStatus, Verdict
from patchproof.core.models import (
    SCHEMA_VERSION,
    AdversarialHypothesis,
    AgentRun,
    ChangeMap,
    CheckRequest,
    CheckResult,
    Finding,
    Requirement,
    TestInventoryItem,
    TestProposal,
    TraceabilityEntry,
)

_PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)ignore\s+(?:all\s+)?(?:previous|prior|system|above)\s+instructions"),
    re.compile(r"(?i)disregard\s+(?:all\s+)?(?:previous|prior|system|policy)"),
    re.compile(r"(?i)override\s+(?:security|tool|sandbox)\s+policy"),
    re.compile(r"(?i)mark\s+all\s+requirements?\s+satisfied"),
    re.compile(r"(?i)print\s+(?:env|environment)\s+vars"),
    re.compile(r"(?i)exfiltrate|169\.254\.169\.254"),
    re.compile(r"(?i)curl\s+https?://.*\|\s*(?:sh|bash)"),
)


def detect_prompt_injection_lines(text: str) -> list[str]:
    """Scan untrusted text for prompt-injection phrases and return matched lines."""
    matches: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(pat.search(line) for pat in _PROMPT_INJECTION_PATTERNS):
            matches.append(line[:200])
    return matches


def is_prompt_injection_line(line: str) -> bool:
    """Return True if a single line contains a known prompt-injection pattern."""
    return any(pat.search(line) for pat in _PROMPT_INJECTION_PATTERNS)


class BaseAgentOutput(BaseModel):
    """Common envelope fields required for every agent output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent_name: str = Field(min_length=1)
    schema_version: str = Field(default=SCHEMA_VERSION)
    status: AgentStatus
    summary: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: int = Field(default=0, ge=0)

    def to_agent_run(self, payload: dict[str, object] | None = None) -> AgentRun:
        """Convert this typed output into an AgentRun record."""
        return AgentRun(
            agent_name=self.agent_name,
            schema_version=self.schema_version,
            status=self.status,
            summary=self.summary,
            evidence_ids=list(self.evidence_ids),
            warnings=list(self.warnings),
            duration_ms=self.duration_ms,
            payload=dict(payload or {}),
        )


class IntentAnalystOutput(BaseAgentOutput):
    """Typed output contract for the Intent Analyst agent."""

    requirements: list[Requirement] = Field(default_factory=list)
    ambiguity_questions: list[str] = Field(default_factory=list)


class ChangeInvestigatorOutput(BaseAgentOutput):
    """Typed output contract for the Change Investigator agent."""

    change_map: ChangeMap


class TestCoverageOutput(BaseAgentOutput):
    """Typed output contract for the Test & Coverage Agent."""

    test_inventory: list[TestInventoryItem] = Field(default_factory=list)
    requirement_to_tests: dict[str, list[str]] = Field(default_factory=dict)
    test_gap_findings: list[Finding] = Field(default_factory=list)
    test_proposals: list[TestProposal] = Field(default_factory=list)
    check_requests: list[CheckRequest] = Field(default_factory=list)


class AdversarialReviewerOutput(BaseAgentOutput):
    """Typed output contract for the Adversarial Reviewer agent."""

    hypotheses: list[AdversarialHypothesis] = Field(default_factory=list)
    hypothesis_findings: list[Finding] = Field(default_factory=list)
    targeted_check_requests: list[CheckRequest] = Field(default_factory=list)


class VerificationAgentOutput(BaseAgentOutput):
    """Typed output contract for the Verification Agent."""

    check_results: list[CheckResult] = Field(default_factory=list)


class AdjudicatorOutput(BaseAgentOutput):
    """Typed output contract for the Evidence Adjudicator agent."""

    verdict: Verdict
    requirements: list[Requirement] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    traceability: list[TraceabilityEntry] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

