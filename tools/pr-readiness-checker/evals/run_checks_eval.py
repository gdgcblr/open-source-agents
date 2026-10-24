"""Rule-check eval: runs every labelled case and scores each check.

    python -m evals.run_checks_eval            # table + exit code 1 on any mismatch
    python -m evals.run_checks_eval --json out.json

For each check it reports true/false positives and negatives, precision and
recall, where "positive" means the check flagged the case (fail, warn or info).
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from prcheck.models import Status
from prcheck.registry import all_checks
from prcheck.runner import run

from . import fixtures
from .cases import CASES, Case

FLAGGED = {Status.FAIL, Status.WARN, Status.INFO}
SEED = 1234


@dataclass
class CaseResult:
    name: str
    ok: bool
    mismatches: list[str] = field(default_factory=list)
    statuses: dict[str, str] = field(default_factory=dict)


@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None


def run_case(case: Case, workdir: Path, rng: random.Random) -> CaseResult:
    project = fixtures.build_repo(workdir, project=case.project, files=case.files(rng),
                                  base_files=case.base_files, branch_files=case.branch_files,
                                  use_git=case.use_git)
    report, _ = run(project, use_git=case.use_git)
    statuses = {r.id: r.status.value for r in report.checks}
    mismatches = []
    for result in report.checks:
        expected = case.expect.get(result.id)
        if result.status is Status.CRASH:
            mismatches.append(f"{result.id} crashed: {result.skip_reason}")
        elif expected is None and result.status in FLAGGED:
            detail = "; ".join(f.message for f in result.findings)[:160]
            mismatches.append(f"{result.id} unexpectedly {result.status.value}: {detail}")
        elif expected is not None and result.status.value != expected:
            mismatches.append(f"{result.id} expected {expected}, got {result.status.value}")
    if case.use_git:
        # Scope checks must actually run on git cases, otherwise a broken git setup would look like a pass.
        for check_id in ("G1", "G2", "G3"):
            if statuses.get(check_id) == Status.SKIP.value:
                mismatches.append(f"{check_id} was skipped on a git case")
    return CaseResult(case.name, not mismatches, mismatches, statuses)


def evaluate(cases: list[Case] = CASES, seed: int = SEED) -> tuple[list[CaseResult], dict[str, Confusion]]:
    rng = random.Random(seed)
    git_ok = shutil.which("git") is not None
    results: list[CaseResult] = []
    confusion = {spec.id: Confusion() for spec in all_checks()}
    for case in cases:
        if case.use_git and not git_ok:
            continue
        with tempfile.TemporaryDirectory(prefix="prcheck-eval-") as tmp:
            result = run_case(case, Path(tmp), rng)
        results.append(result)
        for check_id, status in result.statuses.items():
            if status == Status.SKIP.value or check_id not in confusion:
                continue
            flagged = status in {s.value for s in FLAGGED}
            expected = check_id in case.expect
            c = confusion[check_id]
            if flagged and expected:
                c.tp += 1
            elif flagged:
                c.fp += 1
            elif expected:
                c.fn += 1
            else:
                c.tn += 1
    return results, confusion


def _fmt(value: float | None) -> str:
    return "  -  " if value is None else f"{value:5.2f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="Write results to this JSON file.")
    args = parser.parse_args(argv)

    results, confusion = evaluate()
    passed = sum(r.ok for r in results)
    print(f"Rule-check eval: {passed}/{len(results)} cases correct\n")
    for r in results:
        if not r.ok:
            print(f"  MISMATCH {r.name}")
            for m in r.mismatches:
                print(f"    - {m}")
    print(f"\n  {'check':<6} {'TP':>3} {'FP':>3} {'FN':>3} {'TN':>3}  precision  recall")
    for check_id, c in confusion.items():
        print(f"  {check_id:<6} {c.tp:>3} {c.fp:>3} {c.fn:>3} {c.tn:>3}    {_fmt(c.precision)}   {_fmt(c.recall)}")

    if args.json:
        args.json.write_text(json.dumps({
            "cases_total": len(results),
            "cases_correct": passed,
            "cases": [r.__dict__ for r in results],
            "per_check": {k: {**v.__dict__, "precision": v.precision, "recall": v.recall}
                          for k, v in confusion.items()},
        }, indent=2), encoding="utf-8")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
