"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .checks import lint_project
from .models import ERROR, INFO, WARN, Report

COLORS = {ERROR: "\033[31m", WARN: "\033[33m", INFO: "\033[36m"}
RESET, DIM, BOLD = "\033[0m", "\033[2m", "\033[1m"


def render_text(report: Report, color: bool) -> str:
    def c(code: str, s: str) -> str:
        return f"{code}{s}{RESET}" if color else s

    lines = [c(BOLD, f"submission-linter {__version__} — {report.project}"), ""]
    for f in report.findings:
        where = ""
        if f.path:
            where = f"{f.path}:{f.line}" if f.line else f.path
        label = c(COLORS[f.severity], f"{f.severity.upper():5}")
        lines.append(f"{label} {f.code}  {f.message}")
        if where:
            lines.append(c(DIM, f"      at {where}"))
        if f.hint:
            lines.append(c(DIM, f"      hint: {f.hint}"))
    if not report.findings:
        lines.append("No findings.")
    lines += [
        "",
        f"{report.errors} error(s), {report.warnings} warning(s), {report.count(INFO)} note(s)",
        "Result: " + ("FAIL — fix the errors before opening a PR." if report.errors else "PASS"),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="submission-linter",
        description="Pre-flight check for open-source-ai contributions (agents/<slug> or tools/<slug>).",
    )
    p.add_argument("path", help="Path to your project directory, e.g. agents/research-assistant")
    p.add_argument("--base", help="Base git ref for the PR scope check (default: upstream/main, origin/main, main)")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    p.add_argument("--no-color", action="store_true")
    p.add_argument("--llm", action="store_true",
                   help="Add an advisory LLM review of README honesty (README and code are sent to the configured endpoint)")
    p.add_argument("--llm-dry-run", action="store_true", help="Show exactly which files --llm would send, then exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    report, ctx = lint_project(args.path, base=args.base)
    if not ctx:
        print(render_text(report, False), file=sys.stderr)
        return 2

    if args.llm or args.llm_dry_run:
        from . import llm_review

        if args.llm_dry_run:
            _, sent = llm_review.build_prompt(ctx["project"], ctx["listing"], ctx["readme"], ctx["tainted"])
            cfg = llm_review.config()
            print(f"Would send to {cfg['base_url']} (model {cfg['model']}):")
            for path, n in sent:
                print(f"  {path} ({n} chars)")
            print("Files containing detected secrets and .env* files are never sent.")
            return 0
        report.findings.extend(llm_review.review(ctx["project"], ctx["listing"], ctx["readme"], ctx["tainted"]))

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        color = sys.stdout.isatty() and not args.no_color and "NO_COLOR" not in os.environ
        print(render_text(report, color))
    failed = report.errors > 0 or (args.strict and report.warnings > 0)
    return 1 if failed else 0
