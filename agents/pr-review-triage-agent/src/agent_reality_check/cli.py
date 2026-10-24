from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluator import run_scenario_suite
from .providers import MockAgentProvider, OllamaAgentProvider
from .scenarios import build_scenarios


def format_report(report: dict) -> str:
    lines: list[str] = []
    lines.append("Agent Reality Check Report")
    lines.append("=" * 28)
    lines.append(f"Total scenarios: {report['scenarios_total']}")
    lines.append(f"Passed: {report['scenarios_passed']}")
    lines.append(f"Failed: {report['scenarios_failed']}")
    lines.append(f"Inconclusive: {report['scenarios_inconclusive']}")
    lines.append(f"Pass percentage: {report['pass_percentage']:.1f}%")
    lines.append("")

    for result in report["results"]:
        expected = result.get("expected_behavior") or result.get("category") or "Not specified"
        actual = result.get("actual_response") or result.get("observed_response") or "<empty response>"
        lines.append(f"Scenario: {result['title']}")
        lines.append(f"Expected behavior: {expected}")
        lines.append(f"Actual model response: {actual}")
        lines.append(f"Judgment: {result['status']}")
        lines.append(f"Explanation: {result['reason']}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _write_report(report: dict, output_path: str | None = None) -> Path | None:
    if output_path is None:
        return None

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate whether an agent behaves responsibly across scenario tests.")
    parser.add_argument("--demo", action="store_true", help="Run the built-in demonstration scenarios against the mock provider.")
    parser.add_argument("--provider", choices=["mock", "ollama"], default="mock", help="Agent backend to use for evaluation.")
    parser.add_argument("--report", default="reports/agent_reality_check_report.json", help="Where to save the JSON report.")
    args = parser.parse_args()

    if args.provider == "ollama":
        provider = OllamaAgentProvider()
    else:
        provider = MockAgentProvider()

    scenarios = build_scenarios()
    report = run_scenario_suite(provider, scenarios)
    payload = report.to_dict()

    _write_report(payload, args.report)
    print(format_report(payload))
    return 0 if report.scenarios_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
