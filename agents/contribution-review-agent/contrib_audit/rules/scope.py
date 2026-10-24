"""Rule R09: scope check — changes must be inside the project folder (via git)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..models import Finding, Severity


def _run_git(args: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run a git command; return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode, result.stdout, result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return -1, "", str(exc)


def check_scope(
    project_path: Path, repo_root: Path, git_available: bool = True
) -> list[Finding]:
    """R09: files changed vs upstream/main (fallback origin/main) must be inside project_path
    or at most one row edit in agents/README.md or tools/README.md."""
    findings: list[Finding] = []

    if not git_available:
        findings.append(
            Finding(
                rule_id="R09",
                severity=Severity.INFO,
                file=None,
                line=None,
                message="Git unavailable; scope check skipped.",
                evidence=None,
                fix_hint="Ensure git is installed and the repo has an upstream remote.",
            )
        )
        return findings

    # Try upstream/main, then origin/main
    base_ref = None
    for candidate in ("upstream/main", "origin/main"):
        rc, out, _ = _run_git(["rev-parse", "--verify", candidate], cwd=repo_root)
        if rc == 0:
            base_ref = candidate
            break

    if base_ref is None:
        findings.append(
            Finding(
                rule_id="R09",
                severity=Severity.INFO,
                file=None,
                line=None,
                message="Could not find upstream/main or origin/main; scope check skipped.",
                evidence=None,
                fix_hint="Add an upstream remote: git remote add upstream <url>",
            )
        )
        return findings

    rc, out, err = _run_git(
        ["diff", "--name-only", f"{base_ref}...HEAD"], cwd=repo_root
    )
    if rc != 0:
        findings.append(
            Finding(
                rule_id="R09",
                severity=Severity.INFO,
                file=None,
                line=None,
                message=f"git diff failed ({err.strip()[:120]}); scope check skipped.",
                evidence=None,
                fix_hint="Ensure your branch has commits on top of upstream/main.",
            )
        )
        return findings

    changed_files = [Path(f) for f in out.splitlines() if f.strip()]
    try:
        project_rel = project_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return findings

    # Allowed: project folder prefix, or single index edit
    index_files = {
        Path("agents") / "README.md",
        Path("tools") / "README.md",
    }

    out_of_scope = []
    for f in changed_files:
        if str(f).startswith(str(project_rel)):
            continue
        if f in index_files:
            continue
        out_of_scope.append(f)

    for f in out_of_scope:
        findings.append(
            Finding(
                rule_id="R09",
                severity=Severity.ERROR,
                file=f,
                line=None,
                message=f"Changed file is outside the project directory: {f}",
                evidence=str(f),
                fix_hint=(
                    "Revert changes to files outside your project folder. "
                    "Only agents/README.md or tools/README.md index edits are allowed."
                ),
            )
        )

    return findings
