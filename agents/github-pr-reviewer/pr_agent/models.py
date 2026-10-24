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
    raw_llm_analysis: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "source": self.source,
            "created_at": self.created_at,
            "triage": {
                "pr_type": self.triage.pr_type,
                "size_tier": self.triage.size_tier,
                "risk_level": self.triage.risk_level,
                "total_additions": self.triage.total_additions,
                "total_deletions": self.triage.total_deletions,
                "total_files": self.triage.total_files,
                "summary": self.triage.summary,
            },
            "issues": [
                {
                    "file": issue.file,
                    "line": issue.line,
                    "severity": issue.severity,
                    "category": issue.category,
                    "title": issue.title,
                    "description": issue.description,
                    "suggestion": issue.suggestion,
                }
                for issue in self.issues
            ],
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

        lines = [
            f"# 🤖 Pull Request Review & Triage Report",
            f"",
            f"**Target:** `{self.title}` ({self.source})  ",
            f"**Generated:** {self.created_at}  ",
            f"",
            f"---",
            f"",
            f"## 📊 Triage Summary",
            f"",
            f"| Metric | Assessment |",
            f"| :--- | :--- |",
            f"| **Type** | `{self.triage.pr_type}` |",
            f"| **Size** | `{self.triage.size_tier}` (+{self.triage.total_additions} / -{self.triage.total_deletions} lines across {self.triage.total_files} file{'s' if self.triage.total_files != 1 else ''}) |",
            f"| **Risk Level** | {risk_emoji} |",
            f"",
            f"**Triage Note:** {self.triage.summary}",
            f"",
            f"---",
            f"",
            f"## 📝 Executive Summary",
            f"",
            f"{self.executive_summary}",
            f"",
            f"---",
            f"",
            f"## 🔍 Findings & Recommendations ({len(self.issues)} issue{'s' if len(self.issues) != 1 else ''} identified)",
            f"",
        ]

        if not self.issues:
            lines.append("🎉 **No major issues or security concerns detected in this diff.** Good to proceed to maintainer review.\n")
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

                loc = f"`{issue.file}`" + (f":L{issue.line}" if issue.line else "")
                lines.append(f"### {i}. {icon}: {issue.title}")
                lines.append(f"- **Location:** {loc}")
                lines.append(f"- **Category:** `{issue.category}`")
                lines.append(f"- **Description:** {issue.description}")
                if issue.suggestion:
                    lines.append(f"- **Suggested Fix:**\n")
                    lines.append(f"```suggestion\n{issue.suggestion}\n```\n")
                lines.append("")

        lines.extend([
            "---",
            "",
            "## ✅ Reviewer Checklist",
            "",
        ])
        for rec in self.recommendations:
            lines.append(f"- [ ] {rec}")

        lines.append("")
        return "\n".join(lines)
