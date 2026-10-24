"""Pydantic models for OSS Pulse Agent health reports.

Every model is designed to carry evidence — no score or finding exists without
traceable data backing it up.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    """Finding severity levels, ordered from most to least critical."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Confidence(str, Enum):
    """Confidence levels for findings and scores."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Category(str, Enum):
    """Health report categories with defined weights."""
    ACTIVITY = "activity"
    SECURITY = "security"
    DOCUMENTATION = "documentation"
    COMMUNITY = "community"


# Category weights for overall score calculation
CATEGORY_WEIGHTS: dict[Category, float] = {
    Category.ACTIVITY: 0.30,
    Category.SECURITY: 0.25,
    Category.DOCUMENTATION: 0.20,
    Category.COMMUNITY: 0.25,
}


# ---------------------------------------------------------------------------
# Evidence & Findings
# ---------------------------------------------------------------------------

class Evidence(BaseModel):
    """A piece of verifiable evidence supporting a finding or score."""
    source: str = Field(description="Data source, e.g. 'GitHub REST API', 'Repository file check'")
    metric: str = Field(description="Metric identifier, e.g. 'commits_30d', 'has_security_policy'")
    value: Any = Field(description="The measured value")
    context: str = Field(description="Human-readable explanation of what this value means")
    url: Optional[str] = Field(default=None, description="URL where this evidence can be verified")


class Finding(BaseModel):
    """An actionable finding from the repository analysis.

    Each finding is backed by evidence and includes a specific,
    actionable recommendation with estimated effort.
    """
    id: str = Field(description="Unique finding identifier, e.g. 'SEC-001'")
    category: Category
    severity: Severity
    title: str
    description: str
    evidence: list[Evidence] = Field(default_factory=list)
    impact: str = Field(description="What impact this has on the project")
    recommended_fix: str = Field(description="Specific, actionable fix recommendation")
    effort: str = Field(description="Estimated effort: 'low', 'medium', or 'high'")
    confidence: Confidence


class DataCoverage(BaseModel):
    """Tracks whether a specific metric was successfully measured.

    Transparency about what we could and could not measure is critical
    for trustworthy AI. Missing data is never silently treated as zero
    or as a pass.
    """
    metric: str
    available: bool
    reason: Optional[str] = Field(default=None, description="Why data is unavailable")
    sample_size: Optional[int] = None
    measurement_window: Optional[str] = None


# ---------------------------------------------------------------------------
# Category-specific result models
# ---------------------------------------------------------------------------

class RepositoryMetadata(BaseModel):
    """Basic repository information from GitHub API."""
    owner: str
    name: str
    full_name: str
    description: Optional[str] = None
    url: str
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    open_issues: int = 0
    language: Optional[str] = None
    license_name: Optional[str] = None
    created_at: str
    updated_at: str
    pushed_at: Optional[str] = None
    default_branch: str = "main"
    topics: list[str] = Field(default_factory=list)
    is_fork: bool = False
    is_archived: bool = False
    has_wiki: bool = False
    has_discussions: bool = False
    size_kb: int = 0


class ActivityMetrics(BaseModel):
    """Repository activity and maintenance metrics.

    Measures how actively a project is maintained, not just how popular it is.
    All temporal metrics include their measurement window and sample size.
    """
    commits_30d: int = 0
    commits_90d: int = 0
    commits_365d: int = 0
    avg_commits_per_week_90d: float = 0.0
    last_commit_date: Optional[str] = None
    days_since_last_commit: int = 0
    issue_response_time_median_hours: Optional[float] = None
    pr_merge_time_median_hours: Optional[float] = None
    open_issues_count: int = 0
    closed_issues_30d: int = 0
    stale_issues_count: int = 0
    stale_issues_percentage: float = 0.0
    recent_releases_count: int = 0
    release_frequency_days: Optional[float] = None
    evidence: list[Evidence] = Field(default_factory=list)
    data_coverage: list[DataCoverage] = Field(default_factory=list)


class SecurityConfig(BaseModel):
    """Security configuration analysis results.

    Inspects observable security practices — this is NOT a vulnerability
    scan or security audit.
    """
    has_security_policy: bool = False
    security_policy_url: Optional[str] = None
    has_dependabot_config: bool = False
    dependabot_ecosystems: list[str] = Field(default_factory=list)
    has_code_scanning: bool = False
    code_scanning_tools: list[str] = Field(default_factory=list)
    has_secret_scanning: bool = False
    dependency_manifests: list[str] = Field(default_factory=list)
    has_branch_protection: Optional[bool] = None
    evidence: list[Evidence] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    data_coverage: list[DataCoverage] = Field(default_factory=list)


class DocumentationQuality(BaseModel):
    """Documentation analysis results.

    Evaluates not just whether documentation files exist, but whether
    they contain the sections developers actually need.
    """
    has_readme: bool = False
    readme_length_chars: int = 0
    readme_has_badges: bool = False
    readme_has_installation: bool = False
    readme_has_usage: bool = False
    readme_has_examples: bool = False
    readme_has_api_docs: bool = False
    readme_sections: list[str] = Field(default_factory=list)
    has_contributing: bool = False
    has_license: bool = False
    license_type: Optional[str] = None
    has_code_of_conduct: bool = False
    has_changelog: bool = False
    has_issue_templates: bool = False
    has_pr_templates: bool = False
    has_docs_directory: bool = False
    evidence: list[Evidence] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    data_coverage: list[DataCoverage] = Field(default_factory=list)


class CommunityHealth(BaseModel):
    """Community health analysis results.

    Analyzes contributor ecosystem health, including bus factor analysis
    and contribution readiness for newcomers.
    """
    total_contributors: int = 0
    recent_contributors_90d: int = 0
    bus_factor: int = 0
    contributor_concentration: float = 0.0
    has_discussions: bool = False
    good_first_issues_count: int = 0
    help_wanted_issues_count: int = 0
    contribution_opportunities: list[ContributionOpportunity] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    data_coverage: list[DataCoverage] = Field(default_factory=list)


class ContributionOpportunity(BaseModel):
    """A recommended opportunity to contribute to the repository."""
    title: str
    url: str
    labels: list[str] = Field(default_factory=list)
    difficulty: str = Field(description="'beginner', 'intermediate', or 'advanced'")
    why_good_fit: str
    created_at: Optional[str] = None
    comments_count: int = 0
    is_assigned: bool = False


# ---------------------------------------------------------------------------
# Scoring & Report
# ---------------------------------------------------------------------------

class CategoryScore(BaseModel):
    """Score for a single health category with full evidence trail."""
    category: Category
    score: float = Field(ge=0, le=100, description="Score out of 100")
    weight: float = Field(description="Weight in overall score calculation")
    weighted_score: float = Field(default=0.0, description="score * weight")
    evidence_summary: str = Field(description="Brief explanation of the score")
    findings: list[Finding] = Field(default_factory=list)
    data_coverage: list[DataCoverage] = Field(default_factory=list)
    sub_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Breakdown of sub-metric scores, e.g. {'commit_frequency': 85, 'issue_response': 70}"
    )
    sufficient_data: bool = Field(
        default=True,
        description="Whether enough data was available to calculate a meaningful score"
    )


class HealthReport(BaseModel):
    """Complete repository health report with evidence-backed scoring.

    The report links every score and finding to verifiable evidence,
    tracks data coverage, and provides actionable recommendations
    prioritized by impact and effort.
    """
    repository: RepositoryMetadata
    overall_score: float = Field(ge=0, le=100)
    overall_grade: str = Field(description="Letter grade: A+, A, B+, B, C+, C, D, F")
    category_scores: list[CategoryScore] = Field(default_factory=list)
    all_findings: list[Finding] = Field(default_factory=list)
    contribution_opportunities: list[ContributionOpportunity] = Field(default_factory=list)
    ai_summary: str = ""
    ai_recommendations: list[str] = Field(default_factory=list)
    data_coverage_summary: dict[str, int] = Field(
        default_factory=dict,
        description="{'measured': N, 'unavailable': M, 'insufficient': K}"
    )
    data_coverage_percentage: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description="Percentage of verifiable metrics successfully collected",
    )
    evidence_quality: str = Field(
        default="High",
        description="Confidence tier based on coverage: 'High' (>80%), 'Medium' (50-80%), 'Low' (<50%)",
    )
    analysis_timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    analysis_duration_seconds: float = 0.0
    disclaimer: str = Field(
        default=(
            "This health score reflects publicly observable repository metrics and "
            "configuration. It is not a security audit, code quality assessment, or "
            "endorsement. A lower score may reflect a project's stage or scope rather "
            "than its quality."
        )
    )


# Update forward references
CommunityHealth.model_rebuild()
