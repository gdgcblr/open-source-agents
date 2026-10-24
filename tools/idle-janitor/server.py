"""idle-janitor MCP server.

Exposes six tools to any MCP-compatible AI client (Cursor, Claude Desktop, ...):

    * list_idle_resources(min_idle_minutes=0)
    * estimate_waste(min_idle_minutes=0)
    * history_waste(window="7d")
    * snooze_resource(resource_id, minutes)
    * terminate_resource(resource_id, dry_run=True, force=False)
    * apply_policies(dry_run=True)

Resource IDs are prefixed strings:
    * "docker:<short_id>"  for Docker containers
    * "proc:<pid>"         for local dev-server processes

The server is intentionally offline-only and never phones home.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.mcpserver import MCPServer

from janitor import (
    aws_scan,
    cost,
    docker_scan,
    firebase_scan,
    history,
    policies as policies_mod,
    process_scan,
    safety,
    scan,
    snooze as snooze_store,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("idle-janitor")

mcp = MCPServer(
    name="idle-janitor",
    description="Audit, cost-estimate, and shut down idle local dev resources.",
    version="0.1.0",
)


@mcp.tool()
def list_idle_resources(min_idle_minutes: int = 0) -> dict[str, Any]:
    """List idle Docker containers and local dev-server processes.

    Args:
        min_idle_minutes: Only include resources that have been running at
            least this long. 0 = include everything idle right now.
    """
    snap = scan.scan_and_journal(min_idle_minutes=min_idle_minutes)
    return {
        "resources": snap["resources"],
        "docker_available": snap["docker_available"],
        "docker_error": snap["docker_error"],
        "snoozed": snap["snoozed"],
        "count": len(snap["resources"]),
    }


@mcp.tool()
def estimate_waste(min_idle_minutes: int = 0) -> dict[str, Any]:
    """Summarize how much battery / money / CO2 the idle resources are burning right now.

    Returns a dict with a headline string plus total_wh, total_inr, total_co2_g,
    and a human-friendly analogy ("~2 phone charges", etc.).
    """
    snap = scan.scan_and_journal(min_idle_minutes=min_idle_minutes)
    summary = cost.summarize(snap["resources"])
    summary["resources"] = [
        {
            "id": r["id"],
            "name": r.get("name"),
            "kind": r["kind"],
            "uptime_human": r["uptime_human"],
            "wh": r["wh"],
            "inr": r["inr"],
            "co2_g": r.get("co2_g"),
        }
        for r in snap["resources"]
    ]
    return summary


@mcp.tool()
def history_waste(window: str = "7d") -> dict[str, Any]:
    """Historical waste over a time window from the local SQLite journal.

    Args:
        window: "7d", "24h", "60m", or raw integer seconds. Default: 7 days.

    Use this to answer questions like "how much have I wasted this week?"
    """
    return history.summarize_window(window)


@mcp.tool()
def snooze_resource(resource_id: str, minutes: int = 60) -> dict[str, Any]:
    """Ignore a resource for N minutes. Useful for `yarn dev` you're actively using.

    Args:
        resource_id: "docker:<short_id>" or "proc:<pid>".
        minutes: How long to snooze. Default: 60.
    """
    until = snooze_store.snooze(resource_id, minutes)
    return {
        "ok": True,
        "resource_id": resource_id,
        "snoozed_for_minutes": minutes,
        "expires_at_unix": until,
    }


@mcp.tool()
def safety_check(resource_id: str) -> dict[str, Any]:
    """Preview whether terminate_resource would be allowed, without side effects.

    Agents should call this before terminate_resource when a human asks to kill
    something, so the agent can explain to the user WHY an action was refused
    (e.g., "that container matches your protect clause for postgres").
    """
    verdict = safety.check_reap(resource_id)
    return verdict.to_dict()


@mcp.tool()
def terminate_resource(
    resource_id: str, dry_run: bool = True, force: bool = False
) -> dict[str, Any]:
    """Stop a Docker container or kill a local dev-server process.

    SAFETY: dry_run defaults to True. The AI agent should always run a dry_run
    first, show the user what WOULD be stopped, and only call with
    dry_run=False after the human confirms.

    Args:
        resource_id: "docker:<short_id>" or "proc:<pid>".
        dry_run: If True (default), returns the plan without acting.
        force: Only for processes. SIGKILL instead of SIGTERM.

    Guardrails enforced (even on dry_run=False):
      1. hard blocklist (process name/path)
      2. dev-server pattern allowlist (processes)
      3. policy protect clauses from ~/.idle-janitor/policies.yaml
      4. active snoozes
      5. rate limit (default: 10 reaps / 60s)
    """
    verdict = safety.check_reap(resource_id)
    if not verdict.allowed:
        history.record_reap(
            {"id": resource_id, "kind": resource_id.split(":", 1)[0]},
            dry_run=dry_run,
            reason=f"REFUSED: {'; '.join(verdict.reasons)}",
        )
        return {
            "ok": False,
            "error": "Refused by safety guard: " + "; ".join(verdict.reasons),
            "verdict": verdict.to_dict(),
        }

    kind, _, raw_id = resource_id.partition(":")
    if not dry_run:
        safety.record_action()

    if kind == "docker":
        result = docker_scan.terminate(raw_id, dry_run=dry_run)
    elif kind == "proc":
        try:
            pid = int(raw_id)
        except ValueError:
            return {"ok": False, "error": f"Invalid pid: {raw_id}"}
        result = process_scan.terminate(pid, dry_run=dry_run, force=force)
    else:
        return {"ok": False, "error": f"Unknown resource kind: {kind}"}

    # Redact any secrets before journaling.
    payload = result.get("terminated") or result.get("would_terminate") or {}
    if payload.get("cmdline"):
        payload = {**payload, "cmdline": safety.redact(payload["cmdline"])}
    history.record_reap(
        {**payload, "kind": kind, "id": resource_id},
        dry_run=dry_run,
        reason="agent-call" if result.get("ok") else "FAILED: " + str(result.get("error")),
    )
    return result


@mcp.tool()
def list_aws_resources(include_stopped: bool = False) -> dict[str, Any]:
    """List EC2-like instances from the AWS adapter (fixture-driven in v1).

    v1 is intentionally fixture-driven: numbers come from aws_fixture.example.yaml
    (or AWS_FIXTURE_PATH env var), NOT a live boto3 call. This keeps the demo
    offline, deterministic, and credential-free. Replace _load_fixture() with
    ec2.describe_instances() to go live without changing any other code.

    Each instance has: id, instance_type, region, uptime_human, usd_per_hour,
    wh, usd, inr, co2_g. The response includes "totals" across all instances.
    """
    return aws_scan.list_instances(include_stopped=include_stopped)


@mcp.tool()
def list_firebase_emulators() -> dict[str, Any]:
    """List every running Firebase local emulator (via the hub at 127.0.0.1:4400).

    Returns an "ok": false response with a hint if the Firebase CLI isn't
    installed or the emulator suite isn't running. All traffic is strictly
    loopback \u2014 nothing is sent to Google.
    """
    return firebase_scan.list_emulators()


@mcp.tool()
def apply_policies(dry_run: bool = True, min_idle_minutes: int = 0) -> dict[str, Any]:
    """Evaluate ~/.idle-janitor/policies.yaml against the current snapshot.

    Returns the full list of policy decisions (reap / warn / protect) PLUS, if
    dry_run=False, the result of executing every 'reap' decision.

    Args:
        dry_run: If True (default), only returns decisions without acting.
        min_idle_minutes: Only evaluate resources older than this.

    The AI agent should always call with dry_run=True first, show the human
    the plan, and only re-call with dry_run=False after confirmation.
    """
    snap = scan.scan_and_journal(min_idle_minutes=min_idle_minutes)
    decisions = policies_mod.evaluate(snap["resources"])
    decisions_dicts = policies_mod.decisions_to_dicts(decisions)

    executed: list[dict[str, Any]] = []
    if not dry_run:
        by_id = {r["id"]: r for r in snap["resources"]}
        for d in decisions:
            if d.action != "reap":
                continue
            resource = by_id.get(d.resource_id)
            if not resource:
                continue
            # Second line of defense: run every candidate through the central
            # safety guard, even though the policy engine already said "reap".
            verdict = safety.check_reap(d.resource_id, resource=resource)
            if not verdict.allowed:
                history.record_reap(
                    resource, dry_run=False,
                    reason=f"REFUSED by guard despite rule={d.rule}: {'; '.join(verdict.reasons)}",
                )
                executed.append({
                    "resource_id": d.resource_id, "rule": d.rule,
                    "result": {"ok": False, "error": "Refused by safety guard",
                               "verdict": verdict.to_dict()},
                })
                continue
            safety.record_action()
            kind, _, raw_id = d.resource_id.partition(":")
            if kind == "docker":
                res = docker_scan.terminate(raw_id, dry_run=False)
            elif kind == "proc":
                try:
                    pid = int(raw_id)
                    res = process_scan.terminate(pid, dry_run=False)
                except ValueError:
                    res = {"ok": False, "error": f"Invalid pid: {raw_id}"}
            else:
                res = {"ok": False, "error": f"Unknown kind: {kind}"}
            history.record_reap(resource, dry_run=False, reason=d.rule)
            executed.append({"resource_id": d.resource_id, "rule": d.rule, "result": res})

    return {
        "dry_run": dry_run,
        "decision_count": len(decisions_dicts),
        "decisions": decisions_dicts,
        "executed": executed,
    }


if __name__ == "__main__":
    log.info("idle-janitor MCP server starting on stdio")
    mcp.run()
