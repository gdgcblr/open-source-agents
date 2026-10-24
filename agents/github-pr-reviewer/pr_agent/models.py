from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class ChangedLine:
    line_number: Optional[int]
    line_type: str  # '+', '-', ' '
    content: str


@dataclass
class FileDiff:
    filename: str
    old_filename: Optional[str]
    additions: int
    deletions: int
    patch: str
    changed_lines: List[ChangedLine] = field(default_factory=list)


@dataclass
class ReviewIssue:
    file: str
    line: Optional[int]
    severity: str  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'
    category: str  # 'SECURITY', 'BUG', 'CODE_SMELL', 'PERFORMANCE', 'STYLE'
    title: str
    description: str
    suggestion: Optional[str] = None
    cwe_id: Optional[str] = None  # e.g. "CWE-89: SQL Injection"
    suggested_replacement: Optional[str] = None


@dataclass
class SpecialistVerdict:
    agent_name: str
    score: int  # 0 to 100
    status: str  # 'PASSED', 'WARNING', 'FAILED'
    summary: str
    findings: List[ReviewIssue] = field(default_factory=list)


@dataclass
class GeneratedTest:
    test_name: str
    framework: str  # 'pytest' or 'unittest'
    code: str
    target_file: str
    description: str


@dataclass
class TriageResult:
    pr_type: str  # 'Feature', 'Bug Fix', 'Refactor', 'Security Fix', 'Documentation', 'Chore'
    size_tier: str  # 'XS', 'S', 'M', 'L', 'XL'
    risk_level: str  # 'Low', 'Medium', 'High', 'Critical'
    total_additions: int
    total_deletions: int
    total_files: int
    summary: str


