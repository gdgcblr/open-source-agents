import sys
from .models import ReviewReport

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def print_rich_report(report: ReviewReport) -> None:
    """Render a terminal scorecard and report using rich (or ANSI fallback)."""
    if not HAS_RICH:
        print(report.to_markdown())
        return

    console = Console()

    # Verdict banner
    verdict_styles = {
        "APPROVED": "bold green",
        "CHANGES_REQUESTED": "bold yellow",
        "BLOCKED": "bold red on black",
    }
    style = verdict_styles.get(report.verdict, "bold cyan")
    banner_text = Text(f"\n  VERDICT: {report.verdict}  |  HEALTH SCORE: {report.health_score}/100  \n", style=style)
    console.print(Panel(banner_text, title=f"🤖 PR Council Review: {report.title}", border_style="cyan"))

    # Specialist Council Table
    table = Table(title="🏛️ Specialist Agent Council Scorecard", border_style="blue")
    table.add_column("Specialist Agent", style="bold white")
    table.add_column("Health Score", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Key Observation", style="dim")

    for s in report.specialist_reviews:
        status_color = "green" if s.status == "PASSED" else ("yellow" if s.status == "WARNING" else "red")
        table.add_row(
            s.agent_name,
            f"{s.score}/100",
            f"[{status_color}]{s.status}[/{status_color}]",
            s.summary
        )
    console.print(table)

    # Triage Info
    triage_table = Table(title="📊 Triage & Sizing Analysis", border_style="magenta")
    triage_table.add_column("Classification", justify="center")
    triage_table.add_column("Size Tier", justify="center")
    triage_table.add_column("Lines (+/-)", justify="center")
    triage_table.add_column("Risk Level", justify="center")

    risk_style = "red" if report.triage.risk_level == "Critical" else ("yellow" if report.triage.risk_level == "High" else "green")
    triage_table.add_row(
        report.triage.pr_type,
        report.triage.size_tier,
        f"+{report.triage.total_additions} / -{report.triage.total_deletions}",
        f"[{risk_style}]{report.triage.risk_level}[/{risk_style}]"
    )
    console.print(triage_table)

    # Print Findings
    console.print(f"\n[bold underline]🔍 Findings & Remediation ({len(report.issues)} identified):[/bold underline]\n")
    for i, issue in enumerate(report.issues, 1):
        color = "red" if issue.severity == "CRITICAL" else ("yellow" if issue.severity == "HIGH" else "blue")
        cwe = f" [{issue.cwe_id}]" if issue.cwe_id else ""
        console.print(f"{i}. [{color} bold][{issue.severity}][/{color} bold] [white bold]{issue.title}[/white bold]{cwe}")
        console.print(f"   [dim]Location: {issue.file}:{issue.line or 'N/A'}[/dim]")
        console.print(f"   {issue.description}")
        if issue.suggestion:
            console.print(f"   [green]Fix:[/green] {issue.suggestion}")
        console.print("")

    if report.remediation_patch:
        console.print(Panel(
            report.remediation_patch.strip(),
            title="🩹 Autonomous Remediation Patch (git apply)",
            border_style="green"
        ))
