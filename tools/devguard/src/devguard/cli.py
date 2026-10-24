"""Command-line interface for DevGuard."""

from __future__ import annotations

import sys
from pathlib import Path
import click

from devguard import __version__
from devguard.config import ConfigError, load_config
from devguard.policy import Decision, evaluate_command
from devguard.runner import execute_command
from devguard.audit import record_audit, get_audit_history
from devguard.presets import list_presets, get_preset, PRESETS
from devguard.diagnose import diagnose_failure
from devguard.pr_description import generate_pr_description
import json
import os
import time
from devguard.commit_message import (
    get_staged_diff,
    get_staged_stats,
    generate_commit_message,
    generate_commit_message_result,
    generate_fallback_message,
)
from devguard.ai_provider import create_provider


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
    "-p", "--preset",
    default=None,
    type=click.Choice(["conservative", "development", "custom"], case_sensitive=False),
    help="Initialize configuration using a pre-configured policy preset.",
)
@click.option(
    "-f", "--force",
    is_flag=True,
    help="Overwrite existing configuration file if present.",
)
def init_cmd(config: str, preset: str | None, force: bool):
    """Initialize a sample DevGuard configuration file."""
    config_path = Path(config)
    if config_path.exists() and not force:
        click.secho(
            f"Configuration file '{config_path}' already exists. Use --force to overwrite.",
            fg="yellow",
        )
        return

    if preset:
        content = (
            f"# DevGuard Policy Configuration\n"
            f"# Initialized from preset: {preset}\n"
            f"preset: {preset}\n\n"
            f"# Custom overrides (optional):\n"
            f"allow:\n"
            f"  # - [\"my-tool\", \"status\"]\n\n"
            f"ask:\n"
            f"  # - [\"my-tool\", \"deploy\"]\n\n"
            f"deny:\n"
            f"  # - [\"my-tool\", \"destroy\"]\n"
        )
    else:
        content = SAMPLE_CONFIG_TEMPLATE

    try:
        config_path.write_text(content, encoding="utf-8")
        preset_msg = f" (using preset '{preset}')" if preset else ""
        click.secho(f"✓ Initialized DevGuard configuration{preset_msg} at '{config_path}'.", fg="green")
    except OSError as exc:
        click.secho(f"Error creating configuration file: {exc}", fg="red", err=True)
        sys.exit(1)


@main.group("preset")
def preset_group():
    """Inspect and manage reusable DevGuard policy presets."""
    pass


@preset_group.command("list")
def preset_list_cmd():
    """List all available policy presets."""
    presets = list_presets()
    click.echo("\n" + "=" * 80)
    click.secho("Available DevGuard Policy Presets", bold=True, fg="cyan")
    click.echo("=" * 80)
    for p in presets:
        click.secho(f"\n• {p.name.upper()}", bold=True, fg="green")
        click.echo(f"  Description: {p.description}")
        click.echo(f"  Trade-offs:  {p.risks_and_tradeoffs}")
        click.echo(f"  Default:     {p.config.default_policy.upper()}")
        click.echo(f"  Allow rules: {len(p.config.allow_rules)} rules | Deny rules: {len(p.config.deny_rules)} rules")
    click.echo("\n" + "=" * 80)
    click.secho("To use a preset: devguard init --preset <name>  OR  set 'preset: <name>' in devguard.yaml\n", fg="cyan")


