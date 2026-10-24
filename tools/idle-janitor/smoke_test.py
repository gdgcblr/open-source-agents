"""Local smoke test — exercises the janitor without needing an MCP client.

Usage:
    python smoke_test.py           # list + estimate
    python smoke_test.py --kill ID # dry-run terminate on a resource id
"""

from __future__ import annotations

import argparse
import json

from janitor import cost, docker_scan, process_scan, snooze


def _dump(label: str, obj) -> None:
    print(f"\n=== {label} ===")
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="idle-janitor smoke test")
    parser.add_argument("--kill", help="Dry-run terminate the given resource id")
    parser.add_argument("--snooze", help="Snooze the given resource id for 10 min")
    parser.add_argument(
        "--min-idle-minutes", type=int, default=0, help="Only show resources older than this"
    )
    args = parser.parse_args()

    docker_result = docker_scan.list_containers()
    _dump("docker containers", docker_result)

    proc_result = process_scan.list_processes()
    _dump("local dev-server processes", proc_result)

    all_resources = []
    all_resources.extend(docker_result.get("containers", []))
    all_resources.extend(proc_result.get("processes", []))

    min_uptime = args.min_idle_minutes * 60
    idle = [
        r
        for r in all_resources
        if r["idle"]
        and r["uptime_seconds"] >= min_uptime
        and not snooze.is_snoozed(r["id"])
    ]
    _dump("idle resources (after snooze + idle filter)", idle)
    _dump("waste summary", cost.summarize(idle))
    _dump("current snoozes", snooze.list_snoozed())

    if args.snooze:
        _dump("snooze result", {"until": snooze.snooze(args.snooze, 10)})
    if args.kill:
        kind, _, raw = args.kill.partition(":")
        if kind == "docker":
            _dump("dry-run terminate", docker_scan.terminate(raw, dry_run=True))
        elif kind == "proc":
            _dump("dry-run terminate", process_scan.terminate(int(raw), dry_run=True))
        else:
            print("resource id must start with docker: or proc:")


if __name__ == "__main__":
    main()
