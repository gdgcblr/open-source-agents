"""Rules R01, R02, R03, R04: structure, naming, required files."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from ..models import Finding, Severity

# R03 generic name blocklist
_GENERIC_NAMES = frozenset(
    {"my-agent", "my-tool", "final-project", "final-test", "test", "demo", "helper"}
)

# R04 recognised manifests
_MANIFESTS = frozenset(
    {"requirements.txt", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"}
)

# R04 all required files (manifest is checked separately)
_REQUIRED = frozenset({"README.md", ".env.example", ".gitignore"})


def check_location(project_path: Path, repo_root: Path) -> list[Finding]:
    """R01: project must be a direct child of agents/ or tools/."""
    findings: list[Finding] = []
    try:
        rel = project_path.relative_to(repo_root)
    except ValueError:
        findings.append(
            Finding(
                rule_id="R01",
                severity=Severity.ERROR,
                file=None,
                line=None,
                message="Project path is outside the repo root.",
                evidence=str(project_path),
                fix_hint="Move your project under agents/<slug>/ or tools/<slug>/.",
            )
        )
        return findings

    parts = rel.parts
    if len(parts) != 2 or parts[0] not in ("agents", "tools"):
        findings.append(
            Finding(
                rule_id="R01",
                severity=Severity.ERROR,
                file=None,
                line=None,
                message=f"Project must be a direct child of agents/ or tools/, got: {rel}",
                evidence=str(rel),
                fix_hint="Place your project at agents/<slug>/ or tools/<slug>/.",
            )
        )
    return findings


def check_naming(project_path: Path) -> list[Finding]:
    """R02, R03: kebab-case naming and non-generic names."""
    findings: list[Finding] = []
    name = project_path.name

    # R02
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        findings.append(
            Finding(
                rule_id="R02",
                severity=Severity.ERROR,
                file=None,
                line=None,
                message=f"Directory name '{name}' is not lowercase kebab-case.",
                evidence=name,
                fix_hint="Rename to lowercase-kebab-case, e.g. my-cool-agent.",
            )
        )

    # R03
    if name.lower() in _GENERIC_NAMES:
        findings.append(
            Finding(
                rule_id="R03",
                severity=Severity.ERROR,
                file=None,
                line=None,
                message=f"Directory name '{name}' is too generic.",
                evidence=name,
                fix_hint=(
                    "Choose a descriptive name like 'meeting-summarizer' "
                    "instead of generic names like 'my-agent', 'test', 'demo'."
                ),
            )
        )
    return findings


def check_required_files(project_path: Path) -> list[Finding]:
    """R04: README.md, .env.example, .gitignore, and one manifest must exist."""
    findings: list[Finding] = []

    for fname in sorted(_REQUIRED):
        if not (project_path / fname).exists():
            findings.append(
                Finding(
                    rule_id="R04",
                    severity=Severity.ERROR,
                    file=project_path / fname,
                    line=None,
                    message=f"Required file '{fname}' is missing.",
                    evidence=None,
                    fix_hint=f"Add {fname} to your project directory.",
                )
            )

    has_manifest = any((project_path / m).exists() for m in _MANIFESTS)
    if not has_manifest:
        findings.append(
            Finding(
                rule_id="R04",
                severity=Severity.ERROR,
                file=None,
                line=None,
                message="No dependency manifest found.",
                evidence=None,
                fix_hint=(
                    "Add requirements.txt, pyproject.toml, package.json, "
                    "Cargo.toml, or go.mod."
                ),
            )
        )
    return findings
