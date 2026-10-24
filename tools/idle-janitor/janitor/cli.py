"""idle-janitor CLI.

Entry point installed as the `idle-janitor` command. Commands:

    idle-janitor status      One-shot summary of idle resources + waste.
    idle-janitor live        Live refreshing TUI dashboard (showstopper).
    idle-janitor history     Weekly / windowed waste summary from the journal.
    idle-janitor reap        Dry-run (default) or real termination of idle items.
    idle-janitor policies    Show, edit, or (re)initialize the policy file.
    idle-janitor serve       Start the MCP server on stdio.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import aws_scan, cost, docker_scan, firebase_scan, history, policies as policies_mod, process_scan, safety, scan, snooze
from . import tui as tui_mod
from . import watcher as watcher_mod

app = typer.Typer(
    help=(
        "idle-janitor \u2014 audit, cost, and reap idle Docker containers "
        "and local dev-server processes. All local, no network, no secrets."
    ),
    no_args_is_help=True,
    add_completion=False,
)

console = Console()


def _idle_from_snapshot(min_idle_minutes: int = 0) -> dict:
    snap = scan.scan_and_journal(min_idle_minutes=min_idle_minutes)
    return snap


@app.command()
def status(
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    min_idle_minutes: int = typer.Option(0, "--min-idle-minutes", help="Only count resources older than this."),
) -> None:
    """One-shot summary of currently idle resources + ₹/Wh/CO₂ wasted."""
    snap = _idle_from_snapshot(min_idle_minutes=min_idle_minutes)
    summary = cost.summarize(snap["resources"])
    payload = {
        "headline": summary["headline"],
        "docker_available": snap["docker_available"],
        "docker_error": snap["docker_error"],
        "resources": snap["resources"],
        "summary": summary,
        "snoozed": snap["snoozed"],
    }
    if json_out:
        print(json.dumps(payload, indent=2, default=str))
        return

    console.rule("[bold green]idle-janitor \u2022 status")
    console.print(f"[bold]{summary['headline']}[/bold]\n")
    if not snap["docker_available"]:
        console.print(
            f"[yellow]Docker unavailable:[/yellow] {snap['docker_error']}  "
            f"[dim](process-only mode)[/dim]\n"
        )

    if not snap["resources"]:
        console.print("[green]Nothing idle. Nice.[/green]")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Resource")
    table.add_column("Kind", width=8)
    table.add_column("Uptime", width=10)
    table.add_column("CPU %", justify="right")
    table.add_column("Mem MB", justify="right")
    table.add_column("Wh", justify="right")
    table.add_column("\u20b9", justify="right")
    table.add_column("g CO\u2082", justify="right")

    for r in sorted(snap["resources"], key=lambda x: x.get("wh", 0), reverse=True):
        table.add_row(
            r.get("name") or r.get("id", "?"),
            r.get("kind", "?"),
            r.get("uptime_human", "?"),
            f"{r.get('cpu_percent', 0):.1f}",
            f"{r.get('mem_mb', 0):.0f}",
            f"{r.get('wh', 0):.1f}",
            f"{r.get('inr', 0):.2f}",
            f"{r.get('co2_g', 0):.1f}",
        )
    console.print(table)


@app.command()
def live(
    refresh: float = typer.Option(2.0, "--refresh", help="Refresh interval seconds."),
    min_idle_minutes: int = typer.Option(0, "--min-idle-minutes"),
) -> None:
    """Live refreshing dashboard. Press Ctrl+C to exit."""
    tui_mod.run(refresh_seconds=refresh, min_idle_minutes=min_idle_minutes)


@app.command("history")
def history_cmd(
    window: str = typer.Option("7d", "--window", help="7d, 24h, 60m, or raw seconds."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """Windowed waste summary from the local SQLite journal."""
    summary = history.summarize_window(window)
    if json_out:
        print(json.dumps(summary, indent=2))
        return
    console.rule(f"[bold green]idle-janitor \u2022 history ({window})")
    console.print(
        f"\u20b9{summary['total_inr']:.2f}, "
        f"{summary['total_wh']:.1f} Wh, "
        f"{summary['total_co2_g']:.1f} g CO\u2082 "
        f"across {summary['resource_count']} resource(s) in the last {window}.\n"
    )
    if not summary["resources"]:
        console.print(
            "[dim]No history yet. Run `idle-janitor status` or `idle-janitor live` "
            "a few times to prime the journal.[/dim]"
        )
        return
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Resource")
    table.add_column("Kind", width=8)
    table.add_column("Wh", justify="right")
    table.add_column("\u20b9", justify="right")
    table.add_column("g CO\u2082", justify="right")
    table.add_column("Samples", justify="right")
    for r in summary["resources"]:
        table.add_row(
            r["name"] or r["resource_id"],
            r["kind"],
            f"{r['wh']:.1f}",
            f"{r['inr']:.2f}",
            f"{r['co2_g']:.1f}",
            str(r["samples"]),
        )
    console.print(table)


@app.command()
def reap(
    only_policy: bool = typer.Option(
        True,
        "--only-policy/--all-idle",
        help="Only reap resources whose policy action is 'reap' (safe). --all-idle reaps everything idle except protected ones.",
    ),
    dry_run: bool = typer.Option(True, "--dry-run/--for-real", help="Default: dry run."),
    min_idle_minutes: int = typer.Option(0, "--min-idle-minutes"),
    force: bool = typer.Option(False, "--force", help="SIGKILL instead of SIGTERM for processes."),
) -> None:
    """Reap idle resources per the policy engine. Dry-run by default."""
    snap = _idle_from_snapshot(min_idle_minutes=min_idle_minutes)
    decisions = policies_mod.evaluate(snap["resources"])
    decisions_by_id = {d.resource_id: d for d in decisions}

    plan: list[dict] = []
    for r in snap["resources"]:
        d = decisions_by_id.get(r["id"])
        action = d.action if d else "none"
        if action == "protect":
            continue
        if only_policy and action != "reap":
            continue
        plan.append({"resource": r, "decision": d})

    if not plan:
        console.print("[green]Nothing to reap. Everything idle is protected or has no reap policy.[/green]")
        return

    console.rule("[bold red]reap plan" + (" (dry-run)" if dry_run else ""))
    for item in plan:
        r = item["resource"]
        d = item["decision"]
        rule = d.rule if d else "all-idle"
        console.print(
            f"- [bold]{r.get('name') or r['id']}[/bold] "
            f"([cyan]{r['kind']}[/cyan], uptime {r.get('uptime_human')}, "
            f"\u20b9{r.get('inr', 0):.2f}) \u2192 "
            f"[red]{'DRY-RUN ' if dry_run else ''}REAP[/red] "
            f"[dim]rule={rule}[/dim]"
        )

    if dry_run:
        console.print(
            f"\n[dim]{len(plan)} resource(s) would be reaped. "
            "Re-run with --for-real to actually stop them.[/dim]"
        )
        for item in plan:
            history.record_reap(item["resource"], dry_run=True, reason=item["decision"].rule if item["decision"] else "all-idle")
        return

    for item in plan:
        r = item["resource"]
        rule = item["decision"].rule if item["decision"] else "all-idle"
        verdict = safety.check_reap(r["id"], resource=r)
        if not verdict.allowed:
            history.record_reap(
                r, dry_run=False,
                reason=f"REFUSED by guard despite rule={rule}: {'; '.join(verdict.reasons)}",
            )
            console.print(
                f"  {r.get('name') or r['id']}: [yellow]REFUSED[/yellow] "
                f"({'; '.join(verdict.reasons)})"
            )
            continue
        safety.record_action()
        if r["kind"] == "docker":
            res = docker_scan.terminate(r["id"].split(":", 1)[1], dry_run=False)
        elif r["kind"] == "process":
            res = process_scan.terminate(int(r["id"].split(":", 1)[1]), dry_run=False, force=force)
        else:
            res = {"ok": False, "error": f"unknown kind {r['kind']}"}
        history.record_reap(r, dry_run=False, reason=rule)
        mark = "[green]OK[/green]" if res.get("ok") else f"[red]FAIL[/red] ({res.get('error')})"
        console.print(f"  {r.get('name') or r['id']}: {mark}")


@app.command()
def policies(
    init: bool = typer.Option(False, "--init", help="Write the default policies file."),
    show: bool = typer.Option(True, "--show/--no-show", help="Print the active policies."),
    evaluate: bool = typer.Option(False, "--evaluate", help="Evaluate policies against the current snapshot."),
) -> None:
    """Show, initialize, or evaluate the policy engine."""
    if init:
        path = policies_mod.write_default_policies(force=True)
        console.print(f"[green]Wrote default policies to {path}[/green]")
    active = policies_mod.load_policies()
    if show:
        import yaml  # local
        console.rule("[bold green]active policies")
        console.print(yaml.safe_dump(active, sort_keys=False), highlight=False)
    if evaluate:
        snap = _idle_from_snapshot()
        decisions = policies_mod.evaluate(snap["resources"])
        console.rule("[bold green]decisions on current snapshot")
        if not decisions:
            console.print("[dim]No matches.[/dim]")
        for d in decisions:
            console.print(
                f"- [bold]{d.name or d.resource_id}[/bold] ({d.kind}) \u2192 "
                f"[yellow]{d.action.upper()}[/yellow] via [cyan]{d.rule}[/cyan] "
                f"[dim]({d.reason})[/dim]"
            )


@app.command("snooze")
def snooze_cmd(
    resource_id: str = typer.Argument(..., help="docker:<short_id> or proc:<pid>"),
    minutes: int = typer.Argument(60),
) -> None:
    """Snooze a resource so idle-janitor ignores it for N minutes."""
    until = snooze.snooze(resource_id, minutes)
    console.print(
        f"[green]Snoozed[/green] {resource_id} for {minutes}m "
        f"(expires at unix {int(until)})"
    )


@app.command()
def aws(
    include_stopped: bool = typer.Option(False, "--include-stopped"),
    fixture: str = typer.Option("", "--fixture", help="Path to a YAML fixture (default: packaged example)."),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List EC2-like instances from the AWS adapter (fixture-driven in v1)."""
    from pathlib import Path as _Path
    path = _Path(fixture) if fixture else None
    result = aws_scan.list_instances(include_stopped=include_stopped, fixture_path=path)
    if json_out:
        print(json.dumps(result, indent=2))
        return
    console.rule("[bold green]idle-janitor \u2022 aws")
    console.print(f"[dim]source: {result['source']}  fixture: {result['fixture_path']}[/dim]\n")
    if not result["instances"]:
        console.print("[dim]No running instances in the fixture.[/dim]")
        return
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Instance")
    table.add_column("Type", width=12)
    table.add_column("Region", width=12)
    table.add_column("Uptime", width=10)
    table.add_column("$ / hr", justify="right")
    table.add_column("$ so far", justify="right")
    table.add_column("\u20b9 so far", justify="right")
    table.add_column("g CO\u2082", justify="right")
    for i in result["instances"]:
        table.add_row(
            f"{i['name']}\n[dim]{i['instance_id']}[/dim]",
            i["instance_type"],
            i["region"],
            i["uptime_human"],
            f"{i['usd_per_hour']:.4f}",
            f"{i['usd']:.2f}",
            f"{i['inr']:.2f}",
            f"{i['co2_g']:.1f}",
        )
    console.print(table)
    t = result["totals"]
    console.print(
        f"\n[bold]Totals:[/bold] ${t['usd']:.2f}  "
        f"\u20b9{t['inr']:.2f}  "
        f"{t['wh']:.0f} Wh  "
        f"{t['co2_g']:.1f} g CO\u2082"
    )
    console.print(f"\n[yellow]{result['note']}[/yellow]")


