"""CLI interface layer.  Example:
    python cli.py --junit samples/flaky/junit.xml --log samples/flaky/ci.log --mock
"""
import argparse
import sys

from triage.adapters.files import load_run
from triage.adapters.providers import get_provider
from triage.adapters.report import render
from triage.service import DEFAULT_MAX_LLM_CALLS, triage


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Triage CI test failures: flaky, infra or real regression?")
    ap.add_argument("--junit", required=True, help="Path to JUnit XML")
    ap.add_argument("--log", help="Path to raw CI log (optional)")
    ap.add_argument("--history", help='JSON like {"test_name": ["pass","fail",...]} (optional)')
    ap.add_argument("--mock", action="store_true", help="Offline mode: no API key or network needed")
    ap.add_argument("--max-llm-calls", type=int, default=DEFAULT_MAX_LLM_CALLS, help="Hard cap on LLM calls per run")
    ap.add_argument("--output", help="Write the report to this file instead of stdout")
    args = ap.parse_args(argv)

    run = load_run(args.junit, args.log, args.history)
    result = triage(run, lambda: get_provider(args.mock), args.max_llm_calls)
    report = render(result, "mock" if args.mock else "gemini")
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
