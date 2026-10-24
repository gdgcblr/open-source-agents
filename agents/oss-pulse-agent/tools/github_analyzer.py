"""GitHub repository activity and maintenance analyzer.

Measures how actively a project is maintained — commit frequency,
issue response times, PR merge velocity, stale issues, and release cadence.
Every metric includes evidence and data coverage tracking.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from statistics import median as _std_median
from typing import Any, Optional

from models.report import (
    RepositoryMetadata,
    ActivityMetrics,
    Evidence,
    DataCoverage,
    Finding,
    Category,
    Severity,
    Confidence,
)
from tools.github_client import GitHubClient


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 datetime string from GitHub API."""
    if not s:
        return None
    try:
        cleaned = s.rstrip("Z") + "+00:00" if s.endswith("Z") else s
        return datetime.fromisoformat(cleaned)
    except Exception:
        return None


def _safe_median(values: list[float]) -> Optional[float]:
    """Return median of values, or None if list is empty."""
    if not values:
        return None
    return float(_std_median(values))


def get_repository_metadata(
    owner: str,
    repo: str,
    client: GitHubClient,
) -> RepositoryMetadata:
    """Fetch core repository metadata from the GitHub REST API."""
    data = client.get(f"/repos/{owner}/{repo}")
    if not data or not isinstance(data, dict):
        raise ValueError(f"Repository {owner}/{repo} not found or inaccessible")

    license_name = None
    if data.get("license") and isinstance(data["license"], dict):
        license_name = data["license"].get("spdx_id") or data["license"].get("name")

    return RepositoryMetadata(
        owner=data.get("owner", {}).get("login", owner),
        name=data.get("name", repo),
        full_name=data.get("full_name", f"{owner}/{repo}"),
        description=data.get("description"),
        url=data.get("html_url", f"https://github.com/{owner}/{repo}"),
        stars=data.get("stargazers_count", 0),
        forks=data.get("forks_count", 0),
        watchers=data.get("subscribers_count", 0),
        open_issues=data.get("open_issues_count", 0),
        language=data.get("language"),
        license_name=license_name,
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        pushed_at=data.get("pushed_at"),
        default_branch=data.get("default_branch", "main"),
        topics=data.get("topics", []) or [],
        is_fork=data.get("fork", False),
        is_archived=data.get("archived", False),
        has_wiki=data.get("has_wiki", False),
        has_discussions=data.get("has_discussions", False),
        size_kb=data.get("size", 0),
    )