@preset_group.command("show")
@click.argument("name")
def preset_show_cmd(name: str):
    """Show detailed configuration and rules for a named preset."""
    try:
        cfg = get_preset(name)
    except ValueError as exc:
        click.secho(f"Error: {exc}", fg="red", err=True)
        sys.exit(1)

    meta = PRESETS[name.lower()]
    click.echo("\n" + "=" * 70)
    click.secho(f"Preset Details: {name.upper()}", bold=True, fg="cyan")
    click.echo("=" * 70)
    click.echo(f"Description:     {meta.description}")
    click.echo(f"Trade-offs:      {meta.risks_and_tradeoffs}")
    click.echo(f"Default Policy:  {cfg.default_policy.upper()}")

    click.echo("\nALLOW Rules:")
    if cfg.allow_rules:
        for r in cfg.allow_rules:
            click.echo(f"  + [{' '.join(r)}]")
    else:
        click.echo("  (none)")

    click.echo("\nASK Rules:")
    if cfg.ask_rules:
        for r in cfg.ask_rules:
            click.echo(f"  ? [{' '.join(r)}]")
    else:
        click.echo("  (none)")

    click.echo("\nDENY Rules (Authoritative):")
    for r in cfg.deny_rules:
        click.echo(f"  - [{' '.join(r)}]")
    click.echo("=" * 70 + "\n")


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
@click.option(
    "--non-interactive",
    is_flag=True,
    help="Force non-interactive execution; commands requiring approval will fail safely.",
)
@click.pass_context
def run_cmd(ctx: click.Context, config: str, non_interactive: bool):
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
    is_non_interactive = (
        non_interactive
        or not sys.stdin.isatty()
        or os.getenv("CI") == "true"
        or os.getenv("DEVGUARD_NON_INTERACTIVE") == "1"
    )

    approval_status = "not_required"

    if res.decision == Decision.DENY:
        click.secho(f"✖ [DENIED] {cmd_str}", fg="red", bold=True)
        click.secho(f"  Reason: {res.reason}", fg="red")
        record_audit(
            command=command_args,
            executable=res.effective_executable,
            decision=res.decision.value,
            approval_status="not_required",
            matched_rule=res.matched_rule,
            exit_code=1,
        )
        sys.exit(1)

    elif res.decision == Decision.ASK:
        click.secho("? [CONFIRMATION REQUIRED]", fg="yellow", bold=True)
        click.echo(f"  Executable:   {res.effective_executable} ({res.resolved_path or 'path not found'})")
        click.echo(f"  Arguments:    {command_args[1:]}")
        click.echo(f"  Matched Rule: {'[' + ' '.join(res.matched_rule) + ']' if res.matched_rule else 'None'}")
        click.secho(f"  Reason:       {res.reason}", fg="yellow")

        is_non_interactive = (
            non_interactive
            or os.getenv("CI") == "true"
            or os.getenv("DEVGUARD_NON_INTERACTIVE") == "1"
        )

        if is_non_interactive:
            click.secho(
                "✖ [REFUSED] Command requires user approval but environment is non-interactive.",
                fg="red",
                bold=True,
                err=True,
            )
            record_audit(
                command=command_args,
                executable=res.effective_executable,
                decision=res.decision.value,
                approval_status="non_interactive_blocked",
                matched_rule=res.matched_rule,
                exit_code=1,
            )
            sys.exit(1)

        try:
            confirmed = click.confirm("Do you want to execute this command?", default=False)
        except (click.exceptions.Abort, EOFError, OSError):
            click.secho(
                "✖ [REFUSED] Command requires user approval but environment is non-interactive.",
                fg="red",
                bold=True,
                err=True,
            )
            record_audit(
                command=command_args,
                executable=res.effective_executable,
                decision=res.decision.value,
                approval_status="non_interactive_blocked",
                matched_rule=res.matched_rule,
                exit_code=1,
            )
            sys.exit(1)

        if not confirmed:
            click.secho("Execution cancelled by user.", fg="yellow")
            record_audit(
                command=command_args,
                executable=res.effective_executable,
                decision=res.decision.value,
                approval_status="rejected",
                matched_rule=res.matched_rule,
                exit_code=1,
            )
            sys.exit(1)
        approval_status = "approved"

    elif res.decision == Decision.ALLOW:
        click.secho(f"✓ [ALLOWED] {cmd_str}", fg="green")
        click.secho(f"  Reason: {res.reason}", fg="cyan")

    # Execute the command
    t0 = time.perf_counter()
    result = execute_command(command_args)
    duration_ms = (time.perf_counter() - t0) * 1000

    combined_output = (result.stdout or "") + (result.stderr or "")
    record_audit(
        command=command_args,
        executable=res.effective_executable,
        decision=res.decision.value,
        approval_status=approval_status,
        matched_rule=res.matched_rule,
        exit_code=result.exit_code,
        duration_ms=duration_ms,
        raw_output=combined_output,
    )

    if result.stdout:
        click.echo(result.stdout, nl=False)
    if result.stderr:
        click.echo(result.stderr, nl=False, err=True)

    sys.exit(result.exit_code)


