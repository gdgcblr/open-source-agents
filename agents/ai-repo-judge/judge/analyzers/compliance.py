"""Compliance: does the submission follow the repository's contribution rules (CONTRIBUTING.md)?"""

from __future__ import annotations

import re

from judge.models import AnalyzerResult, Check, Finding
from judge.sources import INDEX_FILES
from judge.workspace import Workspace

DIM = "compliance"
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
GENERIC_NAMES = {
    "my-agent",
    "my-tool",
    "final-project",
    "test",
    "tests",
    "demo",
    "helper",
    "agent",
    "tool",
    "project",
    "sample",
    "example",
    "final-test",
    "untitled",
    "new-project",
    "my-project",
    "app",
}
MANIFESTS = (
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "cargo.toml",
    "pipfile",
    "environment.yml",
    "setup.py",
    "pom.xml",
    "build.gradle",
    "gemfile",
)
JUNK = re.compile(
    r"(^|/)(\.venv|venv|node_modules|__pycache__|\.pytest_cache|\.ipynb_checkpoints)/|"
    r"(^|/)\.DS_Store$|\.py[co]$"
)
TITLE_RE = re.compile(r"^(feat|fix|docs|chore|refactor|test)(\((agents|tools)\))?!?:\s+\S", re.I)
MAX_INDEX_LINES = 4  # adding one table row to agents/README.md or tools/README.md is allowed


def analyze(ws: Workspace) -> AnalyzerResult:
    r = AnalyzerResult()
    add = r.checks.append

    # C1 location
    in_category = ws.category in ("agents", "tools")
    add(
        Check(
            id="location",
            dimension=DIM,
            label="Lives in agents/<slug>/ or tools/<slug>/",
            weight=2,
            status="pass" if in_category else "fail",
            detail=f"Project folder: {ws.project_path or '(none found)'}",
            fix=None if in_category else "Move the project into agents/<slug>/ or tools/<slug>/.",
        )
    )

    # C2 naming
    kebab = bool(KEBAB.match(ws.slug))
    add(
        Check(
            id="kebab_case",
            dimension=DIM,
            label="Folder name is lowercase kebab-case",
            weight=1,
            status="pass" if kebab else "fail",
            detail=ws.slug,
            fix=None if kebab else f"Rename the folder to {re.sub(r'[^a-z0-9]+', '-', ws.slug.lower()).strip('-')}.",
        )
    )
    generic = ws.slug.lower() in GENERIC_NAMES or len(ws.slug) < 4
    add(
        Check(
            id="descriptive_name",
            dimension=DIM,
            label="Folder name is descriptive (not generic)",
            weight=1,
            status="warn" if generic else "pass",
            detail=ws.slug,
            fix="Pick a name that says what the project does, e.g. `meeting-summarizer`." if generic else None,
        )
    )

    # C3 required files
    missing = []
    if not ws.exists("README.md"):
        missing.append("README.md")
    if not ws.exists(".gitignore"):
        missing.append(".gitignore")
    if not any(ws.exists(m) or ws.find(m) for m in MANIFESTS):
        missing.append("dependency manifest")
    env_example = ws.exists(".env.example") or ws.find(".env.example", ".env.sample", ".env.template")
    if not env_example:
        missing.append(".env.example")
    status = "pass" if not missing else ("warn" if missing == [".env.example"] else "fail")
    add(
        Check(
            id="required_files",
            dimension=DIM,
            label="README, .gitignore, .env.example and a manifest present",
            weight=2,
            status=status,
            detail="Missing: " + ", ".join(missing) if missing else "All present",
            score=1 - len(missing) / 4,
            fix=f"Add {', '.join(missing)} (copy them from template/)." if missing else None,
        )
    )

    # C4 scope: only the submission's own (new) folders plus a small index-table edit
    own = [ws.project_path, *ws.extra_projects]
    prefixes = tuple(p.rstrip("/") + "/" for p in own)
    outside = [p for p in ws.changed_paths if not p.startswith(prefixes)]
    foreign = tuple(p.rstrip("/") + "/" for p in ws.foreign_projects)
    bad = [p for p in outside if not (p in INDEX_FILES and ws.changed_lines.get(p, 0) <= MAX_INDEX_LINES)]
    extra_note = f" (agent + {', '.join(ws.extra_projects)})" if ws.extra_projects else ""
    add(
        Check(
            id="scope",
            dimension=DIM,
            label="Changes confined to the submission's own folder(s)",
            weight=3,
            status="fail" if bad else "pass",
            detail=("Outside the project: " + ", ".join(bad[:8]) + (" …" if len(bad) > 8 else ""))
            if bad
            else "Only project files" + extra_note + (" + index row" if outside else ""),
            fix="Revert changes outside your folder; only one index row in agents/README.md or "
            "tools/README.md is allowed."
            if bad
            else None,
        )
    )
    for p in bad[:10]:
        theirs = p.startswith(foreign)
        r.findings.append(
            Finding(
                dimension=DIM,
                severity="high",
                file=p,
                gate=True,
                title="Modifies another contributor's project" if theirs else "File changed outside the project folder",
                detail="CONTRIBUTING.md: don't modify another contributor's directory without coordination."
                if theirs
                else "CONTRIBUTING.md asks PRs to touch only their own directory.",
                fix="Revert this file in your branch.",
            )
        )

    # C5 tracked junk (virtualenvs, caches, OS files)
    junk = [f for f in ws.files if JUNK.search(f)]
    add(
        Check(
            id="no_junk",
            dimension=DIM,
            label="No virtualenvs, caches or OS files committed",
            weight=1,
            status="pass" if not junk else "fail",
            detail=f"{len(junk)} junk file(s): " + ", ".join(junk[:5]) if junk else "Clean",
            fix="Delete them and rely on the template .gitignore." if junk else None,
        )
    )

    # C6 PR template checklist and title (PRs only)
    if ws.meta.state != "local":
        body = ws.meta.body or ""
        boxes = re.findall(r"^\s*[-*]\s*\[( |x|X)\]", body, re.M)
        ticked = sum(1 for b in boxes if b.lower() == "x")
        if not boxes:
            st, detail, score = "fail", "PR template checklist not found in the description", 0.0
        else:
            score = ticked / len(boxes)
            st = "pass" if score >= 0.75 else "warn" if score >= 0.4 else "fail"
            detail = f"{ticked}/{len(boxes)} checklist items ticked"
        add(
            Check(
                id="pr_checklist",
                dimension=DIM,
                label="PR template checklist completed",
                weight=1,
                status=st,
                score=score,
                detail=detail,
                fix=None if st == "pass" else "Fill in .github/PULL_REQUEST_TEMPLATE.md in the PR description.",
            )
        )
        title_ok = bool(TITLE_RE.match(ws.meta.title or ""))
        add(
            Check(
                id="pr_title",
                dimension=DIM,
                label="Conventional PR title, e.g. feat(agents): add <slug>",
                weight=0.5,
                status="pass" if title_ok else "warn",
                detail=ws.meta.title or "",
                fix=None if title_ok else f"Retitle to `feat({ws.category}): add {ws.slug}`.",
            )
        )

    r.facts["missing_files"] = missing
    return r
