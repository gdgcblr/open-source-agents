"""Structured data contracts for RunReady.

These dataclasses define the *shape* of diagnoses and patches. They are a
documentation and validation aid only. A schema-valid object is NOT trusted:
``runready.policy`` independently re-validates every path, hash, and state
transition before any consequential action. Structured output is not a
security boundary.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field


class PatchState(enum.Enum):
    """Lifecycle of a proposed patch.

    Transitions are enforced by :func:`runready.policy.assert_transition`.
    ``APPLIED`` and ``VERIFIED`` are deliberately distinct: a patch that was
    written to disk is *applied*, not *verified*. Only a passing bounded check
    promotes ``APPLIED -> VERIFIED``.
    """

    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    APPLIED = "APPLIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


# Legal forward transitions. Anything not listed here is rejected.
LEGAL_TRANSITIONS: dict[PatchState, frozenset[PatchState]] = {
    PatchState.PROPOSED: frozenset({PatchState.VALIDATED, PatchState.REJECTED}),
    PatchState.VALIDATED: frozenset({PatchState.AWAITING_APPROVAL, PatchState.REJECTED}),
    PatchState.AWAITING_APPROVAL: frozenset({PatchState.APPROVED, PatchState.REJECTED}),
    PatchState.APPROVED: frozenset({PatchState.APPLIED, PatchState.REJECTED}),
    PatchState.APPLIED: frozenset({PatchState.VERIFIED, PatchState.REJECTED}),
    PatchState.VERIFIED: frozenset(),
    PatchState.REJECTED: frozenset(),
}


class CheckStatus(enum.Enum):
    """Honest outcome of a bounded validation check.

    ``NOT_RUN`` and ``SKIPPED`` are first-class: a check that could not run
    safely is never silently reported as a pass.
    """

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True)
class Evidence:
    """A single piece of grounding tying a finding to the real project."""

    source: str  # e.g. "deployment configuration", "startup log"
    path: str  # workspace-relative path the excerpt came from
    detail: str  # verified excerpt or value (already secret-redacted)


@dataclass(frozen=True)
class ProposedChange:
    """The exact intended edit to one file. No write happens at proposal time."""

    path: str  # workspace-relative target path
    expected_original_sha256: str  # hash of the file RunReady read
    original_snippet: str  # the exact text to replace
    replacement_snippet: str  # the exact replacement text
    rationale: str  # why this specific minimal change


@dataclass
class Finding:
    """An evidence-backed diagnosis hypothesis. Not a confirmed fact."""

    category: str
    summary: str
    hypothesis: str
    uncertainty: str
    evidence: list[Evidence] = field(default_factory=list)
    verification_steps: list[str] = field(default_factory=list)
    proposed_changes: list[ProposedChange] = field(default_factory=list)


@dataclass
class CheckResult:
    """Result of one bounded validation command."""

    name: str
    status: CheckStatus
    detail: str  # redacted stdout/stderr excerpt or reason for SKIPPED/NOT_RUN
