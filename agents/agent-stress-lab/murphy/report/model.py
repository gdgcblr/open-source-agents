"""ReportData: everything any reporter needs, built from a matrix directory's files."""

from __future__ import annotations

import json
import os
from pathlib import Path

from murphy.config.schema import FailIf
from murphy.core.ci import evaluate
from murphy.core.orchestrator import RunResult
from murphy.core.trace import read_jsonl

SCHEMA_VERSION = 1


def _price() -> float | None:
    value = os.environ.get("PRICE_PER_1K_TOKENS")
    return float(value) if value else None


def _load_cell(cell_dir: Path) -> dict | None:
    path = cell_dir / "result.json"
    if not path.exists():
        return None
    result = RunResult.model_validate(json.loads(path.read_text()))
    return {"cell": cell_dir.name, "result": result.model_dump(), "trace": read_jsonl(cell_dir / "trace.jsonl"),
            "replays": []}


def totals(results: list[RunResult]) -> dict:
    n = len(results)
    passed = [r for r in results if r.passed]
    agent_tokens = sum(r.target_tokens for r in results)
    labels: dict[str, int] = {}
    for r in results:
        for label in r.labels:
            labels[label] = labels.get(label, 0) + 1
    out = {
        "runs": n,
        "passed": len(passed),
        "completion": round(len(passed) / n, 3) if n else 0.0,
        "avg_turns": round(sum(r.turns for r in results) / n, 1) if n else 0.0,
        "labels": labels,
        "policy_violations": sum(r.policy_violations for r in results),
        "policy_blocks": sum(r.policy_blocks for r in results),
        "faults_fired": sum(r.faults_fired for r in results),
        "tokens_total": agent_tokens + sum(r.sim_tokens for r in results),
        "agent_tokens": agent_tokens,
        "agent_tokens_per_success": agent_tokens // len(passed) if passed else None,
        "cost_per_success": None,
        "wall_s": round(sum(r.wall_s for r in results), 1),
    }
    price = _price()
    if price is not None and passed:
        out["cost_per_success"] = round(agent_tokens / 1000 * price / len(passed), 6)
    return out


def build(matrix_dir: Path) -> dict:
    project_file = matrix_dir / "project.json"
    project = json.loads(project_file.read_text()) if project_file.exists() else {"name": matrix_dir.name}
    cells = [c for c in (_load_cell(d) for d in sorted(p for p in matrix_dir.iterdir() if p.is_dir())) if c]
    primary = [c for c in cells if not c["result"]["replay_of"]]
    by_name = {c["cell"]: c for c in primary}
    for c in cells:
        source = c["result"]["replay_of"]
        if source and source in by_name:
            by_name[source]["replays"].append(c)
    results = [RunResult.model_validate(c["result"]) for c in primary]
    first = results[0] if results else None
    run_totals = totals(results)
    fail_if = FailIf.model_validate((project.get("ci") or {}).get("fail_if", {}))
    configured = fail_if.completion_below is not None or bool(fail_if.any_label)
    return {
        "schema_version": SCHEMA_VERSION,
        "matrix": matrix_dir.name,
        "project": project,
        "target": first.target if first else "",
        "policy_mode": first.policy_mode if first else "",
        "seed": first.seed if first else 0,
        "personas": list(dict.fromkeys(r.persona for r in results)),
        "faults": list(dict.fromkeys(r.fault for r in results)),
        "runs": primary,
        "totals": run_totals,
        "ci": {"configured": configured, "tripped": evaluate(run_totals, fail_if) if configured else []},
    }