@main.command(
    "diagnose",
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
@click.option(
    "--fallback",
    is_flag=True,
    help="Force deterministic diagnostic analysis without AI calls.",
)
@click.option(
    "-m", "--model",
    default=None,
    help="Model identifier for AI diagnostics (provider-specific).",
)
@click.option(
    "-p", "--provider",
    default=None,
    type=click.Choice(["gemini", "ollama"], case_sensitive=False),
    help="AI provider to use: 'gemini' or 'ollama' (default: auto-detect from env).",
)
@click.option(
    "--timeout",
    default=120,
    type=int,
    show_default=True,
    help="Execution timeout limit in seconds.",
)
@click.pass_context
def diagnose_cmd(ctx: click.Context, config: str, fallback: bool, model: str | None, provider: str | None, timeout: int):
    """Execute a command under policy supervision and diagnose failures.

    Usage: devguard diagnose -- <COMMAND> [ARGS...]
    """
    command_args = ctx.args
    if not command_args:
        click.secho(
            "Error: No command specified for diagnosis. Usage: devguard diagnose -- <COMMAND> [ARGS...]",
            fg="red",
            err=True,
        )
        sys.exit(1)

    try:
        policy_cfg = load_config(config)
    except ConfigError as exc:
        click.secho(f"Configuration error: {exc}", fg="red", err=True)
        sys.exit(1)

    # 1. CRITICAL: Evaluate policy FIRST. Never bypass authorization.
    res = evaluate_command(command_args, policy_cfg)
    cmd_str = " ".join(command_args)

    if res.decision == Decision.DENY:
        click.secho(f"✖ [DENIED] Cannot diagnose denied command: {cmd_str}", fg="red", bold=True)
        click.secho(f"  Reason: {res.reason}", fg="red")
        record_audit(
            command=command_args,
            executable=res.effective_executable,
            decision=res.decision.value,
            approval_status="not_required",
            matched_rule=res.matched_rule,
            exit_code=1,
        )
        sys.exit(1)

    approval_status = "not_required"
    if res.decision == Decision.ASK:
        click.secho("? [CONFIRMATION REQUIRED]", fg="yellow", bold=True)
        click.echo(f"  Executable:   {res.effective_executable}")
        click.echo(f"  Arguments:    {command_args[1:]}")
        click.secho(f"  Reason:       {res.reason}", fg="yellow")

        is_non_interactive = not sys.stdin.isatty() or os.getenv("CI") == "true" or os.getenv("DEVGUARD_NON_INTERACTIVE") == "1"
        if is_non_interactive:
            click.secho("✖ [REFUSED] Command requires user approval but environment is non-interactive.", fg="red", bold=True, err=True)
            record_audit(
                command=command_args,
                executable=res.effective_executable,
                decision=res.decision.value,
                approval_status="non_interactive_blocked",
                matched_rule=res.matched_rule,
                exit_code=1,
            )
            sys.exit(1)

        try:
            confirmed = click.confirm("Do you want to execute this command for diagnosis?", default=False)
        except (click.exceptions.Abort, EOFError, OSError):
            confirmed = False

        if not confirmed:
            click.secho("Execution cancelled by user.", fg="yellow")
            record_audit(
                command=command_args,
                executable=res.effective_executable,
                decision=res.decision.value,
                approval_status="rejected",
                matched_rule=res.matched_rule,
                exit_code=1,
            )
            sys.exit(1)
        approval_status = "approved"

    click.secho(f"▶ Running under DevGuard supervision: {cmd_str}", fg="cyan")
    t0 = time.perf_counter()
    result = execute_command(command_args, timeout=timeout)
    duration_ms = (time.perf_counter() - t0) * 1000

    combined_output = (result.stdout or "") + (result.stderr or "")
    record_audit(
        command=command_args,
        executable=res.effective_executable,
        decision=res.decision.value,
        approval_status=approval_status,
        matched_rule=res.matched_rule,
        exit_code=result.exit_code,
        duration_ms=duration_ms,
        raw_output=combined_output,
    )

    if result.exit_code == 0:
        if result.stdout:
            click.echo(result.stdout, nl=False)
        click.secho(f"\n✓ Command succeeded in {duration_ms / 1000:.2f}s. No failure to diagnose.", fg="green", bold=True)
        sys.exit(0)

    # Command failed -> perform diagnosis
    timed_out = (result.exit_code == 124)
    ai_provider = None
    if not fallback:
        try:
            ai_provider = create_provider(provider_name=provider, model=model)
        except Exception:
            ai_provider = None

    report = diagnose_failure(
        command=command_args,
        result=result,
        duration_ms=duration_ms,
        timed_out=timed_out,
        provider=ai_provider,
    )

    click.echo("\n" + "=" * 70)
    click.secho(f"DevGuard Failure Diagnosis [{report.source.upper()}]", bold=True, fg="red")
    click.echo("=" * 70)
    click.echo(f"Command:    {' '.join(command_args)}")
    click.echo(f"Exit Code:  {report.exit_code}")
    click.echo(f"Duration:   {report.duration_ms / 1000:.2f}s (Timed out: {report.timed_out})")

    click.secho("\n[Observed Evidence]", bold=True, fg="yellow")
    if report.observed_errors:
        for err_line in report.observed_errors:
            click.echo(f"  • {err_line}")
    else:
        click.echo("  (no explicit exception messages caught)")

    if report.traceback_locations:
        click.secho("\n[Relevant Locations]", bold=True, fg="yellow")
        for loc in report.traceback_locations:
            click.echo(f"  ➜ {loc}")

    click.secho("\n[Likely Causes (Hypotheses)]", bold=True, fg="cyan")
    for cause in report.likely_causes:
        click.echo(f"  ? {cause}")

    click.secho("\n[Suggested Diagnostic Steps]", bold=True, fg="cyan")
    for step in report.suggested_diagnostic_steps:
        click.echo(f"  ▶ {step}")

    click.secho("\n[Potential Fixes (Unverified)]", bold=True, fg="cyan")
    for fix in report.potential_fixes:
        click.echo(f"  ✔ {fix}")

    click.echo("\n" + "-" * 70)
    click.secho(report.disclaimer, fg="yellow")
    click.echo("=" * 70 + "\n")

    sys.exit(result.exit_code)


@main.command("history")
@click.option("-n", "--limit", default=20, show_default=True, help="Number of records to show.")
@click.option("--json", "as_json", is_flag=True, help="Output records as raw JSON.")
def history_cmd(limit: int, as_json: bool):
    """View recent DevGuard command execution history and audit records."""
    records = get_audit_history(limit=limit)
    if not records:
        click.secho("No execution history recorded yet.", fg="yellow")
        return

    if as_json:
        click.echo(json.dumps(records, indent=2))
        return

    click.echo("\n" + "=" * 80)
    click.secho(f"DevGuard Execution History (Last {len(records)} records)", bold=True, fg="cyan")
    click.echo("=" * 80)
    click.echo(f"{'TIMESTAMP':<24} {'DECISION':<8} {'STATUS':<14} {'EXIT':<6} {'COMMAND'}")
    click.echo("-" * 80)
    for rec in records:
        ts = rec.get("timestamp", "")[:19].replace("T", " ")
        dec = rec.get("decision", "")
        status = rec.get("approval_status", "")
        exit_c = str(rec.get("exit_code", "-"))
        cmd_str = " ".join(rec.get("command", []))
        if len(cmd_str) > 36:
            cmd_str = cmd_str[:33] + "..."
        click.echo(f"{ts:<24} {dec:<8} {status:<14} {exit_c:<6} {cmd_str}")
    click.echo("=" * 80 + "\n")


@main.group("policy")
def policy_group():
    """Inspect and explain DevGuard command execution policies."""
    pass


@policy_group.command(
    "explain",
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
def policy_explain_cmd(ctx: click.Context, config: str):
    """Explain how DevGuard policy evaluates a command.

    Usage: devguard policy explain -- <COMMAND> [ARGS...]
    """
    command_args = ctx.args
    if not command_args:
        click.secho(
            "Error: No command specified to explain. Usage: devguard policy explain -- <COMMAND> [ARGS...]",
            fg="red",
            err=True,
        )
        sys.exit(1)

    try:
        policy_cfg = load_config(config)
    except ConfigError as exc:
        click.secho(f"Configuration error: {exc}", fg="red", err=True)
        sys.exit(1)

    res = evaluate_command(command_args, policy_cfg)

    click.echo("\n" + "=" * 60)
    click.secho("DevGuard Policy Explanation", bold=True, fg="cyan")
    click.echo("=" * 60)
    click.echo(f"Command:        {' '.join(command_args)}")
    click.echo(f"Executable:     {res.effective_executable} (resolved: {res.resolved_path or 'not found on PATH'})")

    if res.decision == Decision.ALLOW:
        decision_color = "green"
    elif res.decision == Decision.ASK:
        decision_color = "yellow"
    else:
        decision_color = "red"

    click.secho(f"Decision:       {res.decision.value.upper()}", bold=True, fg=decision_color)
    click.echo(f"Matched Rule:   {'[' + ' '.join(res.matched_rule) + ']' if res.matched_rule else 'None'}")
    click.echo(f"Specificity:    {res.specificity} argument token(s)")
    click.echo(f"Config Source:  {res.config_source}")
    click.echo(f"Reason:         {res.reason}")

    if res.candidates_considered:
        click.echo("-" * 60)
        click.echo("Rules Evaluated:")
        winner_str = " ".join(res.matched_rule) if res.matched_rule else ""
        for rule_str, dec, spec in res.candidates_considered:
            marker = "★ WINNING" if rule_str == winner_str else "  competing"
            click.echo(f"  {marker} [{rule_str}] -> {dec} (specificity {spec})")
    click.echo("=" * 60 + "\n")


@main.command("commit-message")
@click.option(
    "-s", "--scope",
    default=None,
    help="Optional Conventional Commit scope (e.g. 'auth', 'cli', 'docs').",
)
@click.option(
    "-n", "--candidates",
    "candidates_count",
    default=1,
    type=click.IntRange(1, 5),
    show_default=True,
    help="Number of candidate commit messages to generate.",
)
@click.option(
    "--fallback",
    is_flag=True,
    help="Force deterministic conventional commit message generation without AI calls.",
)
@click.option(
    "-m", "--model",
    default=None,
    help="Model identifier (provider-specific; default: gemini-2.5-flash or llama3.2).",
)
@click.option(
    "-p", "--provider",
    default=None,
    type=click.Choice(["gemini", "ollama"], case_sensitive=False),
    help="AI provider to use: 'gemini' or 'ollama' (default: auto-detect from env).",
)
def commit_message_cmd(scope: str | None, candidates_count: int, fallback: bool, model: str | None, provider: str | None):
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

    ai_provider = None
    if not fallback:
        try:
            ai_provider = create_provider(provider_name=provider, model=model)
        except (ValueError, RuntimeError) as exc:
            click.secho(f"Notice: AI provider unavailable ({exc}).", fg="yellow")
            click.secho("Falling back to deterministic commit message generator.\n", fg="cyan")
            ai_provider = None

    staged_files = get_staged_stats()

    def _report_ai_failure(err: Exception) -> None:
        click.secho(f"Notice: AI generation failed ({err}).", fg="yellow")
        click.secho("Falling back to deterministic commit message generator.\n", fg="cyan")

    try:
        res = generate_commit_message_result(
            diff,
            provider=ai_provider,
            staged_files=staged_files,
            scope=scope,
            candidates_count=candidates_count,
            fallback_on_error=True,
            on_error=_report_ai_failure,
        )
    except Exception as exc:
        click.secho(f"Error generating message: {exc}", fg="red", err=True)
        sys.exit(1)

    if res.binary_files_detected:
        click.secho(
            f"Notice: Binary changes detected: {', '.join(res.binary_files_detected)}",
            fg="yellow",
        )

    click.echo("\n" + "=" * 60)
    if res.is_fallback:
        click.secho("Proposed Commit Message [Fallback (Deterministic)]:", bold=True, fg="yellow")
        click.secho("  (Generated via offline heuristic rules, not AI)", fg="cyan")
    else:
        click.secho(f"Proposed Commit Message [AI-Assisted ({res.source})]:", bold=True, fg="green")
    click.echo("=" * 60)

    if len(res.candidates) > 1:
        click.echo("")
        for idx, cand in enumerate(res.candidates, start=1):
            click.secho(f"  Option {idx}: ", bold=True, fg="cyan", nl=False)
            click.echo(cand)
        click.echo("")
    else:
        single_msg = res.candidates[0] if res.candidates else "chore: update staged files"
        click.echo(f"\n{single_msg}\n")

    click.echo("=" * 60)
    click.secho("Copy the message above or run: devguard run -- git commit -m \"...\"", fg="cyan")


@main.command("pr-description")
@click.option(
    "-b", "--base",
    default=None,
    help="Target base branch for comparison (e.g. 'main', 'upstream/main').",
)
@click.option(
    "-o", "--output",
    default=None,
    help="Optional file path to write the generated Pull Request Markdown.",
)
@click.option(
    "--fallback",
    is_flag=True,
    help="Force deterministic PR template generation without AI calls.",
)
@click.option(
    "-m", "--model",
    default=None,
    help="Model identifier (provider-specific; default: gemini-2.5-flash or llama3.2).",
)
@click.option(
    "-p", "--provider",
    default=None,
    type=click.Choice(["gemini", "ollama"], case_sensitive=False),
    help="AI provider to use: 'gemini' or 'ollama' (default: auto-detect from env).",
)
def pr_description_cmd(base: str | None, output: str | None, fallback: bool, model: str | None, provider: str | None):
    """Generate a structured Markdown pull request description from current git state."""
    ai_provider = None
    if not fallback:
        try:
            ai_provider = create_provider(provider_name=provider, model=model)
        except Exception as exc:
            click.secho(f"Notice: AI provider unavailable ({exc}). Using deterministic generator.\n", fg="yellow")
            ai_provider = None

    try:
        res = generate_pr_description(
            base_branch=base,
            provider=ai_provider,
            output_path=output,
        )
    except Exception as exc:
        click.secho(f"Error generating PR description: {exc}", fg="red", err=True)
        sys.exit(1)

    click.echo("\n" + "=" * 80)
    click.secho(f"Pull Request Description [{res.source.upper()}]", bold=True, fg="cyan")
    click.echo(f"Branch: {res.current_branch}  ->  Target: {res.base_branch}")
    click.echo("=" * 80 + "\n")
    click.echo(res.markdown)
    click.echo("\n" + "=" * 80)

    if output:
        click.secho(f"✓ Saved Pull Request description to '{output}'.", fg="green")
    else:
        click.secho("Copy the Markdown above or re-run with '--output <filename>' to save.", fg="cyan")


if __name__ == "__main__":
    main()
