"""Data models for git-pr-review-agent."""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ReviewSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    SUGGESTION = "SUGGESTION"
    INFO = "INFO"


class ReviewCategory(str, Enum):
    SECURITY = "security"
    BUG = "bug"
    PERFORMANCE = "performance"
    STYLE = "style"
    MAINTAINABILITY = "maintainability"


class ReviewIssue(BaseModel):
    file_path: str = Field(..., description="Path to the file where the issue was found")
    line_number: Optional[int] = Field(None, description="Line number if applicable")
    severity: ReviewSeverity = Field(..., description="Severity of the issue")
    category: ReviewCategory = Field(..., description="Category of the finding")
    title: str = Field(..., description="Short summary of the issue")
    description: str = Field(..., description="Detailed explanation of the problem")
    suggestion: Optional[str] = Field(None, description="Recommended remediation or code change")


class PullRequestSummary(BaseModel):
    title: str = Field(..., description="Conventional PR title (e.g., feat(auth): add OAuth2 refresh token)")
    type: str = Field(..., description="Type of change: feat, fix, refactor, docs, perf, chore, test")
    summary: str = Field(..., description="High-level 2-3 sentence overview of changes")
    key_changes: List[str] = Field(default_factory=list, description="Bullet points of core changes")
    breaking_changes: List[str] = Field(default_factory=list, description="List of any breaking changes or N/A")
    security_implications: List[str] = Field(default_factory=list, description="Security analysis notes")
    testing_checklist: List[str] = Field(default_factory=list, description="Actionable verification checklist items")


class ReviewReport(BaseModel):
    pr_summary: PullRequestSummary
    issues: List[ReviewIssue] = Field(default_factory=list)
    risk_score: int = Field(..., ge=0, le=100, description="Risk score from 0 (spotless) to 100 (critical hazard)")
    verdict: str = Field(..., description="APPROVE, REQUEST_CHANGES, or COMMENT")
    statistics: Dict[str, Any] = Field(default_factory=dict, description="Git change stats (files, additions, deletions)")
    model_used: str = Field(..., description="Model identifier used for analysis")
    timestamp: str = Field(..., description="ISO 8601 evaluation timestamp")


class ReviewRequest(BaseModel):
    diff_text: Optional[str] = Field(None, description="Raw git diff text to evaluate")
    branch: Optional[str] = Field("main", description="Target base branch to compare against")
    staged_only: bool = Field(False, description="Whether to review staged changes only")
    repo_path: Optional[str] = Field(".", description="Path to git repository")
    provider: Optional[str] = Field(None, description="LLM provider: gemini, ollama, or mock")
    model_name: Optional[str] = Field(None, description="Model identifier override")
