from __future__ import annotations

import argparse
import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from agent import analyze_repository


def _prompt_for_python_version() -> str:
    value = input("Target Python version for compatibility checks (for example: 3.9 or 3.11.5): ").strip()
    if not value:
        raise ValueError("Python version is required for compatibility checks.")
    return value


def _render_report_tables(result: dict) -> None:
    console = Console()

    summary = Table(title="Dependency Audit Summary")
    summary.add_column("Field", style="cyan")
    summary.add_column("Value", style="magenta")
    summary.add_row("Project Root", str(result.get("project_root", "")))
    summary.add_row("Target Python Version", str(result.get("target_python_version", "")))
    summary.add_row("Package Count", str(result.get("package_count", 0)))
    summary.add_row("Generated Smoke Test", str(result.get("generated_test_file", "")))
    console.print(summary)

    upgrade_rows = result.get("safe_upgrade_report", [])
    upgrades = Table(title="Safe Upgrade Report", show_lines=True)
    upgrades.add_column("Package", style="cyan")
    upgrades.add_column("Current")
    upgrades.add_column("Metadata Candidate")
    upgrades.add_column("Tested Upgrade")
    upgrades.add_column("Recommended")
    upgrades.add_column("Status")
    upgrades.add_column("Reason", overflow="fold")
    for row in upgrade_rows:
        upgrades.add_row(
            str(row.get("package", "")),
            str(row.get("current_version", "") or "-"),
            str(row.get("metadata_candidate_version", row.get("compatible_upgrade_version", "")) or "-"),
            str(row.get("tested_upgrade_version", row.get("validated_upgrade_version", "")) or "-"),
            str(row.get("recommended_upgrade_version", row.get("safe_upgrade_version", "")) or "-"),
            str(row.get("status", "")),
            str(row.get("reason", "")),
        )
    console.print(upgrades)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Python dependencies and generate upgrade guidance.")
    parser.add_argument("--repo", default=".", help="Repository root to scan.")
    parser.add_argument("--output", default=None, help="Optional JSON output file path.")
    parser.add_argument(
        "--limit", type=int, default=None, help="Optional max number of packages to process for testing."
    )
    parser.add_argument(
        "--python-version",
        default=None,
        help="Python version to validate compatibility against (for example: 3.9 or 3.11.5).",
    )
    parser.add_argument(
        "--package",
        default=None,
        help="Comma-separated package names to check; for example: requests,pytest,packaging.",
    )
    parser.add_argument(
        "--console-output",
        choices=("table", "json", "both"),
        default="table",
        help="Console output format. JSON file output is still controlled by --output.",
    )
    args = parser.parse_args()

    requested_python_version = args.python_version
    if requested_python_version is None:
        print("Please provide the Python version to validate against.")
        requested_python_version = _prompt_for_python_version()

    print("Starting Python dependency upgrade audit...")
    print(f"Repository path: {Path(args.repo).resolve()}")
    print(f"Target Python version: {requested_python_version}")
    if args.limit is not None:
        print(f"Processing limit: {args.limit} packages")
    if args.package:
        print(f"Selected packages: {args.package}")
    result = analyze_repository(
        Path(args.repo),
        package_limit=args.limit,
        python_version=requested_python_version,
        selected_packages=args.package,
    )
    payload = json.dumps(result, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
        print(f"Saved analysis report to: {output_path}")
    print("Audit complete.")
    if args.console_output in {"table", "both"}:
        _render_report_tables(result)
    if args.console_output in {"json", "both"}:
        print(payload)


if __name__ == "__main__":
    main()
