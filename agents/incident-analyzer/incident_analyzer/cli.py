"""CLI interface for the Incident Analyzer agent.

Provides three commands:
  - index:    One-time codebase indexing (generates AST spec)
  - analyze:  Diagnose an incident from logs, optional actual/expected output
  - report:   Display a saved diagnosis report
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .ast_indexer import index_codebase, load_spec, save_spec, save_spec_markdown
from .diagnoser import diagnose
from .models import Diagnosis, IncidentInput

logger = logging.getLogger(__name__)

# Default spec file name
DEFAULT_SPEC_FILE = ".incident-spec.json"


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _format_diagnosis(diagnosis: Diagnosis) -> str:
    """Format a Diagnosis into a human-readable report."""
    lines = []
    lines.append("=" * 70)
    lines.append("  INCIDENT ANALYSIS REPORT")
    lines.append("=" * 70)
    lines.append("")

    # Severity badge
    severity_icons = {
        "critical": "🔴 CRITICAL",
        "high": "🟠 HIGH",
        "medium": "🟡 MEDIUM",
        "low": "🔵 LOW",
        "info": "ℹ️  INFO",
    }
    lines.append(
        f"Severity:   {severity_icons.get(diagnosis.severity.value, diagnosis.severity.value)}"
    )
    lines.append(f"Confidence: {diagnosis.confidence:.0%}")
    lines.append("")

    # Root cause
    lines.append("─" * 70)
    lines.append("ROOT CAUSE")
    lines.append("─" * 70)
    lines.append(diagnosis.root_cause)
    lines.append("")

    # Affected symbols
    if diagnosis.affected_symbols:
        lines.append("─" * 70)
        lines.append("AFFECTED SYMBOLS")
        lines.append("─" * 70)
        for sym in diagnosis.affected_symbols:
            lines.append(
                f"  • {sym.name} @ {sym.file_path}:{sym.line_start}-{sym.line_end}"
            )
            lines.append(f"    Relevance: {sym.relevance}")
        lines.append("")

    # Suggested fixes
    if diagnosis.suggested_fixes:
        lines.append("─" * 70)
        lines.append("SUGGESTED FIXES & PATCHES")
        lines.append("─" * 70)
        for i, fix in enumerate(diagnosis.suggested_fixes, 1):
            status = " [Patch Verified ✅]" if fix.patch_verified else ""
            lines.append(f"  Fix #{i}: {fix.file_path}{status}")
            lines.append(f"  Explanation: {fix.explanation}")
            if fix.diff:
                lines.append("  Unified Diff:")
                for dline in fix.diff.splitlines():
                    lines.append(f"    {dline}")
            else:
                lines.append("  Original:")
                for code_line in fix.original_code.splitlines():
                    lines.append(f"    - {code_line}")
                lines.append("  Fixed:")
                for code_line in fix.fixed_code.splitlines():
                    lines.append(f"    + {code_line}")
            lines.append("")

    # Prevention tips
    if diagnosis.prevention_tips:
        lines.append("─" * 70)
        lines.append("PREVENTION TIPS")
        lines.append("─" * 70)
        for tip in diagnosis.prevention_tips:
            lines.append(f"  💡 {tip}")
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def cmd_index(args: argparse.Namespace) -> int:
    """Execute the 'index' command: one-time codebase indexing."""
    root_path = args.path
    output = args.output or str(Path(root_path) / DEFAULT_SPEC_FILE)

    print(f"Indexing codebase at: {root_path}")

    exclude = args.exclude.split(",") if args.exclude else None
    spec = index_codebase(root_path, exclude_dirs=exclude)

    save_spec(spec, output)
    print(f"\n✅ Indexed {spec.total_files} files with {spec.total_symbols} symbols")
    print(f"   Spec saved to: {output}")

    if args.markdown:
        md_output = args.markdown if args.markdown is not True else str(Path(root_path) / "spec.md")
        save_spec_markdown(spec, md_output)
        print(f"   Markdown spec saved to: {md_output}")

    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """Execute the 'analyze' command: diagnose an incident."""
    # Load the spec
    spec_path = args.spec
    if not Path(spec_path).exists():
        print(
            f"❌ Spec file not found: {spec_path}\n"
            f"   Run 'incident-analyzer index <path>' first to create it.",
            file=sys.stderr,
        )
        return 1

    spec = load_spec(spec_path)

    # Read log input
    if args.log_file:
        log_path = Path(args.log_file)
        if not log_path.exists():
            print(f"❌ Log file not found: {args.log_file}", file=sys.stderr)
            return 1
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    elif args.log:
        log_text = args.log
    elif not sys.stdin.isatty():
        log_text = sys.stdin.read()
    else:
        print(
            "❌ No log input provided. Use --log, --log-file, or pipe via stdin.",
            file=sys.stderr,
        )
        return 1

    # Build incident input
    incident = IncidentInput(
        log_text=log_text,
        actual_output=args.actual,
        expected_output=args.expected,
        context=args.context,
    )

    # Run diagnosis
    print("🔍 Analyzing incident...")
    diagnosis = diagnose(
        spec=spec,
        incident=incident,
        mock=args.mock,
        model_name=args.model,
    )

    # Output results
    if args.json:
        print(diagnosis.model_dump_json(indent=2))
    else:
        print(_format_diagnosis(diagnosis))

    # Save report if requested
    if args.save:
        report_path = Path(args.save)
        report_path.write_text(
            diagnosis.model_dump_json(indent=2), encoding="utf-8"
        )
        print(f"\n📄 Report saved to: {args.save}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="incident-analyzer",
        description=(
            "AI-powered incident analyzer that uses AST-indexed codebase "
            "specifications to diagnose errors and suggest code fixes."
        ),
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ── index command ──
    index_parser = subparsers.add_parser(
        "index",
        help="Index a codebase (one-time setup). Parses Python files and "
             "generates an AST specification.",
    )
    index_parser.add_argument(
        "path", help="Path to the codebase root directory"
    )
    index_parser.add_argument(
        "-o", "--output",
        help=f"Output path for the spec file (default: <path>/{DEFAULT_SPEC_FILE})",
    )
    index_parser.add_argument(
        "--exclude",
        help="Comma-separated list of directory names to exclude",
    )
    index_parser.add_argument(
        "--markdown", nargs="?", const=True, default=False,
        help="Also export a human-readable Markdown specification (e.g. spec.md)",
    )

    # ── analyze command ──
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze an incident using logs and the indexed codebase spec.",
    )
    analyze_parser.add_argument(
        "--spec", required=True,
        help="Path to the codebase spec file (generated by 'index')",
    )
    analyze_parser.add_argument(
        "--log", help="Inline log text or stack trace"
    )
    analyze_parser.add_argument(
        "--log-file", help="Path to a log file"
    )
    analyze_parser.add_argument(
        "--actual", help="Actual output observed (optional)"
    )
    analyze_parser.add_argument(
        "--expected", help="Expected output (optional)"
    )
    analyze_parser.add_argument(
        "--context", help="Additional developer context (optional)"
    )
    analyze_parser.add_argument(
        "--mock", action="store_true",
        help="Use mock mode (no API key required). For testing and demos.",
    )
    analyze_parser.add_argument(
        "--model", default="gemini-2.5-flash",
        help="Gemini model to use (default: gemini-2.5-flash)",
    )
    analyze_parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON instead of formatted report",
    )
    analyze_parser.add_argument(
        "--save", help="Save the diagnosis report to a JSON file"
    )

    return parser


def main() -> int:
    """Main entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args()

    _setup_logging(verbose=args.verbose)

    if args.command == "index":
        return cmd_index(args)
    elif args.command == "analyze":
        return cmd_analyze(args)
    else:
        parser.print_help()
        return 0
