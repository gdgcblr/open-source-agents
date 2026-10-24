"""Evidence-based scoring engine.

Calculates health scores with transparent weighting. Every score is
traceable to evidence. Missing data is never silently treated as zero
or as a pass.

Weights:
  Activity & Maintenance: 30%
  Security Configuration: 25%
  Documentation:          20%
  Community Health:       25%
"""

from __future__ import annotations

from models.report import (
    Category,
    CategoryScore,
    DataCoverage,
    Finding,
    ActivityMetrics,
    SecurityConfig,
    DocumentationQuality,
    CommunityHealth,
    CATEGORY_WEIGHTS,
)


def score_activity(metrics: ActivityMetrics) -> CategoryScore:
    """Calculate activity and maintenance score (0-100) based on sub-metrics."""
    sub_scores: dict[str, float] = {}
    max_scores: dict[str, float] = {}

    # 1. Commit Frequency (25 pts max)
    max_scores["commit_frequency"] = 25.0
    if metrics.avg_commits_per_week_90d >= 5.0:
        sub_scores["commit_frequency"] = 25.0
    elif metrics.avg_commits_per_week_90d >= 2.0:
        sub_scores["commit_frequency"] = 20.0
    elif metrics.avg_commits_per_week_90d >= 0.5:
        sub_scores["commit_frequency"] = 15.0
    elif metrics.commits_90d > 0:
        sub_scores["commit_frequency"] = 10.0
    else:
        sub_scores["commit_frequency"] = 0.0

    # 2. Recency / Days since last commit (25 pts max)
    max_scores["recency"] = 25.0
    if metrics.days_since_last_commit <= 7:
        sub_scores["recency"] = 25.0
    elif metrics.days_since_last_commit <= 30:
        sub_scores["recency"] = 20.0
    elif metrics.days_since_last_commit <= 90:
        sub_scores["recency"] = 15.0
    elif metrics.days_since_last_commit <= 180:
        sub_scores["recency"] = 8.0
    else:
        sub_scores["recency"] = 0.0

    # 3. Issue Responsiveness (20 pts max)
    if metrics.issue_response_time_median_hours is not None:
        max_scores["issue_responsiveness"] = 20.0
        hrs = metrics.issue_response_time_median_hours
        if hrs <= 24.0:
            sub_scores["issue_responsiveness"] = 20.0
        elif hrs <= 72.0:
            sub_scores["issue_responsiveness"] = 15.0
        elif hrs <= 168.0:
            sub_scores["issue_responsiveness"] = 10.0
        elif hrs <= 336.0:
            sub_scores["issue_responsiveness"] = 5.0
        else:
            sub_scores["issue_responsiveness"] = 0.0

    # 4. PR Velocity (15 pts max)
    if metrics.pr_merge_time_median_hours is not None:
        max_scores["pr_velocity"] = 15.0
        prs = metrics.pr_merge_time_median_hours
        if prs <= 24.0:
            sub_scores["pr_velocity"] = 15.0
        elif prs <= 72.0:
            sub_scores["pr_velocity"] = 12.0
        elif prs <= 168.0:
            sub_scores["pr_velocity"] = 8.0
        elif prs <= 336.0:
            sub_scores["pr_velocity"] = 4.0
        else:
            sub_scores["pr_velocity"] = 0.0

    # 5. Issue Backlog Health (15 pts max)
    max_scores["backlog_health"] = 15.0
    if metrics.stale_issues_percentage <= 10.0:
        sub_scores["backlog_health"] = 15.0
    elif metrics.stale_issues_percentage <= 25.0:
        sub_scores["backlog_health"] = 11.0
    elif metrics.stale_issues_percentage <= 50.0:
        sub_scores["backlog_health"] = 6.0
    else:
        sub_scores["backlog_health"] = 2.0

    total_achieved = sum(sub_scores.values())
    total_possible = sum(max_scores.values())
    final_score = round((total_achieved / total_possible) * 100.0, 1) if total_possible > 0 else 0.0

    sufficient = len(sub_scores) >= 3
    summary = (
        f"Commit recency ({sub_scores.get('recency', 0):.0f}/25), "
        f"Frequency ({sub_scores.get('commit_frequency', 0):.0f}/25), "
        f"Backlog health ({sub_scores.get('backlog_health', 0):.0f}/15)"
    )

    weight = CATEGORY_WEIGHTS[Category.ACTIVITY]
    return CategoryScore(
        category=Category.ACTIVITY,
        score=final_score,
        weight=weight,
        weighted_score=round(final_score * weight, 2),
        evidence_summary=summary,
        findings=[],  # findings attached at orchestration
        data_coverage=metrics.data_coverage,
        sub_scores=sub_scores,
        sufficient_data=sufficient,
    )


