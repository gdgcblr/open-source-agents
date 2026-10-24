#!/usr/bin/env python3
"""
GitHub PR Guardian — Automated Code Review & Security Auditor Agent.

Usage:
    python main.py --diff sample_diffs/vulnerable_pr.diff
    python main.py --git
    python main.py --pr https://github.com/owner/repo/pull/123
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path


def load_env_file() -> None:
    """Load key-value pairs from .env if present (without requiring external libraries)."""
    env_path = Path(__file__).parent / ".env"
    if env_path.is_file():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")
                        if key and key not in os.environ:
                            os.environ[key] = val
        except Exception:
            pass


def main() -> int:
    load_env_file()

    parser = argparse.ArgumentParser(
        description="🛡️ GitHub PR Guardian — AI-Powered Security Auditor & Code Reviewer Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--diff",
        type=str,
        help="Path to a unified .diff or .patch file to review",
    )
    group.add_argument(
        "--pr",
        type=str,
        help="GitHub PR URL (e.g., https://github.com/owner/repo/pull/12) or owner/repo#12",
    )
    group.add_argument(
        "--git",
        action="store_true",
        help="Review current working directory uncommitted changes via git diff",
    )
    group.add_argument(
        "--staged",
        action="store_true",
        help="Review current git staged changes (--cached)",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file path to save the generated Markdown review report",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Run only local static security and rule scanners (offline mode, no API call)",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Gemini API Key (overrides GEMINI_API_KEY environment variable)",
    )
    parser.add_argument(
        "--github-token",
        type=str,
        default=None,
        help="GitHub Personal Access Token (overrides GITHUB_TOKEN environment variable)",
    )

    args = parser.parse_args()

    # Import agent modules
    from guardian.agent import GuardianAgent
    from guardian.reporter import ReviewReporter

    agent = GuardianAgent(
        gemini_api_key=args.api_key,
        github_token=args.github_token,
    )

    use_llm = not args.no_llm and bool(os.getenv("GEMINI_API_KEY") or args.api_key)

    try:
        if args.pr:
            print(f"[*] Fetching and analyzing GitHub PR: {args.pr}...")
            review_data, static_findings = agent.review_github_pr(args.pr, use_llm=use_llm)
        elif args.diff:
            diff_file = Path(args.diff)
            if not diff_file.is_file():
                print(f"[Error] Diff file not found: {args.diff}", file=sys.stderr)
                return 1
            print(f"[*] Analyzing diff file: {args.diff}...")
            diff_text = diff_file.read_text(encoding="utf-8")
            review_data, static_findings = agent.review_diff_text(
                diff_text=diff_text,
                title=f"Diff: {diff_file.name}",
                use_llm=use_llm,
            )
        elif args.staged:
            print("[*] Analyzing staged git changes...")
            review_data, static_findings = agent.review_local_git(staged_only=True, use_llm=use_llm)
        elif args.git:
            print("[*] Analyzing working tree git changes...")
            review_data, static_findings = agent.review_local_git(staged_only=False, use_llm=use_llm)
        else:
            # Default to bundled demo diff if no arguments supplied
            sample_path = Path(__file__).parent / "sample_diffs" / "vulnerable_pr.diff"
            if sample_path.is_file():
                print("[*] No input provided. Running demonstration on sample_diffs/vulnerable_pr.diff...")
                diff_text = sample_path.read_text(encoding="utf-8")
                review_data, static_findings = agent.review_diff_text(
                    diff_text=diff_text,
                    title="Demo: vulnerable_pr.diff",
                    use_llm=use_llm,
                )
            else:
                parser.print_help()
                return 0

        # Print terminal output
        reporter = ReviewReporter(review_data=review_data, static_findings=static_findings)
        reporter.print_terminal()

        # Save to markdown file if requested
        if args.output:
            out_file = Path(args.output)
            out_file.write_text(reporter.generate_markdown(), encoding="utf-8")
            print(f"[✔] Markdown review report saved to: {out_file.resolve()}")

        return 0

    except Exception as e:
        print(f"\n[Fatal Error] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
