"""Main orchestration Agent for GitHub PR Guardian."""

from __future__ import annotations
import subprocess
from typing import Any
from .diff_parser import parse_unified_diff
from .rules_scanner import RulesScanner, Finding
from .gemini_client import GeminiClient
from .github_client import GitHubClient, parse_pr_identifier
from .reporter import ReviewReporter


class GuardianAgent:
    """Orchestrator for analyzing PRs and generating intelligent code reviews."""

    def __init__(self, gemini_api_key: str | None = None, github_token: str | None = None):
        self.rules_scanner = RulesScanner()
        self.gemini_client = GeminiClient(api_key=gemini_api_key)
        self.github_client = GitHubClient(token=github_token)

    def review_github_pr(self, pr_identifier: str, use_llm: bool = True) -> tuple[dict[str, Any], list[Finding]]:
        """Review a Pull Request directly from GitHub."""
        owner, repo, number = parse_pr_identifier(pr_identifier)
        meta = self.github_client.fetch_pr_metadata(owner, repo, number)
        diff_text = self.github_client.fetch_pr_diff(owner, repo, number)

        return self._execute_pipeline(
            diff_text=diff_text,
            pr_title=f"PR #{meta.number}: {meta.title}",
            pr_description=meta.description,
            use_llm=use_llm,
        )

    def review_diff_text(
        self,
        diff_text: str,
        title: str = "Local Diff / Patch Review",
        use_llm: bool = True,
    ) -> tuple[dict[str, Any], list[Finding]]:
        """Review arbitrary unified diff text."""
        return self._execute_pipeline(
            diff_text=diff_text,
            pr_title=title,
            pr_description="",
            use_llm=use_llm,
        )

    def review_local_git(self, staged_only: bool = False, use_llm: bool = True) -> tuple[dict[str, Any], list[Finding]]:
        """Review changes in the local git repository."""
        cmd = ["git", "diff", "--cached"] if staged_only else ["git", "diff", "HEAD"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            diff_text = res.stdout
        except Exception as e:
            raise RuntimeError(f"Failed to capture local git diff: {e}")

        title = "Local Git Staged Changes" if staged_only else "Local Git Working Tree"
        return self._execute_pipeline(
            diff_text=diff_text,
            pr_title=title,
            pr_description="",
            use_llm=use_llm,
        )

    def _execute_pipeline(
        self,
        diff_text: str,
        pr_title: str,
        pr_description: str,
        use_llm: bool = True,
    ) -> tuple[dict[str, Any], list[Finding]]:
        if not diff_text or not diff_text.strip():
            empty_review = {
                "verdict": "APPROVE",
                "risk_score": 0,
                "risk_level": "LOW",
                "executive_summary": "Empty diff received. No code changes to analyze.",
                "findings": [],
                "key_strengths": ["Clean state"],
                "test_coverage_recommendations": [],
                "maintainer_notes": "Diff contains no changes.",
            }
            return empty_review, []

        # 1. Parse unified diff
        files = parse_unified_diff(diff_text)

        # 2. Run static security heuristic scanner
        static_findings = self.rules_scanner.scan_files(files)

        # Format summary of static findings for LLM context
        static_summary_lines = []
        for f in static_findings:
            loc = f"{f.file}:{f.line}" if f.line else f.file
            static_summary_lines.append(f"- [{f.severity}] {f.title} at {loc}: {f.description}")
        static_summary = "\n".join(static_summary_lines)

        # 3. LLM Reasoning phase (optional / fallback)
        if use_llm:
            try:
                review_data = self.gemini_client.analyze_diff(
                    diff_text=diff_text,
                    pr_title=pr_title,
                    pr_description=pr_description,
                    static_findings_summary=static_summary,
                )
                return review_data, static_findings
            except Exception as e:
                print(f"[Warning] LLM analysis unavailable ({e}). Falling back to static review mode.")

        # Fallback heuristic score calculation if LLM is disabled or unavailable
        has_critical = any(f.severity == "CRITICAL" for f in static_findings)
        has_high = any(f.severity == "HIGH" for f in static_findings)

        if has_critical:
            verdict = "REQUEST_CHANGES"
            score = 90
            level = "CRITICAL"
        elif has_high:
            verdict = "REQUEST_CHANGES"
            score = 65
            level = "HIGH"
        elif static_findings:
            verdict = "COMMENT"
            score = 30
            level = "MEDIUM"
        else:
            verdict = "APPROVE"
            score = 5
            level = "LOW"

        fallback_review = {
            "verdict": verdict,
            "risk_score": score,
            "risk_level": level,
            "executive_summary": f"Completed static rule scan on {len(files)} file(s). Found {len(static_findings)} rule alerts.",
            "findings": [],
            "key_strengths": ["Passed basic static checks"] if not static_findings else [],
            "test_coverage_recommendations": ["Ensure test coverage for modified code paths."],
            "maintainer_notes": "Static mode only. For in-depth reasoning, configure GEMINI_API_KEY.",
        }
        return fallback_review, static_findings
