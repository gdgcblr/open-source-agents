"""OSS Pulse Agent — Gemini-powered repository intelligence agent.

Uses Google Gemini's function calling to orchestrate repository analysis.
The agent selects relevant tools, inspects their results, and synthesizes
evidence-backed recommendations.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from dotenv import load_dotenv

from models.report import (
    HealthReport,
    RepositoryMetadata,
    ActivityMetrics,
    SecurityConfig,
    DocumentationQuality,
    CommunityHealth,
    CategoryScore,
    Finding,
    Severity,
)
from tools.github_client import GitHubClient
from tools.github_analyzer import get_repository_metadata, analyze_activity
from tools.security_scanner import check_security_configuration
from tools.doc_checker import inspect_documentation
from tools.community_analyzer import analyze_community
from scoring.engine import (
    score_activity,
    score_security,
    score_documentation,
    score_community,
    calculate_overall_score,
    calculate_data_coverage_summary,
    calculate_data_coverage_stats,
)

load_dotenv()


# ---------------------------------------------------------------------------
# Tool definitions for Gemini function calling
# ---------------------------------------------------------------------------

def _tool_get_repository_metadata(owner: str, repo: str) -> dict[str, Any]:
    """Get basic repository metadata including stars, forks, language, topics, and license.

    Args:
        owner: GitHub repository owner (user or organization).
        repo: GitHub repository name.

    Returns:
        Repository metadata as a dictionary.
    """
    with GitHubClient() as client:
        metadata = get_repository_metadata(owner, repo, client)
        return metadata.model_dump()


def _tool_analyze_activity(owner: str, repo: str) -> dict[str, Any]:
    """Analyze repository activity and maintenance metrics including commit frequency,
    issue response times, PR merge velocity, stale issues, and release cadence.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.

    Returns:
        Activity metrics with evidence and findings as a dictionary.
    """
    with GitHubClient() as client:
        metrics = analyze_activity(owner, repo, client)
        return metrics.model_dump()


def _tool_check_security(owner: str, repo: str) -> dict[str, Any]:
    """Check repository security configuration including security policy,
    Dependabot, code scanning, secret scanning, and branch protection.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.

    Returns:
        Security configuration with evidence and findings as a dictionary.
    """
    with GitHubClient() as client:
        config = check_security_configuration(owner, repo, client)
        return config.model_dump()


def _tool_inspect_docs(owner: str, repo: str) -> dict[str, Any]:
    """Inspect repository documentation quality including README completeness,
    contributing guide, license, code of conduct, and issue/PR templates.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.

    Returns:
        Documentation quality analysis with evidence and findings as a dictionary.
    """
    with GitHubClient() as client:
        docs = inspect_documentation(owner, repo, client)
        return docs.model_dump()


def _tool_analyze_community_health(owner: str, repo: str) -> dict[str, Any]:
    """Analyze community health including bus factor, contributor concentration,
    newcomer friendliness, and contribution opportunities.

    Args:
        owner: GitHub repository owner.
        repo: GitHub repository name.

    Returns:
        Community health metrics with contribution opportunities as a dictionary.
    """
    with GitHubClient() as client:
        health = analyze_community(owner, repo, client)
        return health.model_dump()


# Map of tool names to their implementations
TOOL_FUNCTIONS = {
    "_tool_get_repository_metadata": _tool_get_repository_metadata,
    "_tool_analyze_activity": _tool_analyze_activity,
    "_tool_check_security": _tool_check_security,
    "_tool_inspect_docs": _tool_inspect_docs,
    "_tool_analyze_community_health": _tool_analyze_community_health,
}

TOOL_LIST = list(TOOL_FUNCTIONS.values())


# ---------------------------------------------------------------------------
# Agent orchestration
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are OSS Pulse, an expert open-source repository intelligence agent.

Your job is to analyze GitHub repositories and produce evidence-backed health reports.
You have access to these tools:
1. _tool_get_repository_metadata — Get basic repo info (stars, forks, language, etc.)
2. _tool_analyze_activity — Measure commit frequency, issue response, PR velocity, staleness
3. _tool_check_security — Check security policy, Dependabot, code scanning, branch protection
4. _tool_inspect_docs — Evaluate README quality, contributing guide, license, templates
5. _tool_analyze_community_health — Analyze bus factor, contributor diversity, newcomer readiness

INSTRUCTIONS:
- Start by getting repository metadata to understand the project.
- Then run ALL four analysis tools to get comprehensive data.
- After receiving all tool results, synthesize your analysis.

When synthesizing, you MUST:
1. Reference specific evidence from tool results (e.g., "With only 3 commits in the last 90 days...")
2. Prioritize findings by severity and impact
3. Provide actionable, specific recommendations (not generic advice)
4. Note data limitations honestly
5. Consider the project's stage and scope (a stable library may have few commits intentionally)

Your final response should be a JSON object with:
{
  "summary": "A 3-5 paragraph analysis of the repository's health...",
  "recommendations": ["Specific recommendation 1", "Specific recommendation 2", ...]
}
"""