def score_security(config: SecurityConfig) -> CategoryScore:
    """Calculate security configuration readiness score (0-100)."""
    sub_scores: dict[str, float] = {}
    max_scores: dict[str, float] = {
        "security_policy": 30.0,
        "dependency_scanning": 25.0,
        "code_scanning": 25.0,
        "branch_protection": 10.0,
        "manifest_detection": 10.0,
    }

    sub_scores["security_policy"] = 30.0 if config.has_security_policy else 0.0
    sub_scores["dependency_scanning"] = 25.0 if config.has_dependabot_config else 0.0
    sub_scores["code_scanning"] = 25.0 if config.has_code_scanning else 0.0

    if config.has_branch_protection is True:
        sub_scores["branch_protection"] = 10.0
    elif config.has_branch_protection is False:
        sub_scores["branch_protection"] = 0.0
    else:
        # Insufficient permission to view branch protection
        del max_scores["branch_protection"]

    sub_scores["manifest_detection"] = 10.0 if len(config.dependency_manifests) > 0 else 5.0

    total_achieved = sum(sub_scores.values())
    total_possible = sum(max_scores.values())
    final_score = round((total_achieved / total_possible) * 100.0, 1) if total_possible > 0 else 0.0

    summary = (
        f"Policy: {'Present' if config.has_security_policy else 'Missing'}, "
        f"Dependabot: {'Configured' if config.has_dependabot_config else 'None'}, "
        f"SAST: {', '.join(config.code_scanning_tools) if config.code_scanning_tools else 'None'}"
    )

    weight = CATEGORY_WEIGHTS[Category.SECURITY]
    return CategoryScore(
        category=Category.SECURITY,
        score=final_score,
        weight=weight,
        weighted_score=round(final_score * weight, 2),
        evidence_summary=summary,
        findings=config.findings,
        data_coverage=config.data_coverage,
        sub_scores=sub_scores,
        sufficient_data=True,
    )


def score_documentation(docs: DocumentationQuality) -> CategoryScore:
    """Calculate documentation quality and completeness score (0-100)."""
    sub_scores: dict[str, float] = {}

    # README existence & length (30 pts)
    if docs.has_readme:
        if docs.readme_length_chars >= 5000:
            sub_scores["readme_depth"] = 30.0
        elif docs.readme_length_chars >= 2000:
            sub_scores["readme_depth"] = 25.0
        elif docs.readme_length_chars >= 500:
            sub_scores["readme_depth"] = 18.0
        else:
            sub_scores["readme_depth"] = 10.0
    else:
        sub_scores["readme_depth"] = 0.0

    # Key README sections (25 pts)
    sect_pts = 0.0
    if docs.readme_has_installation:
        sect_pts += 10.0
    if docs.readme_has_usage:
        sect_pts += 10.0
    if docs.readme_has_examples:
        sect_pts += 5.0
    sub_scores["readme_sections"] = sect_pts

    # License (20 pts)
    sub_scores["license"] = 20.0 if docs.has_license else 0.0

    # Contributing Guide (15 pts)
    sub_scores["contributing_guide"] = 15.0 if docs.has_contributing else 0.0

    # Governance & Templates (10 pts)
    gov_pts = 0.0
    if docs.has_code_of_conduct:
        gov_pts += 4.0
    if docs.has_issue_templates:
        gov_pts += 3.0
    if docs.has_pr_templates:
        gov_pts += 3.0
    sub_scores["governance_templates"] = gov_pts

    final_score = round(sum(sub_scores.values()), 1)
    summary = (
        f"README: {docs.readme_length_chars} chars, "
        f"License: {docs.license_type or ('Present' if docs.has_license else 'Missing')}, "
        f"Contributing Guide: {'Present' if docs.has_contributing else 'Missing'}"
    )

    weight = CATEGORY_WEIGHTS[Category.DOCUMENTATION]
    return CategoryScore(
        category=Category.DOCUMENTATION,
        score=final_score,
        weight=weight,
        weighted_score=round(final_score * weight, 2),
        evidence_summary=summary,
        findings=docs.findings,
        data_coverage=docs.data_coverage,
        sub_scores=sub_scores,
        sufficient_data=True,
    )


