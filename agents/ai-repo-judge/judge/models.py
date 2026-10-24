"""Data contract shared by analyzers, scoring, storage and the dashboard (web/src/types.ts mirrors it)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "low", "medium", "high", "critical"]
Status = Literal["pass", "warn", "fail", "skip"]
Verdict = Literal["ready", "needs_changes", "blocked"]
DimensionKey = Literal["compliance", "security", "quality", "functionality", "ai_native", "docs", "innovation"]

SEVERITY_RANK: dict[str, int] = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


class Finding(BaseModel):
    dimension: DimensionKey
    severity: Severity
    title: str
    detail: str = ""
    file: str | None = None
    line: int | None = None
    snippet: str | None = None
    fix: str | None = None
    commit: str | None = None
    source: Literal["static", "llm"] = "static"
    gate: bool = False  # a gating finding blocks the merge regardless of score


class Check(BaseModel):
    id: str
    dimension: DimensionKey
    label: str
    status: Status
    weight: float = 1.0
    score: float | None = None  # 0..1; overrides the pass/warn/fail mapping when set
    detail: str = ""
    fix: str | None = None


class AnalyzerResult(BaseModel):
    checks: list[Check] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    facts: dict[str, Any] = Field(default_factory=dict)


class FileInfo(BaseModel):
    path: str
    lines: int
    language: str
    findings: int = 0


class Claim(BaseModel):
    feature: str
    status: Literal["implemented", "partial", "missing", "unverified"]
    evidence: str = ""


class SimilarRef(BaseModel):
    id: str
    slug: str
    title: str
    score: float
    kind: Literal["idea", "code"]


class HistoryPoint(BaseModel):
    sha: str
    judged_at: str
    overall: int
    verdict: Verdict


class DimensionResult(BaseModel):
    key: DimensionKey
    label: str
    weight: float
    purpose: str
    score: int | None
    static_score: int | None
    llm_score: int | None
    llm_share: float
    llm_rationale: str | None = None
    checks: list[Check] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class LLMInfo(BaseModel):
    used: bool = False
    provider: str | None = None
    model: str | None = None
    tokens: int = 0
    error: str | None = None


class SubmissionMeta(BaseModel):
    """What we know about a submission before analysing its code."""

    id: str
    number: int | None = None
    title: str = ""
    url: str | None = None
    author: str | None = None
    author_avatar: str | None = None
    state: Literal["open", "closed", "merged", "local"] = "open"
    created_at: str | None = None
    updated_at: str | None = None
    head_sha: str = ""
    head_ref: str | None = None
    base_sha: str | None = None
    body: str = ""
    partial: bool = False  # metadata came from git refs only (GitHub API unavailable)


class Submission(BaseModel):
    """A fully judged submission, as published to the dashboard."""

    id: str
    number: int | None
    title: str
    url: str | None
    author: str | None
    author_avatar: str | None
    state: str
    created_at: str | None
    updated_at: str | None
    head_sha: str
    category: Literal["agents", "tools", "unknown"]
    slug: str
    project_path: str
    extra_projects: list[str] = Field(default_factory=list)
    files: list[FileInfo]
    loc: int
    languages: dict[str, int]
    frameworks: list[str]
    providers: list[str]
    ai_level: int
    ai_level_label: str
    ai_level_evidence: list[str]
    claims: list[Claim]
    summary: str | None
    strengths: list[str]
    top_fixes: list[str]
    dimensions: list[DimensionResult]
    overall: int
    verdict: Verdict
    gates: list[str]
    confidence: int
    manipulation_suspected: bool
    llm: LLMInfo
    similar: list[SimilarRef]
    history: list[HistoryPoint]
    judged_at: str
    judge_version: str


class SubmissionSummary(BaseModel):
    """Compact row for the overview page."""

    id: str
    number: int | None
    title: str
    url: str | None
    author: str | None
    author_avatar: str | None
    state: str
    category: str
    slug: str
    overall: int
    verdict: Verdict
    confidence: int
    scores: dict[str, int | None]
    frameworks: list[str]
    providers: list[str]
    languages: list[str]
    ai_level: int
    ai_level_label: str
    severity_counts: dict[str, int]
    top_fix: str | None
    head_sha: str
    judged_at: str
    updated_at: str | None
    llm_used: bool
