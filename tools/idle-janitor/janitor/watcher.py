"""Autonomous watcher loop \u2014 the "janitor" verb of idle-janitor.

Runs forever. Every tick:
    1. scan + journal (so history fills up automatically)
    2. evaluate policies
    3. for each decision:
         * reap   \u2192 either execute (--autonomous) or just warn + journal plan
         * warn   \u2192 log + optional macOS notification
         * protect\u2192 ignore
    4. if cumulative waste crosses --threshold-inr since start, notify once

Designed to be safe-by-default: a watcher launched with no flags only logs; it
never kills anything until you pass --autonomous.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from rich.console import Console

from . import cost, docker_scan, history, policies as policies_mod, process_scan, safety, scan


console = Console()


@dataclass
class WatcherConfig:
    interval_seconds: int = 300
    autonomous: bool = False
    notify: bool = False
    threshold_inr: float = 1.0
    min_idle_minutes: int = 0
    force: bool = False
    max_ticks: int | None = None   # tests/demos set this; None = forever
    max_reaps: int | None = None   # hard cap on total reaps across the run


def _notify_macos(title: str, message: str) -> None:
    """Fire a native macOS notification via osascript. Silently no-op elsewhere."""
    if platform.system() != "Darwin":
        return
    if not shutil.which("osascript"):
        return
    escaped_msg = message.replace('"', '\\"')
    escaped_title = title.replace('"', '\\"')
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{escaped_msg}" with title "{escaped_title}"',
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _execute_reap(resource: dict[str, Any], force: bool) -> dict[str, Any]:
    kind = resource.get("kind")
    rid = resource.get("id", "")
    raw = rid.split(":", 1)[1] if ":" in rid else ""
    if kind == "docker":
        return docker_scan.terminate(raw, dry_run=False)
    if kind == "process":
        try:
            return process_scan.terminate(int(raw), dry_run=False, force=force)
        except ValueError:
            return {"ok": False, "error": f"Invalid pid: {raw}"}
    return {"ok": False, "error": f"Unknown kind: {kind}"}


def run(cfg: WatcherConfig) -> dict[str, Any]:
    """Blocking watcher loop. Returns a summary dict when it exits."""
    mode = "AUTONOMOUS" if cfg.autonomous else "ADVISORY"
    console.rule(f"[bold green]idle-janitor \u2022 agent ({mode})")
    console.print(
        f"[dim]interval={cfg.interval_seconds}s  notify={cfg.notify}  "
        f"threshold=\u20b9{cfg.threshold_inr}  min_idle_minutes={cfg.min_idle_minutes}[/dim]\n"
    )

    totals = {"reaped": 0, "warned": 0, "protected": 0, "ticks": 0, "notified": False}
    tick = 0
    try:
        while True:
            tick += 1
            totals["ticks"] = tick
            snap = scan.scan_and_journal(min_idle_minutes=cfg.min_idle_minutes)
            summary = cost.summarize(snap["resources"])
            decisions = policies_mod.evaluate(snap["resources"])

            tick_line = (
                f"[dim]tick {tick}[/dim]  "
                f"[bold]\u20b9{summary['total_inr']:.2f}[/bold] "
                f"({summary['total_wh']:.1f} Wh, {summary['total_co2_g']:.1f} g CO\u2082) "
                f"across {summary['resource_count']} idle resource(s)"
            )
            console.print(tick_line)

            # Notify once per watcher run if waste crosses threshold.
            if (
                cfg.notify
                and not totals["notified"]
                and summary["total_inr"] >= cfg.threshold_inr
            ):
                _notify_macos(
                    "idle-janitor \u2022 cleanup due",
                    summary["headline"],
                )
                totals["notified"] = True

            by_id = {r["id"]: r for r in snap["resources"]}
            for d in decisions:
                resource = by_id.get(d.resource_id, {})
                tag = f"[{d.action}] {d.name or d.resource_id} \u2014 {d.reason} (rule={d.rule})"
                if d.action == "protect":
                    totals["protected"] += 1
                    console.print(f"  [cyan]PROTECT[/cyan] {d.name or d.resource_id}")
                elif d.action == "warn":
                    totals["warned"] += 1
                    console.print(f"  [yellow]WARN[/yellow] {d.name} \u2014 {d.reason}")
                elif d.action == "reap":
                    if cfg.autonomous:
                        if cfg.max_reaps is not None and totals["reaped"] >= cfg.max_reaps:
                            console.print(
                                f"  [yellow]SKIP[/yellow] {d.name} \u2014 --max-reaps "
                                f"({cfg.max_reaps}) reached"
                            )
                            continue
                        verdict = safety.check_reap(d.resource_id, resource=resource)
                        if not verdict.allowed:
                            history.record_reap(
                                resource, dry_run=False,
                                reason=f"REFUSED by guard despite rule={d.rule}: "
                                       f"{'; '.join(verdict.reasons)}",
                            )
                            console.print(
                                f"  [yellow]REFUSED[/yellow] {d.name} \u2014 "
                                f"{'; '.join(verdict.reasons)}"
                            )
                            continue
                        safety.record_action()
                        res = _execute_reap(resource, force=cfg.force)
                        history.record_reap(resource, dry_run=False, reason=d.rule)
                        ok = res.get("ok")
                        mark = "[green]OK[/green]" if ok else f"[red]FAIL[/red] {res.get('error')}"
                        console.print(f"  [red]REAP[/red] {d.name} {mark}")
                        if ok:
                            totals["reaped"] += 1
                    else:
                        history.record_reap(resource, dry_run=True, reason=d.rule)
                        console.print(
                            f"  [red]WOULD REAP[/red] {d.name} "
                            f"[dim](advisory; run with --autonomous to act)[/dim]"
                        )

            if cfg.max_ticks is not None and tick >= cfg.max_ticks:
                break
            time.sleep(cfg.interval_seconds)
    except KeyboardInterrupt:
        console.print("\n[dim]idle-janitor agent \u2014 stopped.[/dim]")

    console.rule("[bold green]watcher summary")
    console.print(
        f"ticks={totals['ticks']}  reaped={totals['reaped']}  "
        f"warned={totals['warned']}  protected={totals['protected']}"
    )
    return totals
