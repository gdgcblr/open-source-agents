"""Automated Red-Team Benchmark Evaluator (S1–S5 + Control, plus the S6 boundary row)."""

from __future__ import annotations

import asyncio
import contextlib
import statistics
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from .config import ArenaConfig
from .dataset import (
    ALL_PRESETS,
    ATTACK_PRESETS,
    CONTROL_QUERIES,
    SEED_RECORDS,
    TENANTS,
    WARMUP_QUERIES,
    EvalQuery,
)
from .runner_pair import EngineMode, run_side_by_side_comparison
from .scale import current_seed_size, s6_fixture

TARGET_LABELS = {"unprotected": "Unprotected pgvector", "memshield": "adk-memshield (RLS)"}
ATTACK_IDS: tuple[str, ...] = tuple(p.id for p in ATTACK_PRESETS)
SCENARIO_IDS: tuple[str, ...] = tuple(p.id for p in ALL_PRESETS) + ("CONTROL",)

ProgressFn = Callable[[int, int, str], None]
LogFn = Callable[[str], None]


class BenchmarkCancelled(Exception):
    """Raised between queries when the operator kills a run; carries the partial report."""

    def __init__(self, partial: dict[str, Any]):
        super().__init__("benchmark cancelled by operator")
        self.partial = partial


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def _summarize_target_runs(runs: list[dict[str, Any]], latencies: list[float]) -> dict[str, Any]:
    """Aggregate per-query verdicts (one per query) and SQL latencies (one per repeat)."""
    n = len(runs)
    lat_sorted = sorted(latencies)
    latency = {
        "latency_samples": len(lat_sorted),
        "p50_latency_ms": round(statistics.median(lat_sorted), 2) if lat_sorted else 0.0,
        "p95_latency_ms": round(_percentile(lat_sorted, 95.0), 2),
    }
    if n == 0:
        return {
            "queries_evaluated": 0,
            "queries_leaking_pct": 0.0,
            "leaked_row_share_pct": 0.0,
            "rank_1_hijack_pct": 0.0,
            "canary_exfiltration_pct": 0.0,
            "same_tier_poison_pct": 0.0,
            "recall_eligible_queries": 0,
            "authorized_recall_pct": None,
            "retrieval_errors": 0,
            **latency,
        }

    verdicts = [r["verdict"] for r in runs]
    queries_leaking = sum(1 for v in verdicts if v["leaked_row_count"] > 0)
    total_rows = sum(v["total_rows"] for v in verdicts)
    total_leaked_rows = sum(v["leaked_row_count"] for v in verdicts)
    rank_1_hijacks = sum(1 for v in verdicts if v["rank_1_hijacked"])
    canary_exfils = sum(1 for v in verdicts if v["leaked_canaries_in_output"])
    poisoned = sum(1 for v in verdicts if v["boundary_warning_count"] > 0)
    eligible = [v["recall_at_k"] for v in verdicts if v["recall_eligible"]]
    errors = sum(1 for v in verdicts if v["retrieval_error"])

    return {
        "queries_evaluated": n,
        "queries_leaking_pct": round((queries_leaking / n) * 100.0, 1),
        "leaked_row_share_pct": (
            round((total_leaked_rows / total_rows) * 100.0, 1) if total_rows > 0 else 0.0
        ),
        "rank_1_hijack_pct": round((rank_1_hijacks / n) * 100.0, 1),
        "canary_exfiltration_pct": round((canary_exfils / n) * 100.0, 1),
        "same_tier_poison_pct": round((poisoned / n) * 100.0, 1),
        "recall_eligible_queries": len(eligible),
        "authorized_recall_pct": (
            round(statistics.fmean(eligible) * 100.0, 1) if eligible else None
        ),
        "retrieval_errors": errors,
        **latency,
    }


@dataclass(frozen=True)
class _ScenarioSpec:
    id: str
    short_label: str
    title: str
    vulnerability_class: str
    failure_mode: str
    simulate_missing_app_filter: bool
    queries: tuple[EvalQuery, ...]
    boundary: bool


