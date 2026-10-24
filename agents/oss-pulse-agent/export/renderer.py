"""Report rendering and export.

Renders health reports as:
- Rich terminal output (colorful, interactive)
- Markdown document (for README/PR embedding)
- JSON (for programmatic consumption)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from models.report import HealthReport, Severity, Category


def _get_score_color(score: float) -> str:
    if score >= 80:
        return "bold green"
    if score >= 60:
        return "bold yellow"
    return "bold red"


def _get_severity_style(sev: Severity) -> str:
    if sev == Severity.CRITICAL:
        return "bold white on red"
    if sev == Severity.HIGH:
        return "bold red"
    if sev == Severity.MEDIUM:
        return "bold yellow"
    if sev == Severity.LOW:
        return "cyan"
    return "dim"


def render_terminal(report: HealthReport, console: Optional[Console] = None) -> None:
    """Print an interactive and structured terminal presentation using Rich."""
    c = console or Console()

    # 1. Header Banner
    repo = report.repository
    score_color = _get_score_color(report.overall_score)

    header_text = Text()
    header_text.append(f"{repo.full_name}\n", style="bold cyan")
    if repo.description:
        header_text.append(f"{repo.description}\n", style="italic")
    header_text.append(
        f"Language: {repo.language or 'Unknown'}  |  Stars: {repo.stars:,}  |  Forks: {repo.forks:,}  |  License: {repo.license_name or 'None'}\n",
        style="dim",
    )
    header_text.append(
        f"Health Score: {report.overall_score:.0f}/100 ({report.overall_grade})  |  "
        f"Data Coverage: {report.data_coverage_percentage:.0f}%  |  "
        f"Evidence Quality: {report.evidence_quality}\n",
        style="bold green" if report.overall_score >= 70 else "bold yellow",
    )

    score_panel = Panel(
        Text(f"{report.overall_score:.0f}\n{report.overall_grade}", justify="center", style=score_color),
        title="[bold]Health Score[/bold]",
        border_style="cyan",
        width=18,
    )

    c.print()
    c.print(
        Panel(
            header_text,
            title="[bold blue]🏥 OSS Pulse Intelligence Report[/bold blue]",
            subtitle=f"Analyzed in {report.analysis_duration_seconds}s",
            border_style="blue",
        )
    )

    # 2. Categories Breakdown Table
    cat_table = Table(
        title="Repository Health Dimensions",
        box=box.ROUNDED,
        header_style="bold magenta",
        expand=True,
    )
    cat_table.add_column("Category", style="cyan")
    cat_table.add_column("Score", justify="right")
    cat_table.add_column("Weight", justify="right")
    cat_table.add_column("Key Evidence", style="dim")

    for cs in report.category_scores:
        cat_color = _get_score_color(cs.score)
        label = cs.category.value.title()
        if cs.category == Category.SECURITY:
            label = "Security Config (Not Audit)"
        cat_table.add_row(
            label,
            f"[{cat_color}]{cs.score:.1f}/100[/{cat_color}]",
            f"{cs.weight:.0%}",
            cs.evidence_summary,
        )
    c.print(cat_table)

    # 3. AI Insights / Executive Summary
    if report.ai_summary:
        c.print(
            Panel(
                report.ai_summary,
                title="[bold yellow]🤖 Gemini Agent Insights[/bold yellow]",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )

    # 4. Actionable Findings Table
    if report.all_findings:
        find_table = Table(
            title=f"Actionable Findings & Prioritized Remediation ({len(report.all_findings)})",
            box=box.ROUNDED,
            header_style="bold red",
            expand=True,
        )
        find_table.add_column("ID", width=10, style="dim")
        find_table.add_column("Severity", width=12)
        find_table.add_column("Issue & Impact")
        find_table.add_column("Recommended Fix", style="green")
        find_table.add_column("Effort", width=10, justify="center")

        for f in report.all_findings[:8]:
            sev_style = _get_severity_style(f.severity)
            find_table.add_row(
                f.id,
                f"[{sev_style}]{f.severity.value.upper()}[/{sev_style}]",
                f"[bold]{f.title}[/bold]\n[dim]{f.impact}[/dim]",
                f.recommended_fix,
                f.effort.title(),
            )
        c.print(find_table)

    # 5. Contribution Opportunities
    if report.contribution_opportunities:
        opp_table = Table(
            title=f"🌱 Recommended Contribution Opportunities ({len(report.contribution_opportunities)})",
            box=box.ROUNDED,
            header_style="bold green",
            expand=True,
        )
        opp_table.add_column("Issue Title", style="bold")
        opp_table.add_column("Difficulty", width=14, justify="center")
        opp_table.add_column("Context", style="dim")
        opp_table.add_column("Link")

        for opp in report.contribution_opportunities[:5]:
            opp_table.add_row(
                opp.title[:50] + ("..." if len(opp.title) > 50 else ""),
                opp.difficulty.title(),
                opp.why_good_fit,
                f"[link={opp.url}]View on GitHub[/link]",
            )
        c.print(opp_table)

    # 6. Data Coverage & Footer
    cov = report.data_coverage_summary
    c.print(
        f"[dim]Data Coverage: {cov.get('metrics_measured', 0)} of {cov.get('total_metrics', 0)} metrics measured. "
        f"{report.disclaimer}[/dim]\n"
    )


def render_markdown(report: HealthReport) -> str:
    """Generate a clean, publication-ready GitHub Flavored Markdown report."""
    repo = report.repository
    lines = [
        f"# 🏥 OSS Pulse Health Report: [{repo.full_name}]({repo.url})",
        "",
        f"> **Overall Health Score:** `{report.overall_score:.0f}/100` ({report.overall_grade})  ",
        f"> **Data Coverage:** `{report.data_coverage_percentage:.0f}%` | **Evidence Quality Tier:** `{report.evidence_quality}`  ",
        f"> **Analysis Timestamp:** {report.analysis_timestamp}  ",
        f"> *Security Notice: Evaluates observable repository configuration and posture only. This is not a vulnerability scan or penetration audit.*  ",
        f"> *{report.disclaimer}*",
        "",
        "## 📊 Health Dimension Breakdown",
        "",
        "| Category | Score | Weight | Key Evidence Summary |",
        "| :--- | :---: | :---: | :--- |",
    ]

    for cs in report.category_scores:
        lines.append(
            f"| **{cs.category.value.title()}** | `{cs.score:.1f}/100` | `{cs.weight:.0%}` | {cs.evidence_summary} |"
        )

    lines.extend([
        "",
        "## 🤖 AI Executive Insights & Analysis",
        "",
        report.ai_summary or "Deterministic analysis completed.",
        "",
    ])

    if report.ai_recommendations:
        lines.extend([
            "### 🎯 Strategic Recommendations",
            "",
        ])
        for idx, rec in enumerate(report.ai_recommendations, start=1):
            lines.append(f"{idx}. {rec}")
        lines.append("")

    if report.all_findings:
        lines.extend([
            f"## 🔍 Evidence-Backed Findings ({len(report.all_findings)})",
            "",
        ])
        for f in report.all_findings:
            lines.extend([
                f"### `[{f.id}]` {f.title} ({f.severity.value.upper()})",
                f"- **Category**: `{f.category.value}`",
                f"- **Impact**: {f.impact}",
                f"- **Recommended Fix**: {f.recommended_fix}",
                f"- **Estimated Effort**: `{f.effort}` | **Confidence**: `{f.confidence.value}`",
            ])
            if f.evidence:
                lines.append("- **Supporting Evidence**:")
                for ev in f.evidence:
                    url_part = f" ([Source]({ev.url}))" if ev.url else ""
                    lines.append(f"  - `{ev.metric}` = `{ev.value}`: {ev.context}{url_part}")
            lines.append("")

    if report.contribution_opportunities:
        lines.extend([
            "## 🌱 Contribution Readiness & Good First Issues",
            "",
            "| Issue | Difficulty | Why It's a Good Fit |",
            "| :--- | :---: | :--- |",
        ])
        for opp in report.contribution_opportunities:
            lines.append(f"| [{opp.title}]({opp.url}) | `{opp.difficulty}` | {opp.why_good_fit} |")
        lines.append("")

    cov = report.data_coverage_summary
    lines.extend([
        "---",
        "## 📈 Data Coverage & Verification",
        f"- Metrics verified: `{cov.get('metrics_measured', 0)}`",
        f"- Metrics unavailable/restricted: `{cov.get('metrics_unavailable', 0)}`",
        f"- Analysis duration: `{report.analysis_duration_seconds}s`",
        "",
        "*Generated with ❤️ by OSS Pulse Agent — Powered by Google Gemini.*",
    ])

    return "\n".join(lines)


def render_json(report: HealthReport) -> str:
    """Export report as formatted JSON."""
    return report.model_dump_json(indent=2)


def save_report(report: HealthReport, output_path: str, format_type: str = "markdown") -> None:
    """Save the report to disk in markdown, json, or both formats."""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if format_type in ("markdown", "all"):
        md_file = p.with_suffix(".md")
        md_file.write_text(render_markdown(report), encoding="utf-8")

    if format_type in ("json", "all"):
        json_file = p.with_suffix(".json")
        json_file.write_text(render_json(report), encoding="utf-8")
