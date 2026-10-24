"""Command-line interface for adk-leak-arena (`leak-arena serve` and `leak-arena eval`)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import textwrap
from typing import Any, Sequence, TextIO

import uvicorn

from .config import ArenaConfig
from .evaluator import SCENARIO_IDS, run_full_benchmark
from .runner_pair import ensure_schema_and_seed
from .scale import SEED_SIZE_OPTIONS, TOP_K_OPTIONS, apply_seed_size, delete_synthetic

_ANSI = {
    "red": "\033[91m",
    "green": "\033[92m",
    "amber": "\033[93m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}
_RESET = "\033[0m"

_SHORT_NAMES = {
    "S1": "S1 Semantic Overlap",
    "S2": "S2 Top-K Lure",
    "S3": "S3 Param Spoofing",
    "S4": "S4 Clearance Read-Up",
    "S5": "S5 No-WHERE Chaos",
    "S6": "S6 Same-Tier Boundary",
    "CONTROL": "Control Baseline",
    "AGGREGATE": "S1-S5 Aggregate",
}
_TARGET_NAMES = {"unprotected": "Unprotected pgvector", "memshield": "adk-memshield (RLS)"}


def use_color(stream: TextIO) -> bool:
    """ANSI colors only on a TTY, never when NO_COLOR is set; FORCE_COLOR overrides the TTY check."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return bool(getattr(stream, "isatty", lambda: False)())


class _Painter:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, text: str, *styles: str) -> str:
        if not self.enabled or not styles:
            return text
        return "".join(_ANSI[s] for s in styles) + text + _RESET


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.1f}%"


def _signed(v: float) -> str:
    return f"{v:+.2f}"