def score_community(health: CommunityHealth) -> CategoryScore:
    """Calculate community health and newcomer friendliness score (0-100)."""
    sub_scores: dict[str, float] = {}

    # Bus factor & Contributor diversity (35 pts)
    if health.bus_factor >= 4:
        sub_scores["bus_factor"] = 35.0
    elif health.bus_factor == 3:
        sub_scores["bus_factor"] = 28.0
    elif health.bus_factor == 2:
        sub_scores["bus_factor"] = 20.0
    elif health.total_contributors > 1:
        sub_scores["bus_factor"] = 12.0
    else:
        sub_scores["bus_factor"] = 5.0

    # Contributor activity in last 90 days (25 pts)
    if health.recent_contributors_90d >= 10:
        sub_scores["recent_activity"] = 25.0
    elif health.recent_contributors_90d >= 5:
        sub_scores["recent_activity"] = 20.0
    elif health.recent_contributors_90d >= 2:
        sub_scores["recent_activity"] = 15.0
    elif health.recent_contributors_90d >= 1:
        sub_scores["recent_activity"] = 10.0
    else:
        sub_scores["recent_activity"] = 0.0

    # Newcomer Onboarding (25 pts)
    newcomer_pts = 0.0
    if health.good_first_issues_count >= 5:
        newcomer_pts += 15.0
    elif health.good_first_issues_count >= 1:
        newcomer_pts += 10.0

    if health.help_wanted_issues_count >= 3:
        newcomer_pts += 10.0
    elif health.help_wanted_issues_count >= 1:
        newcomer_pts += 6.0
    sub_scores["newcomer_readiness"] = newcomer_pts

    # Community discussions & engagement channels (15 pts)
    comm_pts = 7.0 if health.has_discussions else 0.0
    if len(health.contribution_opportunities) >= 3:
        comm_pts += 8.0
    elif len(health.contribution_opportunities) >= 1:
        comm_pts += 4.0
    sub_scores["community_channels"] = comm_pts

    final_score = round(sum(sub_scores.values()), 1)
    summary = (
        f"Bus factor: {health.bus_factor}, Total contributors: {health.total_contributors}, "
        f"Good first issues: {health.good_first_issues_count}"
    )

    weight = CATEGORY_WEIGHTS[Category.COMMUNITY]
    return CategoryScore(
        category=Category.COMMUNITY,
        score=final_score,
        weight=weight,
        weighted_score=round(final_score * weight, 2),
        evidence_summary=summary,
        findings=health.findings,
        data_coverage=health.data_coverage,
        sub_scores=sub_scores,
        sufficient_data=True,
    )


def calculate_overall_score(category_scores: list[CategoryScore]) -> tuple[float, str]:
    """Calculate the overall composite score (0-100) and assign a grade."""
    valid_scores = [cs for cs in category_scores if cs.sufficient_data]
    if not valid_scores:
        return 0.0, "N/A"

    total_weight = sum(cs.weight for cs in valid_scores)
    if total_weight <= 0:
        return 0.0, "N/A"

    overall = sum(cs.score * (cs.weight / total_weight) for cs in valid_scores)
    overall = round(max(0.0, min(100.0, overall)), 1)

    if overall >= 95.0:
        grade = "A+"
    elif overall >= 85.0:
        grade = "A"
    elif overall >= 78.0:
        grade = "B+"
    elif overall >= 70.0:
        grade = "B"
    elif overall >= 60.0:
        grade = "C+"
    elif overall >= 50.0:
        grade = "C"
    elif overall >= 35.0:
        grade = "D"
    else:
        grade = "F"

    return overall, grade


def calculate_data_coverage_stats(
    category_scores: list[CategoryScore],
) -> tuple[dict[str, int], float, str]:
    """Calculate detailed data coverage metrics, percentage, and evidence quality tier."""
    measured = 0
    unavailable = 0
    for cs in category_scores:
        for dc in cs.data_coverage:
            if dc.available:
                measured += 1
            else:
                unavailable += 1
    total = measured + unavailable
    pct = round((measured / total * 100.0), 1) if total > 0 else 0.0
    if pct >= 80.0:
        quality = "High"
    elif pct >= 50.0:
        quality = "Medium"
    else:
        quality = "Low"

    summary = {
        "metrics_measured": measured,
        "metrics_unavailable": unavailable,
        "total_metrics": total,
    }
    return summary, pct, quality


def calculate_data_coverage_summary(category_scores: list[CategoryScore]) -> dict[str, int]:
    """Summarize data coverage across all checks."""
    summary, _, _ = calculate_data_coverage_stats(category_scores)
    return summary
