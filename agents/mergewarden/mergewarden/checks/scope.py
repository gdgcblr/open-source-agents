"""Is the PR confined to one project folder (plus the optional index row)?"""

from __future__ import annotations

import difflib
import re

from ..models import Criterion, Finding, Severity, Submission
from ..policy import Policy

GOVERNANCE = ("CONTRIBUTING.md", "README.md", "LICENSE", ".gitignore", ".github/", "template/")


def project_dirs(changed: list[str], policy: Policy) -> list[str]:
    """Distinct `<root>/<slug>` folders touched, most-touched first."""
    counts: dict[str, int] = {}
    for path in changed:
        parts = path.split("/")
        if len(parts) >= 3 and parts[0] in policy.project_roots:
            key = "/".join(parts[:2])
            counts[key] = counts.get(key, 0) + 1
    return sorted(counts, key=lambda k: -counts[k])


def check(sub: Submission, policy: Policy) -> list[Finding]:
    out: list[Finding] = []
    if not sub.project_dir:
        out.append(Finding(
            "scope.no-project", Severity.BLOCKER, Criterion.SCOPE,
            f"No project folder found. Contributions must live in "
            f"{' or '.join(r + '/<project-slug>/' for r in policy.project_roots)}.",
            rule=policy.rule("scope.outside-project"),
        ))
        return out

    others = [d for d in project_dirs(sub.changed_files, policy) if d != sub.project_dir]
    if others:
        out.append(Finding(
            "scope.multiple-projects", Severity.MAJOR, Criterion.SCOPE,
            f"PR also touches other project folders: {', '.join(others)}. "
            "Each contribution should be one folder; never edit another contributor's project.",
            fix="Split this into separate PRs, or revert the changes to other projects.",
            rule=policy.rule("scope.multiple-projects"),
        ))

    for path in sub.changed_files:
        if path in policy.index_files:
            out += _index_edit(sub, path, policy)
            continue
        if path.startswith(sub.project_dir + "/"):
            continue
        if any(path.startswith(o + "/") for o in others):
            continue
        governance = path.startswith(GOVERNANCE) or path in GOVERNANCE
        out.append(Finding(
            "scope.outside-project", Severity.BLOCKER if governance else Severity.MAJOR, Criterion.SCOPE,
            f"`{path}` is outside your project folder"
            + (" and is a repository governance file." if governance else "."),
            file=path,
            fix=f"git checkout upstream/main -- {path}",
            rule=policy.rule("scope.outside-project"),
        ))
    return out


def _index_edit(sub: Submission, path: str, policy: Policy) -> list[Finding]:
    """The index file may gain exactly one table row (and lose the "None yet" placeholder row)."""
    head_p = sub.root / path
    head = head_p.read_bytes().decode("utf-8", "replace") if head_p.is_file() else ""
    problems = []
    if not re.search(r"(?im)^#+\s*directory index", head) or not re.search(r"(?m)^\|\s*:?-{3,}", head):
        problems.append("the Directory Index table is missing")
    base_p = sub.base_root / path if sub.base_root else None
    if base_p and base_p.is_file():
        base = base_p.read_bytes().decode("utf-8", "replace").splitlines()
        diff = list(difflib.ndiff(base, head.splitlines()))
        removed = [l[2:] for l in diff if l.startswith("- ") and l[2:].strip() and "none yet" not in l.lower()]
        added = [l[2:] for l in diff if l.startswith("+ ") and l[2:].strip()]
        rows = [l for l in added if l.lstrip().startswith("|")]
        if removed:
            problems.append(f"{len(removed)} existing line(s) removed or changed")
        if len(rows) > 1:
            problems.append(f"{len(rows)} table rows added (only one is allowed)")
        if len(added) > len(rows):
            problems.append(f"{len(added) - len(rows)} non-table line(s) added")
    if not problems:
        return []
    return [Finding(
        "scope.index-edit", Severity.MAJOR, Criterion.SCOPE,
        f"`{path}` may only gain one row in its Directory Index table, but {'; '.join(problems)}.",
        file=path, fix=f"git checkout upstream/main -- {path}, then add just your one table row.",
        rule=policy.rule("scope.outside-project"),
    )]
