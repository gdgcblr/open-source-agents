"""Run Fix Maadi's offline routing evaluation scenarios."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT))
from fix_maadi import analyze  # noqa: E402


def main() -> int:
    scenarios = json.loads((Path(__file__).parent / "scenarios.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    for scenario in scenarios:
        result = analyze(scenario["input"])
        expected = scenario["expect"]
        if result["category"] != expected["category"]:
            failures.append(f"{scenario['id']}: category={result['category']!r}")
        if expected.get("status") and result["status"] != expected["status"]:
            failures.append(f"{scenario['id']}: status={result['status']!r}")
        if expected.get("related") and expected["related"] not in result["related_categories"]:
            failures.append(f"{scenario['id']}: related={result['related_categories']!r}")
        if expected.get("recommended_channel"):
            recommended = next((item for item in result["submission_options"] if item.get("recommended")), {})
            if recommended.get("id") != expected["recommended_channel"]:
                failures.append(f"{scenario['id']}: recommended={recommended.get('id')!r}")
    passed = len(scenarios) - len(failures)
    print(f"Fix Maadi evals: {passed}/{len(scenarios)} scenarios passed")
    for failure in failures:
        print(f"FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