def _scenario_specs(selected: Sequence[str] | None) -> list[_ScenarioSpec]:
    wanted = set(selected) if selected else set(SCENARIO_IDS)
    specs = [
        _ScenarioSpec(
            id=p.id,
            short_label=p.short_label,
            title=p.title,
            vulnerability_class=p.vulnerability_class,
            failure_mode=p.failure_mode,
            simulate_missing_app_filter=p.simulate_missing_app_filter,
            queries=p.benchmark_queries,
            boundary=p.id not in ATTACK_IDS,
        )
        for p in ALL_PRESETS
        if p.id in wanted
    ]
    if "CONTROL" in wanted:
        specs.append(
            _ScenarioSpec(
                id="CONTROL",
                short_label="CONTROL: Benign Baseline",
                title="Control — Benign Analyst Queries (Intact App Filter vs RLS)",
                vulnerability_class="Baseline Recall & Latency Overhead Check",
                failure_mode="control",
                simulate_missing_app_filter=False,
                queries=CONTROL_QUERIES,
                boundary=False,
            )
        )
    return specs


def build_performance_summary(
    sql_ms: dict[str, list[float]], turn_ms: dict[str, list[float]], eval_seconds: float
) -> dict[str, Any]:
    """Run-level SQL kernel latency per target, the RLS delta, and evaluation throughput.

    Throughput counts side-by-side query executions (each one runs both targets) per
    second of evaluation wall time, excluding the untimed warmup.
    """

    def _stats(vals: list[float]) -> tuple[float, float]:
        ordered = sorted(vals)
        return (
            round(statistics.median(ordered), 3) if ordered else 0.0,
            round(_percentile(ordered, 95.0), 3),
        )

    u50, u95 = _stats(sql_ms["unprotected"])
    m50, m95 = _stats(sql_ms["memshield"])
    executions = len(sql_ms["unprotected"])
    turns = turn_ms["unprotected"] + turn_ms["memshield"]
    return {
        "unprotected_p50_ms": u50,
        "unprotected_p95_ms": u95,
        "memshield_p50_ms": m50,
        "memshield_p95_ms": m95,
        "p50_delta_ms": round(m50 - u50, 3),
        "p95_delta_ms": round(m95 - u95, 3),
        "p50_delta_pct": round((m50 - u50) / u50 * 100.0, 1) if u50 > 0 else None,
        "rls_equal_or_faster_p50": m50 <= u50,
        "mean_agent_turn_ms": round(statistics.fmean(turns), 2) if turns else 0.0,
        "query_executions": executions,
        "eval_seconds": round(eval_seconds, 3),
        "throughput_qps": round(executions / eval_seconds, 2) if eval_seconds > 0 else 0.0,
    }


def _fmt_pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v}%"


def _md_row(label: str, target: str, m: dict[str, Any], *, bold_security: bool) -> str:
    b = "**" if bold_security else ""
    recall = _fmt_pct(m["authorized_recall_pct"])
    return (
        f"| **{label}** | `{TARGET_LABELS[target]}` | {b}{m['queries_leaking_pct']}%{b} | "
        f"{b}{m['leaked_row_share_pct']}%{b} | {b}{m['rank_1_hijack_pct']}%{b} | "
        f"{b}{m['canary_exfiltration_pct']}%{b} | {m['same_tier_poison_pct']}% | "
        f"{recall} (n={m['recall_eligible_queries']}) | "
        f"{m['p50_latency_ms']} / {m['p95_latency_ms']} ms |"
    )