def _sanitize_untrusted_text(text: Optional[str], max_len: int = 300) -> str:
    """Sanitize untrusted text from GitHub repositories to prevent prompt injection."""
    if not text:
        return ""
    # Strip markdown code blocks, control characters, and collapse spaces
    sanitized = text.replace("```", "").replace("\r", " ").replace("\n", " ")
    sanitized = " ".join(sanitized.split())
    if len(sanitized) > max_len:
        sanitized = sanitized[:max_len] + "..."
    return sanitized


class OSSPulseAgent:
    """Gemini-powered repository analysis agent.

    Uses function calling to orchestrate tool execution and synthesize
    evidence-backed recommendations.
    """

    def __init__(self, gemini_api_key: Optional[str] = None):
        self.api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self._gemini_available = False

        if self.api_key:
            try:
                from google import genai
                self._genai = genai
                self._client = genai.Client(api_key=self.api_key)
                self._gemini_available = True
            except ImportError:
                pass

    @property
    def gemini_available(self) -> bool:
        """Whether Gemini API is configured and available."""
        return self._gemini_available

    def analyze(self, owner: str, repo: str) -> HealthReport:
        """Run complete repository analysis.

        If Gemini is available, uses the AI agent to orchestrate analysis
        and generate insights. Otherwise, falls back to deterministic analysis.

        Args:
            owner: GitHub repository owner.
            repo: GitHub repository name.

        Returns:
            Complete HealthReport with scores, findings, and recommendations.
        """
        start_time = time.time()

        # Step 1: Gather all data (deterministic — always runs)
        with GitHubClient() as client:
            metadata = get_repository_metadata(owner, repo, client)
            activity = analyze_activity(owner, repo, client)
            security = check_security_configuration(owner, repo, client)
            docs = inspect_documentation(owner, repo, client)
            community = analyze_community(owner, repo, client)

        # Step 2: Calculate evidence-based scores
        activity_score = score_activity(activity)
        security_score = score_security(security)
        docs_score = score_documentation(docs)
        community_score = score_community(community)

        category_scores = [activity_score, security_score, docs_score, community_score]

        # Step 3: Calculate overall score
        overall_score, grade = calculate_overall_score(category_scores)

        # Step 4: Collect all findings, sorted by severity
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        all_findings = []
        for cs in category_scores:
            all_findings.extend(cs.findings)
        all_findings.sort(key=lambda f: severity_order.get(f.severity, 5))

        # Step 5: Collect contribution opportunities
        opportunities = community.contribution_opportunities

        # Step 6: Calculate data coverage
        coverage_summary, coverage_pct, evidence_tier = calculate_data_coverage_stats(category_scores)

        # Step 7: Get AI-powered summary and recommendations
        ai_summary = ""
        ai_recommendations: list[str] = []

        if self._gemini_available:
            ai_summary, ai_recommendations = self._generate_ai_insights(
                metadata, activity, security, docs, community,
                category_scores, overall_score, grade, all_findings
            )
        else:
            ai_summary, ai_recommendations = self._generate_deterministic_insights(
                metadata, category_scores, overall_score, grade, all_findings
            )

        duration = time.time() - start_time

        return HealthReport(
            repository=metadata,
            overall_score=round(overall_score, 1),
            overall_grade=grade,
            category_scores=category_scores,
            all_findings=all_findings,
            contribution_opportunities=opportunities,
            ai_summary=ai_summary,
            ai_recommendations=ai_recommendations,
            data_coverage_summary=coverage_summary,
            data_coverage_percentage=coverage_pct,
            evidence_quality=evidence_tier,
            analysis_duration_seconds=round(duration, 2),
        )

    def _generate_ai_insights(
        self,
        metadata: RepositoryMetadata,
        activity: ActivityMetrics,
        security: SecurityConfig,
        docs: DocumentationQuality,
        community: CommunityHealth,
        category_scores: list[CategoryScore],
        overall_score: float,
        grade: str,
        findings: list[Finding],
    ) -> tuple[str, list[str]]:
        """Use Gemini to generate evidence-backed summary and recommendations."""
        try:
            from google.genai import types

            # Build a detailed context for Gemini
            context = self._build_analysis_context(
                metadata, activity, security, docs, community,
                category_scores, overall_score, grade, findings
            )

            response = self._client.models.generate_content(
                model="gemini-3.8-flash",
                contents=context,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.3,
                    response_mime_type="application/json",
                ),
            )

            result = json.loads(response.text)
            summary = result.get("summary", "")
            recommendations = result.get("recommendations", [])

            return summary, recommendations

        except Exception as e:
            # Fall back to deterministic if Gemini fails
            return self._generate_deterministic_insights(
                metadata, category_scores, overall_score, grade, findings
            )

    def _build_analysis_context(
        self,
        metadata: RepositoryMetadata,
        activity: ActivityMetrics,
        security: SecurityConfig,
        docs: DocumentationQuality,
        community: CommunityHealth,
        category_scores: list[CategoryScore],
        overall_score: float,
        grade: str,
        findings: list[Finding],
    ) -> str:
        """Build a detailed context string for the AI model."""
        findings_text = "\n".join(
            f"  - [{f.severity.value.upper()}] {f.title}: {f.description} "
            f"(Fix: {f.recommended_fix}, Effort: {f.effort})"
            for f in findings[:15]  # Limit to top 15 findings
        )

        scores_text = "\n".join(
            f"  - {cs.category.value}: {cs.score:.0f}/100 "
            f"(weight: {cs.weight:.0%}, sufficient data: {cs.sufficient_data})"
            for cs in category_scores
        )

        safe_desc = _sanitize_untrusted_text(metadata.description, 250) or 'No description'
        safe_topics = ", ".join(_sanitize_untrusted_text(t, 50) for t in metadata.topics) if metadata.topics else 'None'

        return f"""Analyze this GitHub repository and synthesize your findings into an evidence-backed health report.

REPOSITORY: {metadata.full_name}
Description: {safe_desc}
Language: {metadata.language or 'Unknown'}
Stars: {metadata.stars} | Forks: {metadata.forks} | Open Issues: {metadata.open_issues}
Created: {metadata.created_at} | Last Updated: {metadata.updated_at}
Topics: {safe_topics}
Archived: {metadata.is_archived} | Fork: {metadata.is_fork}

OVERALL SCORE: {overall_score:.0f}/100 ({grade})

CATEGORY SCORES:
{scores_text}

ACTIVITY METRICS:
  - Commits (30d/90d/365d): {activity.commits_30d}/{activity.commits_90d}/{activity.commits_365d}
  - Avg commits/week (90d): {activity.avg_commits_per_week_90d:.1f}
  - Days since last commit: {activity.days_since_last_commit}
  - Issue response time (median): {activity.issue_response_time_median_hours or 'N/A'} hours
  - PR merge time (median): {activity.pr_merge_time_median_hours or 'N/A'} hours
  - Stale issues: {activity.stale_issues_count} ({activity.stale_issues_percentage:.0f}%)

SECURITY:
  - Security policy: {'Yes' if security.has_security_policy else 'No'}
  - Dependabot: {'Yes' if security.has_dependabot_config else 'No'} {('(' + ', '.join(security.dependabot_ecosystems) + ')') if security.dependabot_ecosystems else ''}
  - Code scanning: {'Yes' if security.has_code_scanning else 'No'} {('(' + ', '.join(security.code_scanning_tools) + ')') if security.code_scanning_tools else ''}
  - Branch protection: {security.has_branch_protection}
  - Dependency manifests: {', '.join(security.dependency_manifests) if security.dependency_manifests else 'None found'}

DOCUMENTATION:
  - README: {'Yes' if docs.has_readme else 'No'} ({docs.readme_length_chars} chars)
  - README sections: {', '.join(docs.readme_sections) if docs.readme_sections else 'None detected'}
  - Installation docs: {docs.readme_has_installation}
  - Usage docs: {docs.readme_has_usage}
  - Contributing guide: {docs.has_contributing}
  - License: {docs.license_type or ('Present' if docs.has_license else 'Missing')}
  - Code of Conduct: {docs.has_code_of_conduct}
  - Issue templates: {docs.has_issue_templates}

COMMUNITY:
  - Total contributors: {community.total_contributors}
  - Recent contributors (90d): {community.recent_contributors_90d}
  - Bus factor: {community.bus_factor}
  - Good first issues: {community.good_first_issues_count}
  - Help wanted issues: {community.help_wanted_issues_count}
  - Contribution opportunities: {len(community.contribution_opportunities)}

TOP FINDINGS ({len(findings)} total):
{findings_text}

Based on ALL the evidence above, provide:
1. A summary (3-5 paragraphs) that references specific metrics and explains what they mean for this project.
2. Prioritized recommendations (5-8) that are specific and actionable, ordered by impact.
"""

    def _generate_deterministic_insights(
        self,
        metadata: RepositoryMetadata,
        category_scores: list[CategoryScore],
        overall_score: float,
        grade: str,
        findings: list[Finding],
    ) -> tuple[str, list[str]]:
        """Generate summary and recommendations without AI, based on scores and findings."""
        # Build summary from scores
        score_descriptions = {
            "A+": "excellent", "A": "very good", "B+": "good", "B": "above average",
            "C+": "fair", "C": "below average", "D": "poor", "F": "critical",
        }
        quality = score_descriptions.get(grade, "moderate")

        summary_parts = [
            f"**{metadata.full_name}** received an overall health score of "
            f"**{overall_score:.0f}/100 ({grade})**, indicating {quality} "
            f"repository health.",
        ]

        for cs in category_scores:
            status = "strong" if cs.score >= 70 else "needs improvement" if cs.score >= 40 else "weak"
            summary_parts.append(
                f"**{cs.category.value.title()}** scored {cs.score:.0f}/100 ({status}): "
                f"{cs.evidence_summary}"
            )

        if findings:
            critical_high = [f for f in findings if f.severity in (Severity.CRITICAL, Severity.HIGH)]
            if critical_high:
                summary_parts.append(
                    f"⚠️ **{len(critical_high)} critical/high severity findings** require attention."
                )

        summary = "\n\n".join(summary_parts)

        # Build recommendations from findings (top severity first)
        recommendations = []
        for f in findings[:8]:
            recommendations.append(
                f"[{f.severity.value.upper()}] {f.title}: {f.recommended_fix} "
                f"(Effort: {f.effort})"
            )

        if not recommendations:
            recommendations = ["Repository appears well-maintained. Continue current practices."]

        return summary, recommendations


def run_analysis(repo_full_name: str, gemini_api_key: Optional[str] = None) -> HealthReport:
    """Convenience function to analyze a repository.

    Args:
        repo_full_name: Repository in "owner/repo" format.
        gemini_api_key: Optional Gemini API key (falls back to env var).

    Returns:
        Complete HealthReport.

    Raises:
        ValueError: If repo_full_name is not in "owner/repo" format.
    """
    parts = repo_full_name.strip().split("/")
    if len(parts) != 2:
        raise ValueError(
            f"Repository must be in 'owner/repo' format, got: {repo_full_name}"
        )

    owner, repo = parts[0].strip(), parts[1].strip()
    agent = OSSPulseAgent(gemini_api_key=gemini_api_key)
    return agent.analyze(owner, repo)
