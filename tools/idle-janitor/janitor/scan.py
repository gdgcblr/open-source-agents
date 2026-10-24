"""Thin orchestrator — unifies docker + process scans, filters, and journaling.

Factored out so the MCP server, CLI, and TUI all share the same code path.
"""

from __future__ import annotations

from typing import Any

from . import docker_scan, history, process_scan, snooze as snooze_store


def collect_all() -> dict[str, Any]:
    """Scan everything, return the raw lists + Docker availability status."""
    docker_result = docker_scan.list_containers()
    proc_result = process_scan.list_processes()
    all_resources: list[dict[str, Any]] = []
    all_resources.extend(docker_result.get("containers", []))
    all_resources.extend(proc_result.get("processes", []))
    return {
        "resources": all_resources,
        "docker_available": docker_result.get("ok", False),
        "docker_error": docker_result.get("error"),
    }


def filter_idle(
    resources: list[dict[str, Any]],
    min_idle_minutes: int = 0,
    include_snoozed: bool = False,
) -> list[dict[str, Any]]:
    min_uptime = max(0, min_idle_minutes) * 60
    out = []
    for r in resources:
        if not include_snoozed and snooze_store.is_snoozed(r["id"]):
            continue
        if r["uptime_seconds"] < min_uptime:
            continue
        if not r["idle"]:
            continue
        out.append(r)
    return out


def scan_and_journal(min_idle_minutes: int = 0) -> dict[str, Any]:
    """One-call helper: scan, journal, return the filtered idle list + raw."""
    raw = collect_all()
    history.record_snapshot(raw["resources"])  # journal *everything*, not just idle
    idle = filter_idle(raw["resources"], min_idle_minutes=min_idle_minutes)
    return {
        "resources": idle,
        "all_resources": raw["resources"],
        "docker_available": raw["docker_available"],
        "docker_error": raw["docker_error"],
        "snoozed": snooze_store.list_snoozed(),
    }
