"""Command-line interface for DevGuard."""

from __future__ import annotations

import sys
from pathlib import Path
import click

from devguard import __version__
from devguard.config import ConfigError, load_config
from devguard.policy import Decision, evaluate_command
from devguard.runner import execute_command
from devguard.commit_message import (
    get_staged_diff,
    get_staged_stats,
    generate_commit_message,
    generate_fallback_message,
)
from devguard.ai_provider import GeminiProvider


DEFAULT_CONFIG_NAME = "devguard.yaml"

SAMPLE_CONFIG_TEMPLATE = """# DevGuard Policy Configuration
# -----------------------------------------------------------------------------
# Default decision when no rule matches: 'allow', 'ask', or 'deny' (default: deny)
default_policy: ask

# Commands allowed to run without prompting
allow:
  - ["git", "status"]
  - ["git", "diff"]
  - ["git", "log"]
  - ["python3", "-m", "pytest"]
  - ["echo"]

# Commands requiring explicit user confirmation before running
ask:
  - ["git", "commit"]
  - ["git", "push"]

# Commands that are unconditionally refused
deny:
  - ["git", "reset", "--hard"]
  - ["git", "clean", "-fdx"]
"""


@click.group()
@click.version_option(version=__version__, prog_name="devguard")
def main():
    """DevGuard — A Simple AI Coding Helper CLI.

    Enforce command permissions deterministically and generate conventional commit messages.
    """
    pass


@main.command("init")
@click.option(
    "-c", "--config",
    default=DEFAULT_CONFIG_NAME,
    show_default=True,
    help="Target path for configuration file.",
)
@click.option(
    "-f", "--force",
    is_flag=True,
    help="Overwrite existing configuration file if present.",
)
def init_cmd(config: str, force: bool):
    """Initialize a sample DevGuard configuration file."""
    config_path = Path(config)
    if config_path.exists() and not force:
        click.secho(
            f"Configuration file '{config_path}' already exists. Use --force to overwrite.",
            fg="yellow",
        )
        return

    try:
        config_path.write_text(SAMPLE_CONFIG_TEMPLATE, encoding="utf-8")
        click.secho(f"✓ Initialized DevGuard configuration at '{config_path}'.", fg="green")
    except OSError as exc:
        click.secho(f"Error creating configuration file: {exc}", fg="red", err=True)
        sys.exit(1)


@main.command(
    "run",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
    ),
)
@click.option(
    "-c", "--config",
    default=DEFAULT_CONFIG_NAME,
    show_default=True,
    help="Path to configuration file.",
)
@click.pass_context
def run_cmd(ctx: click.Context, config: str):
    """Run a command under the DevGuard policy manager.

    Usage: devguard run -- <COMMAND> [ARGS...]
    """
    command_args = ctx.args
    if not command_args:
        click.secho("Error: No command specified to run. Usage: devguard run -- <COMMAND> [ARGS...]", fg="red", err=True)
        sys.exit(1)

    # Load configuration
    try:
        policy_cfg = load_config(config)
    except ConfigError as exc:
        click.secho(f"Configuration error: {exc}", fg="red", err=True)
        sys.exit(1)

    # Evaluate command
    res = evaluate_command(command_args, policy_cfg)

    cmd_str = " ".join(command_args)

    if res.decision == Decision.DENY:
        click.secho(f"✖ [DENIED] {cmd_str}", fg="red", bold=True)
        click.secho(f"  Reason: {res.reason}", fg="red")
        sys.exit(1)

    elif res.decision == Decision.ASK:
        click.secho(f"? [CONFIRMATION REQUIRED] {cmd_str}", fg="yellow", bold=True)
        click.secho(f"  Reason: {res.reason}", fg="yellow")
        confirmed = click.confirm("Do you want to execute this command?", default=False)
        if not confirmed:
            click.secho("Execution cancelled by user.", fg="yellow")
            sys.exit(1)

    elif res.decision == Decision.ALLOW:
        click.secho(f"✓ [ALLOWED] {cmd_str}", fg="green")
        click.secho(f"  Reason: {res.reason}", fg="cyan")

    # Execute the command
    result = execute_command(command_args)
    if result.stdout:
        click.echo(result.stdout, nl=False)
    if result.stderr:
        click.echo(result.stderr, nl=False, err=True)

    sys.exit(result.exit_code)


@main.command("commit-message")
@click.option(
    "--fallback",
    is_flag=True,
    help="Force deterministic conventional commit message generation without AI calls.",
)
@click.option(
    "-m", "--model",
    default=None,
    help="Gemini model identifier (default: gemini-2.5-flash).",
)
def commit_message_cmd(fallback: bool, model: str | None):
    """Generate a conventional commit message from staged git changes."""
    # Read staged diff
    try:
        diff = get_staged_diff()
    except RuntimeError as exc:
        click.secho(f"Git error: {exc}", fg="red", err=True)
        sys.exit(1)

    if not diff:
        click.secho("No staged changes found.", fg="yellow")
        click.secho("Hint: Stage files using 'git add <files>' first, then re-run.", fg="cyan")
        sys.exit(0)

    provider = None
    if not fallback:
        try:
            provider = GeminiProvider(model=model)
        except (ValueError, RuntimeError) as exc:
            click.secho(f"Notice: AI provider unavailable ({exc}).", fg="yellow")
            click.secho("Falling back to deterministic commit message generator.\n", fg="cyan")
            provider = None

    staged_files = get_staged_stats()
    def _report_ai_failure(err: Exception) -> None:
        click.secho(f"Notice: AI generation failed ({err}).", fg="yellow")
        click.secho("Falling back to deterministic commit message generator.\n", fg="cyan")

    try:
        message = generate_commit_message(
            diff,
            provider=provider,
            staged_files=staged_files,
            fallback_on_error=True,
            on_error=_report_ai_failure,
        )
    except Exception as exc:
        click.secho(f"Error generating message: {exc}", fg="red", err=True)
        sys.exit(1)

    if not message:
        message = generate_fallback_message(staged_files)

    click.echo("\n" + "=" * 60)
    click.secho("Proposed Commit Message:", bold=True, fg="green")
    click.echo("=" * 60)
    click.echo(f"\n{message}\n")
    click.echo("=" * 60)
    click.secho("Copy the message above or run: git commit -m \"...\"", fg="cyan")


if __name__ == "__main__":
    main()
