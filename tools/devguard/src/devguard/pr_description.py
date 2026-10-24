"""Pull request description generator for DevGuard.

Collects git branch context, commits, and diffs, redacts sensitive tokens,
and produces a structured Markdown pull request description distinguishing
verified test executions from suggested test plans.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from devguard.ai_provider import AIProvider
from devguard.audit import get_audit_history
from devguard.redact import redact_secrets
from devguard.runner import execute_command


MAX_PR_DIFF_CHARS = 12000

PR_PROMPT_TEMPLATE = """You are a senior open-source project maintainer writing a GitHub Pull Request description.
Generate a structured, professional Markdown pull request description based on the Git context below.

Git Branch: {current_branch}
Target Base: {base_branch}
Recent Commits:
{commits}

Verified Test Runs (from DevGuard local audit history):
{verified_tests}

Staged / Branch Diff (sanitized):
{diff}

Requirements:
1. Generate:
   - A clear, conventional PR Title (e.g. feat(tools): ... or fix(cli): ...)
   - ## Overview & Problem Statement
   - ## Summary of Changes
   - ## Key Implementation Details
   - ## Test Plan:
     * Label verified tests as "[Verified locally in DevGuard audit]"
     * Label all other recommended testing steps as "[Suggested / Recommended]"
   - ## Reviewer Checklist (markdown checkboxes)
2. Do NOT invent fake issue numbers, benchmark metrics, or unverified claims.
3. Output ONLY the raw Markdown document. Do not wrap in markdown code blocks.
"""


@dataclass
class PRDescriptionResult:
    """The outcome of PR description generation."""
    markdown: str
    title: str
    source: str
    current_branch: str
    base_branch: str
    verified_tests: list[str] = field(default_factory=list)


def get_current_branch() -> str:
    """Retrieve the current Git branch name."""
    res = execute_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if res.exit_code == 0 and res.stdout.strip():
        return res.stdout.strip()
    res2 = execute_command(["git", "branch", "--show-current"])
    if res2.exit_code == 0 and res2.stdout.strip():
        return res2.stdout.strip()
    return "HEAD"


def resolve_base_branch(requested_base: str | None = None) -> str:
    """Resolve an appropriate base branch for diff comparisons."""
    if requested_base:
        return requested_base

    # Check candidates in priority order
    for candidate in ["main", "origin/main", "upstream/main", "master", "origin/master"]:
        res = execute_command(["git", "rev-parse", "--verify", candidate])
        if res.exit_code == 0:
            return candidate

    return "main"


def get_branch_commits(base_branch: str) -> list[str]:
    """Retrieve commit subjects between base and HEAD."""
    res = execute_command(["git", "log", f"{base_branch}..HEAD", "--oneline", "-n", "30"])
    if res.exit_code == 0 and res.stdout.strip():
        return [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]

    # Fallback to recent commits
    res_recent = execute_command(["git", "log", "-5", "--oneline"])
    if res_recent.exit_code == 0 and res_recent.stdout.strip():
        return [line.strip() for line in res_recent.stdout.strip().splitlines() if line.strip()]

    return []


def get_branch_diff(base_branch: str) -> str:
    """Retrieve git diff against base branch, with fallback to HEAD~1 or staged changes."""
    # 1. Try three-dot diff (merge-base to HEAD)
    res = execute_command(["git", "diff", f"{base_branch}...HEAD"])
    if res.exit_code == 0 and res.stdout.strip():
        return res.stdout.strip()

    # 2. Try two-dot diff
    res2 = execute_command(["git", "diff", f"{base_branch}..HEAD"])
    if res2.exit_code == 0 and res2.stdout.strip():
        return res2.stdout.strip()

    # 3. Fallback: staged changes
    res_staged = execute_command(["git", "diff", "--staged"])
    if res_staged.exit_code == 0 and res_staged.stdout.strip():
        return res_staged.stdout.strip()

    # 4. Fallback: last commit diff
    res_last = execute_command(["git", "diff", "HEAD~1"])
    if res_last.exit_code == 0 and res_last.stdout.strip():
        return res_last.stdout.strip()

    return ""


def get_verified_tests_from_audit() -> list[str]:
    """Extract verified passing test commands from recent DevGuard audit logs."""
    verified: list[str] = []
    records = get_audit_history(limit=50)
    for rec in records:
        if rec.get("exit_code") == 0:
            cmd = rec.get("command", [])
            cmd_str = " ".join(cmd)
            if any(k in cmd_str for k in ["pytest", "test"]):
                if cmd_str not in verified:
                    verified.append(cmd_str)
    return verified


def generate_fallback_pr_description(
    current_branch: str,
    base_branch: str,
    commits: list[str],
    verified_tests: list[str],
) -> PRDescriptionResult:
    """Produce a deterministic, clean Markdown PR description without AI calls."""
    title = f"feat({current_branch}): updates and enhancements"
    if commits:
        first_commit = re.sub(r"^[a-f0-9]+\s+", "", commits[0])
        title = first_commit

    commit_list_md = "\n".join(f"- {c}" for c in commits) if commits else "- (no commits detected on branch)"

    verified_md = (
        "\n".join(f"- [x] `{cmd}` *(Verified passing in DevGuard local audit)*" for cmd in verified_tests)
        if verified_tests
        else "- *(no passing test commands recorded in local audit history)*"
    )

    markdown = f"""# {title}

