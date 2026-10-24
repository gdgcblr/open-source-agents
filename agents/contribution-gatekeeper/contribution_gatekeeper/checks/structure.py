"""Folder naming, required files, dependency manifest and tracked junk."""

from __future__ import annotations

import re

from ..models import Criterion, Finding, Severity, Submission
from ..policy import Policy

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
JUNK_DIRS = {".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache", ".ipynb_checkpoints", "dist", "build"}
JUNK_FILES = re.compile(r"(\.DS_Store|\.sqlite3?|\.db|\.log|\.pyc)$")


def check(sub: Submission, policy: Policy) -> list[Finding]:
    out: list[Finding] = []
    if not sub.project_dir:
        return out
    slug = sub.project_dir.split("/")[-1]
    if policy.kebab_case and not KEBAB.match(slug):
        out.append(Finding(
            "naming.kebab-case", Severity.MAJOR, Criterion.SCOPE,
            f"Folder name `{slug}` is not lowercase kebab-case.",
            fix=f"Rename to `{re.sub(r'[^a-z0-9]+', '-', slug.lower()).strip('-')}`.",
            rule=policy.rule("naming.kebab-case"),
        ))
    if slug in policy.banned_names:
        out.append(Finding(
            "naming.generic", Severity.MAJOR, Criterion.SCOPE,
            f"`{slug}` is a generic name. Pick one that says what the project does.",
            rule=policy.rule("naming.generic"),
        ))

    proj = sub.project_path
    files = sub.project_files()
    if not proj or not proj.is_dir():
        return out

    for req in policy.required_files:
        if not (proj / req).exists():
            out.append(Finding(
                "structure.required-file", Severity.MAJOR, Criterion.DOCUMENTATION if req == "README.md" else Criterion.SECURITY,
                f"Missing `{req}` (copy it from `template/{req}`).", file=f"{sub.project_dir}/{req}",
                fix=f"cp template/{req} {sub.project_dir}/{req}",
                rule=policy.rule("structure.required-file"),
            ))

    names = {f.name for f in files if len(f.relative_to(proj).parts) <= 2}
    if not names & set(policy.manifest_files):
        out.append(Finding(
            "structure.manifest", Severity.MAJOR, Criterion.REPRODUCIBILITY,
            "No dependency manifest (requirements.txt, pyproject.toml, package.json, ...) in the project folder.",
            fix="pip freeze > requirements.txt  # or list only your direct dependencies",
            rule=policy.rule("structure.manifest"),
        ))

    junk = set()
    for f in files:
        rel = f.relative_to(proj)
        top_junk = next((p for p in rel.parts[:-1] if p in JUNK_DIRS), None)
        if top_junk:
            junk.add(f"{sub.project_dir}/{'/'.join(rel.parts[:rel.parts.index(top_junk) + 1])}/")
        elif JUNK_FILES.search(f.name):
            junk.add(f"{sub.project_dir}/{rel}")
        elif f.stat().st_size > 5_000_000:
            junk.add(f"{sub.project_dir}/{rel} ({f.stat().st_size // 1_000_000} MB)")
    for j in sorted(junk):
        out.append(Finding(
            "hygiene.tracked-junk", Severity.MAJOR, Criterion.SECURITY,
            f"`{j}` should not be committed (virtual env, cache, local database or large binary).",
            fix=f"git rm -r --cached {j.split(' ')[0]}",
            rule=policy.rule("hygiene.tracked-junk"),
        ))
    return out
