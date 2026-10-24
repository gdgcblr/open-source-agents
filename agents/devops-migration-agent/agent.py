"""DevOps Migration Agent — Google ADK Implementation.

Migrates GitHub Actions workflows to Azure DevOps Pipelines using Google ADK,
Gemini 2.5 Flash, and deterministic DevOps static analysis.
Supports offline execution without API credentials.
Never executes scripts contained in workflow files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Import configuration
from config import AgentConfig, get_config

# Import models
from models.migration_report import (
    ActionMappingResult,
    MigrationSummary,
    TerraformAnalysisResult,
    ValidationResult,
)
from models.risk_model import RiskAssessment

# Import tools
from tools.action_mapper import map_action
from tools.ado_generator import ADOGenerator, validate_pipeline_yaml
from tools.github_parser import parse_workflow_file
from tools.report_generator import build_migration_summary, write_all_reports
from tools.risk_assessor import assess_migration_risk
from tools.terraform_validator import analyze_terraform_directory

console = Console()


# ---------------------------------------------------------------------------
# Google ADK Tool Functions
# Each function conforms to Google ADK tool conventions with clear type hints
# and descriptive docstrings for model schema extraction.
# ---------------------------------------------------------------------------


def tool_parse_github_workflow(workflow_path: str) -> dict[str, Any]:
    """Parses a GitHub Actions workflow YAML file into structured data.

    Args:
        workflow_path: Path to the GitHub Actions YAML workflow file.

    Returns:
        Dictionary containing workflow name, triggers, jobs, steps, and secrets.
    """
    workflow = parse_workflow_file(workflow_path)
    return {
        "name": workflow.name,
        "file_path": workflow.file_path,
        "total_jobs": workflow.total_jobs,
        "total_steps": workflow.total_steps,
        "detected_secrets": workflow.detected_secrets,
        "jobs": list(workflow.jobs.keys()),
    }


def tool_map_actions(workflow_path: str) -> list[dict[str, Any]]:
    """Evaluates compatibility and maps GitHub Actions to Azure DevOps tasks.

    Args:
        workflow_path: Path to the GitHub Actions YAML workflow file.

    Returns:
        List of action mappings with status, target tasks, and manual notes.
    """
    workflow = parse_workflow_file(workflow_path)
    mappings: list[dict[str, Any]] = []
    for job in workflow.jobs.values():
        for step in job.steps:
            if step.is_action:
                result = map_action(step)
                mappings.append(
                    {
                        "action_name": result.action_name,
                        "version": result.action_version,
                        "status": result.status.value,
                        "ado_task": result.ado_task,
                        "warnings": result.warnings,
                        "manual_steps": result.manual_steps,
                    }
                )
    return mappings


def tool_validate_terraform(terraform_dir: str) -> dict[str, Any]:
    """Analyzes Terraform configurations for providers, backend, and CI risks.

    Args:
        terraform_dir: Directory containing .tf files.

    Returns:
        Dictionary of discovered providers, backend configuration, and service connection needs.
    """
    result = analyze_terraform_directory(terraform_dir)
    return {
        "has_terraform": result.has_terraform,
        "providers": result.providers,
        "backend_type": result.backend_type,
        "resources_count": result.resources_count,
        "service_connections_needed": result.service_connections_needed,
        "findings": result.findings,
    }


def tool_assess_risk(workflow_path: str, terraform_dir: str = "") -> dict[str, Any]:
    """Calculates deterministic risk score and identifies blockers.

    Args:
        workflow_path: Path to the GitHub Actions workflow file.
        terraform_dir: Optional path to Terraform directory.

    Returns:
        Risk evaluation with numeric score (0-100), rating, and blockers.
    """
    workflow = parse_workflow_file(workflow_path)
    mappings = []
    for job in workflow.jobs.values():
        for step in job.steps:
            if step.is_action:
                mappings.append(map_action(step))

    tf_res = analyze_terraform_directory(terraform_dir) if terraform_dir else None
    content = Path(workflow_path).read_text(encoding="utf-8")
    risk = assess_migration_risk(workflow, mappings, tf_res, content)

    return {
        "score": risk.overall_score,
        "level": risk.overall_level.value,
        "summary": risk.summary,
        "blockers": risk.blockers,
        "risk_items_count": len(risk.items),
    }


# ---------------------------------------------------------------------------
# Google ADK Agent Construction
# ---------------------------------------------------------------------------


def create_adk_agent(config: AgentConfig) -> Any:
    """Builds and returns a Google ADK Agent configured with migration tools.

    Uses official Google ADK Agent API with Gemini 2.5 Flash.
    """
    try:
        from google.adk.agents.llm_agent import Agent

        adk_tools = [
            tool_parse_github_workflow,
            tool_map_actions,
            tool_validate_terraform,
            tool_assess_risk,
        ]

        instruction = (
            "You are the DevOps Migration Agent. Your job is to analyze GitHub Actions workflows, "
            "evaluate action mappings to Azure DevOps tasks, assess migration risks, and provide "
            "clear, production-ready modernization advice."
        )

        agent = Agent(
            model=config.model_name,
            name="devops_migration_agent",
            description="Autonomous CI/CD modernization agent for GitHub Actions to Azure DevOps.",
            instruction=instruction,
            tools=adk_tools,
        )
        return agent
    except ImportError:
        console.print(
            "[yellow]Notice: google-adk package not found. Running with deterministic engine.[/yellow]"
        )
        return None
    except Exception as exc:
        console.print(
            f"[yellow]Notice: Could not initialize Google ADK Agent ({exc}). Falling back to deterministic engine.[/yellow]"
        )
        return None


# ---------------------------------------------------------------------------
# Migration Pipeline Execution
# ---------------------------------------------------------------------------


def run_migration(
    workflow_path: str | Path,
    output_dir: str | Path,
    terraform_dir: str | Path | None = None,
    config: AgentConfig | None = None,
) -> tuple[MigrationSummary, ValidationResult, RiskAssessment, dict[str, Path]]:
    """Executes the full deterministic migration pipeline."""
    _ = config or get_config()
    wf_path = Path(workflow_path)
    out_dir = Path(output_dir)

    raw_content = wf_path.read_text(encoding="utf-8")

    # Step 1: Parse workflow
    workflow = parse_workflow_file(wf_path)

    # Step 2: Map actions
    action_mappings: list[ActionMappingResult] = []
    for job in workflow.jobs.values():
        for step in job.steps:
            if step.is_action:
                action_mappings.append(map_action(step))

    # Step 3: Terraform static analysis
    tf_result: TerraformAnalysisResult | None = None
    if terraform_dir:
        tf_result = analyze_terraform_directory(terraform_dir)

    # Step 4: Generate Azure DevOps Pipeline YAML
    generator = ADOGenerator()
    pipeline_yaml = generator.generate_pipeline(workflow)

    # Step 5: Validate generated YAML
    validation = validate_pipeline_yaml(pipeline_yaml)

    # Step 6: Assess migration risk
    risk = assess_migration_risk(workflow, action_mappings, tf_result, raw_content)

    # Step 7: Build summary & write all deliverables
    summary = build_migration_summary(workflow, action_mappings, risk, tf_result)
    generated_files = write_all_reports(
        output_dir=out_dir,
        workflow=workflow,
        mappings=action_mappings,
        pipeline_yaml=pipeline_yaml,
        validation=validation,
        risk=risk,
        tf_result=tf_result,
    )

    return summary, validation, risk, generated_files


# ---------------------------------------------------------------------------
# CLI Command Entry Point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DevOps Migration Agent: Migrate GitHub Actions to Azure DevOps Pipelines."
    )
    parser.add_argument(
        "--workflow",
        "-w",
        required=True,
        help="Path to GitHub Actions workflow YAML file.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="./migration-output",
        help="Destination directory for generated pipeline and reports.",
    )
    parser.add_argument(
        "--terraform",
        "-t",
        default=None,
        help="Optional directory containing Terraform configurations (*.tf).",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run completely offline without contacting Google AI / Gemini API.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Google Gemini model identifier (default: gemini-2.5-flash).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    overrides: dict[str, Any] = {
        "offline_mode": args.offline,
        "verbose": args.verbose,
    }
    if args.model:
        overrides["model_name"] = args.model
    if args.output:
        overrides["default_output_dir"] = Path(args.output)

    cfg = get_config(**overrides)

    console.print(
        Panel.fit(
            f"[bold cyan]DevOps Migration Agent[/bold cyan]\n"
            f"[dim]Google ADK CI/CD Modernization Engine[/dim]\n"
            f"Model: [green]{cfg.model_name}[/green] | Mode: [yellow]{'OFFLINE' if cfg.is_offline() else 'ONLINE (Gemini)'}[/yellow]",
            border_style="cyan",
        )
    )

    # Initialize Google ADK agent if in online mode
    if not cfg.is_offline():
        adk_agent = create_adk_agent(cfg)
        if adk_agent:
            console.print("[dim]Google ADK Agent initialized successfully.[/dim]")
    else:
        console.print("[dim]Operating in offline deterministic mode.[/dim]")

    wf_file = Path(args.workflow)
    if not wf_file.is_file():
        console.print(f"[bold red]Error:[/bold red] Workflow file not found: {args.workflow}")
        return 1

    with console.status("[bold green]Executing migration analysis...[/bold green]"):
        try:
            summary, validation, risk, out_files = run_migration(
                workflow_path=wf_file,
                output_dir=args.output,
                terraform_dir=args.terraform,
                config=cfg,
            )
        except Exception as exc:
            console.print(f"[bold red]Migration Error:[/bold red] {exc}")
            if cfg.verbose:
                console.print_exception()
            return 1

    # Render results table
    table = Table(title="Migration Analysis Summary", border_style="cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", style="green")

    table.add_row("Workflow Name", summary.workflow_name)
    table.add_row("Total Jobs", str(summary.jobs_count))
    table.add_row("Total Steps", str(summary.steps_count))
    table.add_row("Direct Mappings", f"[green]{summary.direct_mappings_count}[/green]")
    table.add_row("Partial Mappings", f"[yellow]{summary.partial_mappings_count}[/yellow]")
    table.add_row("Manual Migrations", f"[yellow]{summary.manual_mappings_count}[/yellow]")
    table.add_row("Unsupported Actions", f"[red]{summary.unsupported_count}[/red]")
    table.add_row("Secrets Identified", str(summary.secrets_count))
    table.add_row(
        "Risk Score", f"{summary.risk_score}/100 ([bold]{summary.risk_level.value}[/bold])"
    )
    table.add_row(
        "Validation Status", "[green]PASSED[/green]" if validation.is_valid else "[red]FAILED[/red]"
    )
    table.add_row("Estimated Effort", f"{summary.estimated_effort_hours} hrs")

    console.print(table)

    # Display generated files
    console.print("\n[bold green]Successfully generated migration artifacts:[/bold green]")
    for key, path in out_files.items():
        console.print(f"  • [cyan]{path.name}[/cyan] -> {path}")

    if risk.blockers:
        console.print("\n[bold red]Deployment Blockers Detected:[/bold red]")
        for b in risk.blockers:
            console.print(f"  [red]✖[/red] {b}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
