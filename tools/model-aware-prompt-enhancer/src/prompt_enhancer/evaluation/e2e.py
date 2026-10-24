"""End-to-end A/B evaluation: run the original and the enhanced prompt through the
same provider and model, score both answers with the same deterministic checks,
and report per-case wins, losses and ties.

This is the only way the toolkit claims an enhancement *helped*. Results depend
on the model, sampling and the checks you write; small samples are noisy, so
reports always show n and per-case outcomes, never a single headline number.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
from typing import Any

from ..analyzer import Options
from ..engine import enhance
from .dataset import Case
from .providers import Provider


def _words(s: str) -> int:
    return len(s.split())


def _json(s: str) -> Any:
    t = s.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.S)
    if fence:
        t = fence.group(1)
    return json.loads(t)


def run_check(check: dict[str, Any], answer: str) -> bool:
    """Deterministic answer checks. Unknown check types raise, so typos are not silently 'passed'."""
    t = check["type"]
    v: Any = check.get("value")
    ci = check.get("ignore_case", True)
    a = answer.lower() if ci else answer
    val: Any = v.lower() if (ci and isinstance(v, str)) else v
    if t == "contains":
        return val in a
    if t == "not_contains":
        return val not in a
    if t == "contains_all":
        return all((x.lower() if ci else x) in a for x in v)
    if t == "regex":
        return re.search(v, answer, re.I if ci else 0) is not None
    if t == "not_regex":
        return re.search(v, answer, re.I if ci else 0) is None
    if t == "max_words":
        return _words(answer) <= int(v)
    if t == "min_words":
        return _words(answer) >= int(v)
    if t == "max_chars":
        return len(answer.strip()) <= int(v)
    if t == "count_regex":
        n = len(re.findall(check["pattern"], answer, re.M | (re.I if ci else 0)))
        return int(check.get("min", 0)) <= n <= int(check.get("max", 10**9))
    if t == "max_lines":
        return len([ln for ln in answer.splitlines() if ln.strip()]) <= int(v)
    if t == "json_valid":
        try:
            _json(answer)
            return True
        except ValueError:
            return False
    if t == "json_keys":
        try:
            obj = _json(answer)
        except ValueError:
            return False
        items = obj if isinstance(obj, list) else [obj]
        return bool(items) and all(isinstance(i, dict) and set(v) <= set(i) for i in items)
    raise ValueError(f"unknown check type {t!r}")


@dataclass
class Arm:
    passed_checks: int
    total_checks: int
    trials: int
    failures: list[str] = field(default_factory=list)
    answers: list[dict[str, Any]] = field(default_factory=list)  # each: {"text", "checks": [{"name", "passed"}]}
    input_tokens: list[int] = field(default_factory=list)
    output_tokens: list[int] = field(default_factory=list)
    ms: list[float] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.passed_checks / self.total_checks if self.total_checks else 0.0


@dataclass
class E2ECaseResult:
    id: str
    status: str
    original: Arm
    enhanced: Arm
    outcome: str  # "win", "loss", "tie", "not-enhanced"
    tags: list[str] = field(default_factory=list)
    original_prompt: str = ""
    enhanced_prompt: str = ""
    diff: str = ""
    applied: list[str] = field(default_factory=list)


def _score(completions: list[Any], checks: list[dict[str, Any]]) -> Arm:
    arm = Arm(0, 0, len(completions))
    for c in completions:
        arm.ms.append(round(c.ms, 1))
        if c.input_tokens is not None:
            arm.input_tokens.append(c.input_tokens)
        if c.output_tokens is not None:
            arm.output_tokens.append(c.output_tokens)
        results = []
        for chk in checks:
            arm.total_checks += 1
            ok = run_check(chk, c.text)
            results.append({"name": chk.get("name", chk["type"]), "passed": ok})
            if ok:
                arm.passed_checks += 1
            else:
                arm.failures.append(chk.get("name", chk["type"]))
        arm.answers.append({"text": c.text, "checks": results})
    return arm


def _complete_with_retry(provider: Provider, prompt: str, model: str, max_tokens: int, attempts: int = 2) -> Any:
    for i in range(attempts):
        try:
            return provider.complete(prompt, model, max_tokens)
        except Exception:
            if i == attempts - 1:
                raise
    raise AssertionError("unreachable")


def run_e2e(cases: list[Case], provider: Provider, model: str, trials: int = 1, max_tokens: int = 1024,
            options: Options | None = None, workers: int = 1) -> dict[str, Any]:
    plans = []  # (case, enhancement result, prompts to send per arm)
    for case in cases:
        if not case.checks:
            continue
        r = enhance(case.prompt, model=case.model or model, options=options, accept=case.accept, answers=case.answers)
        arms = {"original": case.prompt} if r.enhanced == case.prompt else {"original": case.prompt, "enhanced": r.enhanced}
        plans.append((case, r, arms))

    jobs = [(i, arm, prompt) for i, (_, _, arms) in enumerate(plans) for arm, prompt in arms.items() for _ in range(trials)]
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        outs = list(pool.map(lambda j: _complete_with_retry(provider, j[2], model, max_tokens), jobs))
    got: dict[tuple[int, str], list[Any]] = {}
    for (i, arm, _), c in zip(jobs, outs, strict=True):
        got.setdefault((i, arm), []).append(c)

    results: list[E2ECaseResult] = []
    for i, (case, r, arms) in enumerate(plans):
        orig = _score(got[(i, "original")], case.checks)
        if "enhanced" not in arms:
            results.append(E2ECaseResult(case.id, r.status, orig, orig, "not-enhanced", list(case.tags), case.prompt, case.prompt, "", []))
            continue
        enh = _score(got[(i, "enhanced")], case.checks)
        outcome = "win" if enh.score > orig.score else "loss" if enh.score < orig.score else "tie"
        results.append(E2ECaseResult(case.id, r.status, orig, enh, outcome, list(case.tags), case.prompt, r.enhanced, r.diff, r.applied))

    def summarize(rows: list[E2ECaseResult]) -> dict[str, Any]:
        compared = [x for x in rows if x.outcome != "not-enhanced"]
        return {
            "cases": len(rows), "compared": len(compared),
            "wins": sum(x.outcome == "win" for x in compared), "losses": sum(x.outcome == "loss" for x in compared),
            "ties": sum(x.outcome == "tie" for x in compared), "not_enhanced": len(rows) - len(compared),
            "original_check_pass_rate": _pool(x.original for x in compared),
            "enhanced_check_pass_rate": _pool(x.enhanced for x in compared),
        }

    groups = sorted({t for x in results for t in x.tags})
    return {
        "kind": "end-to-end-mock" if getattr(provider, "name", "") == "mock" else "end-to-end-llm",
        "provider": getattr(provider, "name", "custom"),
        "model": model,
        "trials_per_arm": trials,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cases_with_checks": len(results),
        **summarize(results),
        "by_group": {g: summarize([x for x in results if g in x.tags]) for g in groups},
        "results": [asdict(x) for x in results],
        "caveat": "Check pass rates on a small sample; sampling noise can exceed the difference. Re-run with more trials before drawing conclusions.",
    }


def _pool(arms: Any) -> float | None:
    arms = list(arms)
    total = sum(a.total_checks for a in arms)
    return round(sum(a.passed_checks for a in arms) / total, 3) if total else None
