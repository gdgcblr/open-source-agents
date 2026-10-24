#!/usr/bin/env python3
"""Runner script for offline deterministic evaluation suite."""

import json
import sys
from pathlib import Path

# Add package root to sys.path
pkg_root = Path(__file__).resolve().parent.parent
if str(pkg_root) not in sys.path:
    sys.path.insert(0, str(pkg_root))

from agentrelay.evaluator import run_eval_suite


def main() -> int:
    cases_file = Path(__file__).parent / "test_cases.json"
    if not cases_file.exists():
        print(f"Error: test cases file not found at {cases_file}", file=sys.stderr)
        return 2

    with open(cases_file, encoding="utf-8") as f:
        cases = json.load(f)

    summary = run_eval_suite(cases)

    print("=" * 70)
    print(" AgentRelay — Offline Evaluation Suite")
    print("=" * 70)
    print(f"Total Cases:                      {summary.total_cases}")
    print(f"Passed:                           {summary.passed_cases}/{summary.total_cases} ({summary.pass_rate * 100:.1f}%)")
    print(f"Mean Score:                       {summary.mean_score:.2f}")
    print(f"Evidence Citation Validity Rate:  {summary.citation_validity_rate * 100:.1f}%")
    print(f"Abstention Accuracy:              {summary.abstention_accuracy * 100:.1f}%")
    print(f"Prompt Injection Resistance:      {summary.prompt_injection_resistance_rate * 100:.1f}%")
    print(f"Suite Execution Time:             {summary.duration_ms:.1f} ms")
    print("=" * 70)

    for res in summary.case_results:
        status = "PASS" if res.passed else "FAIL"
        print(f"  [{status}] {res.case_id:<36} ({res.category:<12}) - Score: {res.score:.2f}")
        if not res.passed and res.details:
            print(f"         Issues: {res.details}")
    print("=" * 70)

    return 0 if summary.passed_cases == summary.total_cases else 1


if __name__ == "__main__":
    sys.exit(main())
