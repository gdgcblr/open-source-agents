from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from claimcheck.tools import Audit


def build_report(audit: Audit, *, agent: dict[str, Any] | None = None) -> dict[str, Any]:
    results = audit.ledger.complete()
    counts: Counter[str] = Counter(result.status for result in results)
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "project": str(audit.root),
        "summary": {
            status: counts[status] for status in ("passed", "failed", "not_verified", "error")
        },
        "coverage": {
            "discovered": len(results),
            "executed": len(audit.ledger.results),
            "scope": "Supported command/link, image configuration, and API example claims only.",
        },
        "agent": agent,
        "claims": [
            {**audit.ledger.get(result.claim_id).public(), **asdict(result)} for result in results
        ],
    }


def markdown(report: dict[str, Any]) -> str:
    def cell(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")

    lines = [
        "# ClaimCheck evidence report",
        "",
        "Scope is bounded; passing supported checks is not proof that all project prose is true.",
        "",
        " | ".join(f"{key}: {value}" for key, value in report["summary"].items()),
        "",
        "| Status | Source | Claim | Observation |",
        "|---|---|---|---|",
    ]
    for claim in report["claims"]:
        lines.append(
            f"| {cell(claim['status'])} | {cell(claim['source'])}:{claim['line']} "
            f"| {cell(claim['statement'])} | {cell(claim['observed'])} |"
        )
    if report.get("agent"):
        lines.extend(
            [
                "",
                "## Agent commentary (advisory, not evidence)",
                "",
                report["agent"].get("text", ""),
            ]
        )
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (directory / "report.md").write_text(markdown(report))


def exit_code(report: dict[str, Any]) -> int:
    if report["summary"]["error"]:
        return 2
    if report["summary"]["failed"]:
        return 1
    if report["summary"]["not_verified"]:
        return 3
    return 0
