#!/usr/bin/env python3
"""CLI entry point for IntentGuard.

Usage:
    # Run the built-in demo scenario:
    python -m intent_guard.cli --example

    # Review a specific intent + diff:
    python -m intent_guard.cli \
        --intent intent.md \
        --diff changes.patch \
        --language python
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from .models import ReviewRequest, ReviewVerdict, Verdict, IssueSeverity, RequirementStatus
from .runner import run_review

load_dotenv()

console = Console()

EXAMPLES_DIR = Path(__file__).parent / "examples"


def load_example() -> ReviewRequest:
    """Load the built-in example scenario."""
    intent_path = EXAMPLES_DIR / "example_intent.md"
    diff_path = EXAMPLES_DIR / "example_diff.patch"

    if not intent_path.exists() or not diff_path.exists():
        console.print("[red]Example files not found. Ensure examples/ directory is intact.[/red]")
        sys.exit(1)

    return ReviewRequest(
        intent_context=intent_path.read_text(),
        code_diff=diff_path.read_text(),
        language="python",
    )


def display_verdict(verdict: ReviewVerdict) -> None:
    """Render the review verdict as a rich terminal output."""

    # --- Header: Verdict Banner ---
    verdict_colors = {
        Verdict.PASS: "green",
        Verdict.FAIL: "red",
        Verdict.NEEDS_REVISION: "yellow",
    }
    color = verdict_colors.get(verdict.verdict, "white")
    verdict_text = f"  VERDICT: {verdict.verdict.value.upper()}  |  Confidence: {verdict.confidence:.0%}  "
    console.print()
    console.print(Panel(
        verdict_text,
        style=f"bold {color}",
        box=box.DOUBLE,
        title="Code Correctness Review",
        subtitle="Intent → Implementation Alignment",
    ))

    # --- Requirements Table ---
    if verdict.requirements:
        console.print()
        req_table = Table(
            title="Requirements Coverage",
            box=box.ROUNDED,
            show_lines=True,
        )
        req_table.add_column("ID", style="cyan", width=8)
        req_table.add_column("Requirement", width=40)
        req_table.add_column("Status", width=24)
        req_table.add_column("Explanation", width=50)

        status_styles = {
            RequirementStatus.IMPLEMENTED: "[green]✅ Implemented[/green]",
            RequirementStatus.PARTIALLY_IMPLEMENTED: "[yellow]⚠️  Partial[/yellow]",
            RequirementStatus.MISSING: "[red]❌ Missing[/red]",
            RequirementStatus.MISINTERPRETED: "[red]🔀 Misinterpreted[/red]",
        }

        for req in verdict.requirements:
            status_display = status_styles.get(req.status, str(req.status))
            req_table.add_row(
                req.id,
                req.description,
                status_display,
                req.explanation,
            )

        console.print(req_table)

    # --- Scope Creep ---
    if verdict.unmatched_changes:
        console.print()
        creep_table = Table(
            title="🚨 Scope Creep — Unrequested Changes",
            box=box.ROUNDED,
            show_lines=True,
            style="yellow",
        )
        creep_table.add_column("Location", width=30)
        creep_table.add_column("Description", width=40)
        creep_table.add_column("Risk", width=40)

        for change in verdict.unmatched_changes:
            creep_table.add_row(
                change.location,
                change.description,
                change.risk_assessment,
            )

        console.print(creep_table)

    # --- Issues ---
    if verdict.issues:
        console.print()
        issue_table = Table(
            title="Issues Found",
            box=box.ROUNDED,
            show_lines=True,
        )
        issue_table.add_column("Severity", width=10)
        issue_table.add_column("Category", width=24)
        issue_table.add_column("Description", width=50)
        issue_table.add_column("Suggestion", width=40)

        severity_styles = {
            IssueSeverity.CRITICAL: "[bold red]CRITICAL[/bold red]",
            IssueSeverity.MAJOR: "[red]MAJOR[/red]",
            IssueSeverity.MINOR: "[yellow]MINOR[/yellow]",
            IssueSeverity.INFO: "[blue]INFO[/blue]",
        }

        for issue in verdict.issues:
            issue_table.add_row(
                severity_styles.get(issue.severity, str(issue.severity)),
                issue.category.value.replace("_", " ").title(),
                issue.description,
                issue.suggestion or "—",
            )

        console.print(issue_table)

    # --- Summary ---
    console.print()
    console.print(Panel(
        verdict.summary,
        title="Summary",
        box=box.ROUNDED,
        style="dim",
    ))
    console.print()


def main():
    parser = argparse.ArgumentParser(
        prog="intent-guard",
        description="IntentGuard — autonomous intent-to-implementation correctness verifier",
    )
    parser.add_argument(
        "--example",
        action="store_true",
        help="Run the built-in demo scenario",
    )
    parser.add_argument("--intent", type=str, help="Path to intent context file (JIRA ticket, HLD, etc.)")
    parser.add_argument("--diff", type=str, help="Path to code diff / patch file")
    parser.add_argument("--language", type=str, default="python", help="Programming language (default: python)")
    parser.add_argument("--repo-context", type=str, help="Path to optional repo context file")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of rich display")
    parser.add_argument(
        "--report",
        nargs="?",
        const="INTENTGUARD_REPORT.md",
        help="Export Markdown audit scorecard to file (default: INTENTGUARD_REPORT.md)",
    )

    args = parser.parse_args()

    # Validate API key.
    if not os.getenv("GOOGLE_API_KEY"):
        console.print(
            "[red]Error: GOOGLE_API_KEY environment variable not set.[/red]\n"
            "Set it in your .env file or export it:\n"
            "  export GOOGLE_API_KEY='your-key-here'"
        )
        sys.exit(1)

    # Build the request.
    if args.example:
        console.print("[bold cyan]Running built-in demo scenario...[/bold cyan]\n")
        request = load_example()
    elif args.intent and args.diff:
        intent_text = Path(args.intent).read_text()
        diff_text = Path(args.diff).read_text()
        repo_ctx = Path(args.repo_context).read_text() if args.repo_context else None
        request = ReviewRequest(
            intent_context=intent_text,
            code_diff=diff_text,
            language=args.language,
            repo_context=repo_ctx,
        )
    else:
        parser.print_help()
        console.print("\n[yellow]Provide --example or both --intent and --diff[/yellow]")
        sys.exit(1)

    # Run the review.
    console.print("[dim]Analyzing intent and cross-referencing code changes (with active guardrails)...[/dim]")
    try:
        verdict = asyncio.run(run_review(request))
    except ValueError as val_err:
        console.print(f"[bold red]Guardrail validation error:[/bold red] {val_err}")
        sys.exit(1)

    # Output.
    if args.json:
        print(json.dumps(verdict.model_dump(), indent=2))
    else:
        display_verdict(verdict)

    if args.report:
        from .guardrails import generate_markdown_scorecard
        report_md = generate_markdown_scorecard(verdict)
        Path(args.report).write_text(report_md, encoding="utf-8")
        console.print(f"[bold green]✓ Markdown audit scorecard saved to: {args.report}[/bold green]\n")


if __name__ == "__main__":
    main()

