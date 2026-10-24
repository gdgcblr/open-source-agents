"""OSS Pulse Agent CLI — Command-line interface for open source repository intelligence.

Usage:
  python cli.py analyze <owner/repo> [--output report.md] [--format markdown|json|all]
  python cli.py compare <owner1/repo1> <owner2/repo2>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Fix Windows cp1252 emoji encoding issues
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent))

from agent import run_analysis, OSSPulseAgent
from export.renderer import render_terminal, save_report


def analyze_command(args: argparse.Namespace, console: Console) -> int:
    """Analyze a single repository and display/save reports."""
    repo = args.repository
    console.print(f"\n[bold blue]🚀 Launching OSS Pulse Agent for [cyan]{repo}[/cyan]...[/bold blue]")

    try:
        report = run_analysis(repo)
        render_terminal(report, console=console)

        if args.output:
            save_report(report, args.output, format_type=args.format)
            console.print(f"[bold green]✓ Report saved to {args.output}[/bold green]\n")

        return 0
    except Exception as e:
        console.print(f"[bold red]Error analyzing {repo}: {e}[/bold red]")
        return 1


def compare_command(args: argparse.Namespace, console: Console) -> int:
    """Compare two repositories side by side."""
    repo1, repo2 = args.repo1, args.repo2
    console.print(f"\n[bold blue]⚖️ Comparing [cyan]{repo1}[/cyan] vs [cyan]{repo2}[/cyan]...[/bold blue]\n")

    try:
        agent = OSSPulseAgent()
        console.print(f"Analyzing {repo1}...")
        r1 = agent.analyze(*repo1.split("/"))
        console.print(f"Analyzing {repo2}...")
        r2 = agent.analyze(*repo2.split("/"))

        from rich.table import Table
        from rich import box

        comp_table = Table(
            title=f"Side-by-Side Comparison: {repo1} vs {repo2}",
            box=box.ROUNDED,
            header_style="bold magenta",
        )
        comp_table.add_column("Metric / Dimension", style="cyan")
        comp_table.add_column(repo1, justify="right")
        comp_table.add_column(repo2, justify="right")

        comp_table.add_row(
            "Overall Health Score",
            f"{r1.overall_score:.0f}/100 ({r1.overall_grade})",
            f"{r2.overall_score:.0f}/100 ({r2.overall_grade})",
        )
        comp_table.add_row(
            "Data Coverage %",
            f"{r1.data_coverage_percentage:.0f}% ({r1.evidence_quality})",
            f"{r2.data_coverage_percentage:.0f}% ({r2.evidence_quality})",
        )
        comp_table.add_row("Stars", f"{r1.repository.stars:,}", f"{r2.repository.stars:,}")
        comp_table.add_row("Forks", f"{r1.repository.forks:,}", f"{r2.repository.forks:,}")

        # Categories
        for cs1 in r1.category_scores:
            cs2_match = next((c for c in r2.category_scores if c.category == cs1.category), None)
            score2_str = f"{cs2_match.score:.1f}/100" if cs2_match else "N/A"
            comp_table.add_row(
                cs1.category.value.title(),
                f"{cs1.score:.1f}/100",
                score2_str,
            )

        comp_table.add_row("Total Findings", str(len(r1.all_findings)), str(len(r2.all_findings)))
        comp_table.add_row(
            "Good First Issues",
            str(len(r1.contribution_opportunities)),
            str(len(r2.contribution_opportunities)),
        )

        console.print(comp_table)
        
        # Validate and warn on comparability if data coverage differs significantly
        cov_diff = abs(r1.data_coverage_percentage - r2.data_coverage_percentage)
        if cov_diff >= 15.0:
            console.print(
                f"[bold yellow]⚠️ Comparability Notice:[/bold yellow] "
                f"Data coverage differs by {cov_diff:.0f}% ({repo1}: {r1.data_coverage_percentage:.0f}%, "
                f"{repo2}: {r2.data_coverage_percentage:.0f}%). "
                f"[dim]Scores reflect differing amounts of accessible evidence and should be interpreted with this context.[/dim]\n"
            )
        else:
            console.print()
        return 0
    except Exception as e:
        console.print(f"[bold red]Error comparing repositories: {e}[/bold red]")
        return 1


def main() -> int:
    console = Console()
    parser = argparse.ArgumentParser(
        description="OSS Pulse Agent — Evidence-driven, explainable open source intelligence",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze repository health")
    analyze_parser.add_argument("repository", help="Target GitHub repository (owner/name)")
    analyze_parser.add_argument("-o", "--output", help="Save report to file path")
    analyze_parser.add_argument(
        "-f",
        "--format",
        choices=["markdown", "json", "all"],
        default="markdown",
        help="Export format (default: markdown)",
    )

    # compare command
    compare_parser = subparsers.add_parser("compare", help="Compare two repositories")
    compare_parser.add_argument("repo1", help="First repository (owner/repo)")
    compare_parser.add_argument("repo2", help="Second repository (owner/repo)")

    # If no subcommand passed, treat the first arg as a repository name for analyze
    if len(sys.argv) > 1 and sys.argv[1] not in ("analyze", "compare", "-h", "--help"):
        sys.argv.insert(1, "analyze")

    args = parser.parse_args()

    if args.command == "analyze":
        return analyze_command(args, console)
    elif args.command == "compare":
        return compare_command(args, console)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
