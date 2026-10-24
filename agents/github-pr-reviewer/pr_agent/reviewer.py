import json
import os
import re
from typing import List, Optional
import requests

from .models import ReviewReport, ReviewIssue, TriageResult, FileDiff, SpecialistVerdict, GeneratedTest
from .diff_parser import parse_unified_diff
from .rules import calculate_triage
from .prompts import REVIEW_SYSTEM_PROMPT, build_review_prompt
from .specialists import SecurityAuditorAgent, PerformanceArchitectAgent, AutoTestGeneratorAgent, LeadArchitectAgent
from .patch_generator import AutoPatchGenerator


class PRReviewerAgent:
    """Multi-Agent Autonomous GitHub PR Reviewer & Triage Council."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-1.5-flash",
        offline: bool = False
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self.model_name = model_name or os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        self.offline = offline or not bool(self.api_key)

        # Initialize specialist council
        self.security_agent = SecurityAuditorAgent()
        self.performance_agent = PerformanceArchitectAgent()
        self.test_generator = AutoTestGeneratorAgent()
        self.lead_architect = LeadArchitectAgent()

    def analyze(self, diff_text: str, source_title: str) -> ReviewReport:
        """Execute full multi-agent review and triage workflow."""
        # 1. Parse unified diff
        file_diffs = parse_unified_diff(diff_text)
        if not file_diffs:
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

        # 2. Run Specialist Agents in parallel / sequence
        sec_verdict = self.security_agent.evaluate(file_diffs)
        perf_verdict = self.performance_agent.evaluate(file_diffs)
        test_verdict, generated_tests = self.test_generator.evaluate(file_diffs)

        specialist_verdicts: List[SpecialistVerdict] = [sec_verdict, perf_verdict, test_verdict]

        # Consolidate issues
        combined_issues: List[ReviewIssue] = []
        combined_issues.extend(sec_verdict.findings)
        combined_issues.extend(perf_verdict.findings)

        # 3. Compute triage and volume metrics
        triage = calculate_triage(file_diffs, combined_issues, title=source_title)

        # 4. Lead Architect Adjudication
        verdict, health_score, exec_summary, recommendations = self.lead_architect.adjudicate(
            triage,
            specialist_verdicts,
            combined_issues
        )

        # 5. Autonomous Remediation Patch Generation
        remediation_patch = AutoPatchGenerator.generate_remediation_patch(file_diffs, combined_issues)

        # 6. LLM Deep Synthesis (if online and key present)
        raw_llm = None
        if not self.offline and self.api_key:
            try:
                llm_data = self._call_gemini_api(diff_text, source_title, combined_issues)
                raw_llm = json.dumps(llm_data, indent=2)

                # Merge extra LLM issues
                for raw in llm_data.get("issues", []):
                    issue = ReviewIssue(
                        file=raw.get("file", "unknown"),
                        line=raw.get("line"),
                        severity=raw.get("severity", "MEDIUM").upper(),
                        category=raw.get("category", "CODE_SMELL").upper(),
                        title=raw.get("title", "Review observation"),
                        description=raw.get("description", ""),
                        suggestion=raw.get("suggestion")
                    )
                    if not any(h.file == issue.file and h.title == issue.title for h in combined_issues):
                        combined_issues.append(issue)

                if llm_data.get("executive_summary"):
                    exec_summary = llm_data["executive_summary"] + f"\n\nCouncil Verdict: {verdict} (Health Score: {health_score}/100)."

            except Exception as e:
                exec_summary += f"\n\n*(Notice: LLM deep synthesis bypassed: {e})*"

        return ReviewReport(
            title=source_title,
            source=source_title,
            triage=triage,
            issues=combined_issues,
            executive_summary=exec_summary,
            recommendations=recommendations,
            verdict=verdict,
            health_score=health_score,
            specialist_reviews=specialist_verdicts,
            generated_tests=generated_tests,
            remediation_patch=remediation_patch,
            raw_llm_analysis=raw_llm
        )

    def _call_gemini_api(self, diff_text: str, source_title: str, issues: List[ReviewIssue]) -> dict:
        """Call Gemini API via REST endpoint with structured JSON response."""
        heuristics_summary = (
            f"Found {len(issues)} council issues: " +
            ", ".join(f"{i.severity}: {i.title}" for i in issues[:5])
            if issues else "No initial static heuristic issues."
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
        cleaned = re.sub(r"^```(?:json)?\n", "", text_content.strip())
        cleaned = re.sub(r"\n```$", "", cleaned)
        return json.loads(cleaned)
