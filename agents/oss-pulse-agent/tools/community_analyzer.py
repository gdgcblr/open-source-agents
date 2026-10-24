"""Community health and contribution readiness analyzer.

Analyzes contributor ecosystem health, bus factor, and identifies
concrete opportunities for new contributors.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional

from models.report import (
    CommunityHealth,
    ContributionOpportunity,
    Evidence,
    DataCoverage,
    Finding,
    Category,
    Severity,
    Confidence,
)
from tools.github_client import GitHubClient


def analyze_community(
    owner: str,
    repo: str,
    client: GitHubClient,
) -> CommunityHealth:
    """Analyze contributor distribution, community engagement, and contribution paths."""
    evidence: list[Evidence] = []
    coverage: list[DataCoverage] = []
    findings: list[Finding] = []

    total_contributors = 0
    recent_contributors_90d = 0
    bus_factor = 1
    contributor_concentration = 1.0

    # 1. Contributors API
    try:
        contrib_list = client.get(f"/repos/{owner}/{repo}/contributors", params={"per_page": 100})
        if isinstance(contrib_list, list):
            total_contributors = len(contrib_list)
            total_commits_sample = sum(c.get("contributions", 0) for c in contrib_list)

            if total_commits_sample > 0:
                top_contrib_commits = contrib_list[0].get("contributions", 0) if contrib_list else 0
                contributor_concentration = round(top_contrib_commits / total_commits_sample, 2)

                # Calculate bus factor: how many contributors account for >= 50% of commits
                running_sum = 0
                bus_count = 0
                target_threshold = total_commits_sample * 0.50
                for c in contrib_list:
                    running_sum += c.get("contributions", 0)
                    bus_count += 1
                    if running_sum >= target_threshold:
                        break
                bus_factor = max(1, bus_count)

            evidence.append(
                Evidence(
                    source="GitHub Contributors API",
                    metric="bus_factor",
                    value=bus_factor,
                    context=f"Calculated Bus Factor is {bus_factor} ({total_contributors} total contributors, "
                    f"top contributor accounts for {contributor_concentration:.0%} of sample commits)",
                    url=f"https://github.com/{owner}/{repo}/graphs/contributors",
                )
            )
            coverage.append(
                DataCoverage(
                    metric="contributors",
                    available=True,
                    sample_size=total_contributors,
                    measurement_window="All-time commit distribution",
                )
            )
        else:
            coverage.append(
                DataCoverage(
                    metric="contributors",
                    available=False,
                    reason="Contributors list empty or not accessible",
                )
            )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="contributors",
                available=False,
                reason=f"Failed to query contributors: {str(e)}",
            )
        )

    # 2. Recent Contributors (90 days) via Stats API
    try:
        contributor_stats = client.get(f"/repos/{owner}/{repo}/stats/contributors")
        if isinstance(contributor_stats, list):
            active_last_90d = 0
            for person in contributor_stats:
                weeks = person.get("weeks", [])
                recent_weeks = weeks[-13:] if len(weeks) >= 13 else weeks
                if any(w.get("c", 0) > 0 for w in recent_weeks):
                    active_last_90d += 1
            recent_contributors_90d = active_last_90d
            evidence.append(
                Evidence(
                    source="GitHub Stats API (contributors)",
                    metric="recent_contributors_90d",
                    value=recent_contributors_90d,
                    context=f"{recent_contributors_90d} contributor(s) made commits in the last 90 days",
                    url=f"https://github.com/{owner}/{repo}/graphs/contributors",
                )
            )
        else:
            recent_contributors_90d = 1 if total_contributors > 0 else 0
    except Exception:
        recent_contributors_90d = 1 if total_contributors > 0 else 0

    # 3. Community features (Discussions)
    has_discussions = False
    try:
        repo_data = client.get(f"/repos/{owner}/{repo}")
        if isinstance(repo_data, dict):
            has_discussions = repo_data.get("has_discussions", False)
    except Exception:
        pass

    # 4. Good First Issues & Contribution Opportunities
    good_first_issues_count = 0
    help_wanted_issues_count = 0
    opportunities: list[ContributionOpportunity] = []

    try:
        gfi_issues = client.get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "open", "labels": "good first issue", "per_page": 10},
        )
        if isinstance(gfi_issues, list):
            good_first_issues_count = len(gfi_issues)
            for iss in gfi_issues:
                if "pull_request" in iss:
                    continue
                label_names = [lbl.get("name", "") for lbl in iss.get("labels", []) if isinstance(lbl, dict)]
                opportunities.append(
                    ContributionOpportunity(
                        title=iss.get("title", ""),
                        url=iss.get("html_url", ""),
                        labels=label_names,
                        difficulty="beginner",
                        why_good_fit="Explicitly labeled by maintainers as 'good first issue' for newcomers",
                        created_at=iss.get("created_at"),
                        comments_count=iss.get("comments", 0),
                        is_assigned=bool(iss.get("assignee")),
                    )
                )

        hw_issues = client.get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "open", "labels": "help wanted", "per_page": 10},
        )
        if isinstance(hw_issues, list):
            help_wanted_issues_count = len(hw_issues)
            for iss in hw_issues:
                if "pull_request" in iss:
                    continue
                if any(op.url == iss.get("html_url") for op in opportunities):
                    continue
                label_names = [lbl.get("name", "") for lbl in iss.get("labels", []) if isinstance(lbl, dict)]
                opportunities.append(
                    ContributionOpportunity(
                        title=iss.get("title", ""),
                        url=iss.get("html_url", ""),
                        labels=label_names,
                        difficulty="intermediate",
                        why_good_fit="Marked as 'help wanted', ideal for developers looking for scoped problems",
                        created_at=iss.get("created_at"),
                        comments_count=iss.get("comments", 0),
                        is_assigned=bool(iss.get("assignee")),
                    )
                )

        evidence.append(
            Evidence(
                source="GitHub Issues API (Labels)",
                metric="good_first_issues_count",
                value=good_first_issues_count,
                context=f"Found {good_first_issues_count} 'good first issue' and {help_wanted_issues_count} 'help wanted' issues",
                url=f"https://github.com/{owner}/{repo}/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22",
            )
        )
        coverage.append(
            DataCoverage(
                metric="contribution_opportunities",
                available=True,
                sample_size=len(opportunities),
                measurement_window="Open labeled issues",
            )
        )
    except Exception as e:
        coverage.append(
            DataCoverage(
                metric="contribution_opportunities",
                available=False,
                reason=f"Failed to query labeled issues: {str(e)}",
            )
        )

    # Formulate Findings
    if bus_factor == 1 and total_contributors > 1:
        findings.append(
            Finding(
                id="COM-001",
                category=Category.COMMUNITY,
                severity=Severity.HIGH,
                title="Single Maintainer Dependency (Bus Factor = 1)",
                description=f"A single contributor accounts for more than 50% of the project's commit history (concentration: {contributor_concentration:.0%}).",
                evidence=[e for e in evidence if e.metric == "bus_factor"],
                impact="If the primary maintainer steps away or becomes unavailable, development and bug fixes may stall.",
                recommended_fix="Invite frequent contributors as co-maintainers and grant triage / review permissions.",
                effort="high",
                confidence=Confidence.HIGH,
            )
        )

    if good_first_issues_count == 0:
        findings.append(
            Finding(
                id="COM-002",
                category=Category.COMMUNITY,
                severity=Severity.MEDIUM,
                title="No 'good first issue' Labels for Prospective Contributors",
                description="The repository does not have any open issues tagged with 'good first issue'.",
                evidence=[e for e in evidence if e.metric == "good_first_issues_count"],
                impact="New open-source contributors find it hard to identify safe, approachable entry points.",
                recommended_fix="Tag 2-3 scoped tasks (documentation fixes, test coverage, small bugs) with 'good first issue'.",
                effort="low",
                confidence=Confidence.HIGH,
            )
        )

    return CommunityHealth(
        total_contributors=total_contributors,
        recent_contributors_90d=recent_contributors_90d,
        bus_factor=bus_factor,
        contributor_concentration=contributor_concentration,
        has_discussions=has_discussions,
        good_first_issues_count=good_first_issues_count,
        help_wanted_issues_count=help_wanted_issues_count,
        contribution_opportunities=opportunities[:10],
        evidence=evidence,
        findings=findings,
        data_coverage=coverage,
    )
