"""Command-Line Interface for Autonomous Code Healer Agent."""

import argparse
import os
import sys
from dotenv import load_dotenv

# Safe UTF-8 reconfiguration on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from healer.core import AutonomousCodeHealer
from healer.reporter import generate_healing_html_dashboard


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Autonomous Code Healer - Test-driven self-healing agent with AST safety guardrails and atomic rollback."
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        default="examples/broken_math.py",
        help="Path to the Python source file needing repair (default: examples/broken_math.py)",
    )
    parser.add_argument(
        "--test-cmd",
        "-t",
        type=str,
        default="pytest test_math.py",
        help="Test command to run for verification (default: 'pytest test_math.py')",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum healing cycles before aborting/rolling back (default: 3)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Hard sandbox timeout in seconds per test run (default: 10s)",
    )
    parser.add_argument(
        "--no-rollback",
        action="store_true",
        help="Disable automatic rollback if all attempts fail",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force offline mock mode without calling Gemini API",
    )
    parser.add_argument(
        "--output-html",
        "-o",
        type=str,
        default="healing_report.html",
        help="Path to generate self-contained HTML dashboard (default: healing_report.html)",
    )

    args = parser.parse_args()

    # Resolve paths relative to working directory or agent folder
    target_path = os.path.abspath(args.file)
    if not os.path.exists(target_path):
        # Check relative to script dir
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alt_path = os.path.join(script_dir, args.file)
        if os.path.exists(alt_path):
            target_path = alt_path
        else:
            print(f"[Error] Target file does not exist: {args.file}")
            sys.exit(1)

    print("=" * 70)
    print("   AUTONOMOUS CODE HEALER - SELF-HEALING AGENTIC WORKFLOW")
    print("=" * 70)
    print(f" Target File       : {target_path}")
    print(f" Test Command      : {args.test_cmd}")
    print(f" Max Cycles        : {args.max_attempts}")
    print(f" Sandbox Timeout   : {args.timeout}s")
    print(f" Auto Rollback     : {not args.no_rollback}")
    print(f" Mode              : {'Offline Mock' if args.mock else 'Gemini Live'}")
    print("=" * 70)

    def event_listener(event):
        ev = event.get("event", "info")
        msg = event.get("message", "")
        ts = event.get("timestamp", "")
        print(f"[{ts}] [{ev.upper()}] {msg}")

    healer = AutonomousCodeHealer(
        max_attempts=args.max_attempts,
        sandbox_timeout=args.timeout,
        auto_rollback=not args.no_rollback,
        mock_mode=args.mock,
        event_callback=event_listener,
    )

    result = healer.heal(target_path, args.test_cmd)

    print("\n" + "=" * 70)
    print(f" HEALING RESULT: {result['status'].upper()}")
    print("=" * 70)

    if result.get("diff"):
        print("\nUnified Diff Applied:")
        print(result["diff"])
    else:
        print("\nNo diff generated.")

    # Save HTML report
    if args.output_html:
        report_path = os.path.abspath(args.output_html)
        generate_healing_html_dashboard(result, report_path)
        print(f"\n[Dashboard] Interactive HTML report generated at: {report_path}")

    metrics = result.get("metrics", {})
    print(f"\nDuration: {metrics.get('duration_seconds', 0)}s | Attempts: {metrics.get('attempts_made', 0)} | Status: {result['status']}")

    if result["status"] == "healed_successfully" or result["status"] == "already_passing":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
