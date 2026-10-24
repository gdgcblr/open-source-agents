"""Offline benchmark runner.

Measures what the toolkit itself does, deterministically and without a model:
requirement preservation, expected/unexpected diagnostics, unnecessary changes
to good prompts, enhancement/no-change rates, token overhead and run time.
It does NOT measure whether a model answers better; that is e2e.py's job.
"""

from __future__ import annotations

import statistics
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from ..analyzer import Options
from ..engine import enhance
from ..requirements import is_subsequence
from ..tokens import count as count_tokens
from .dataset import Case


@dataclass
class CaseResult:
    id: str
    category: str
    model: str | None
    profile: str
    status: str
    changed: bool
    passed: bool
    failures: list[str]
    lock_ok: bool
    rules_fired: list[str]
    token_overhead: int
    ms: float


@dataclass
class EvalReport:
    kind: str
    token_method: str
    results: list[CaseResult]
    summary: dict[str, Any] = field(default_factory=dict)
    by_category: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_profile: dict[str, dict[str, Any]] = field(default_factory=dict)
    regressions: list[str] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 3) if d else None


def _group(results: list[CaseResult]) -> dict[str, Any]:
    return {
        "cases": len(results),
        "passed": sum(r.passed for r in results),
        "enhancement_rate": _rate(sum(r.changed for r in results), len(results)),
        "lock_ok_rate": _rate(sum(r.lock_ok for r in results), len(results)),
    }


def evaluate_case(case: Case, model: str | None, harness: str, options: Options) -> CaseResult:
    m = case.model or model
    t0 = time.perf_counter()
    r = enhance(case.prompt, model=m, harness=harness, options=options, accept=case.accept, answers=case.answers)
    ms = (time.perf_counter() - t0) * 1000
    a = r.analysis
    fired = sorted({d.rule_id for d in a.diagnostics})
    e = case.expect
    fails: list[str] = []
    if not r.lock.ok:
        fails.append(f"requirement lock failed: {r.lock.missing}")
    if r.status == "enhanced" and r.mode == "rewrite" and not is_subsequence(case.prompt, r.enhanced) and not any(
        p.op == "replace" for p in a.patches if p.id in r.applied
    ):
        fails.append("original prompt text not preserved")
    if "task_type" in e and a.task_type != e["task_type"]:
        fails.append(f"task_type {a.task_type!r} != expected {e['task_type']!r}")
    for rid in e.get("rules", []):
        if rid not in fired:
            fails.append(f"expected rule {rid} did not fire")
    for rid in e.get("absent_rules", []):
        if rid in fired:
            fails.append(f"unexpected rule {rid} fired")
    if "changed" in e and r.changed != e["changed"]:
        fails.append(f"changed={r.changed} expected {e['changed']}")
    if "status" in e and r.status != e["status"]:
        fails.append(f"status {r.status!r} != expected {e['status']!r}")
    for s in e.get("preserved", []):
        if s not in r.enhanced:
            fails.append(f"expected text not preserved: {s[:40]!r}")
    if "good-prompt" in case.tags and r.changed:
        fails.append("good prompt was changed")
    overhead = count_tokens(r.enhanced)[0] - count_tokens(case.prompt)[0]
    if "max_token_overhead" in e and overhead > e["max_token_overhead"]:
        fails.append(f"token overhead {overhead} > {e['max_token_overhead']}")
    return CaseResult(
        id=case.id, category=case.category or a.task_type, model=m, profile=a.model_profile, status=r.status,
        changed=r.changed, passed=not fails, failures=fails, lock_ok=r.lock.ok, rules_fired=fired,
        token_overhead=overhead, ms=round(ms, 3),
    )


def run_offline(cases: list[Case], model: str | None = None, harness: str = "api", options: Options | None = None) -> EvalReport:
    opts = options or Options()
    results = [evaluate_case(c, model, harness, opts) for c in cases]
    n = len(results)
    good = [r for r, c in zip(results, cases, strict=True) if "good-prompt" in c.tags]
    expected_hits = sum(len(c.expect.get("rules", [])) for c in cases)
    missed = sum(1 for r in results for f in r.failures if f.startswith("expected rule"))
    unexpected = sum(1 for r in results for f in r.failures if f.startswith("unexpected rule"))
    changed = [r for r in results if r.changed]
    times = sorted(r.ms for r in results)
    summary = {
        "cases": n,
        "passed": sum(r.passed for r in results),
        "failed": sum(not r.passed for r in results),
        "requirement_preservation_rate": _rate(sum(r.lock_ok for r in results), n),
        "enhancement_rate": _rate(len(changed), n),
        "no_change_rate": _rate(n - len(changed), n),
        "good_prompts": len(good),
        "good_prompts_left_unchanged_rate": _rate(sum(not r.changed for r in good), len(good)),
        "expected_rule_recall": _rate(expected_hits - missed, expected_hits),
        "unexpected_rule_firings": unexpected,
        "token_overhead_mean_when_changed": round(statistics.mean(r.token_overhead for r in changed), 1) if changed else 0,
        "token_overhead_max": max((r.token_overhead for r in results), default=0),
        "ms_mean": round(statistics.mean(times), 3) if times else 0,
        "ms_p95": times[max(0, int(round(0.95 * len(times))) - 1)] if times else 0,
    }
    by_cat: dict[str, list[CaseResult]] = defaultdict(list)
    by_prof: dict[str, list[CaseResult]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)
        by_prof[r.profile].append(r)
    return EvalReport(
        kind="offline-deterministic", token_method=count_tokens("x")[1], results=results, summary=summary,
        by_category={k: _group(v) for k, v in sorted(by_cat.items())},
        by_profile={k: _group(v) for k, v in sorted(by_prof.items())},
    )


def compare_to_baseline(report: EvalReport, baseline: dict[str, Any]) -> EvalReport:
    """Mark regressions (passed in baseline, fails now) and fixes (the reverse)."""
    before = {r["id"]: r["passed"] for r in baseline.get("results", [])}
    for r in report.results:
        if before.get(r.id) is True and not r.passed:
            report.regressions.append(r.id)
        elif before.get(r.id) is False and r.passed:
            report.fixed.append(r.id)
    report.summary["regressions"] = len(report.regressions)
    report.summary["fixed_since_baseline"] = len(report.fixed)
    return report