@dataclass
class ReviewReport:
    title: str
    source: str
    triage: TriageResult
    issues: List[ReviewIssue]
    executive_summary: str
    recommendations: List[str]
    verdict: str = "APPROVED"  # 'APPROVED', 'CHANGES_REQUESTED', 'BLOCKED'
    health_score: int = 100  # 0 to 100
    specialist_reviews: List[SpecialistVerdict] = field(default_factory=list)
    generated_tests: List[GeneratedTest] = field(default_factory=list)
    remediation_patch: Optional[str] = None
    raw_llm_analysis: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "created_at": self.created_at,
            "verdict": self.verdict,
            "health_score": self.health_score,
            "triage": {
                "pr_type": self.triage.pr_type,
                "size_tier": self.triage.size_tier,
                "risk_level": self.triage.risk_level,
                "total_additions": self.triage.total_additions,
                "total_deletions": self.triage.total_deletions,
                "total_files": self.triage.total_files,
                "summary": self.triage.summary,
            },
            "specialist_reviews": [
                {
                    "agent_name": s.agent_name,
                    "score": s.score,
                    "status": s.status,
                    "summary": s.summary,
                    "findings_count": len(s.findings),
                }
                for s in self.specialist_reviews
            ],
            "issues": [
                {
                    "file": issue.file,
                    "line": issue.line,
                    "severity": issue.severity,
                    "category": issue.category,
                    "cwe_id": issue.cwe_id,
                    "title": issue.title,
                    "description": issue.description,
                    "suggestion": issue.suggestion,
                }
                for issue in self.issues
            ],
            "generated_tests": [
                {
                    "test_name": t.test_name,
                    "framework": t.framework,
                    "target_file": t.target_file,
                    "description": t.description,
                    "code": t.code,
                }
                for t in self.generated_tests
            ],
            "remediation_patch_available": bool(self.remediation_patch),
            "executive_summary": self.executive_summary,
            "recommendations": self.recommendations,
        }

    def to_markdown(self) -> str:
        risk_emoji = {
            "Low": "🟢 Low",
            "Medium": "🟡 Medium",
            "High": "🟠 High",
            "Critical": "🔴 Critical",
        }.get(self.triage.risk_level, self.triage.risk_level)

        verdict_badge = {
            "APPROVED": "✅ **MERGE APPROVED**",
            "CHANGES_REQUESTED": "⚠️ **CHANGES REQUESTED**",
            "BLOCKED": "🛑 **MERGE BLOCKED (SECURITY RISK)**",
        }.get(self.verdict, self.verdict)

        lines = [
            f"# 🤖 Autonomous PR Review & Triage Council Report",
            f"",
            f"**Target:** `{self.title}` ({self.source})  ",
            f"**Generated:** {self.created_at}  ",
            f"**Verdict:** {verdict_badge} | **Code Health Score:** `{self.health_score}/100`  ",
            f"",
            f"---",
            f"",
            f"## 🏛️ Specialist Agent Council Scorecard",
            f"",
            f"| Specialist Agent | Health Score | Status | Key Observation |",
            f"| :--- | :---: | :---: | :--- |",
        ]

        for s in self.specialist_reviews:
            status_icon = "🟢" if s.status == "PASSED" else ("🟡" if s.status == "WARNING" else "🔴")
            lines.append(f"| **{s.agent_name}** | `{s.score}/100` | {status_icon} `{s.status}` | {s.summary} |")

        lines.extend([
            f"",
            f"---",
            f"",
            f"## 📊 Triage & Sizing Analysis",
            f"",
            f"| Metric | Assessment |",
            f"| :--- | :--- |",
            f"| **PR Classification** | `{self.triage.pr_type}` |",
            f"| **Change Volume** | `{self.triage.size_tier}` (+{self.triage.total_additions} / -{self.triage.total_deletions} lines across {self.triage.total_files} file{'s' if self.triage.total_files != 1 else ''}) |",
            f"| **Composite Risk** | {risk_emoji} |",
            f"",
            f"**Triage Note:** {self.triage.summary}",
            f"",
            f"---",
            f"",
            f"## 📝 Executive Decision",
            f"",
            f"{self.executive_summary}",
            f"",
            f"---",
            f"",
            f"## 🔍 Findings & Remediation ({len(self.issues)} issue{'s' if len(self.issues) != 1 else ''} identified)",
            f"",
        ])

        if not self.issues:
            lines.append("🎉 **No major issues or security concerns detected in this diff.** Ready to merge.\n")
        else:
            severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
            sorted_issues = sorted(self.issues, key=lambda x: severity_order.get(x.severity, 99))

            for i, issue in enumerate(sorted_issues, 1):
                icon = {
                    "CRITICAL": "🚨 **CRITICAL**",
                    "HIGH": "⚠️ **HIGH**",
                    "MEDIUM": "⚡ **MEDIUM**",
                    "LOW": "ℹ️ **LOW**",
                    "INFO": "💡 **INFO**",
                }.get(issue.severity, issue.severity)

                cwe_tag = f" `[{issue.cwe_id}]`" if issue.cwe_id else ""
                loc = f"`{issue.file}`" + (f":L{issue.line}" if issue.line else "")
                lines.append(f"### {i}. {icon}: {issue.title}{cwe_tag}")
                lines.append(f"- **Location:** {loc}")
                lines.append(f"- **Category:** `{issue.category}`")
                lines.append(f"- **Description:** {issue.description}")
                if issue.suggestion:
                    lines.append(f"- **Suggested Remediation:**\n")
                    lines.append(f"```suggestion\n{issue.suggestion}\n```\n")
                lines.append("")

        if self.remediation_patch:
            lines.extend([
                "---",
                "",
                "## 🩹 Autonomous Remediation Patch",
                "",
                "> An automated patch file has been compiled for detected issues. Apply with `git apply remediation.patch`.",
                "",
                "```diff",
                self.remediation_patch.strip(),
                "```",
                "",
            ])

        if self.generated_tests:
            lines.extend([
                "---",
                "",
                "## 🧪 Synthesized Regression & Unit Tests",
                "",
                f"> The **Test Generator Agent** automatically authored {len(self.generated_tests)} test case(s) covering changed logic:",
                "",
            ])
            for t in self.generated_tests:
                lines.append(f"### Test: `{t.test_name}` ({t.target_file})")
                lines.append(f"*{t.description}*\n")
                lines.append(f"```python\n{t.code.strip()}\n```\n")

        lines.extend([
            "---",
            "",
            "## ✅ Reviewer Action Checklist",
            "",
        ])
        for rec in self.recommendations:
            lines.append(f"- [ ] {rec}")

        lines.append("")
        return "\n".join(lines)
