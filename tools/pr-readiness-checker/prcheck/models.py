"""Data shapes shared by the checks, the runner, the CLI and the JSON report.

The JSON report is the contract other front ends (MCP server, GitHub Action,
fix-mode agent) build on, so it carries a schema_version. Bump it when a field
is renamed or removed; adding optional fields is backwards compatible.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

REPORT_SCHEMA_VERSION = "1"


class Severity(str, Enum):
    ERROR = "error"  # the PR would be rejected
    WARN = "warn"  # a reviewer will probably ask for a change
    INFO = "info"  # worth knowing, never blocks

    @property
    def rank(self) -> int:
        return {"error": 3, "warn": 2, "info": 1}[self.value]


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"  # at least one error finding
    WARN = "warn"  # worst finding is a warning
    INFO = "info"  # only informational findings
    SKIP = "skip"  # the check could not run (e.g. no git, no README)
    CRASH = "crash"  # the check itself raised an exception (a bug in prcheck)


class Finding(BaseModel):
    message: str
    severity: Severity
    file: str | None = None  # path relative to the project folder
    line: int | None = None


class CheckResult(BaseModel):
    id: str
    group: str
    title: str
    status: Status
    findings: list[Finding] = Field(default_factory=list)
    skip_reason: str | None = None


class Summary(BaseModel):
    errors: int = 0
    warnings: int = 0
    infos: int = 0
    passed: int = 0
    failed: int = 0
    warned: int = 0
    skipped: int = 0
    crashed: int = 0
    ready: bool = False
    strict: bool = False


class CriterionScore(BaseModel):
    criterion: str
    score: int = Field(ge=1, le=5)
    reason: str
    suggestions: list[str] = Field(default_factory=list)


class ReadmeReview(BaseModel):
    criteria: list[CriterionScore]
    summary: str
    top_fixes: list[str] = Field(default_factory=list)


class AIUsage(BaseModel):
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    attempts: int = 0


AIStatus = Literal["ok", "skipped", "error", "invalid_output"]


class AIResult(BaseModel):
    """Advisory only: never changes Summary.ready or the exit code."""

    status: AIStatus
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    message: str | None = None
    review: ReadmeReview | None = None
    usage: AIUsage = Field(default_factory=AIUsage)
    flags: list[str] = Field(default_factory=list)  # e.g. suspected prompt injection
    notes: list[str] = Field(default_factory=list)  # setup hints, e.g. an ignored .env value
    truncated: bool = False
    redactions: int = 0


class Metrics(BaseModel):
    duration_ms: int = 0
    files_listed: int = 0
    files_scanned: int = 0
    bytes_scanned: int = 0


class Report(BaseModel):
    schema_version: str = REPORT_SCHEMA_VERSION
    tool_version: str
    target: str
    category: str | None = None
    slug: str
    repo_root: str | None = None
    file_mode: Literal["git", "filesystem"]
    base: str | None = None
    template_source: Literal["repo", "bundled"]
    checks: list[CheckResult]
    summary: Summary
    ai: AIResult | None = None
    metrics: Metrics = Field(default_factory=Metrics)