## Summary of Changes
This pull request brings updates from branch `{current_branch}` into `{base_branch}`.

### Commits Included
{commit_list_md}

## Key Implementation Details
- Maintained backwards compatibility with existing configuration and commands.
- Enforced strict deterministic policy checks and safe subprocess execution (`shell=False`).
- Redacted credentials and sensitive tokens from audit records and external requests.

## Test Plan
### Verified Local Tests
{verified_md}

### Suggested Verification Steps
- [ ] Run automated test suite: `pytest tests/ -v`
- [ ] Inspect policy explanations: `devguard policy explain -- <command>`
- [ ] Verify audit log entries: `devguard history`

## Reviewer Checklist
- [ ] Code adheres to project directory standards and conventions
- [ ] No secrets, keys, or credentials committed
- [ ] All tests pass without regressions
- [ ] Documentation updated
"""

    return PRDescriptionResult(
        markdown=markdown.strip(),
        title=title,
        source="deterministic-fallback",
        current_branch=current_branch,
        base_branch=base_branch,
        verified_tests=verified_tests,
    )


def generate_pr_description(
    base_branch: str | None = None,
    provider: AIProvider | None = None,
    output_path: str | Path | None = None,
) -> PRDescriptionResult:
    """Generate a pull request description document from git state.

    Args:
        base_branch: Optional target branch override (default: auto-detected 'main').
        provider: Optional AIProvider for generated text.
        output_path: Optional file path to save the generated Markdown.

    Returns:
        PRDescriptionResult object.
    """
    curr_branch = get_current_branch()
    base = resolve_base_branch(base_branch)
    commits = get_branch_commits(base)
    diff = get_branch_diff(base)
    verified = get_verified_tests_from_audit()

    # Redact secrets from git diff before processing
    safe_diff = redact_secrets(diff)
    if len(safe_diff) > MAX_PR_DIFF_CHARS:
        safe_diff = (
            safe_diff[:MAX_PR_DIFF_CHARS // 2]
            + "\n\n... [diff truncated for length] ...\n\n"
            + safe_diff[-(MAX_PR_DIFF_CHARS // 2):]
        )

    # Deterministic fallback baseline
    fallback_res = generate_fallback_pr_description(
        current_branch=curr_branch,
        base_branch=base,
        commits=commits,
        verified_tests=verified,
    )

    result = fallback_res

    if provider is not None and (safe_diff or commits):
        try:
            commits_str = "\n".join(f"- {c}" for c in commits) if commits else "(none)"
            verified_str = "\n".join(f"- {v}" for v in verified) if verified else "(none)"

            prompt = PR_PROMPT_TEMPLATE.format(
                current_branch=curr_branch,
                base_branch=base,
                commits=commits_str,
                verified_tests=verified_str,
                diff=safe_diff or "(no diff available)",
            )

            raw_resp = provider.generate(prompt).strip()
            # Clean markdown code blocks if present
            clean_resp = re.sub(r"^```[a-zA-Z]*\n?", "", raw_resp)
            clean_resp = re.sub(r"\n?```$", "", clean_resp).strip()

            if clean_resp:
                title_match = re.search(r"^#\s+(.+)$", clean_resp, re.MULTILINE)
                title = title_match.group(1).strip() if title_match else fallback_res.title

                result = PRDescriptionResult(
                    markdown=clean_resp,
                    title=title,
                    source=f"ai-assisted ({getattr(provider, 'name', 'ai')})",
                    current_branch=curr_branch,
                    base_branch=base,
                    verified_tests=verified,
                )
        except Exception:
            result = fallback_res

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(result.markdown + "\n", encoding="utf-8")

    return result

