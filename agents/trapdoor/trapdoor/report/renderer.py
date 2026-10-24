"""
Report renderer — rich CLI output and JSON serialization.
Kept separate so the eval logic has zero UI dependency.
"""

import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ..eval.evaluator import EvaluationReport
from ..traps.scenarios import TRAP_TOOL_NAMES

console = Console()


def render_rich(report: EvaluationReport) -> None:
    verdict_color = "red" if report.verdict == "COMPROMISED" else "green"
    verdict_label = "❌  COMPROMISED" if report.verdict == "COMPROMISED" else "✅  SAFE"

    console.print()
    console.print(Panel(
        f"[bold {verdict_color}]{verdict_label}[/bold {verdict_color}]",
        title="[bold]TrapDoor — Agent Security Evaluation[/bold]",
        subtitle=f"[dim]{report.turns} turn(s) · {len(report.all_tool_calls)} tool call(s)[/dim]",
        border_style=verdict_color,
        expand=False,
    ))

    # Tool call trace table
    table = Table(title="Agent Tool Call Trace", box=box.ROUNDED, show_lines=True)
    table.add_column("Turn", justify="center", style="dim", width=6)
    table.add_column("Tool", style="cyan")
    table.add_column("Type", justify="center", width=12)
    table.add_column("Args", overflow="fold")

    for tc in report.all_tool_calls:
        is_trap = tc.name in TRAP_TOOL_NAMES
        tag = "[bold red]TRAP[/bold red]" if is_trap else "[green]safe[/green]"
        args_str = json.dumps(tc.args) if tc.args else "—"
        table.add_row(str(tc.turn), tc.name, tag, args_str)

    console.print(table)

    # Evidence
    if report.evidence:
        console.print("\n[bold yellow]Evidence:[/bold yellow]")
        for e in report.evidence:
            console.print(f"  • {e}")

    # Findings with mitigations
    if report.findings:
        console.print("\n[bold red]Findings & Mitigations:[/bold red]")
        for f in report.findings:
            console.print(f"\n  [red]● {f.attack_type}[/red] via `{f.tool_call.name}` (turn {f.tool_call.turn})")
            console.print(f"    [blue]💡 Mitigation:[/blue] {f.mitigation}")

    if report.suspicious_patterns:
        console.print("\n[bold yellow]Suspicious Patterns Detected:[/bold yellow]")
        for p in report.suspicious_patterns:
            console.print(f"  ⚠ `{p}`")

    if report.verdict == "SAFE":
        console.print("\n[bold green]Agent successfully resisted all adversarial instructions.[/bold green]")

    console.print()


def render_json(report: EvaluationReport) -> str:
    data = {
        "verdict": report.verdict,
        "turns": report.turns,
        "total_tool_calls": len(report.all_tool_calls),
        "trap_tools_invoked": [f.tool_call.name for f in report.findings],
        "suspicious_patterns": report.suspicious_patterns,
        "evidence": report.evidence,
        "findings": [
            {
                "tool": f.tool_call.name,
                "attack_type": f.attack_type,
                "turn": f.tool_call.turn,
                "mitigation": f.mitigation,
            }
            for f in report.findings
        ],
        "tool_call_trace": [
            {"turn": tc.turn, "name": tc.name, "args": tc.args, "is_trap": tc.name in TRAP_TOOL_NAMES}
            for tc in report.all_tool_calls
        ],
    }
    return json.dumps(data, indent=2)
