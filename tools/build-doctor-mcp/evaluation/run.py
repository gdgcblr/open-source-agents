"""Run the deterministic BuildDoctor evaluation cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from build_doctor_mcp.server import analyze_failure

CASES_PATH = Path(__file__).with_name("cases.json")


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def evaluate_case(case: dict[str, Any]) -> list[str]:
    result = json.loads(analyze_failure(case["log"]))
    failures: list[str] = []
    if result["failure_type"] != case["expected_failure_type"]:
        failures.append(f"failure_type={result['failure_type']!r}, expected {case['expected_failure_type']!r}")
    if result.get("confidence") != case.get("expected_confidence", result.get("confidence")):
        failures.append(f"confidence={result['confidence']!r}, expected {case['expected_confidence']!r}")
    signals = set(result.get("scoring", {}).get("matched_signals", []))
    missing = set(case.get("required_signals", [])) - signals
    if missing:
        failures.append(f"missing signals: {sorted(missing)}")
    return failures


def run() -> dict[str, Any]:
    cases = load_cases()
    results = []
    for case in cases:
        failures = evaluate_case(case)
        results.append({"id": case["id"], "status": "passed" if not failures else "failed", "failures": failures})
    passed = sum(result["status"] == "passed" for result in results)
    return {"total": len(results), "passed": passed, "failed": len(results) - passed, "results": results}


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["failed"] == 0 else 1)
