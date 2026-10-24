"""Rich terminal output, diff coloring, and UI rendering for AgentFeat."""

from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.theme import Theme

custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "highlight": "magenta",
})

console = Console(theme=custom_theme)


def print_banner() -> None:
    """Print the AgentFeat startup banner."""
    banner = """
 [bold cyan]⚡ AgentFeat[/bold cyan] : [italic green]AI-Powered Feature Development Agent[/italic green]
 [dim]From feature request to working code, with AI[/dim]
"""
    console.print(Panel(banner, border_style="cyan", expand=False))


def print_plan(plan) -> None:
    """Display the structured FeaturePlan in a clean, readable table and panel."""
    console.print(f"\n[bold magenta]📋 Feature Plan:[/bold magenta] [bold white]{plan.feature_title}[/bold white]")
    console.print(f"[dim]{plan.summary}[/dim]\n")

    table = Table(title="Implementation Steps", show_header=True, header_style="bold cyan")
    table.add_column("Step", style="dim", width=6)
    table.add_column("Action", style="bold", width=10)
    table.add_column("Target File", style="yellow")
    table.add_column("Description")

    action_colors = {
        "create": "[green]CREATE[/green]",
        "modify": "[yellow]MODIFY[/yellow]",
        "delete": "[red]DELETE[/red]",
        "test": "[blue]TEST[/blue]",
    }

    for s in plan.steps:
        act = action_colors.get(s.action, s.action.upper())
        table.add_row(str(s.step_number), act, s.target_file, s.description)

    console.print(table)

    if plan.new_dependencies:
        dep_str = ", ".join(f"[bold green]{d}[/bold green]" for d in plan.new_dependencies)
        console.print(f"\n[bold cyan]📦 New Dependencies:[/bold cyan] {dep_str}")

    console.print(f"\n[bold cyan]🧪 Testing Strategy:[/bold cyan] {plan.test_strategy}")
    console.print(f"[bold yellow]⚠️  Risk Assessment:[/bold yellow] {plan.risk_assessment}\n")


def print_diff(file_path: str, diff_text: str) -> None:
    """Render a colored unified diff in terminal."""
    console.print(f"\n[bold cyan]Changes preview for:[/bold cyan] [bold white]{file_path}[/bold white]")
    if not diff_text.strip():
        console.print("[dim](No line-level changes)[/dim]")
        return
    syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=True)
    console.print(syntax)


def print_summary_table(changes: List, applied: bool) -> None:
    """Display summary table of changes made."""
    table = Table(title="Generated Changes Summary", show_header=True, header_style="bold green")
    table.add_column("File", style="bold white")
    table.add_column("Action", width=10)
    table.add_column("Validation", width=14)
    table.add_column("Status", width=12)

    for c in changes:
        val_status = "[green]PASSED[/green]" if c.is_valid else f"[red]FAILED[/red] ({c.validation_error or 'Syntax error'})"
        app_status = "[green]APPLIED[/green]" if applied else "[yellow]DRY-RUN[/yellow]"
        table.add_row(c.file_path, c.action.upper(), val_status, app_status)

    console.print(table)
