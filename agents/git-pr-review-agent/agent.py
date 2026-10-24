"""Agent orchestrator for git-pr-review-agent."""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from models import (
    ReviewReport,
    PullRequestSummary,
    ReviewIssue,
    ReviewSeverity,
    ReviewCategory
)
from git_utils import get_git_diff, filter_and_calculate_stats
from security_scanner import scan_diff_for_security_issues
from llm_client import get_llm_provider


class GitPRReviewAgent:
    """Autonomous agent that reviews git diffs, catches security leaks, and writes PR descriptions."""

    def __init__(
        self,
        provider_type: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.provider, self.model_label = get_llm_provider(
            provider_type=provider_type,
            model_name=model_name,
            api_key=api_key
        )

    def review_repository(
        self,
        repo_path: str = ".",
        base_branch: str = "main",
        staged_only: bool = False
    ) -> ReviewReport:
        """Extract diff from local repository and run full review."""
        diff_text, stats = get_git_diff(
            repo_path=repo_path,
            base_branch=base_branch,
            staged_only=staged_only
        )
        return self.review_diff_text(diff_text, stats=stats)

    def review_diff_text(
        self,
        diff_text: str,
        stats: Optional[Dict[str, Any]] = None
    ) -> ReviewReport:
        """Analyze a raw diff string."""
        if not diff_text or not diff_text.strip():
            # Clean repository state
            return ReviewReport(
                pr_summary=PullRequestSummary(
                    title="chore: no modifications detected",
                    type="chore",
                    summary="No staged or unstaged changes were found to review.",
                    key_changes=[],
                    breaking_changes=[],
                    security_implications=["Working tree is clean."],
                    testing_checklist=[]
                ),
                issues=[],
                risk_score=0,
                verdict="APPROVE",
                statistics=stats or {"files_changed_count": 0, "additions": 0, "deletions": 0},
                model_used=self.model_label,
                timestamp=datetime.now(timezone.utc).isoformat()
            )

        if stats is None:
            _, stats = filter_and_calculate_stats(diff_text)

        # 1. Deterministic Security & Secret Scan
        security_issues = scan_diff_for_security_issues(diff_text)

        # 2. LLM Reasoning & PR Description Generation
        llm_output = self.provider.review_diff(diff_text, stats)

        # 3. Aggregate & Deduplicate Findings
        combined_issues: List[ReviewIssue] = list(security_issues)
        raw_llm_issues = llm_output.get("issues", [])

        for item in raw_llm_issues:
            try:
                issue = ReviewIssue(**item)
                # Avoid duplicate entries for the same file/line
                is_duplicate = any(
                    existing.file_path == issue.file_path and existing.title == issue.title
                    for existing in combined_issues
                )
                if not is_duplicate:
                    combined_issues.append(issue)
            except Exception:
                continue

        # 4. Strict Risk Assessment
        risk_score = int(llm_output.get("risk_score", 10))
        verdict = llm_output.get("verdict", "APPROVE")

        # Escalate risk if critical security issues exist
        critical_count = sum(1 for i in combined_issues if i.severity == ReviewSeverity.CRITICAL)
        warning_count = sum(1 for i in combined_issues if i.severity == ReviewSeverity.WARNING)

        if critical_count > 0:
            risk_score = max(risk_score, 85 + (critical_count * 5))
            risk_score = min(risk_score, 100)
            verdict = "REQUEST_CHANGES"
        elif warning_count > 0:
            risk_score = max(risk_score, 40)
            if verdict == "APPROVE":
                verdict = "COMMENT"

        # 5. Build PR Summary
        raw_pr = llm_output.get("pr_summary", {})
        pr_summary = PullRequestSummary(
            title=raw_pr.get("title", f"feat: updates across {stats.get('files_changed_count', 1)} files"),
            type=raw_pr.get("type", "feat"),
            summary=raw_pr.get("summary", "Automated code changes reviewed by Jarvis - A PR Review Agent."),
            key_changes=raw_pr.get("key_changes", []),
            breaking_changes=raw_pr.get("breaking_changes", []),
            security_implications=raw_pr.get("security_implications", []),
            testing_checklist=raw_pr.get("testing_checklist", ["Run automated test suite", "Verify local build"])
        )

        return ReviewReport(
            pr_summary=pr_summary,
            issues=combined_issues,
            risk_score=risk_score,
            verdict=verdict,
            statistics=stats,
            model_used=self.model_label,
            timestamp=datetime.now(timezone.utc).isoformat()
        )

    def generate_markdown_pr(self, report: ReviewReport) -> str:
        """Formats the review report into an official GitHub PR description."""
        pr = report.pr_summary
        stats = report.statistics

        verdict_badge = {
            "APPROVE": "🟢 **APPROVED**",
            "REQUEST_CHANGES": "🔴 **CHANGES REQUESTED**",
            "COMMENT": "🟡 **COMMENT / REVIEW FEEDBACK**"
        }.get(report.verdict, report.verdict)

        lines = [
            f"# {pr.title}",
            "",
            "> 🤖 *Automated review and PR description generated by **Jarvis - A PR Review Agent**.*",
            "",
            "## Summary",
            pr.summary,
            "",
            "## Review Overview",
            f"- **Verdict**: {verdict_badge}",
            f"- **Risk Score**: `{report.risk_score}/100`",
            f"- **Model Used**: `{report.model_used}`",
            f"- **Changes**: `{stats.get('files_changed_count', 0)} files` (+{stats.get('additions', 0)} / -{stats.get('deletions', 0)})",
            "",
            "## Key Changes",
        ]

        for item in pr.key_changes:
            lines.append(f"- {item}")

        if pr.breaking_changes:
            lines.extend(["", "## ⚠️ Breaking Changes"])
            for bc in pr.breaking_changes:
                lines.append(f"- {bc}")

        if pr.security_implications:
            lines.extend(["", "## 🛡️ Security & Privacy Assessment"])
            for sec in pr.security_implications:
                lines.append(f"- {sec}")

        if report.issues:
            lines.extend(["", "## 🔍 Code Review Findings"])
            for issue in report.issues:
                sev_icon = {
                    "CRITICAL": "🚨",
                    "WARNING": "⚠️",
                    "SUGGESTION": "💡",
                    "INFO": "ℹ️"
                }.get(issue.severity.value, "•")

                line_info = f":L{issue.line_number}" if issue.line_number else ""
                lines.append(f"### {sev_icon} [{issue.severity.value}] {issue.title}")
                lines.append(f"**File**: `{issue.file_path}{line_info}` | **Category**: `{issue.category.value}`")
                lines.append(f"\n{issue.description}")
                if issue.suggestion:
                    lines.append(f"\n> **Suggestion**: {issue.suggestion}")
                lines.append("")

        lines.extend([
            "## 📋 Verification Checklist",
        ])
        for check in pr.testing_checklist:
            lines.append(f"- [ ] {check}")

        lines.extend([
            "",
            "---",
            f"*Generated at {report.timestamp} via [git-pr-review-agent](agents/git-pr-review-agent)*"
        ])

        return "\n".join(lines)
