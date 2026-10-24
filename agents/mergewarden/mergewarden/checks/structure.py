"""Folder naming, required files, dependency manifest, tracked junk, and
anything that would keep files out of the review (attributes, submodules, LFS)."""

from __future__ import annotations

import re

from ..models import Criterion, Finding, Severity, Submission
from ..policy import Policy
from ._files import read

KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
JUNK_DIRS = {".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache", ".ipynb_checkpoints", "dist", "build"}
JUNK_FILES = re.compile(r"(\.DS_Store|\.sqlite3?|\.db|\.log|\.pyc)$")
# A slug made only of these words says nothing about the project ("test-agent", "my-ai-bot").
GENERIC_TOKENS = {"test", "tests", "demo", "my", "agent", "agents", "tool", "tools", "final", "project", "sample",
                  "example", "helper", "new", "app", "bot", "ai", "the", "first", "hello", "world", "hackathon",
                  "submission", "v1", "v2", "1", "2", "simple", "basic", "temp", "tmp"}
# Attributes that hide files from exports or collapse/hide their diff in PR review.
ATTR_TRICKS = re.compile(r"(export-ignore|export-subst|filter=|(?<![\w-])-diff\b|linguist-generated)")
LFS_POINTER = b"version https://git-lfs.github.com/spec/v1"


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
    if slug in policy.banned_names or set(slug.split("-")) <= GENERIC_TOKENS:
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

    for f in files:
        rel = f"{sub.project_dir}/{f.relative_to(proj)}"
        trick = ATTR_TRICKS.search(read(f)) if f.name == ".gitattributes" else None
        if trick:
            out.append(Finding(
                "hygiene.gitattributes", Severity.MAJOR, Criterion.SECURITY,
                f"`{rel}` sets git attributes (`{trick.group(1)}`) that can hide or rewrite "
                "files in exports and diffs. A contribution folder has no reason to need this.",
                file=rel, fix=f"git rm {rel}",
            ))
        elif f.stat().st_size < 1024 and f.read_bytes().startswith(LFS_POINTER):
            out.append(Finding(
                "hygiene.lfs-pointer", Severity.MAJOR, Criterion.REPRODUCIBILITY,
                f"`{rel}` is a Git LFS pointer, so its real content isn't in the PR and can't be reviewed.",
                file=rel, fix="Commit the file directly (if small) or link to where it can be downloaded.",
            ))
    for link in sub.gitlinks:
        if link == sub.project_dir or link.startswith(sub.project_dir + "/"):
            out.append(Finding(
                "hygiene.submodule", Severity.MAJOR, Criterion.SECURITY,
                f"`{link}` is a git submodule: its code lives in another repository and is never part of this review.",
                file=link, fix="Vendor the code you need into your folder, or depend on it through your manifest.",
            ))

    names = {f.name for f in files if len(f.relative_to(proj).parts) <= 2}
    for m in sorted(names & set(policy.manifest_files)):
        mf = next(f for f in files if f.name == m and len(f.relative_to(proj).parts) <= 2)
        meaningful = [l for l in read(mf).splitlines() if l.strip() and not l.strip().startswith(("#", "//"))]
        if not meaningful:
            out.append(Finding(
                "structure.manifest", Severity.MAJOR, Criterion.REPRODUCIBILITY,
                f"`{sub.project_dir}/{mf.relative_to(proj)}` is empty, so a fresh install gets none of your dependencies.",
                file=f"{sub.project_dir}/{mf.relative_to(proj)}", fix="List every package your code imports, with versions.",
                rule=policy.rule("structure.manifest"),
            ))
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