def analyze_activity(
    owner: str,
    repo: str,
    client: GitHubClient,
) -> ActivityMetrics:
    """Analyze repository maintenance activity, velocity, and responsiveness."""
    now = datetime.now(timezone.utc)
    evidence: list[Evidence] = []
    coverage: list[DataCoverage] = []
    findings: list[Finding] = []

    commits_30d = 0
    commits_90d = 0
    commits_365d = 0
    avg_commits_per_week_90d = 0.0

    # 1. Commit Activity via Stats API
    try:
        stats = client.get(f"/repos/{owner}/{repo}/stats/commit_activity")
        if isinstance(stats, list) and len(stats) >= 52:
            weekly_totals = [w.get("total", 0) for w in stats]
            commits_30d = sum(weekly_totals[-4:])
            commits_90d = sum(weekly_totals[-13:])
            commits_365d = sum(weekly_totals)
            avg_commits_per_week_90d = round(commits_90d / 13.0, 2)

            evidence.append(
                Evidence(
                    source="GitHub REST API (commit_activity)",
                    metric="commits_90d",
                    value=commits_90d,
                    context=f"{commits_90d} commits recorded in the last 90 days (~{avg_commits_per_week_90d}/week)",
                    url=f"https://github.com/{owner}/{repo}/pulse",
                )
            )
            coverage.append(
                DataCoverage(
                    metric="commit_activity",
                    available=True,
                    sample_size=52,
                    measurement_window="52 weeks (365 days)",
                )
            )
        else:
            coverage.append(
                DataCoverage(
                    metric="commit_activity",
                    available=False,
                    reason="GitHub stats cache is computing or returned empty",
                )
            )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="commit_activity",
                available=False,
                reason=f"Failed to fetch commit activity: {str(e)}",
            )
        )

    # 2. Last Commit Date
    days_since_last_commit = 0
    last_commit_date_str: Optional[str] = None
    try:
        recent_commits = client.get(f"/repos/{owner}/{repo}/commits", params={"per_page": 1})
        if isinstance(recent_commits, list) and recent_commits:
            commit_meta = recent_commits[0].get("commit", {})
            author_meta = commit_meta.get("author") or commit_meta.get("committer") or {}
            last_commit_date_str = author_meta.get("date")
            parsed_last_commit = _parse_dt(last_commit_date_str)
            if parsed_last_commit:
                days_since_last_commit = max(0, (now - parsed_last_commit).days)
                evidence.append(
                    Evidence(
                        source="GitHub REST API (commits)",
                        metric="days_since_last_commit",
                        value=days_since_last_commit,
                        context=f"Most recent commit was {days_since_last_commit} days ago ({last_commit_date_str})",
                        url=f"https://github.com/{owner}/{repo}/commits",
                    )
                )
                coverage.append(
                    DataCoverage(
                        metric="last_commit_date",
                        available=True,
                        sample_size=1,
                        measurement_window="Latest commit",
                    )
                )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="last_commit_date",
                available=False,
                reason=f"Failed to fetch latest commit: {str(e)}",
            )
        )

    # 3. Issue Response Time (from recently closed issues)
    issue_response_time_median: Optional[float] = None
    try:
        closed_issues = client.get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "closed", "per_page": 30, "sort": "created", "direction": "desc"},
        )
        if isinstance(closed_issues, list):
            durations: list[float] = []
            for item in closed_issues:
                if "pull_request" in item:
                    continue
                c_at = _parse_dt(item.get("created_at"))
                cl_at = _parse_dt(item.get("closed_at"))
                if c_at and cl_at:
                    durations.append(max(0.0, (cl_at - c_at).total_seconds() / 3600.0))

            if durations:
                issue_response_time_median = round(_safe_median(durations) or 0.0, 1)
                evidence.append(
                    Evidence(
                        source="GitHub REST API (issues)",
                        metric="issue_response_time_median_hours",
                        value=issue_response_time_median,
                        context=f"Median issue resolution/response time is {issue_response_time_median:.1f} hours based on recent issues",
                        url=f"https://github.com/{owner}/{repo}/issues?q=is%3Aissue+is%3Aclosed",
                    )
                )
                coverage.append(
                    DataCoverage(
                        metric="issue_response_time",
                        available=True,
                        sample_size=len(durations),
                        measurement_window=f"Last {len(durations)} closed issues",
                    )
                )
            else:
                coverage.append(
                    DataCoverage(
                        metric="issue_response_time",
                        available=False,
                        reason="No closed issues found to measure resolution duration",
                    )
                )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="issue_response_time",
                available=False,
                reason=f"Failed to calculate issue response time: {str(e)}",
            )
        )

    # 4. PR Merge Time
    pr_merge_time_median: Optional[float] = None
    try:
        closed_prs = client.get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "closed", "per_page": 30, "sort": "created", "direction": "desc"},
        )
        if isinstance(closed_prs, list):
            pr_durations: list[float] = []
            for item in closed_prs:
                m_at = _parse_dt(item.get("merged_at"))
                c_at = _parse_dt(item.get("created_at"))
                if m_at and c_at:
                    pr_durations.append(max(0.0, (m_at - c_at).total_seconds() / 3600.0))

            if pr_durations:
                pr_merge_time_median = round(_safe_median(pr_durations) or 0.0, 1)
                evidence.append(
                    Evidence(
                        source="GitHub REST API (pulls)",
                        metric="pr_merge_time_median_hours",
                        value=pr_merge_time_median,
                        context=f"Median PR merge time is {pr_merge_time_median:.1f} hours based on recent merged pull requests",
                        url=f"https://github.com/{owner}/{repo}/pulls?q=is%3Apr+is%3Amerged",
                    )
                )
                coverage.append(
                    DataCoverage(
                        metric="pr_merge_time",
                        available=True,
                        sample_size=len(pr_durations),
                        measurement_window=f"Last {len(pr_durations)} merged PRs",
                    )
                )
            else:
                coverage.append(
                    DataCoverage(
                        metric="pr_merge_time",
                        available=False,
                        reason="No merged PRs found in sample",
                    )
                )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="pr_merge_time",
                available=False,
                reason=f"Failed to calculate PR merge velocity: {str(e)}",
            )
        )

    # 5. Stale Open Issues
    open_issues_count = 0
    stale_issues_count = 0
    stale_issues_percentage = 0.0
    try:
        open_issues = client.get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "open", "per_page": 100},
        )
        if isinstance(open_issues, list):
            real_open_issues = [item for item in open_issues if "pull_request" not in item]
            open_issues_count = len(real_open_issues)
            cutoff = now - timedelta(days=90)
            for it in real_open_issues:
                up_at = _parse_dt(it.get("updated_at"))
                if up_at and up_at < cutoff:
                    stale_issues_count += 1

            if open_issues_count > 0:
                stale_issues_percentage = round((stale_issues_count / open_issues_count) * 100.0, 1)

            evidence.append(
                Evidence(
                    source="GitHub REST API (issues/stale)",
                    metric="stale_issues_percentage",
                    value=stale_issues_percentage,
                    context=f"{stale_issues_count} of {open_issues_count} open issues have no activity in >90 days ({stale_issues_percentage:.1f}%)",
                    url=f"https://github.com/{owner}/{repo}/issues",
                )
            )
            coverage.append(
                DataCoverage(
                    metric="stale_issues",
                    available=True,
                    sample_size=open_issues_count,
                    measurement_window="Open issues (up to 100 sampled)",
                )
            )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="stale_issues",
                available=False,
                reason=f"Failed to inspect stale issues: {str(e)}",
            )
        )

    # 6. Releases cadence
    recent_releases_count = 0
    release_frequency_days: Optional[float] = None
    try:
        releases = client.get(f"/repos/{owner}/{repo}/releases", params={"per_page": 10})
        if isinstance(releases, list):
            cutoff_yr = now - timedelta(days=365)
            in_year = [
                r for r in releases
                if _parse_dt(r.get("published_at") or r.get("created_at")) and
                   _parse_dt(r.get("published_at") or r.get("created_at")) > cutoff_yr
            ]
            recent_releases_count = len(in_year)
            if recent_releases_count >= 2:
                release_frequency_days = round(365.0 / recent_releases_count, 1)

            evidence.append(
                Evidence(
                    source="GitHub REST API (releases)",
                    metric="recent_releases_count",
                    value=recent_releases_count,
                    context=f"{recent_releases_count} release(s) published in the last 365 days",
                    url=f"https://github.com/{owner}/{repo}/releases",
                )
            )
            coverage.append(
                DataCoverage(
                    metric="releases",
                    available=True,
                    sample_size=len(releases),
                    measurement_window="Releases in last 365 days",
                )
            )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="releases",
                available=False,
                reason=f"Failed to inspect releases: {str(e)}",
            )
        )

    # 7. Formulate Findings
    if days_since_last_commit > 180:
        findings.append(
            Finding(
                id="ACT-001",
                category=Category.ACTIVITY,
                severity=Severity.HIGH,
                title="Repository Appears Inactive (>180 Days Without Commits)",
                description=f"The last commit was recorded {days_since_last_commit} days ago. Inactive projects pose operational risks for users.",
                evidence=[e for e in evidence if e.metric == "days_since_last_commit"],
                impact="Potential contributors and adopters may consider the repository abandoned.",
                recommended_fix="Review open issues and PRs, release pending updates, or publish a status badge clarifying maintenance mode.",
                effort="low",
                confidence=Confidence.HIGH,
            )
        )
    elif days_since_last_commit > 90:
        findings.append(
            Finding(
                id="ACT-002",
                category=Category.ACTIVITY,
                severity=Severity.MEDIUM,
                title="Declining Commit Activity (>90 Days Since Last Commit)",
                description=f"No commits have been pushed for {days_since_last_commit} days.",
                evidence=[e for e in evidence if e.metric == "days_since_last_commit"],
                impact="Indicates slower turnaround and potential backlog accumulation.",
                recommended_fix="Triage existing pull requests and refresh the main branch.",
                effort="low",
                confidence=Confidence.HIGH,
            )
        )

    if stale_issues_percentage > 50 and open_issues_count >= 5:
        findings.append(
            Finding(
                id="ACT-003",
                category=Category.ACTIVITY,
                severity=Severity.MEDIUM,
                title="High Proportion of Stale Issues (>50%)",
                description=f"{stale_issues_percentage:.1f}% of open issues haven't received updates in over 90 days ({stale_issues_count}/{open_issues_count}).",
                evidence=[e for e in evidence if e.metric == "stale_issues_percentage"],
                impact="Backlog bloat makes it difficult for new contributors to discover actionable tasks.",
                recommended_fix="Conduct an issue triage sprint or enable GitHub actions (e.g. actions/stale) to prompt reporters.",
                effort="medium",
                confidence=Confidence.HIGH,
            )
        )

    if issue_response_time_median is not None and issue_response_time_median > 168:
        findings.append(
            Finding(
                id="ACT-005",
                category=Category.ACTIVITY,
                severity=Severity.MEDIUM,
                title="Prolonged Issue Resolution Time (>7 Days Median)",
                description=f"Median issue resolution time is {issue_response_time_median:.1f} hours ({issue_response_time_median / 24.0:.1f} days).",
                evidence=[e for e in evidence if e.metric == "issue_response_time_median_hours"],
                impact="Slow maintainer responses may discourage external community bug reports.",
                recommended_fix="Establish issue triage rotations or auto-responders setting SLA expectations.",
                effort="medium",
                confidence=Confidence.MEDIUM,
            )
        )

    if pr_merge_time_median is not None and pr_merge_time_median > 336:
        findings.append(
            Finding(
                id="ACT-006",
                category=Category.ACTIVITY,
                severity=Severity.MEDIUM,
                title="Extended PR Review/Merge Velocity (>14 Days Median)",
                description=f"Median merged pull request duration is {pr_merge_time_median:.1f} hours ({pr_merge_time_median / 24.0:.1f} days).",
                evidence=[e for e in evidence if e.metric == "pr_merge_time_median_hours"],
                impact="Contributors face long wait times, leading to merge conflicts and contributor fatigue.",
                recommended_fix="Add CODEOWNERS, configure automatic reviewer assignment, and split large PRs.",
                effort="medium",
                confidence=Confidence.MEDIUM,
            )
        )

    return ActivityMetrics(
        commits_30d=commits_30d,
        commits_90d=commits_90d,
        commits_365d=commits_365d,
        avg_commits_per_week_90d=avg_commits_per_week_90d,
        last_commit_date=last_commit_date_str,
        days_since_last_commit=days_since_last_commit,
        issue_response_time_median_hours=issue_response_time_median,
        pr_merge_time_median_hours=pr_merge_time_median,
        open_issues_count=open_issues_count,
        closed_issues_30d=0,
        stale_issues_count=stale_issues_count,
        stale_issues_percentage=stale_issues_percentage,
        recent_releases_count=recent_releases_count,
        release_frequency_days=release_frequency_days,
        evidence=evidence,
        data_coverage=coverage,
    )
