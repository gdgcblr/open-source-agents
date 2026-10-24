"""Rules R05, R06, R10: README heading completeness, env sync, example section."""
from __future__ import annotations

import re
from pathlib import Path

from ..models import Finding, Severity

# Fallback heading list when template/README.md is not readable
_FALLBACK_HEADINGS = [
    "Overview",
    "Technical Stack",
    "Architecture & Data Flow",
    "Prerequisites",
    "Installation & Setup",
    "Configuration & Environment Variables",
    "How to Run",
    "Example Input & Output",
    "How to Test",
    "Known Limitations",
    "Security & Privacy Considerations",
    "Future Improvements",
    "License",
]

# Template placeholder patterns (catch leftover template text)
_PLACEHOLDER_RE = re.compile(
    r"\[(?:Project Name|One-sentence summary|your[- ]|Language Runtime|"
    r"Package manager|Required API keys|project-slug|e\.g\.|"
    r"Feature \d|Brief description|Explain what|Who is this|"
    r"List the primary|Provide a brief|Before running|Provide the exact|"
    r"Explain how another|Be honest|How are credentials|Is any prompt|"
    r"Does the agent)\b",
    re.IGNORECASE,
)

# Template example output (R10 verbatim match)
_TEMPLATE_EXAMPLE = "Analysis completed:"

# The heading that must contain the env-var table (R06)
_ENV_HEADING_RE = re.compile(
    r"^#{1,4}\s+Configuration\s*(?:&|and)\s*Environment\s+Variables",
    re.IGNORECASE | re.MULTILINE,
)


def _load_template_headings(repo_root: Path) -> list[str]:
    """Parse ## and deeper headings from template/README.md; fall back to bundled list.

    H1 titles (# ...) are intentionally skipped — the project title varies per project.
    """
    tpl = repo_root / "template" / "README.md"
    headings = []
    if tpl.exists():
        try:
            for line in tpl.read_text(encoding="utf-8", errors="replace").splitlines():
                # Only ## level headings; skip # H1 (project title) and ### subheadings
                m = re.match(r"^##\s+(.+)$", line)
                if m:
                    headings.append(m.group(1).strip())
        except OSError:
            pass
    return headings or _FALLBACK_HEADINGS


def check_headings(project_path: Path, repo_root: Path) -> list[Finding]:
    """R05: README must contain every heading from template, with no leftover placeholders."""
    findings: list[Finding] = []
    readme = project_path / "README.md"
    if not readme.exists():
        return findings  # R04 will report this

    text = readme.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    template_headings = _load_template_headings(repo_root)

    # Extract ## and deeper headings present in this README (skip H1 project title)
    present = set()
    for line in lines:
        m = re.match(r"^#{2,4}\s+(.+)$", line)
        if m:
            present.add(m.group(1).strip())

    for heading in template_headings:
        if heading not in present:
            findings.append(
                Finding(
                    rule_id="R05",
                    severity=Severity.ERROR,
                    file=readme,
                    line=None,
                    message=f"README is missing required heading: '{heading}'",
                    evidence=None,
                    fix_hint=f"Add a '## {heading}' section to your README.",
                )
            )

    # Placeholder check
    for lineno, line in enumerate(lines, 1):
        if _PLACEHOLDER_RE.search(line):
            findings.append(
                Finding(
                    rule_id="R05",
                    severity=Severity.WARNING,
                    file=readme,
                    line=lineno,
                    message="Possible leftover template placeholder.",
                    evidence=line.strip()[:80],
                    fix_hint="Replace template placeholder text with real content.",
                )
            )

    return findings


def _parse_env_example(project_path: Path) -> set[str]:
    """Return variable names from .env.example (uncommented KEY=... lines)."""
    env_file = project_path / ".env.example"
    names: set[str] = set()
    if not env_file.exists():
        return names
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key:
                names.add(key)
    return names


def _parse_readme_env_table(project_path: Path) -> set[str]:
    """Extract variable names from the README env-var table (backtick-wrapped column 1)."""
    readme = project_path / "README.md"
    names: set[str] = set()
    if not readme.exists():
        return names

    text = readme.read_text(encoding="utf-8", errors="replace")
    in_env_section = False

    for line in text.splitlines():
        if _ENV_HEADING_RE.match(line):
            in_env_section = True
            continue
        if in_env_section:
            # Stop at next heading
            if re.match(r"^#{1,4}\s+", line):
                break
            # Extract backtick-wrapped names from table cells
            for m in re.finditer(r"`([A-Z][A-Z0-9_]*)`", line):
                names.add(m.group(1))

    return names


def check_env_sync(project_path: Path) -> list[Finding]:
    """R06: every var in .env.example appears in README env table, and vice versa."""
    findings: list[Finding] = []
    env_vars = _parse_env_example(project_path)
    readme_vars = _parse_readme_env_table(project_path)

    readme = project_path / "README.md"
    env_file = project_path / ".env.example"

    for var in sorted(env_vars - readme_vars):
        findings.append(
            Finding(
                rule_id="R06",
                severity=Severity.WARNING,
                file=env_file,
                line=None,
                message=f"'{var}' is in .env.example but not documented in the README env table.",
                evidence=var,
                fix_hint="Add this variable to the README 'Configuration & Environment Variables' table.",
            )
        )

    for var in sorted(readme_vars - env_vars):
        findings.append(
            Finding(
                rule_id="R06",
                severity=Severity.WARNING,
                file=readme,
                line=None,
                message=f"'{var}' is in README env table but not in .env.example.",
                evidence=var,
                fix_hint="Add this variable to .env.example with a placeholder value.",
            )
        )

    return findings


def check_example_section(project_path: Path) -> list[Finding]:
    """R10: Example section must not be unmodified template text."""
    findings: list[Finding] = []
    readme = project_path / "README.md"
    if not readme.exists():
        return findings

    text = readme.read_text(encoding="utf-8", errors="replace")
    if _TEMPLATE_EXAMPLE in text:
        findings.append(
            Finding(
                rule_id="R10",
                severity=Severity.ERROR,
                file=readme,
                line=None,
                message="Example section appears to contain unmodified template text.",
                evidence=_TEMPLATE_EXAMPLE[:40],
                fix_hint=(
                    "Replace the example output with real output from an actual run."
                ),
            )
        )
    return findings
