"""Git staged diff reader and commit message generator."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from devguard.runner import execute_command
from devguard.ai_provider import AIProvider
from devguard.redact import redact_secrets


MAX_DIFF_CHARS = 12000

COMMIT_PROMPT_TEMPLATE = """You are a senior developer writing a Git commit message.
Given the following staged git diff, generate {count_instruction}.

Rules:
1. Follow the Conventional Commits format: <type>{scope_format}: <description>
   Allowed types: feat, fix, docs, refactor, test, chore, perf, style, build, ci
2. First line must be 72 characters or fewer, in imperative mood (e.g., "feat: add user authentication").
3. Output ONLY the raw commit message text ({one_per_line_instruction}). Do NOT wrap in markdown code blocks or explanations.

Staged diff:
{diff}
"""


@dataclass(frozen=True)
class CommitMessageResult:
    """The result of generating commit messages."""
    candidates: list[str]
    is_fallback: bool
    source: str
    binary_files_detected: list[str] = field(default_factory=list)


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


def detect_binary_files(diff: str) -> list[str]:
    """Identify binary files mentioned in the diff output."""
    binary_matches = re.findall(r"Binary files (?:a/)?(\S+) and (?:b/)?\S+ differ", diff)
    return binary_matches


def generate_fallback_messages(staged_files: list[str], scope: str | None = None, count: int = 1) -> list[str]:
    """Generate deterministic conventional commit message candidates based on staged filenames.

    Args:
        staged_files: List of staged file paths.
        scope: Optional commit scope.
        count: Number of candidate variations to return.

    Returns:
        List of conventional commit message strings.
    """
    if not staged_files:
        return ["chore: no changes staged"]

    scope_prefix = f"({scope})" if scope else ""
    num_files = len(staged_files)

    candidates: list[str] = []

    # Heuristic 1: Documentation changes
    if all(f.endswith((".md", ".txt", ".rst")) or "doc" in f.lower() for f in staged_files):
        candidates.append(f"docs{scope_prefix}: update documentation ({num_files} file{'s' if num_files > 1 else ''})")
        if count > 1:
            candidates.append(f"docs{scope_prefix}: revise project documentation and guides")

    # Heuristic 2: Test files
    elif all("test" in f.lower() for f in staged_files):
        candidates.append(f"test{scope_prefix}: update test suite ({num_files} file{'s' if num_files > 1 else ''})")
        if count > 1:
            candidates.append(f"test{scope_prefix}: add automated regression tests")

    # Heuristic 3: Configuration files
    elif all(f.endswith((".yaml", ".yml", ".json", ".toml", ".ini", ".cfg")) for f in staged_files):
        candidates.append(f"chore{scope_prefix}: update configuration ({num_files} file{'s' if num_files > 1 else ''})")
        if count > 1:
            candidates.append(f"build{scope_prefix}: update project settings and manifests")

    # Heuristic 4: Single file
    elif num_files == 1:
        single = staged_files[0].split("/")[-1]
        base_name = single.split(".")[0]
        eff_scope = f"({scope or base_name})"
        candidates.append(f"chore{eff_scope}: update {single}")
        if count > 1:
            candidates.append(f"feat{eff_scope}: enhance {single} functionality")
        if count > 2:
            candidates.append(f"refactor{eff_scope}: improve implementation in {single}")

    # Heuristic 5: Multi-file changes
    else:
        candidates.append(f"chore{scope_prefix}: update {num_files} staged files")
        if count > 1:
            candidates.append(f"feat{scope_prefix}: implement changes across {num_files} files")
        if count > 2:
            candidates.append(f"refactor{scope_prefix}: restructure codebase across {num_files} files")

    return candidates[:max(1, count)]


def generate_fallback_message(staged_files: list[str]) -> str:
    """Backward-compatible helper returning a single fallback message."""
    candidates = generate_fallback_messages(staged_files, count=1)
    return candidates[0] if candidates else "chore: no changes staged"


def generate_commit_message_result(
    diff: str,
    provider: AIProvider | None = None,
    staged_files: list[str] | None = None,
    scope: str | None = None,
    candidates_count: int = 1,
    fallback_on_error: bool = True,
    on_error: Any | None = None,
) -> CommitMessageResult:
    """Generate commit message candidates with secret redaction and graceful fallback.

    Args:
        diff: Staged git diff string.
        provider: AIProvider instance.
        staged_files: Staged files list.
        scope: Optional scope string.
        candidates_count: Number of candidates to generate.
        fallback_on_error: If True, falls back to deterministic generator.
        on_error: Error callback.

    Returns:
        CommitMessageResult containing candidates, fallback status, and detected binary files.
    """
    if not diff.strip():
        return CommitMessageResult(candidates=[], is_fallback=False, source="none")

    binary_files = detect_binary_files(diff)

    # CRITICAL SECURITY STEP: Redact secrets before sending to AI provider
    safe_diff = redact_secrets(diff)

    # Truncate large diffs to avoid token overflows
    if len(safe_diff) > MAX_DIFF_CHARS:
        safe_diff = safe_diff[:MAX_DIFF_CHARS] + "\n\n... [staged diff truncated for length] ..."

    if provider is not None:
        try:
            scope_format = f"({scope})" if scope else "(<optional scope>)"
            if candidates_count > 1:
                count_instruction = f"exactly {candidates_count} diverse candidate commit messages"
                one_per_line_instruction = "one single-line message per line, no numbering"
            else:
                count_instruction = "a concise conventional commit message"
                one_per_line_instruction = "one single line"

            prompt = COMMIT_PROMPT_TEMPLATE.format(
                diff=safe_diff,
                scope_format=scope_format,
                count_instruction=count_instruction,
                one_per_line_instruction=one_per_line_instruction,
            )

            raw_resp = provider.generate(prompt).strip()
            # Clean markdown code blocks
            clean_resp = re.sub(r"^```[a-zA-Z]*\n?", "", raw_resp)
            clean_resp = re.sub(r"\n?```$", "", clean_resp).strip()

            lines = [
                re.sub(r"^\d+\.\s*", "", line).strip()
                for line in clean_resp.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]

            if lines:
                return CommitMessageResult(
                    candidates=lines[:candidates_count],
                    is_fallback=False,
                    source=getattr(provider, "name", "ai"),
                    binary_files_detected=binary_files,
                )
        except Exception as exc:
            if on_error is not None:
                try:
                    on_error(exc)
                except Exception:
                    pass
            if not fallback_on_error:
                raise

    # Deterministic fallback
    files = staged_files if staged_files is not None else get_staged_stats()
    fallback_msgs = generate_fallback_messages(files, scope=scope, count=candidates_count)
    return CommitMessageResult(
        candidates=fallback_msgs,
        is_fallback=True,
        source="deterministic-fallback",
        binary_files_detected=binary_files,
    )


def generate_commit_message(
    diff: str,
    provider: AIProvider | None = None,
    staged_files: list[str] | None = None,
    fallback_on_error: bool = True,
    on_error: Any | None = None,
) -> str:
    """Backward-compatible single-message generator."""
    res = generate_commit_message_result(
        diff=diff,
        provider=provider,
        staged_files=staged_files,
        fallback_on_error=fallback_on_error,
        on_error=on_error,
    )
    return res.candidates[0] if res.candidates else ""
