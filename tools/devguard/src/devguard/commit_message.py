"""Git staged diff reader and commit message generator."""

from __future__ import annotations

import re
from typing import Any
from devguard.runner import execute_command
from devguard.ai_provider import AIProvider


MAX_DIFF_CHARS = 12000

COMMIT_PROMPT_TEMPLATE = """You are a senior developer writing a Git commit message.
Given the following staged git diff, generate a concise, conventional commit message.

Rules:
1. Follow the Conventional Commits format: <type>(<optional scope>): <description>
   Allowed types: feat, fix, docs, refactor, test, chore, perf, style, build, ci
2. First line must be 72 characters or fewer, in imperative mood (e.g., "feat: add user authentication").
3. Output ONLY the commit message text. Do NOT wrap in quotes, markdown code blocks, or explanations.

Staged diff:
{diff}
"""


def get_staged_diff() -> str:
    """Read the staged Git diff via `git diff --staged`.

    Returns:
        The staged diff as a string.

    Raises:
        RuntimeError: If Git command fails or git is not in a repository.
    """
    res = execute_command(["git", "diff", "--staged"])
    if res.exit_code != 0:
        raise RuntimeError(f"Failed to read git diff: {res.stderr.strip()}")
    return res.stdout.strip()


def get_staged_stats() -> list[str]:
    """Read names of staged files via `git diff --staged --name-only`."""
    res = execute_command(["git", "diff", "--staged", "--name-only"])
    if res.exit_code != 0 or not res.stdout.strip():
        return []
    return [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]


def generate_fallback_message(staged_files: list[str]) -> str:
    """Generate a deterministic conventional commit message based on staged filenames.

    Args:
        staged_files: List of staged file paths.

    Returns:
        A conventional commit message string.
    """
    if not staged_files:
        return "chore: no changes staged"

    count = len(staged_files)

    # Check common single-type patterns
    if all(f.endswith((".md", ".txt", ".rst")) or "doc" in f.lower() for f in staged_files):
        return f"docs: update documentation ({count} file{'s' if count > 1 else ''})"

    if all("test" in f.lower() for f in staged_files):
        return f"test: update test suite ({count} file{'s' if count > 1 else ''})"

    if all(f.endswith((".yaml", ".yml", ".json", ".toml", ".ini", ".cfg")) for f in staged_files):
        return f"chore: update configuration ({count} file{'s' if count > 1 else ''})"

    # If single file, mention it
    if count == 1:
        single = staged_files[0].split("/")[-1]
        return f"chore: update {single}"

    return f"chore: update {count} staged files"


def generate_commit_message(
    diff: str,
    provider: AIProvider | None = None,
    staged_files: list[str] | None = None,
    fallback_on_error: bool = True,
    on_error: Any | None = None,
) -> str:
    """Generate a commit message using an AI provider with fallback support.

    Args:
        diff: Staged diff content.
        provider: AIProvider instance (e.g. GeminiProvider). If None, uses fallback.
        staged_files: Optional list of staged file paths for fallback heuristics.
        fallback_on_error: If True, falls back to deterministic generator on provider failure.
        on_error: Optional callback invoked with the exception when provider fails.

    Returns:
        Proposed commit message.
    """
    if not diff.strip():
        return ""

    # Truncate large diffs to avoid token overflows
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + "\n\n... [diff truncated for length] ..."

    if provider is not None:
        try:
            prompt = COMMIT_PROMPT_TEMPLATE.format(diff=diff)
            msg = provider.generate(prompt).strip()
            # Clean any markdown code blocks if the model wrapped it
            msg = re.sub(r"^```[a-zA-Z]*\n?", "", msg)
            msg = re.sub(r"\n?```$", "", msg).strip()
            if msg:
                return msg
        except Exception as exc:
            if on_error is not None:
                try:
                    on_error(exc)
                except Exception:
                    pass
            if not fallback_on_error:
                raise
            # Fall back below

    # Deterministic fallback
    files = staged_files if staged_files is not None else get_staged_stats()
    return generate_fallback_message(files)