def render_box_table(report: dict[str, Any], *, color: bool) -> str:
    """Render the evaluation matrix as a fixed-width Unicode box-drawing table."""
    paint = _Painter(color)
    top_k = report.get("top_k", 3)
    columns = [
        ("Scenario", 21, "<"),
        ("Target", 20, "<"),
        ("Leak>=1", 7, ">"),
        ("LeakShare", 9, ">"),
        ("Rank1Hijack", 11, ">"),
        ("CanaryExfil", 11, ">"),
        (f"Recall@{top_k}", 12, ">"),
        ("p50/p95 ms", 13, ">"),
        ("RLS Delta", 9, ">"),
    ]

    def border(left: str, mid: str, right: str) -> str:
        return left + mid.join("─" * (w + 2) for _, w, _ in columns) + right

    def line(cells: list[tuple[str, tuple[str, ...]]]) -> str:
        parts = []
        for (text, styles), (_, width, align) in zip(cells, columns, strict=True):
            clipped = text if len(text) <= width else text[: width - 1] + "~"
            padded = f"{clipped:{align}{width}}"
            parts.append(" " + paint(padded, *styles) + " ")
        return "│" + "│".join(parts) + "│"

    def leak_cell(v: float) -> tuple[str, tuple[str, ...]]:
        return _pct(v), ("green",) if v == 0 else ("red", "bold")

    def recall_cell(m: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
        v = m.get("authorized_recall_pct")
        if v is None:
            return "n/a", ("dim",)
        return f"{v:.1f}% n={m['recall_eligible_queries']}", ("green",) if v >= 100 else ("amber",)

    def row(label: str, target: str, m: dict[str, Any], *, boundary: bool, delta: float | None) -> str:
        label_styles: tuple[str, ...] = ("amber", "bold") if boundary else ("bold",)
        delta_cell: tuple[str, tuple[str, ...]] = ("", ())
        if delta is not None:
            delta_cell = (_signed(delta), ("green",) if delta <= 0 else ())
        return line(
            [
                (label, label_styles),
                (_TARGET_NAMES[target], ("red",) if target == "unprotected" else ("green",)),
                leak_cell(m["queries_leaking_pct"]),
                leak_cell(m["leaked_row_share_pct"]),
                leak_cell(m["rank_1_hijack_pct"]),
                leak_cell(m["canary_exfiltration_pct"]),
                recall_cell(m),
                (f"{m['p50_latency_ms']:.2f}/{m['p95_latency_ms']:.2f}", ()),
                delta_cell,
            ]
        )

    out = [border("┌", "┬", "┐"), line([(name, ("bold",)) for name, _, _ in columns]), border("├", "┼", "┤")]
    groups: list[list[str]] = []
    for s in report["scenarios"]:
        label = _SHORT_NAMES.get(s["id"], s["id"])
        boundary = bool(s.get("boundary"))
        delta = s.get("rls_delta_p50_ms")
        groups.append(
            [
                row(label, "unprotected", s["unprotected"], boundary=boundary, delta=None),
                row(label, "memshield", s["memshield"], boundary=boundary, delta=delta),
            ]
        )
    agg = report.get("aggregate_attacks")
    if agg:
        delta = round(agg["memshield"]["p50_latency_ms"] - agg["unprotected"]["p50_latency_ms"], 2)
        groups.append(
            [
                row(_SHORT_NAMES["AGGREGATE"], "unprotected", agg["unprotected"], boundary=False, delta=None),
                row(_SHORT_NAMES["AGGREGATE"], "memshield", agg["memshield"], boundary=False, delta=delta),
            ]
        )
    for i, group in enumerate(groups):
        if i:
            out.append(border("├", "┼", "┤"))
        out.extend(group)
    out.append(border("└", "┴", "┘"))
    return "\n".join(out)


def render_performance_box(report: dict[str, Any], *, color: bool, width: int = 86) -> str:
    """Summary box: SQL kernel latency per target, net RLS delta, agent turn and throughput."""
    paint = _Painter(color)
    perf = report.get("performance") or {}
    inner = width - 4
    title = " Performance & RLS Kernel Overhead "
    lines = ["┌─" + title + "─" * (width - 3 - len(title)) + "┐"]

    def add(text: str, *styles: str) -> None:
        for chunk in textwrap.wrap(text, inner) or [""]:
            lines.append("│ " + paint(f"{chunk:<{inner}}", *styles) + " │")

    d50, d95 = perf.get("p50_delta_ms", 0.0), perf.get("p95_delta_ms", 0.0)
    pct = perf.get("p50_delta_pct")
    add(
        f"{'Unprotected SQL kernel':<30} p50 {perf.get('unprotected_p50_ms', 0):7.2f} ms"
        f"   p95 {perf.get('unprotected_p95_ms', 0):7.2f} ms"
    )
    add(
        f"{'adk-memshield RLS SQL kernel':<30} p50 {perf.get('memshield_p50_ms', 0):7.2f} ms"
        f"   p95 {perf.get('memshield_p95_ms', 0):7.2f} ms"
    )
    pct_str = f" ({pct:+.1f}%)" if pct is not None else ""
    add(
        f"{'Net RLS kernel delta':<30} p50 {d50:+7.2f} ms{pct_str}   p95 {d95:+7.2f} ms",
        "green" if d50 <= 0 else "amber",
    )
    if perf.get("rls_equal_or_faster_p50"):
        add(
            "Note: RLS is equal or faster at p50. Policy predicates filter rows before the vector "
            "distance sort; at larger seed sizes the planner serves them from the B-tree "
            "idx_memories_scope_lookup (bitmap index scan), so fewer distances are computed.",
            "dim",
        )
    else:
        add(
            "Note: the RLS cost is the transaction-local set_config round-trip plus policy "
            "predicate evaluation; differences under ~1 ms are within Docker Desktop jitter.",
            "dim",
        )
    add(f"{'Mean ADK agent turn':<30} {perf.get('mean_agent_turn_ms', 0):.2f} ms per target (Runner + model)")
    add(
        f"{'Evaluation throughput':<30} {perf.get('throughput_qps', 0):.1f} queries/sec "
        f"({perf.get('query_executions', 0)} runs in {perf.get('eval_seconds', 0):.2f} s)",
        "bold",
    )
    lines.append("└" + "─" * (width - 2) + "┘")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="leak-arena",
        description="Red-Team Evaluation & Live SQL/RLS Telemetry Console for Google ADK Memory",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser("serve", help="Start the ADK Leak Arena web console and API server")
    serve_p.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    serve_p.add_argument("--port", type=int, default=8090, help="Bind port (default: 8090)")

    eval_p = sub.add_parser(
        "eval", help="Seed the arena DB and run the S1-S5 + S6 + Control benchmark"
    )
    eval_p.add_argument(
        "--caller",
        default="alice_analyst",
        choices=["alice_analyst", "exec_agent"],
        help="Active caller identity for benchmark evaluation",
    )
    eval_p.add_argument(
        "--engine",
        default="deterministic_agent",
        choices=["deterministic_agent", "ollama_gemma", "gemini_api"],
        help="ADK Runner LLM execution mode",
    )
    eval_p.add_argument(
        "--repeats",
        type=int,
        default=3,
        help="Latency samples per query (security verdicts use the first run; default: 3)",
    )
    eval_p.add_argument(
        "--top-k",
        type=int,
        default=3,
        choices=TOP_K_OPTIONS,
        help="Top-K rows retrieved per query on both targets (default: 3)",
    )
    eval_p.add_argument(
        "--seed-size",
        type=int,
        default=SEED_SIZE_OPTIONS[0],
        choices=SEED_SIZE_OPTIONS,
        help="Rows per table: 36 baseline plus deterministic synthetic background rows",
    )
    eval_p.add_argument(
        "--scenarios",
        default=",".join(SCENARIO_IDS),
        help=f"Comma-separated subset of {','.join(SCENARIO_IDS)}",
    )
    eval_p.add_argument(
        "--format",
        default="table",
        choices=["table", "markdown", "json"],
        help="table: box-drawing terminal table (default); markdown: GitHub table; json: raw report only",
    )
    eval_p.add_argument(
        "--json",
        action="store_true",
        help="Deprecated alias for --format json",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)
    cfg = ArenaConfig()

    if args.command == "serve":
        uvicorn.run("adk_leak_arena.server:app", host=args.host, port=args.port, reload=False)
        return 0

    if args.command == "eval":
        fmt = "json" if args.json else args.format
        scenarios = [s.strip().upper() for s in args.scenarios.split(",") if s.strip()]
        unknown = [s for s in scenarios if s not in SCENARIO_IDS]
        if unknown or not scenarios:
            parser.error(f"--scenarios must be a subset of {','.join(SCENARIO_IDS)}")
        seed_info = ensure_schema_and_seed(cfg)
        scale_info = apply_seed_size(cfg, args.seed_size) if args.seed_size > SEED_SIZE_OPTIONS[0] else None
        try:
            report = asyncio.run(
                run_full_benchmark(
                    cfg,
                    caller_id=args.caller,
                    engine=args.engine,  # type: ignore[arg-type]
                    repeats=args.repeats,
                    top_k=args.top_k,
                    scenarios=scenarios,
                )
            )
        finally:
            if scale_info:
                delete_synthetic(cfg)

        if fmt == "json":
            # Machine-readable: the report only, so the output parses as one JSON document.
            print(json.dumps(report | {"scale": scale_info}, indent=2))
            return 0

        rows = seed_info["records_seeded_per_table"] + (
            scale_info["synthetic_rows_per_table"] if scale_info else 0
        )
        print(
            f"\n=== adk-leak-arena v0.1.0 | Red-Team Evaluation Matrix "
            f"(caller={args.caller}, top_k={args.top_k}, seed_size={rows} rows/table) ===\n"
        )
        if scale_info:
            print(
                f"scale: {scale_info['synthetic_rows_per_table']} synthetic rows/table via "
                f"{scale_info['method']} in {scale_info['elapsed_ms']} ms (removed after the run)\n"
            )
        if fmt == "markdown":
            print(report["markdown_table"])
        else:
            color = use_color(sys.stdout)
            print(render_box_table(report, color=color))
            print()
            print(render_performance_box(report, color=color))
        meth = report["methodology"]
        warm = meth["warmup"] or {}
        print(
            f"\n{meth['seed_records']} seed records across {len(meth['tenants'])} tenants | "
            f"{sum(meth['queries_per_scenario'].values())} queries | top_k={meth['top_k']} | "
            f"{meth['latency_repeats_per_query']} latency samples/query | "
            f"untimed warmup: {warm.get('queries', 0)} queries x 2 targets ({warm.get('elapsed_ms', 0)} ms)"
        )
        print()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