@app.command()
def firebase(
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """List Firebase local emulators via the hub at 127.0.0.1:4400."""
    result = firebase_scan.list_emulators()
    if json_out:
        print(json.dumps(result, indent=2))
        return
    console.rule("[bold green]idle-janitor \u2022 firebase")
    if not result["ok"]:
        console.print(f"[yellow]{result['error']}[/yellow]")
        return
    if not result["emulators"]:
        console.print("[dim]Hub reachable but no emulators running.[/dim]")
        return
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Emulator")
    table.add_column("Port", justify="right")
    table.add_column("PID", justify="right")
    table.add_column("Watts (est)", justify="right")
    table.add_column("Wh / h", justify="right")
    table.add_column("\u20b9 / h", justify="right")
    table.add_column("g CO\u2082 / h", justify="right")
    for e in result["emulators"]:
        table.add_row(
            e["name"],
            str(e.get("port") or "?"),
            str(e.get("pid") or "?"),
            f"{e['estimated_watts']:.1f}",
            f"{e['wh']:.2f}",
            f"{e['inr']:.2f}",
            f"{e['co2_g']:.2f}",
        )
    console.print(table)
    console.print(f"\n[dim]{result.get('note', '')}[/dim]")


@app.command()
def agent(
    interval: int = typer.Option(300, "--interval", help="Seconds between ticks."),
    autonomous: bool = typer.Option(
        False, "--autonomous/--advisory",
        help="Actually reap per policy. Default: advisory only (safe).",
    ),
    notify: bool = typer.Option(
        False, "--notify",
        help="Fire a macOS notification when cumulative waste crosses --threshold-inr.",
    ),
    threshold_inr: float = typer.Option(1.0, "--threshold-inr"),
    min_idle_minutes: int = typer.Option(0, "--min-idle-minutes"),
    force: bool = typer.Option(False, "--force", help="SIGKILL instead of SIGTERM for processes."),
    max_ticks: int = typer.Option(
        0, "--max-ticks",
        help="Stop after N ticks (0 = run forever). Useful for demos / tests.",
    ),
    max_reaps: int = typer.Option(
        0, "--max-reaps",
        help="Hard cap on total reaps across the whole run (0 = unlimited).",
    ),
) -> None:
    """Autonomous watcher loop. Safe-by-default (advisory). Press Ctrl+C to exit."""
    cfg = watcher_mod.WatcherConfig(
        interval_seconds=max(1, interval),
        autonomous=autonomous,
        notify=notify,
        threshold_inr=threshold_inr,
        min_idle_minutes=min_idle_minutes,
        force=force,
        max_ticks=max_ticks if max_ticks > 0 else None,
        max_reaps=max_reaps if max_reaps > 0 else None,
    )
    watcher_mod.run(cfg)


@app.command()
def serve() -> None:
    """Start the MCP server on stdio (for Cursor / Claude Desktop)."""
    from server import mcp  # type: ignore
    mcp.run()


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
