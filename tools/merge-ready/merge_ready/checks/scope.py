"""Checks for contribution diff scope and index table modification (P01, I01)."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

from merge_ready.model import Finding, RuleResult, Severity, Verdict
from merge_ready.project import ProjectContext


def get_git_diff_name_status(repo_root: Path, base_ref: str) -> list[tuple[str, str]]:
    """Get list of (status, file_path) from git diff base...HEAD using NUL-delimited output."""
    res = subprocess.run(
        ["git", "diff", "--name-status", "-z", "--no-renames", f"{base_ref}...HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=True,
    )
    raw = res.stdout.split("\0")
    results: list[tuple[str, str]] = []
    i = 0
    while i < len(raw) - 1:
        status = raw[i].strip()
        path_str = raw[i + 1].strip()
        if status and path_str:
            results.append((status, path_str))
        i += 2
    return results


def check_p01(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """P01: Changed paths limited to project folder plus optional category index row."""
    rule_id = "P01"
    name = "Contribution Diff Scope"
    source = config.get("source_rule", "CONTRIBUTING.md Scoping Your Pull Request")

    if not ctx.base_ref:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.SKIP,
            reason="No Git base reference provided (--base <ref>). Scope check skipped.",
        )

    if not ctx.repo_root:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.SKIP,
            reason="Project is not located inside a Git repository root. Scope check skipped.",
        )

    try:
        changed = get_git_diff_name_status(ctx.repo_root, ctx.base_ref)
    except subprocess.CalledProcessError as e:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.SKIP,
            reason=f"Failed to inspect git diff against base '{ctx.base_ref}': {e}",
        )

    if not changed:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.PASS,
            reason="No changed files detected relative to base reference.",
        )

    permitted_prefix = f"{ctx.category}/{ctx.slug}/"
    allowed_index = f"{ctx.category}/README.md"

    findings: list[Finding] = []
    for status, changed_path in changed:
        posix = changed_path.replace("\\", "/")
        if posix.startswith(permitted_prefix):
            continue
        if posix == allowed_index:
            continue

        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message=f"Out-of-scope file modified in PR: '{posix}'.",
                path=posix,
                evidence=f"Git status: {status} on file '{posix}'. Allowed paths are '{permitted_prefix}*' and '{allowed_index}'.",
                fix=f"Revert changes to '{posix}'. Pull requests must strictly touch only their own project directory and category index.",
                source_rule=source,
            )
        )

    if findings:
        return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.FAIL, findings=findings)

    return RuleResult(rule_id=rule_id, name=name, verdict=Verdict.PASS)


def check_i01(ctx: ProjectContext, config: dict[str, Any]) -> RuleResult:
    """I01: Verify that category index table modification adds exactly one row for this project."""
    rule_id = "I01"
    name = "Category Index Entry"
    source = config.get("source_rule", "CONTRIBUTING.md Scoping Your Pull Request & tools/README.md")

    if not ctx.base_ref or not ctx.repo_root:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.SKIP,
            reason="Git base reference or repository root not available.",
        )

    allowed_index = f"{ctx.category}/README.md"
    try:
        changed = get_git_diff_name_status(ctx.repo_root, ctx.base_ref)
    except Exception:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.SKIP,
            reason=f"Git diff against '{ctx.base_ref}' failed.",
        )

    index_modified = any(p.replace("\\", "/") == allowed_index for _, p in changed)
    if not index_modified:
        # Index row modification is optional
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.PASS,
            reason=f"Category index '{allowed_index}' was not modified (optional).",
        )

    try:
        diff_res = subprocess.run(
            ["git", "diff", f"{ctx.base_ref}...HEAD", "--", allowed_index],
            cwd=str(ctx.repo_root),
            capture_output=True,
            text=True,
            check=True,
        )
        diff_text = diff_res.stdout
    except Exception as e:
        return RuleResult(
            rule_id=rule_id,
            name=name,
            verdict=Verdict.SKIP,
            reason=f"Could not retrieve diff for index file: {e}",
        )

    findings: list[Finding] = []
    added_table_rows = []
    deleted_table_rows = []

    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") and line[1:].strip().startswith("|"):
            added_table_rows.append(line[1:].strip())
        elif line.startswith("-") and line[1:].strip().startswith("|"):
            deleted_table_rows.append(line[1:].strip())

    # Negative control: removing the "None yet" placeholder row is permitted
    cleaned_deleted = [r for r in deleted_table_rows if "(None yet)" not in r and "None yet" not in r]
    if cleaned_deleted:
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message=f"Unexpected table row deletion in '{allowed_index}'.",
                path=allowed_index,
                evidence=f"Deleted row: {cleaned_deleted[0]}",
                fix="Do not delete existing project rows in the category index.",
                source_rule=source,
            )
        )

    if len(added_table_rows) == 0:
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message=f"Category index '{allowed_index}' was modified but no project row was added.",
                path=allowed_index,
                fix="Add a markdown table row registering your project in the Directory Index.",
                source_rule=source,
            )
        )
    elif len(added_table_rows) > 1:
        findings.append(
            Finding(
                rule_id=rule_id,
                severity=Severity.ERROR,
                message=f"More than one table row ({len(added_table_rows)}) added to '{allowed_index}'.",
                path=allowed_index,
                evidence=f"Added rows: {added_table_rows}",
                fix="Modify at most one row corresponding to your own project.",
                source_rule=source,
            )
        )
    else:
        # Check that the single added row references ctx.slug
        row = added_table_rows[0]
        if ctx.slug not in row:
            findings.append(
                Finding(
                    rule_id=rule_id,
                    severity=Severity.ERROR,
                    message=f"Added index row does not match project slug '{ctx.slug}'.",
                    path=allowed_index,
                    evidence=f"Row content: {row}",
                    fix=f"Include '{ctx.slug}' or '[{ctx.slug}]({ctx.slug}/)' in the directory column.",
                    source_rule=source,
                )
            )

    # Informational finding about concurrent PR rebase
    findings.append(
        Finding(
            rule_id=rule_id,
            severity=Severity.INFO,
            message="Shared category index files may conflict with concurrent PRs.",
            path=allowed_index,
            fix="Rebase your feature branch on upstream main immediately before opening or merging the PR.",
            source_rule=source,
        )
    )

    has_errors = any(f.severity == Severity.ERROR for f in findings)
    verdict = Verdict.FAIL if has_errors else Verdict.PASS
    return RuleResult(rule_id=rule_id, name=name, verdict=verdict, findings=findings)
