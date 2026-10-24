#!/usr/bin/env python3
"""
GitHub PR Reviewer & Triage Agent CLI Entrypoint.
Analyzes GitHub PRs, local diffs, or sample patches using heuristics and Gemini LLM.
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


def parse_args():
    parser = argparse.ArgumentParser(
        description="🤖 GitHub PR Reviewer & Triage Agent: Automated PR analysis, security scanning, and code review suggestions."
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
        help="Force offline mode using local heuristic rule engine without LLM API calls"
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
        print("ℹ️ No target specified. Defaulting to bundled sample patch (--sample).\nUse --help to see all options.\n")
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

    # Format output
    if args.json:
        output_str = json.dumps(report.to_dict(), indent=2)
    else:
        output_str = report.to_markdown()

    # Print to console
    print(output_str)

    # Write to output file if requested
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_str)
        print(f"\n📁 Report successfully saved to: {args.output}")


if __name__ == "__main__":
    main()
