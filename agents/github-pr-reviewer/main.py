#!/usr/bin/env python3
"""
Autonomous GitHub PR Reviewer & Triage Agent Council CLI.
Orchestrates Security, Performance, and Test Synthesizer specialist agents.
"""

import argparse
import json
import os
import sys

# Load environment variables from .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from pr_agent.reviewer import PRReviewerAgent
from pr_agent.github_client import fetch_pr_diff, load_diff_from_file, load_diff_from_stdin
from pr_agent.html_reporter import generate_html_dashboard
from pr_agent.terminal_ui import print_rich_report


def parse_args():
    parser = argparse.ArgumentParser(
        description="🏛️ Autonomous GitHub PR Reviewer & Triage Council: Multi-agent security audit, performance analysis, automated test synthesis, and remediation patching."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--pr",
        type=str,
        help="GitHub PR URL (https://github.com/owner/repo/pull/123) or slug (owner/repo#123)"
    )
    group.add_argument(
        "--diff",
        type=str,
        help="Path to local unified diff or patch file"
    )
    group.add_argument(
        "--stdin",
        action="store_true",
        help="Read diff from standard input (e.g., git diff | python main.py --stdin)"
    )
    group.add_argument(
        "--sample",
        action="store_true",
        help="Run analysis on bundled sample diff (zero configuration demonstration)"
    )

    parser.add_argument(
        "--offline",
        action="store_true",
        help="Force offline mode using specialist rule council without external LLM API calls"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"),
        help="Gemini model name to use (default: gemini-1.5-flash)"
    )
    parser.add_argument(
        "--token",
        type=str,
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub Personal Access Token (for private repositories or higher rate limits)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path to write the review markdown report (e.g. review_report.md)"
    )
    parser.add_argument(
        "--html",
        type=str,
        help="Path to export an interactive dark-mode HTML dashboard (e.g. dashboard.html)"
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Automatically generate a remediation.patch file for detected issues"
    )
    parser.add_argument(
        "--patch-output",
        type=str,
        default="remediation.patch",
        help="Custom path for the auto-fix patch file (default: remediation.patch)"
    )
    parser.add_argument(
        "--generate-tests",
        type=str,
        help="Path to write synthesized unit & regression tests (e.g. generated_tests.py)"
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: exits with status code 1 if council verdict is BLOCKED"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output review report as structured JSON"
    )

    return parser.parse_args()


def main():
    args = parse_args()

    # Determine input source
    diff_text = None
    source_title = None

    if args.sample:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sample_path = os.path.join(current_dir, "samples", "sample_pr_diff.patch")
        diff_text, source_title = load_diff_from_file(sample_path)
        source_title = f"Sample PR Diff ({source_title})"
    elif args.pr:
        try:
            diff_text, source_title = fetch_pr_diff(args.pr, token=args.token)
        except Exception as e:
            sys.stderr.write(f"Error fetching PR: {e}\n")
            sys.exit(1)
    elif args.diff:
        try:
            diff_text, source_title = load_diff_from_file(args.diff)
        except Exception as e:
            sys.stderr.write(f"Error reading diff file: {e}\n")
            sys.exit(1)
    elif args.stdin:
        try:
            diff_text, source_title = load_diff_from_stdin()
        except Exception as e:
            sys.stderr.write(f"Error reading from stdin: {e}\n")
            sys.exit(1)
    else:
        # Default fallback to sample mode if no argument provided
        current_dir = os.path.dirname(os.path.abspath(__file__))
        sample_path = os.path.join(current_dir, "samples", "sample_pr_diff.patch")
        diff_text, source_title = load_diff_from_file(sample_path)
        source_title = f"Sample PR Diff ({source_title})"

    # Initialize reviewer agent
    agent = PRReviewerAgent(
        model_name=args.model,
        offline=args.offline
    )

    report = agent.analyze(diff_text, source_title)

    # Auto-fix patch generation
    if (args.auto_fix or args.patch_output != "remediation.patch") and report.remediation_patch:
        patch_path = args.patch_output
        with open(patch_path, "w", encoding="utf-8") as f:
            f.write(report.remediation_patch)
        print(f"🩹 Auto-fix patch written to: {patch_path}")

    # Synthesized tests export
    if args.generate_tests and report.generated_tests:
        with open(args.generate_tests, "w", encoding="utf-8") as f:
            for t in report.generated_tests:
                f.write(f"# --- {t.test_name} ({t.target_file}) ---\n")
                f.write(t.code + "\n\n")
        print(f"🧪 Synthesized unit tests written to: {args.generate_tests}")

    # HTML Dashboard export
    if args.html:
        html_code = generate_html_dashboard(report)
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(html_code)
        print(f"🌐 Interactive dashboard exported to: {args.html}")

    # Output to console
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_rich_report(report)

    # Write markdown to output file if requested
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())
        print(f"\n📁 Report successfully saved to: {args.output}")

    # CI exit code handling
    if args.ci and report.verdict == "BLOCKED":
        sys.stderr.write(f"\n🛑 CI Check Failed: Pull request is BLOCKED by Council with Health Score {report.health_score}/100.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
