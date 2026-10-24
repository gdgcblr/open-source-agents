import json
import os
import re
from typing import List, Optional
import requests

from .models import ReviewReport, ReviewIssue, TriageResult, FileDiff
from .diff_parser import parse_unified_diff
from .rules import run_heuristic_checks, calculate_triage
from .prompts import REVIEW_SYSTEM_PROMPT, build_review_prompt


class PRReviewerAgent:
    """Intelligent GitHub PR Reviewer & Triage Agent."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-1.5-flash",
        offline: bool = False
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model_name or os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        self.offline = offline or not bool(self.api_key)

    def analyze(self, diff_text: str, source_title: str) -> ReviewReport:
        """Execute full review and triage workflow."""
        # 1. Parse diff
        file_diffs = parse_unified_diff(diff_text)
        if not file_diffs:
            # If standard git header wasn't found, create dummy diff entry
            file_diffs = [
                FileDiff(
                    filename="unspecified",
                    old_filename=None,
                    additions=diff_text.count("\n+"),
                    deletions=diff_text.count("\n-"),
                    patch=diff_text,
                    changed_lines=[]
                )
            ]

        # 2. Heuristic rule scanner
        heuristic_issues = run_heuristic_checks(file_diffs)

        # 3. Compute triage metrics
        triage = calculate_triage(file_diffs, heuristic_issues, title=source_title)

        # 4. LLM synthesis or offline fallback
        if not self.offline and self.api_key:
            try:
                llm_data = self._call_gemini_api(diff_text, source_title, heuristic_issues)
                return self._build_report(source_title, triage, heuristic_issues, llm_data)
            except Exception as e:
                # Graceful degradation to offline heuristics if API fails
                return self._build_offline_report(
                    source_title,
                    triage,
                    heuristic_issues,
                    warning_note=f"LLM synthesis bypassed (Error: {e}). Fallback to offline heuristic engine."
                )
        else:
            return self._build_offline_report(source_title, triage, heuristic_issues)

    def _call_gemini_api(self, diff_text: str, source_title: str, heuristic_issues: List[ReviewIssue]) -> dict:
        """Call Gemini API via REST endpoint with structured JSON parsing."""
        heuristics_summary = (
            f"Found {len(heuristic_issues)} heuristic issues: " +
            ", ".join(f"{i.severity}: {i.title}" for i in heuristic_issues[:5])
            if heuristic_issues else "No automated heuristic flags."
        )

        prompt = build_review_prompt(source_title, diff_text, heuristics_summary)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": REVIEW_SYSTEM_PROMPT + "\n\n" + prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=45)
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API returned status {resp.status_code}: {resp.text}")

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini API returned empty candidates.")

        text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        # Clean potential markdown fences
        cleaned = re.sub(r"^```(?:json)?\n", "", text_content.strip())
        cleaned = re.sub(r"\n```$", "", cleaned)
        return json.loads(cleaned)

    def _build_report(
        self,
        source_title: str,
        triage: TriageResult,
        heuristic_issues: List[ReviewIssue],
        llm_data: dict
    ) -> ReviewReport:
        """Combine heuristic findings with LLM analysis."""
        combined_issues: List[ReviewIssue] = list(heuristic_issues)

        # Parse LLM issues
        for raw in llm_data.get("issues", []):
            issue = ReviewIssue(
                file=raw.get("file", "unknown"),
                line=raw.get("line"),
                severity=raw.get("severity", "MEDIUM").upper(),
                category=raw.get("category", "CODE_SMELL").upper(),
                title=raw.get("title", "Code review observation"),
                description=raw.get("description", ""),
                suggestion=raw.get("suggestion")
            )
            # Avoid duplicate heuristic titles
            if not any(h.file == issue.file and h.title == issue.title for h in combined_issues):
                combined_issues.append(issue)

        executive_summary = llm_data.get(
            "executive_summary",
            f"Pull request `{source_title}` introduces {triage.total_additions} additions and {triage.total_deletions} deletions across {triage.total_files} files."
        )

        recommendations = llm_data.get("recommendations", [
            "Verify all test suites pass in CI.",
            "Confirm sensitive credentials are not tracked in revision history.",
            "Perform manual sanity test of changed endpoints."
        ])

        return ReviewReport(
            title=source_title,
            source=source_title,
            triage=triage,
            issues=combined_issues,
            executive_summary=executive_summary,
            recommendations=recommendations,
            raw_llm_analysis=json.dumps(llm_data, indent=2)
        )

    def _build_offline_report(
        self,
        source_title: str,
        triage: TriageResult,
        heuristic_issues: List[ReviewIssue],
        warning_note: Optional[str] = None
    ) -> ReviewReport:
        """Construct a high-quality review report using local rules when offline."""
        summary_paragraphs = [
            f"This pull request has been analyzed via the **Local Heuristic Rule Engine**.",
            f"It encompasses **{triage.total_files} file(s)** with **+{triage.total_additions} additions** and **-{triage.total_deletions} deletions**."
        ]
        if warning_note:
            summary_paragraphs.append(f"> ⚠️ *Notice:* {warning_note}")

        if triage.risk_level == "Critical":
            summary_paragraphs.append("🚨 **Action Required:** Critical security vulnerabilities or hardcoded secrets were detected. Immediate remediation is required before merging.")
        elif triage.risk_level == "High":
            summary_paragraphs.append("⚠️ **Caution:** Elevated risk profile identified due to sensitive file changes or security anti-patterns.")
        else:
            summary_paragraphs.append("✅ Changes appear self-contained with no high-severity static pattern warnings.")

        recommendations = [
            "Verify all unit and integration tests pass cleanly.",
            "Verify that no sensitive environment variables or secrets are exposed.",
            "Ensure adequate test coverage has been added for modified code paths.",
            "Check for edge cases and input validation on external data."
        ]

        return ReviewReport(
            title=source_title,
            source=source_title,
            triage=triage,
            issues=heuristic_issues,
            executive_summary="\n\n".join(summary_paragraphs),
            recommendations=recommendations
        )
