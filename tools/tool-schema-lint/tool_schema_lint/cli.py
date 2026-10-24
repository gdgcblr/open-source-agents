"""Command-line interface.

Exit codes:
  0  no findings at or above the --fail-on level
  1  findings at or above the --fail-on level
  2  usage error or unreadable / unrecognized input
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .linter import LintResult, lint
from .loader import load_tools, read_json
from .models import SOURCE_FORMATS, TARGETS, InputError, Severity
from .report import RENDERERS, render_rules
from .rules import REGISTRY

EXIT_OK, EXIT_FINDINGS, EXIT_USAGE = 0, 1, 2
FAIL_LEVELS = {"error": Severity.ERROR, "warning": Severity.WARNING, "info": Severity.INFO, "never": None}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tool-schema-lint",
        description="Lint LLM tool / function definitions (MCP, OpenAI, Gemini, Anthropic) "
                    "for structural errors, provider incompatibilities, and weak descriptions.",
    )
    p.add_argument("files", nargs="*", help="JSON files to lint ('-' reads standard input)")
    p.add_argument("-t", "--target", action="append", choices=[*TARGETS, "all"],
                   help="provider rules to apply; repeatable (default: the format each tool is written in)")
    p.add_argument("--input-format", choices=SOURCE_FORMATS,
                   help="force how tool objects are read (only needed for ambiguous input)")
    p.add_argument("-f", "--format", choices=sorted(RENDERERS), default="text", help="output format (default: text)")
    p.add_argument("--fail-on", choices=list(FAIL_LEVELS), default="error",
                   help="lowest severity that makes the exit code 1 (default: error)")
    p.add_argument("--disable", action="append", default=[], metavar="RULE",
                   help="skip a rule by id, e.g. --disable G011; repeatable or comma-separated")
    p.add_argument("--max-tokens", type=int, metavar="N",
                   help="report G016 if the estimated size of all definitions exceeds N tokens")
    p.add_argument("--list-rules", action="store_true", help="print the rule catalogue and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    # Tool names and descriptions may contain any Unicode; never crash on a narrow console.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_rules:
        print(render_rules())
        return EXIT_OK
    if not args.files:
        parser.print_usage(sys.stderr)
        print("tool-schema-lint: error: no input files (use '-' for stdin)", file=sys.stderr)
        return EXIT_USAGE

    disabled = {r.strip().upper() for item in args.disable for r in item.split(",") if r.strip()}
    unknown = sorted(disabled - REGISTRY.keys())
    if unknown:
        print(f"tool-schema-lint: error: unknown rule id(s): {', '.join(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    if args.max_tokens is not None and args.max_tokens < 1:
        print("tool-schema-lint: error: --max-tokens must be a positive integer", file=sys.stderr)
        return EXIT_USAGE

    targets = list(TARGETS) if args.target and "all" in args.target else args.target

    results: dict[str, LintResult] = {}
    for path in args.files:
        label = "<stdin>" if path == "-" else path
        try:
            tools = load_tools(read_json(path), args.input_format)
        except InputError as exc:
            print(f"tool-schema-lint: error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        results[label] = lint(tools, targets, disabled, args.max_tokens, label)

    print(RENDERERS[args.format](results))

    threshold = FAIL_LEVELS[args.fail_on]
    if threshold is not None and any(f.severity >= threshold for r in results.values() for f in r.findings):
        return EXIT_FINDINGS
    return EXIT_OK
