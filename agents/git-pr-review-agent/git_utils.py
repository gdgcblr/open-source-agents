"""Git utility functions for extracting diffs, log history, and repo metadata."""

import os
import re
import subprocess
from typing import Dict, Any, List, Tuple, Optional

# Files that should be excluded from LLM context to prevent token bloat
IGNORE_EXTENSIONS = {
    ".lock", ".lockb", ".min.js", ".min.css", ".map", ".png", ".jpg",
    ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot",
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".bin"
}

IGNORE_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "Cargo.lock", "composer.lock", "go.sum", ".DS_Store"
}


def is_git_repo(repo_path: str = ".") -> bool:
    """Check if the directory is inside a valid git repository."""
    try:
        res = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:
        return False


def get_git_diff(
    repo_path: str = ".",
    base_branch: Optional[str] = None,
    staged_only: bool = False,
    unstaged_only: bool = False
) -> Tuple[str, Dict[str, Any]]:
    """
    Extract git diff and file statistics from a local repository.

    Returns:
        (filtered_diff_text, stats_dict)
    """
    if not is_git_repo(repo_path):
        raise ValueError(f"Path '{repo_path}' is not a valid git repository.")

    cmd = ["git", "-C", repo_path, "diff"]

    if staged_only:
        cmd.append("--staged")
    elif unstaged_only:
        pass  # git diff defaults to unstaged
    elif base_branch:
        # Check if base_branch exists locally or on remote
        branch_check = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--verify", base_branch],
            capture_output=True,
            text=True
        )
        if branch_check.returncode == 0:
            cmd.append(f"{base_branch}...HEAD")
        else:
            # Fall back to checking unstaged + staged
            cmd = ["git", "-C", repo_path, "diff", "HEAD"]

    # Execute git diff
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0 and base_branch:
        # Fallback to unstaged + staged diff
        fallback = subprocess.run(["git", "-C", repo_path, "diff", "HEAD"], capture_output=True, text=True)
        raw_diff = fallback.stdout
    else:
        raw_diff = result.stdout

    # Also capture recent commit messages if branch comparison is active
    commit_messages = []
    if base_branch:
        log_res = subprocess.run(
            ["git", "-C", repo_path, "log", f"{base_branch}..HEAD", "--oneline"],
            capture_output=True,
            text=True,
            check=False
        )
        if log_res.returncode == 0 and log_res.stdout.strip():
            commit_messages = log_res.stdout.strip().split("\n")

    filtered_diff, stats = filter_and_calculate_stats(raw_diff)
    stats["commit_messages"] = commit_messages
    return filtered_diff, stats


def filter_and_calculate_stats(raw_diff: str) -> Tuple[str, Dict[str, Any]]:
    """
    Filters out noise (lockfiles, minified assets) and computes additions/deletions.
    """
    file_chunks = split_diff_into_files(raw_diff)
    filtered_chunks: List[str] = []

    files_changed: List[str] = []
    total_additions = 0
    total_deletions = 0

    for file_path, chunk in file_chunks:
        # Check ignore list
        filename = os.path.basename(file_path)
        _, ext = os.path.splitext(filename)

        if filename in IGNORE_FILENAMES or ext.lower() in IGNORE_EXTENSIONS:
            continue

        filtered_chunks.append(chunk)
        files_changed.append(file_path)

        # Count +/- lines
        for line in chunk.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                total_additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                total_deletions += 1

    stats = {
        "files_changed_count": len(files_changed),
        "files_changed": files_changed,
        "additions": total_additions,
        "deletions": total_deletions,
        "raw_diff_lines": len(raw_diff.split("\n")) if raw_diff else 0
    }

    return "\n".join(filtered_chunks), stats


def split_diff_into_files(diff_text: str) -> List[Tuple[str, str]]:
    """
    Splits a git diff string into a list of (file_path, chunk_text) tuples.
    """
    if not diff_text or not diff_text.strip():
        return []

    lines = diff_text.split("\n")
    chunks: List[Tuple[str, str]] = []
    current_file = "unknown"
    current_lines: List[str] = []

    for line in lines:
        if line.startswith("diff --git "):
            if current_lines:
                chunks.append((current_file, "\n".join(current_lines)))
                current_lines = []
            # Extract target path
            match = re.search(r"diff --git a/.*? b/(.*)$", line)
            current_file = match.group(1) if match else "unknown"

        current_lines.append(line)

    if current_lines:
        chunks.append((current_file, "\n".join(current_lines)))

    return chunks
