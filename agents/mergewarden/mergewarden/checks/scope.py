"""Is the PR confined to one project folder (plus the optional index row)?"""

from __future__ import annotations

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
        if path.startswith(sub.project_dir + "/") or path in policy.index_files:
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
