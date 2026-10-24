"""Command-line interface for AgentFeat."""

import argparse
import sys
from pathlib import Path
from typing import Optional

from agentfeat.config import config
from agentfeat.core.analyzer import CodebaseAnalyzer
from agentfeat.core.planner import FeaturePlanner
from agentfeat.core.reporter import PRReporter
from agentfeat.llm.gemini_client import GeminiClient
from agentfeat.orchestration.coordinator import AgentCoordinator
from agentfeat.utils.console import (
    console,
    print_banner,
    print_diff,
    print_plan,
    print_summary_table,
)
from agentfeat.utils.file_ops import apply_file_changes


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="agentfeat",
        description="AgentFeat: AI-powered feature development agent for modern engineering teams.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Command: scan
    scan_parser = subparsers.add_parser("scan", help="Scan and analyze target codebase")
    scan_parser.add_argument(
        "--target-dir", "-d",
        type=str,
        default=".",
        help="Path to repository to inspect (default: current directory)",
    )

    # Command: plan
    plan_parser = subparsers.add_parser("plan", help="Generate a feature implementation plan")
    plan_parser.add_argument(
        "request",
        type=str,
        help="Feature prompt (e.g. 'Add Google OAuth login to my application')",
    )
    plan_parser.add_argument(
        "--target-dir", "-d",
        type=str,
        default=".",
        help="Path to target repository (default: current directory)",
    )
    plan_parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="Gemini model to use (default: gemini-2.5-flash)",
    )

    # Command: run (Default full workflow)
    run_parser = subparsers.add_parser("run", help="Full workflow: analyze, plan, generate code, diff, and apply")
    run_parser.add_argument(
        "request",
        type=str,
        help="Feature prompt (e.g. 'Add Google OAuth login to my application')",
    )
    run_parser.add_argument(
        "--target-dir", "-d",
        type=str,
        default=".",
        help="Path to target repository (default: current directory)",
    )
    run_parser.add_argument(
        "--apply",
        action="store_true",
        help="Directly apply validated code changes to disk",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview diffs and plan without writing any changes to disk (default mode)",
    )
    run_parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip interactive confirmation before applying changes",
    )
    run_parser.add_argument(
        "--save-pr",
        type=str,
        default=None,
        help="Save generated GitHub PR description to a markdown file",
    )
    run_parser.add_argument(
        "--model", "-m",
        type=str,
        default=None,
        help="Gemini model to use (default: gemini-2.5-flash)",
    )
    run_parser.add_argument(
        "--offline",
        action="store_true",
        help="Run in offline demonstration mode without live Gemini API calls",
    )

    # Command: web
    web_parser = subparsers.add_parser("web", help="Launch interactive browser-based visual console")
    web_parser.add_argument(
        "--port", "-p",
        type=int,
        default=8080,
        help="Port to serve web console on (default: 8080)",
    )

    return parser.parse_args(argv)


def handle_scan(target_dir: Path) -> None:
    """Execute scan command."""
    print_banner()
    console.print(f"[bold cyan]🔍 Scanning codebase at:[/bold cyan] {target_dir}\n")

    analyzer = CodebaseAnalyzer(target_dir)
    summary = analyzer.analyze()

    console.print(f"• Total files scanned: [bold white]{summary.total_files}[/bold white]")
    console.print(f"• Languages: [bold green]{', '.join(summary.languages) or 'None'}[/bold green]")
    console.print(f"• Frameworks: [bold magenta]{', '.join(summary.frameworks) or 'None'}[/bold magenta]")
    console.print(f"• Manifests: [yellow]{', '.join(summary.manifest_files) or 'None'}[/yellow]\n")

    console.print("[bold cyan]Codebase Tree:[/bold cyan]")
    console.print(summary.file_tree)


def handle_plan(request: str, target_dir: Path, model: Optional[str]) -> None:
    """Execute plan command."""
    print_banner()
    console.print(f"[bold cyan]🎯 Feature Request:[/bold cyan] {request}\n")

    analyzer = CodebaseAnalyzer(target_dir)
    summary = analyzer.analyze(request)

    client = GeminiClient(model=model)
    planner = FeaturePlanner(client=client)

    with console.status("[bold cyan]Consulting Gemini to architect implementation plan...[/bold cyan]"):
        plan = planner.create_plan(request, summary)

    print_plan(plan)


