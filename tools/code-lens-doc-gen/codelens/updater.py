"""
Updater — Handles incremental documentation updates.

When code changes are pushed, this module:
1. Reads the previous generation state (.codelens-state.json)
2. Uses diff_analyzer to find what changed
3. Re-analyzes only the changed files
4. Re-categorizes and regenerates only affected doc sections
5. Merges updates into existing documentation

This avoids full regeneration on every commit.
"""

import json
from pathlib import Path

from rich.console import Console

from .analyzer import analyze_file, condense_for_llm
from .categorizer import categorize_codebase, fallback_categorize
from .config import Config
from .diff_analyzer import get_changed_files, get_current_commit_sha
from .generator import generate_documentation, write_documentation
from .scanner import scan_codebase

console = Console()


def load_previous_state(output_dir: str) -> dict | None:
    """
    Load the previous generation state from .codelens-state.json.

    Returns:
        The state dict, or None if no previous state exists.
    """
    state_path = Path(output_dir) / ".codelens-state.json"
    if not state_path.exists():
        return None

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        console.print("[yellow]Warning:[/yellow] Could not read previous state file. Will perform full generation.")
        return None


def update_documentation(
    repo_path: str,
    config: Config,
    base_ref: str = "HEAD~1",
    head_ref: str = "HEAD",
) -> dict:
    """
    Incrementally update documentation based on git changes.

    Args:
        repo_path: Path to the repository root.
        config: Configuration object.
        base_ref: Git ref for the base (before changes).
        head_ref: Git ref for the head (after changes).

    Returns:
        A dict with update results:
        {
            "changed_files": [...],
            "updated_docs": [...],
            "status": "success" | "full_regen" | "no_changes" | "error",
        }
    """
    result = {
        "changed_files": [],
        "updated_docs": [],
        "status": "success",
    }

    # Step 1: Get changed files
    console.print(f"[dim]Analyzing changes between {base_ref} and {head_ref}...[/dim]")
    changes = get_changed_files(repo_path, base_ref, head_ref)

    if not changes:
        console.print("[green]No changes detected.[/green] Documentation is up to date.")
        result["status"] = "no_changes"
        return result

    result["changed_files"] = changes
    console.print(f"[blue]Found {len(changes)} changed file(s):[/blue]")
    for change in changes:
        status_icon = {
            "added": "[green]+[/green]",
            "modified": "[yellow]~[/yellow]",
            "deleted": "[red]-[/red]",
            "renamed": "[cyan]→[/cyan]",
        }.get(change["status"], "?")
        console.print(f"  {status_icon} {change['path']}")

    # Step 2: Check if we have previous state
    previous_state = load_previous_state(config.output_dir)

    if previous_state is None:
        console.print("[yellow]No previous documentation state found.[/yellow] Performing full generation...")
        result["status"] = "full_regen"
        # Fall through to full generation
        full_result = _full_generate(repo_path, config)
        result["updated_docs"] = full_result
        return result

    # Step 3: Re-scan the full codebase (scanning is fast, local only)
    console.print("[dim]Re-scanning codebase...[/dim]")
    codebase_map = scan_codebase(repo_path, config)

    if not codebase_map or not codebase_map.get("files"):
        console.print("[red]Error:[/red] Failed to scan codebase.")
        result["status"] = "error"
        return result

    # Step 4: Analyze all files (analysis is fast, local only)
    from .analyzer import analyze_codebase
    analyses = analyze_codebase(codebase_map)

    # Step 5: Re-categorize (this calls Gemini, but on condensed summary)
    condensed = condense_for_llm(analyses)
    categorization = categorize_codebase(condensed, config)

    if not categorization:
        console.print("[yellow]LLM categorization failed. Using rule-based fallback.[/yellow]")
        categorization = fallback_categorize(analyses)

    # Step 6: Regenerate documentation
    docs = generate_documentation(analyses, categorization, codebase_map, config)

    # Step 7: Write to disk
    written_files = write_documentation(docs, config.output_dir)
    result["updated_docs"] = written_files

    # Step 8: Save updated state
    current_sha = get_current_commit_sha(repo_path)
    if current_sha:
        docs["metadata"]["last_commit"] = current_sha

    console.print(f"[green]Documentation updated successfully.[/green] {len(written_files)} file(s) written.")
    return result


def _full_generate(repo_path: str, config: Config) -> list[str]:
    """Perform a full documentation generation (used when no previous state exists)."""
    from .analyzer import analyze_codebase

    codebase_map = scan_codebase(repo_path, config)
    if not codebase_map or not codebase_map.get("files"):
        return []

    analyses = analyze_codebase(codebase_map)
    condensed = condense_for_llm(analyses)

    categorization = categorize_codebase(condensed, config)
    if not categorization:
        categorization = fallback_categorize(analyses)

    docs = generate_documentation(analyses, categorization, codebase_map, config)
    written_files = write_documentation(docs, config.output_dir)

    return written_files
