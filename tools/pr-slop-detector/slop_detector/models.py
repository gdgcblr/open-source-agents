"""Data models shared by the fetcher, heuristics engine, ADK agent, and reporter."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ChangedFile(BaseModel):
    filename: str
    status: str = "modified"  # added | modified | removed | renamed
    additions: int = 0
    deletions: int = 0
    patch: str | None = None  # unified diff hunk text; None for binary / huge files


class AuthorInfo(BaseModel):
    login: str = "unknown"
    account_created_at: str | None = None  # ISO-8601
    association: str = "NONE"  # OWNER | MEMBER | CONTRIBUTOR | FIRST_TIME_CONTRIBUTOR | NONE ...
    recent_pr_count: int | None = None  # PRs opened across GitHub in the lookback window
    recent_pr_repo_count: int | None = None  # distinct repos those PRs went to


class PullRequest(BaseModel):
    repo: str = "local/local"
    number: int = 0
    title: str = ""
    body: str = ""
    url: str | None = None
    created_at: str | None = None
    author: AuthorInfo = Field(default_factory=AuthorInfo)
    files: list[ChangedFile] = Field(default_factory=list)
    commit_messages: list[str] = Field(default_factory=list)
    # Dependency manifests from the head ref, keyed by path (requirements.txt, package.json, ...)
    manifests: dict[str, str] = Field(default_factory=dict)
    # Names of every directory and module in the repo tree, so imports of local code aren't flagged
    local_modules: list[str] = Field(default_factory=list)

    @property
    def additions(self) -> int:
        return sum(f.additions for f in self.files)

    @property
    def deletions(self) -> int:
        return sum(f.deletions for f in self.files)


class Signal(BaseModel):
    """One deterministic heuristic finding."""

    id: str
    category: str  # description | diff | context
    title: str
    weight: int  # contribution to the 0-100 heuristic score
    evidence: list[str] = Field(default_factory=list)


class HeuristicReport(BaseModel):
    score: int
    signals: list[Signal]


class Verdict(str, Enum):
    LOOKS_GOOD = "looks_good"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    LIKELY_SLOP = "likely_slop"


class LlmFinding(BaseModel):
    claim: str = Field(description="What is wrong, in one sentence.")
    file: str | None = Field(default=None, description="File path the evidence comes from, if any.")
    evidence: str = Field(description="Short verbatim snippet from the PR that supports the claim.")
    severity: str = Field(description="One of: low, medium, high.")


class LlmVerdict(BaseModel):
    """Structured output of the ADK reviewer agent."""

    slop_score: int = Field(ge=0, le=100, description="0 = careful, substantive work; 100 = pure low-effort slop.")
    verdict: Verdict
    summary: str = Field(description="Two or three sentences a maintainer can read in ten seconds.")
    findings: list[LlmFinding] = Field(default_factory=list)
    questions_for_author: list[str] = Field(
        default_factory=list,
        description="Specific questions that a contributor who understands their change can answer easily.",
    )
    strengths: list[str] = Field(default_factory=list, description="Genuinely good aspects of the PR, if any.")


class FinalReport(BaseModel):
    pr: PullRequest
    heuristics: HeuristicReport
    llm: LlmVerdict | None = None
    llm_error: str | None = None
    score: int
    verdict: Verdict
    threshold: int
