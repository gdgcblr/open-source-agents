"""Live terminal dashboard for idle-janitor.

Renders a scrollable table of running Docker containers + dev-server processes
with uptime, CPU%, memory, idle status, and a live ₹ / Wh / CO2 counter in the
header. Refreshes every N seconds. Policy decisions decorate each row.

This module is the showstopper surface for a judge demo.
"""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import cost, policies, scan


_ACTION_STYLE = {
    "reap": "bold red",
    "warn": "yellow",
    "protect": "cyan",
    "snooze": "magenta",
    "none": "dim",
    "": "dim",
}


def _render_header(summary: dict[str, Any], docker_available: bool, tick: int) -> Panel:
    headline = Text()
    headline.append("idle-janitor ", style="bold green")
    headline.append("\u2022 live\n", style="dim")
    headline.append(summary["headline"], style="bold white")
    headline.append("\n")
    headline.append(
        f"Resources tracked: {summary['resource_count']}   "
        f"Docker: {'reachable' if docker_available else 'unreachable (process-only)'}   "
        f"Tick #{tick}",
        style="dim",
    )
    return Panel(headline, border_style="green", title="\u2728 idle-janitor")


def _render_table(
    resources: list[dict[str, Any]],
    decisions_by_id: dict[str, policies.Decision],
) -> Table:
    table = Table(expand=True, show_lines=False, header_style="bold cyan")
    table.add_column("Resource", overflow="fold")
    table.add_column("Kind", width=8)
    table.add_column("Uptime", width=10)
    table.add_column("CPU %", justify="right", width=7)
    table.add_column("Mem MB", justify="right", width=8)
    table.add_column("Wh", justify="right", width=7)
    table.add_column("\u20b9", justify="right", width=7)
    table.add_column("g CO\u2082", justify="right", width=8)
    table.add_column("Policy", overflow="fold")

    if not resources:
        table.add_row(
            Text("No idle resources detected. Your laptop is thanking you.", style="dim"),
            "", "", "", "", "", "", "", "",
        )
        return table

    # Sort: biggest wasters first.
    resources = sorted(resources, key=lambda r: r.get("wh", 0.0), reverse=True)

    for r in resources:
        decision = decisions_by_id.get(r["id"])
        policy_text = Text()
        if decision:
            policy_text.append(
                f"{decision.action.upper()} ",
                style=_ACTION_STYLE.get(decision.action, "white"),
            )
            policy_text.append(decision.rule, style="dim")
        else:
            policy_text.append("(no rule)", style="dim")

        label = r.get("name") or r.get("id", "?")
        subtitle_bits = []
        if r.get("image"):
            subtitle_bits.append(r["image"])
        if r.get("cmdline"):
            subtitle_bits.append(r["cmdline"][:60])
        label_full = Text(label, style="bold")
        if subtitle_bits:
            label_full.append(f"\n{subtitle_bits[0]}", style="dim")

        cpu = r.get("cpu_percent", 0.0)
        cpu_style = "green" if cpu < 1 else "yellow" if cpu < 10 else "red"

        table.add_row(
            label_full,
            r.get("kind", "?"),
            r.get("uptime_human", "?"),
            Text(f"{cpu:.1f}", style=cpu_style),
            f"{r.get('mem_mb', 0):.0f}",
            f"{r.get('wh', 0):.1f}",
            f"{r.get('inr', 0):.2f}",
            f"{r.get('co2_g', 0):.1f}",
            policy_text,
        )

    return table


def _render_footer(history_summary: dict[str, Any]) -> Panel:
    text = Text()
    text.append("Last 7 days: ", style="bold")
    text.append(
        f"\u20b9{history_summary.get('total_inr', 0):.2f}, "
        f"{history_summary.get('total_wh', 0):.1f} Wh, "
        f"{history_summary.get('total_co2_g', 0):.1f} g CO\u2082 "
        f"across {history_summary.get('resource_count', 0)} distinct resource(s)."
    )
    text.append("\n", style="")
    text.append(
        "Press Ctrl+C to exit. Policies: ~/.idle-janitor/policies.yaml  "
        "DB: ~/.idle-janitor/history.db",
        style="dim",
    )
    return Panel(text, border_style="dim", title="history")


def run(refresh_seconds: float = 2.0, min_idle_minutes: int = 0) -> None:
    """Blocking live dashboard loop until Ctrl+C."""
    from . import history as history_mod  # local import to avoid cycle

    console = Console()
    tick = 0

    with Live(console=console, screen=False, refresh_per_second=1 / refresh_seconds) as live:
        try:
            while True:
                tick += 1
                snap = scan.scan_and_journal(min_idle_minutes=min_idle_minutes)
                idle = snap["resources"]
                summary = cost.summarize(idle)
                decisions = policies.evaluate(idle)
                decisions_by_id = {d.resource_id: d for d in decisions}
                history_summary = history_mod.summarize_window("7d")

                group = Group(
                    _render_header(summary, snap["docker_available"], tick),
                    _render_table(idle, decisions_by_id),
                    _render_footer(history_summary),
                )
                live.update(group)
                time.sleep(refresh_seconds)
        except KeyboardInterrupt:
            console.print("\n[dim]idle-janitor live \u2014 bye.[/dim]")