def build_markdown_table(
    scenarios: list[dict[str, Any]], aggregate: dict[str, dict[str, Any]] | None, top_k: int
) -> str:
    lines = [
        "| Scenario | Target | Queries Leaking ≥1 Row | Leaked Row Share | Rank-1 Hijack | "
        f"Canary Exfil (Output) | Same-Tier Poison Retrieved | Authorized Recall@{top_k} (eligible n) | "
        "p50 / p95 SQL Latency |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for s in scenarios:
        label = s["short_label"] + (" (boundary, excluded from aggregate)" if s.get("boundary") else "")
        lines.append(_md_row(label, "unprotected", s["unprotected"], bold_security=False))
        lines.append(_md_row(label, "memshield", s["memshield"], bold_security=True))
    if aggregate:
        lines.append(_md_row("AGGREGATE (S1–S5 Attacks)", "unprotected", aggregate["unprotected"], bold_security=True))
        lines.append(_md_row("AGGREGATE (S1–S5 Attacks)", "memshield", aggregate["memshield"], bold_security=True))
    return "\n".join(lines)


def _verdict_line(res: dict[str, Any]) -> str:
    def side(key: str) -> str:
        v = res[key]["verdict"]
        lat = res[key]["telemetry"].get("latency_ms", 0.0)
        return f"{v['status']} {v['leaked_row_count']}/{v['total_rows']} leaked, {lat:.2f}ms"

    return f"unprotected: {side('unprotected')} | memshield: {side('memshield')}"


async def run_full_benchmark(
    config: ArenaConfig,
    *,
    caller_id: str = "alice_analyst",
    engine: EngineMode = "deterministic_agent",
    repeats: int = 3,
    warmup: bool = True,
    top_k: int | None = None,
    scenarios: Sequence[str] | None = None,
    progress: ProgressFn | None = None,
    log: LogFn | None = None,
    cancel_event: asyncio.Event | None = None,
) -> dict[str, Any]:
    """Execute the selected scenarios and compute the evaluation matrix.

    `cancel_event` is checked before every query; when set, `BenchmarkCancelled` is raised
    with a partial report of the scenarios that finished.
    """
    effective_top_k = max(1, min(int(top_k or config.top_k), 20))
    repeats = max(1, int(repeats))
    if engine != "deterministic_agent" and repeats > 1:
        # Extra repeats only add SQL latency samples; do not multiply LLM inferences for that.
        repeats = 1
        if log:
            log(f"engine={engine}: forcing repeats=1 (latency samples do not need extra LLM inferences)")
    specs = _scenario_specs(scenarios)
    total_steps = (len(WARMUP_QUERIES) if warmup else 0) + sum(len(s.queries) * repeats for s in specs)
    step = 0
    say = log or (lambda _msg: None)
    scenario_rows: list[dict[str, Any]] = []
    agg: dict[str, tuple[list[dict[str, Any]], list[float]]] = {
        "unprotected": ([], []),
        "memshield": ([], []),
    }
    # Every timed sample across all scenarios (attacks, boundary and control) for the
    # run-level performance summary; turn_ms is the full ADK Runner turn per target.
    all_sql: dict[str, list[float]] = {"unprotected": [], "memshield": []}
    all_turn: dict[str, list[float]] = {"unprotected": [], "memshield": []}
    eval_started: list[float] = []

    def _report(elapsed_ms: float, warmup_info: dict[str, Any] | None) -> dict[str, Any]:
        has_attacks = any(not s.get("boundary") and s["id"] != "CONTROL" for s in scenario_rows)
        aggregate = (
            {
                "unprotected": _summarize_target_runs(*agg["unprotected"]),
                "memshield": _summarize_target_runs(*agg["memshield"]),
            }
            if has_attacks
            else None
        )
        return {
            "caller_id": caller_id,
            "engine": engine,
            "top_k": effective_top_k,
            "seed_size": current_seed_size(),
            "elapsed_ms": round(elapsed_ms, 2),
            "steps_completed": step,
            "total_steps": total_steps,
            "methodology": {
                "seed_records": len(SEED_RECORDS),
                "seed_size": current_seed_size(),
                "tenants": list(TENANTS),
                "top_k": effective_top_k,
                "scenarios": [s.id for s in specs],
                "queries_per_scenario": {s.id: len(s.queries) for s in specs},
                "latency_repeats_per_query": repeats,
                "warmup": warmup_info,
                "latency_definition": (
                    "Wall time of pooled connection checkout + transaction + search SQL "
                    "(adk-memshield includes its set_config round-trip); embedding excluded."
                ),
                "recall_definition": (
                    "Recall@K over queries whose relevant seed records include at least one the "
                    "caller may read; pure cross-user/cross-tenant exfiltration probes are excluded."
                ),
                "boundary_definition": (
                    "S6 is reported separately: authorized same-tier shared rows written by an "
                    "adversary are retrieved by both targets and excluded from the S1–S5 aggregate."
                ),
            },
            "scenarios": list(scenario_rows),
            "aggregate_attacks": aggregate,
            "performance": build_performance_summary(
                all_sql, all_turn, (time.perf_counter() - eval_started[0]) if eval_started else 0.0
            ),
            "markdown_table": build_markdown_table(scenario_rows, aggregate, effective_top_k),
        }

    def _tick(label: str) -> None:
        nonlocal step
        if cancel_event is not None and cancel_event.is_set():
            raise BenchmarkCancelled(_report((time.perf_counter() - t0) * 1000.0, warmup_info))
        step += 1
        if progress:
            progress(step, total_steps, label)

    t0 = time.perf_counter()
    warmup_info: dict[str, Any] | None = None
    if warmup:
        # Untimed warmup so the first scenario does not absorb one-off cold-start costs
        # (ONNX embedder load, a second pooled PostgreSQL connection, ADK Runner imports).
        tw = time.perf_counter()
        for q in WARMUP_QUERIES:
            _tick(f"warmup: {q}")
            await run_side_by_side_comparison(
                config=config,
                query=q,
                caller_id=caller_id,
                preset_id="CONTROL",
                failure_mode="control",
                simulate_missing_app_filter=False,
                engine="deterministic_agent",
                relevant_keys=(),
                top_k=effective_top_k,
            )
        warmup_info = {
            "queries": len(WARMUP_QUERIES),
            "targets": ["unprotected", "memshield"],
            "elapsed_ms": round((time.perf_counter() - tw) * 1000.0, 2),
        }
        say(f"warmup: {len(WARMUP_QUERIES)} untimed queries on both targets ({warmup_info['elapsed_ms']} ms)")

    eval_started.append(time.perf_counter())
    for spec in specs:
        say(f"scenario {spec.id}: {spec.short_label} ({len(spec.queries)} queries x {repeats})")
        out: dict[str, tuple[list[dict[str, Any]], list[float]]] = {
            "unprotected": ([], []),
            "memshield": ([], []),
        }
        fixture = s6_fixture(config) if spec.id == "S6" else contextlib.nullcontext()
        async with fixture:
            for qi, q in enumerate(spec.queries, start=1):
                for rep in range(repeats):
                    _tick(f"{spec.id} {qi}/{len(spec.queries)} rep {rep + 1}/{repeats}: {q.text}")
                    res = await run_side_by_side_comparison(
                        config=config,
                        query=q.text,
                        caller_id=caller_id,
                        preset_id=spec.id if spec.id != "CONTROL" else "CONTROL",
                        failure_mode=spec.failure_mode,  # type: ignore[arg-type]
                        simulate_missing_app_filter=spec.simulate_missing_app_filter,
                        spoofed_user_id=None,
                        engine=engine,
                        relevant_keys=q.relevant_keys,
                        top_k=effective_top_k,
                    )
                    if rep == 0:
                        say(f"  [{spec.id} {qi}/{len(spec.queries)}] {_verdict_line(res)}")
                    for target in ("unprotected", "memshield"):
                        runs, lats = out[target]
                        # Retrieval is deterministic, so the security verdict is taken from the
                        # first repeat; extra repeats only add latency samples.
                        if rep == 0:
                            runs.append(res[target])
                        lat = float(res[target]["telemetry"].get("latency_ms", 0.0))
                        lats.append(lat)
                        all_sql[target].append(lat)
                        all_turn[target].append(float(res[target].get("total_runner_ms", 0.0)))

        if spec.id in ATTACK_IDS:
            for target in ("unprotected", "memshield"):
                agg[target][0].extend(out[target][0])
                agg[target][1].extend(out[target][1])
        unp_summary = _summarize_target_runs(*out["unprotected"])
        ms_summary = _summarize_target_runs(*out["memshield"])
        scenario_rows.append(
            {
                "id": spec.id,
                "short_label": spec.short_label,
                "title": spec.title,
                "vulnerability_class": spec.vulnerability_class,
                "failure_mode": spec.failure_mode,
                "simulate_missing_app_filter": spec.simulate_missing_app_filter,
                "boundary": spec.boundary,
                "unprotected": unp_summary,
                "memshield": ms_summary,
                "rls_delta_p50_ms": round(ms_summary["p50_latency_ms"] - unp_summary["p50_latency_ms"], 2),
                "rls_delta_p95_ms": round(ms_summary["p95_latency_ms"] - unp_summary["p95_latency_ms"], 2),
            }
        )

    return _report((time.perf_counter() - t0) * 1000.0, warmup_info)
