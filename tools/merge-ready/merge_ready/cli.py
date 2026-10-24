"""Command-line interface for MergeReady contribution validator."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import Optional

from merge_ready import __version__
from merge_ready.checks import run_all_checks
from merge_ready.project import ProjectContext
from merge_ready.report import (
    format_github_annotations,
    format_json,
    format_markdown,
    format_terminal,
)


def safe_print(text: str) -> None:
    """Print text safely across different terminal encodings (e.g. Windows cp1252)."""
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            sys.stdout.buffer.write(text.encode("utf-8", errors="replace") + b"\n")
            sys.stdout.buffer.flush()
        except Exception:
            print(text.encode("ascii", errors="backslashreplace").decode("ascii"))


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for MergeReady."""
    parser = argparse.ArgumentParser(
        prog="merge-ready",
        description="MergeReady: Contribution Validator for Open-Source AI Agents & Tools.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"merge-ready {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    check_parser = subparsers.add_parser(
        "check",
        help="Validate a project directory against repository contribution rules.",
    )
    check_parser.add_argument(
        "project_path",
        type=str,
        help="Path to the agent or tool directory (e.g. 'tools/merge-ready' or 'agents/my-agent').",
    )
    check_parser.add_argument(
        "--base",
        type=str,
        default=None,
        help="Git base reference (e.g. 'upstream/main' or 'origin/main') to validate diff scope.",
    )
    check_parser.add_argument(
        "--format",
        choices=["terminal", "json", "markdown", "github"],
        default="terminal",
        help="Output format (default: terminal).",
    )
    check_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional file path to write the formatted validation report.",
    )
    check_parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings and skipped checks as failures.",
    )

    return parser


def run_check(
    project_path_str: str,
    base_ref: Optional[str] = None,
    output_format: str = "terminal",
    output_file: Optional[str] = None,
    strict: bool = False,
) -> int:
    """Execute validation and format report."""
    log_level = os.getenv("LOG_LEVEL", "info")
    target_path = Path(project_path_str)
    if not target_path.exists() or not target_path.is_dir():
        sys.stderr.write(f"Error: Target path '{project_path_str}' does not exist or is not a directory.\n")
        return 2

    try:
        ctx = ProjectContext(project_path=target_path, base_ref=base_ref)
    except Exception as e:
        sys.stderr.write(f"Error initializing project context: {e}\n")
        return 2

    try:
        report = run_all_checks(ctx)
    except Exception as e:
        sys.stderr.write(f"Operational error running validation checks: {e}\n")
        return 2

    try:
        if output_format == "json":
            output_text = format_json(report)
        elif output_format == "markdown":
            output_text = format_markdown(report)
        elif output_format == "github":
            output_text = format_github_annotations(report)
        else:
            output_text = format_terminal(report)
    except Exception as e:
        sys.stderr.write(f"Operational error generating {output_format} report: {e}\n")
        return 2

    if output_file:
        try:
            out_p = Path(output_file)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(output_text, encoding="utf-8")
        except Exception as e:
            sys.stderr.write(f"Error writing report to '{output_file}': {e}\n")
            return 2
    else:
        try:
            safe_print(output_text)
        except Exception as e:
            sys.stderr.write(f"Error printing report: {e}\n")
            return 2

    return report.exit_code(strict=strict)


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point for merge-ready."""
    try:
        parser = build_parser()
        args = parser.parse_args(argv)

        if not args.command:
            # If run directly with a path without "check", support ergonomics: merge-ready <path>
            if argv and len(argv) >= 1 and not argv[0].startswith("-"):
                # synthesize check command
                return run_check(project_path_str=argv[0])
            parser.print_help(sys.stderr)
            return 2

        if args.command == "check":
            return run_check(
                project_path_str=args.project_path,
                base_ref=args.base,
                output_format=args.format,
                output_file=args.output,
                strict=args.strict,
            )

        return 2
    except Exception as e:
        sys.stderr.write(f"Unexpected CLI error: {e}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
