"""Report formatter for terminal display and GitHub Markdown comments."""

from __future__ import annotations
from typing import Any
from .rules_scanner import Finding


def get_verdict_badge(verdict: str) -> str:
    verdict = verdict.upper()
    if verdict == "APPROVE":
        return "✅ APPROVED"
    elif verdict == "REQUEST_CHANGES":
        return "❌ CHANGES REQUESTED"
    else:
        return "💬 COMMENT ONLY"


def get_severity_emoji(severity: str) -> str:
    sev = severity.upper()
    if sev == "CRITICAL":
        return "🚨 CRITICAL"
    elif sev == "HIGH":
        return "🔴 HIGH"
    elif sev == "MEDIUM":
        return "🟡 MEDIUM"
    elif sev == "LOW":
        return "🔵 LOW"
    return "ℹ️ INFO"


class ReviewReporter:
    """Formats and prints review reports."""

    def __init__(self, review_data: dict[str, Any], static_findings: list[Finding]):
        self.review = review_data
        self.static_findings = static_findings

    def generate_markdown(self) -> str:
        """Generate a complete Markdown comment suitable for GitHub PRs."""
        verdict = self.review.get("verdict", "COMMENT")
        risk_score = self.review.get("risk_score", 0)
        risk_level = self.review.get("risk_level", "LOW")
        summary = self.review.get("executive_summary", "No summary provided.")
        strengths = self.review.get("key_strengths", [])
        findings = self.review.get("findings", [])
        test_advice = self.review.get("test_coverage_recommendations", [])
        maintainer_notes = self.review.get("maintainer_notes", "")

        lines: list[str] = []
        lines.append(f"# 🛡️ GitHub PR Guardian — Review Summary")
        lines.append("")
        lines.append(f"**Verdict:** {get_verdict_badge(verdict)}  ")
        lines.append(f"**Security & Risk Score:** `{risk_score}/100` ({risk_level.upper()})")
        lines.append("")
        lines.append("### 📝 Executive Summary")
        lines.append(summary)
        lines.append("")

        if strengths:
            lines.append("### ✨ Key Strengths")
            for s in strengths:
                lines.append(f"- {s}")
            lines.append("")

        lines.append("### 🔍 Detailed Findings")
        if not findings and not self.static_findings:
            lines.append("No security vulnerabilities or major code smells were detected. Great job!")
            lines.append("")
        else:
            lines.append("| Severity | Category | Location | Title & Suggested Fix |")
            lines.append("| :--- | :--- | :--- | :--- |")

            # Static pre-scan findings
            for sf in self.static_findings:
                loc = f"`{sf.file}:{sf.line}`" if sf.line else f"`{sf.file}`"
                fix_text = f"**{sf.title}**<br>{sf.description}"
                if sf.suggested_fix:
                    fix_text += f"<br>_Fix:_ `{sf.suggested_fix}`"
                lines.append(f"| {get_severity_emoji(sf.severity)} | `{sf.category}` | {loc} | {fix_text} |")

            # LLM findings
            for f in findings:
                sev = f.get("severity", "MEDIUM")
                cat = f.get("category", "QUALITY")
                file_path = f.get("file", "unknown")
                line_no = f.get("line")
                loc = f"`{file_path}:{line_no}`" if line_no else f"`{file_path}`"
                title = f.get("title", "")
                comment = f.get("comment", "")
                suggested_fix = f.get("suggested_fix", "")
                detail = f"**{title}**<br>{comment}"
                if suggested_fix:
                    detail += f"<br>_Recommendation:_ `{suggested_fix}`"
                lines.append(f"| {get_severity_emoji(sev)} | `{cat}` | {loc} | {detail} |")

            lines.append("")

        if test_advice:
            lines.append("### 🧪 Testing & Validation Recommendations")
            for ta in test_advice:
                lines.append(f"- {ta}")
            lines.append("")

        if maintainer_notes:
            lines.append("### 💡 Maintainer Notes")
            lines.append(maintainer_notes)
            lines.append("")

        lines.append("---")
        lines.append("_Generated autonomously by [GitHub PR Guardian](https://github.com/sourabh1005kumar/open-source-agents)._")
        return "\n".join(lines)

    def print_terminal(self) -> None:
        """Print formatted review report to standard output."""
        verdict = self.review.get("verdict", "COMMENT")
        risk_score = self.review.get("risk_score", 0)
        risk_level = self.review.get("risk_level", "LOW")
        summary = self.review.get("executive_summary", "")
        findings = self.review.get("findings", [])
        test_advice = self.review.get("test_coverage_recommendations", [])

        # ANSI Colors
        BOLD = "\033[1m"
        RESET = "\033[0m"
        RED = "\033[91m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        BLUE = "\033[94m"
        CYAN = "\033[96m"

        verdict_color = GREEN if verdict == "APPROVE" else (RED if verdict == "REQUEST_CHANGES" else YELLOW)

        print("\n" + "=" * 70)
        print(f"{BOLD}{CYAN}🛡️  GITHUB PR GUARDIAN — AUTOMATED CODE REVIEW REPORT{RESET}")
        print("=" * 70)
        print(f"{BOLD}Verdict:{RESET} {verdict_color}{get_verdict_badge(verdict)}{RESET}")
        print(f"{BOLD}Risk Score:{RESET} {risk_score}/100 [{risk_level.upper()}]")
        print("-" * 70)
        print(f"{BOLD}Executive Summary:{RESET}\n{summary}\n")

        print(f"{BOLD}🔍 Identified Findings & Recommendations:{RESET}")
        all_findings = []

        for sf in self.static_findings:
            all_findings.append({
                "source": "Static Rule",
                "severity": sf.severity,
                "file": sf.file,
                "line": sf.line,
                "title": sf.title,
                "comment": sf.description,
                "fix": sf.suggested_fix,
            })

        for f in findings:
            all_findings.append({
                "source": "AI Reasoning",
                "severity": f.get("severity", "MEDIUM"),
                "file": f.get("file", ""),
                "line": f.get("line"),
                "title": f.get("title", ""),
                "comment": f.get("comment", ""),
                "fix": f.get("suggested_fix", ""),
            })

        if not all_findings:
            print(f"{GREEN}  ✔ No security issues or bad practices detected!{RESET}")
        else:
            for i, item in enumerate(all_findings, 1):
                sev = item["severity"].upper()
                col = RED if sev in ("CRITICAL", "HIGH") else (YELLOW if sev == "MEDIUM" else BLUE)
                loc = f"{item['file']}:{item['line']}" if item["line"] else item["file"]
                print(f"\n  {col}[{sev}]{RESET} {BOLD}{item['title']}{RESET} ({item['source']})")
                print(f"  Location: {CYAN}{loc}{RESET}")
                print(f"  Details:  {item['comment']}")
                if item["fix"]:
                    print(f"  Fix:      {GREEN}{item['fix']}{RESET}")

        if test_advice:
            print(f"\n{BOLD}🧪 Recommended Tests:{RESET}")
            for t in test_advice:
                print(f"  • {t}")

        print("\n" + "=" * 70 + "\n")
