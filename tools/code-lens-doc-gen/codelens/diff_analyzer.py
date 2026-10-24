"""
Git Diff Analyzer — Detects code changes between commits.

Uses git subprocess calls (no external git library dependency) to:
- Get the list of changed files between two refs
- Classify changes as Added, Modified, Deleted, or Renamed
- Extract the actual diff content for changed files

This module is used by the 'update' command to figure out
which documentation sections need to be refreshed.
"""

import subprocess
from pathlib import Path

from rich.console import Console

console = Console()


def get_changed_files(
    repo_path: str,
    base_ref: str = "HEAD~1",
    head_ref: str = "HEAD",
) -> list[dict]:
    """
    Get the list of files changed between two git refs.

    Args:
        repo_path: Path to the git repository root.
        base_ref: The base git ref (e.g., "HEAD~1", a commit SHA, a branch name).
        head_ref: The head git ref (default: "HEAD").

    Returns:
        A list of dicts, each containing:
        {
            "status": str ("added"|"modified"|"deleted"|"renamed"),
            "path": str (relative file path),
            "old_path": str | None (only for renames),
        }
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", base_ref, head_ref],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        console.print("[red]Error:[/red] 'git' command not found. Make sure git is installed and in your PATH.")
        return []
    except subprocess.TimeoutExpired:
        console.print("[red]Error:[/red] git diff command timed out.")
        return []

    if result.returncode != 0:
        error_msg = result.stderr.strip()
        console.print(f"[red]Error running git diff:[/red] {error_msg}")
        return []

    changes = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue

        parts = line.split("\t")
        status_code = parts[0].strip()

        if status_code == "A":
            changes.append({
                "status": "added",
                "path": parts[1].replace("\\", "/"),
                "old_path": None,
            })
        elif status_code == "M":
            changes.append({
                "status": "modified",
                "path": parts[1].replace("\\", "/"),
                "old_path": None,
            })
        elif status_code == "D":
            changes.append({
                "status": "deleted",
                "path": parts[1].replace("\\", "/"),
                "old_path": None,
            })
        elif status_code.startswith("R"):
            changes.append({
                "status": "renamed",
                "path": parts[2].replace("\\", "/") if len(parts) > 2 else parts[1].replace("\\", "/"),
                "old_path": parts[1].replace("\\", "/"),
            })

    return changes


def get_diff_content(
    repo_path: str,
    file_path: str,
    base_ref: str = "HEAD~1",
    head_ref: str = "HEAD",
) -> str | None:
    """
    Get the actual diff content for a specific file.

    Args:
        repo_path: Path to the git repository root.
        file_path: Relative path to the file within the repo.
        base_ref: The base git ref.
        head_ref: The head git ref.

    Returns:
        The diff output as a string, or None on error.
    """
    try:
        result = subprocess.run(
            ["git", "diff", base_ref, head_ref, "--", file_path],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    return result.stdout


def get_current_commit_sha(repo_path: str) -> str | None:
    """Get the current HEAD commit SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def is_git_repo(path: str) -> bool:
    """Check if the given path is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
