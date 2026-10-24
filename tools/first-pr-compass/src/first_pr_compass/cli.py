"""Command-line interface for First PR Compass."""

from __future__ import annotations

import argparse
from dataclasses import replace
import sys
from pathlib import Path
from typing import Sequence

from first_pr_compass.analyzer import analyze_repository
from first_pr_compass.github import download_github_repository
from first_pr_compass.report import render_json, render_markdown

DEFAULT_REPORT = "first-pr-compass-report.md"


def _build_parser(default_output: str = DEFAULT_REPORT) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=Path(sys.argv[0]).name,
        description="Create an evidence-backed onboarding report for a local or public GitHub repository.",
    )
    parser.add_argument(
        "repository",
        help="Local repository path or public GitHub URL (https://github.com/owner/repository).",
    )
    parser.add_argument(
        "--ref",
        help="GitHub branch, tag, or commit to analyze (defaults to the repository's default branch).",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Report format (default: markdown).",
    )
    parser.add_argument(
        "--output",
        default=default_output,
        help=(
            "Output file; use '-' to write to stdout "
            "(default: first-pr-compass-report.md)."
        ),
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    default_output: str = DEFAULT_REPORT,
) -> int:
    parser = _build_parser(default_output)
    arguments = parser.parse_args(argv)
    try:
        if "://" in arguments.repository or arguments.repository.startswith("git@"):
            with download_github_repository(arguments.repository, arguments.ref) as source:
                analysis = replace(
                    analyze_repository(source.path),
                    source_url=source.url,
                    source_ref=source.ref,
                )
        else:
            if arguments.ref:
                raise ValueError("--ref can only be used with a GitHub repository URL.")
            analysis = analyze_repository(arguments.repository)

        report = (
            render_markdown(analysis)
            if arguments.format == "markdown"
            else render_json(analysis)
        )
        if arguments.output == "-":
            sys.stdout.write(report)
        else:
            output_path = Path(arguments.output).expanduser()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report, encoding="utf-8")
            print(f"Report written to {output_path.resolve()}")
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


def get_report() -> int:
    """Console-script alias that saves the report to a file by default."""
    return main(default_output=DEFAULT_REPORT)


def guide_me_to_contribute() -> int:
    """Console-script alias that prints the report for quick onboarding."""
    return main(default_output="-")
