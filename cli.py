"""CLI entry point.  Example:
    python cli.py --junit samples/flaky/junit.xml --log samples/flaky/ci.log --mock
"""
import argparse
import json
import sys

from triage.llm import get_provider
from triage.models import Category, TriagedFailure
from triage.parse import parse_junit, read_log
from triage.redact import redact
from triage.report import render
from triage.rules import classify, scan_log_for_infra


def log_context(failure_name: str, lines: list[str], width: int = 3, limit: int = 40) -> list[str]:
    """Lines around mentions of the test name (bounded)."""
    out: list[str] = []
    for i, line in enumerate(lines):
        if failure_name in line:
            out += lines[max(0, i - width) : i + width + 1]
        if len(out) >= limit:
            break
    return out[:limit]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Triage CI test failures: flaky, infra or real regression?")
    ap.add_argument("--junit", required=True, help="Path to JUnit XML")
    ap.add_argument("--log", help="Path to raw CI log (optional)")
    ap.add_argument("--history", help='JSON like {"test_name": ["pass","fail",...]} (optional)')
    ap.add_argument("--mock", action="store_true", help="Offline mode: no API key or network needed")
    ap.add_argument("--max-llm-calls", type=int, default=5, help="Hard cap on LLM calls per run (default 5)")
    ap.add_argument("--output", help="Write the report to this file instead of stdout")
    args = ap.parse_args(argv)

    failures, total = parse_junit(args.junit)
    lines = read_log(args.log)
    infra_hits = scan_log_for_infra(lines)
    history = json.load(open(args.history)) if args.history else None

    provider = None
    llm_calls = 0
    results: list[TriagedFailure] = []
    for f in failures:
        verdict = classify(f, infra_hits, history)
        note = None
        if verdict is None:
            if llm_calls >= args.max_llm_calls:
                verdict = get_provider(mock=True).classify(f, [])
                note = f"LLM call cap ({args.max_llm_calls}) reached; left for manual review."
            else:
                provider = provider or get_provider(args.mock)
                verdict = provider.classify(f, log_context(f.name, lines))
                llm_calls += 1
        results.append(TriagedFailure(failure=f, verdict=verdict, note=note))

    name = "mock" if args.mock else "gemini"
    report = render(results, total, name)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
