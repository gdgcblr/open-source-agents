"""`prcheck` command line. Kept thin: all logic lives in runner/checks/ai."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer
from rich.console import Console

from . import __version__, report as report_view
from .registry import all_checks
from .runner import run

EXIT_READY = 0
EXIT_NOT_READY = 1
EXIT_USAGE = 2
EXIT_BUG = 3

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Check an open-source-ai contribution before opening a pull request.")


_AI_ENV_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "MODEL_NAME")


def _load_dotenv() -> list[str]:
    """Load .env files without overriding the real environment. Returns notes about values that were
    ignored because the environment already sets something different (the key itself is never shown)."""
    try:
        from dotenv import dotenv_values, find_dotenv, load_dotenv
    except ImportError:
        return []
    notes = []
    for path in (find_dotenv(usecwd=True), str(Path(__file__).resolve().parent.parent / ".env")):
        if not path or not Path(path).is_file():
            continue
        for name, value in dotenv_values(path).items():
            current = os.environ.get(name)
            if name in _AI_ENV_VARS and value and current and current != value:
                notes.append(f"{name} in {path} was ignored: the environment already sets a different value, "
                             f"which takes precedence. To use the .env value, clear it first "
                             f"(PowerShell: Remove-Item Env:{name}; bash: unset {name}).")
        load_dotenv(path, override=False)
    return list(dict.fromkeys(notes))


@app.command()
def check(
    path: Path = typer.Argument(..., help="Project folder, e.g. tools/my-tool"),
    ai: bool = typer.Option(False, "--ai", help="Also get Gemini feedback on the README (needs GEMINI_API_KEY)."),
    base: str = typer.Option(None, "--base", help="Branch to compare against for scope checks [default: upstream/main]."),
    strict: bool = typer.Option(False, "--strict", help="Treat warnings as blocking."),
    json_out: bool = typer.Option(False, "--json", help="Print the report as JSON."),
    no_git: bool = typer.Option(False, "--no-git", help="Don't use git (lists files from disk, skips scope checks)."),
    model: str = typer.Option(None, "--model", help="Gemini model id [default: MODEL_NAME or gemini-3.6-flash]."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="List passing checks individually."),
) -> None:
    """Run every check on PATH. Exit code 0 = ready, 1 = not ready, 2 = usage error, 3 = prcheck bug."""
    console = Console(stderr=json_out)
    if not path.is_dir():
        console.print(f"[red]Not a folder:[/red] {path}")
        raise typer.Exit(EXIT_USAGE)

    result, ctx = run(path, base=base, strict=strict, use_git=not no_git)

    if ai:
        from .ai import review_readme
        from .ai.providers import GeminiProvider, ProviderUnavailable
        from .models import AIResult

        env_notes = _load_dotenv()
        try:
            provider = GeminiProvider(model=model)
        except ProviderUnavailable as exc:
            result.ai = AIResult(status="skipped", provider="gemini", message=str(exc))
        else:
            result.ai = review_readme(ctx, result, provider)
        result.ai.notes = env_notes + result.ai.notes

    if json_out:
        sys.stdout.write(report_view.to_json(result) + "\n")
    else:
        report_view.render(result, console, verbose=verbose)

    if result.summary.crashed:
        raise typer.Exit(EXIT_BUG)
    raise typer.Exit(EXIT_READY if result.summary.ready else EXIT_NOT_READY)


@app.command()
def rules() -> None:
    """List every check, its default severity, and the rule it comes from."""
    console = Console()
    group = None
    for spec in all_checks():
        if spec.group != group:
            group = spec.group
            console.print(f"\n[bold]{group}[/bold]")
        console.print(f"  {spec.id:<3} \\[{spec.severity.value:<5}] {spec.title}  [dim]{spec.rule}[/dim]")


@app.command()
def version() -> None:
    """Print the prcheck version."""
    print(__version__)


if __name__ == "__main__":
    app()