def handle_run(args: argparse.Namespace) -> int:
    """Execute full feature development lifecycle using Hub-and-Spoke coordination."""
    print_banner()
    target_dir = Path(args.target_dir).resolve()
    request = args.request

    console.print(f"[bold cyan]🎯 Feature Request:[/bold cyan] {request}")
    console.print(f"[bold cyan]📁 Target Workspace:[/bold cyan] {target_dir}\n")

    client = GeminiClient(model=args.model, offline=args.offline)
    if client.offline:
        console.print("[dim yellow]ℹ️  Running in offline demonstration mode (mock Gemini client).[/dim yellow]\n")
    else:
        console.print(f"[dim green]✓ Connected to Google Gemini ({client.model})[/dim green]\n")

    # Initialize Central Hub (AgentCoordinator)
    coordinator = AgentCoordinator(client=client)

    with console.status("[bold cyan]Coordinating multi-agent workflow (Hub -> Analyzer -> Planner -> Developer -> QA)...[/bold cyan]"):
        state = coordinator.run_workflow(request, target_dir)

    if state.current_stage == "failed":
        console.print("\n[bold red]❌ Multi-agent workflow failed during execution.[/bold red]")
        return 1

    if state.codebase_summary:
        console.print(f"✓ [bold green]Analyzer Spoke[/bold green]: Detected {len(state.codebase_summary.languages)} languages ({', '.join(state.codebase_summary.languages)})")
        if state.codebase_summary.frameworks:
            console.print(f"✓ [bold green]Analyzer Spoke[/bold green]: Detected frameworks: {', '.join(state.codebase_summary.frameworks)}")

    if state.plan:
        print_plan(state.plan)

    console.print(f"\n✓ [bold green]Developer Spoke[/bold green]: Generated {len(state.changes)} proposed file changes and tests.")

    if state.qa_findings:
        console.print("\n[bold cyan]🔍 QA Spoke Review & Quality Gate Findings:[/bold cyan]")
        for f in state.qa_findings:
            console.print(f"  • {f}")

    # Show diff previews
    for c in state.changes:
        if c.diff:
            print_diff(c.file_path, c.diff)

    # Show summary table
    print_summary_table(state.changes, applied=False)

    all_valid = state.qa_passed

    # Safety Gate: Application / Dry Run
    should_apply = False
    if args.dry_run:
        should_apply = False
    elif not all_valid:
        console.print("\n[bold red]🛑 Changes will NOT be applied because QA validation checks failed.[/bold red]")
        should_apply = False
    elif args.apply:
        should_apply = True
    else:
        # Prompt user if interactive
        if args.yes:
            should_apply = True
        else:
            try:
                user_choice = console.input("\n[bold yellow]Apply these changes to your workspace? [y/N]: [/bold yellow]")
                should_apply = user_choice.strip().lower() in ("y", "yes")
            except (KeyboardInterrupt, EOFError):
                should_apply = False

    if should_apply:
        backup_dir = apply_file_changes(target_dir, state.changes, create_backups=True)
        state.applied = True
        if backup_dir:
            console.print(f"\n[bold green]✓ Safety backup created at:[/bold green] [dim]{backup_dir}[/dim]")
        console.print("[bold green]✓ All changes successfully applied to workspace![/bold green]\n")
    else:
        console.print("\n[dim cyan]ℹ️  Changes preserved as dry-run preview. No files were modified on disk.[/dim cyan]\n")

    # Generate PR description
    if state.plan:
        pr_markdown = PRReporter.generate_pr_markdown(request, state.plan, state.changes, applied=should_apply)

        if args.save_pr:
            pr_path = Path(args.save_pr)
            pr_path.write_text(pr_markdown, encoding="utf-8")
            console.print(f"[bold green]✓ Pull Request description saved to:[/bold green] {pr_path}")
        else:
            console.print("[bold cyan]📝 Generated Pull Request Description:[/bold cyan]\n")
            console.print(pr_markdown)

    return 0


def handle_web(port: int = 8080) -> int:
    """Launch FastAPI web server for the interactive visual console and API endpoints."""
    import uvicorn
    import os

    # Respect environment PORT if configured (e.g. Cloud Run)
    effective_port = int(os.getenv("PORT", str(port)))

    print_banner()
    console.print(f"[bold green]🚀 AgentFeat FastAPI Web Server running at:[/bold green] [bold cyan]http://0.0.0.0:{effective_port}[/bold cyan]")
    console.print(f"[dim]Endpoints: GET /api/health | POST /api/workflow/run | GET / (Web Console)[/dim]")
    console.print("[dim]Press Ctrl+C to terminate.[/dim]\n")

    try:
        from agentfeat.web.server import app
        uvicorn.run(app, host="0.0.0.0", port=effective_port, log_level="info")
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down AgentFeat web server...[/yellow]")
    return 0


def main(argv: Optional[list] = None) -> int:
    """Main CLI entrypoint."""
    args = parse_args(argv)

    if args.command == "scan":
        handle_scan(Path(args.target_dir))
        return 0
    elif args.command == "plan":
        handle_plan(args.request, Path(args.target_dir), args.model)
        return 0
    elif args.command == "run":
        return handle_run(args)
    elif args.command == "web":
        return handle_web(args.port)
    else:
        # Default help
        parse_args(["--help"])
        return 0


if __name__ == "__main__":
    sys.exit(main())
