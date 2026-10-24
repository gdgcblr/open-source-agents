"""Pydantic models for the Code Correctness Reviewer agent."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RequirementStatus(str, Enum):
    """Status of a single requirement after review."""
    IMPLEMENTED = "implemented"
    PARTIALLY_IMPLEMENTED = "partially_implemented"
    MISSING = "missing"
    MISINTERPRETED = "misinterpreted"


class IssueSeverity(str, Enum):
    """Severity level of a detected issue."""
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class IssueCategory(str, Enum):
    """Category of a detected issue."""
    MISSING_REQUIREMENT = "missing_requirement"
    MISINTERPRETATION = "misinterpretation"
    SCOPE_CREEP = "scope_creep"
    LOGIC_ERROR = "logic_error"
    SECURITY_CONCERN = "security_concern"
    INCOMPLETE_IMPLEMENTATION = "incomplete_implementation"


class Verdict(str, Enum):
    """Overall verdict for the review."""
    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVISION = "needs_revision"


# --- Input Models ---

class ReviewRequest(BaseModel):
    """Input payload for the correctness review."""
    intent_context: str = Field(
        ...,
        description=(
            "The original intent context: JIRA ticket description, HLD, "
            "meeting notes, acceptance criteria — everything the developer "
            "fed to the coding AI."
        ),
    )
    code_diff: str = Field(
        ...,
        description=(
            "The code changes produced by the coding AI. "
            "Can be a unified diff / patch, or raw file contents."
        ),
    )
    language: str = Field(
        default="python",
        description="Primary programming language of the changes.",
    )
    repo_context: Optional[str] = Field(
        default=None,
        description=(
            "Optional additional context about the existing codebase — "
            "file tree, relevant existing code, architecture notes."
        ),
    )


# --- Output Models ---

class ExtractedRequirement(BaseModel):
    """A single requirement extracted from the intent context."""
    id: str = Field(..., description="Short identifier, e.g. REQ-1, REQ-2.")
    description: str = Field(..., description="What this requirement asks for.")
    acceptance_criteria: Optional[str] = Field(
        default=None,
        description="Specific acceptance criteria if stated.",
    )
    priority: str = Field(
        default="must_have",
        description="Priority: must_have, should_have, or nice_to_have.",
    )


class RequirementResult(BaseModel):
    """Assessment of a single requirement against the code changes."""
    id: str = Field(..., description="Requirement ID (matches ExtractedRequirement.id).")
    description: str = Field(..., description="Requirement description.")
    status: RequirementStatus = Field(..., description="Implementation status.")
    evidence: Optional[str] = Field(
        default=None,
        description="File and line reference from the diff supporting this assessment.",
    )
    explanation: str = Field(
        ...,
        description="Detailed explanation of why this status was assigned.",
    )


class UnmatchedChange(BaseModel):
    """A code change that doesn't map to any stated requirement (scope creep)."""
    location: str = Field(..., description="File and line or function reference.")
    description: str = Field(..., description="What this change does.")
    risk_assessment: str = Field(
        ...,
        description="Why this unrequested change could be problematic.",
    )


class Issue(BaseModel):
    """A specific problem detected during the review."""
    severity: IssueSeverity
    category: IssueCategory
    description: str = Field(..., description="Clear description of the issue.")
    location: Optional[str] = Field(
        default=None,
        description="File and line reference if applicable.",
    )
    requirement_id: Optional[str] = Field(
        default=None,
        description="Which requirement this relates to, if any.",
    )
    suggestion: Optional[str] = Field(
        default=None,
        description="Suggested fix or action.",
    )


class ReviewVerdict(BaseModel):
    """Complete structured output from the correctness review."""
    verdict: Verdict = Field(
        ...,
        description="Overall verdict: pass, fail, or needs_revision.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in the verdict (0.0 to 1.0).",
    )
    requirements: List[RequirementResult] = Field(
        default_factory=list,
        description="Per-requirement assessment results.",
    )
    unmatched_changes: List[UnmatchedChange] = Field(
        default_factory=list,
        description="Code changes not tied to any stated requirement.",
    )
    issues: List[Issue] = Field(
        default_factory=list,
        description="All issues detected during review.",
    )
    summary: str = Field(
        ...,
        description="Human-readable summary of the review findings.",
    )

