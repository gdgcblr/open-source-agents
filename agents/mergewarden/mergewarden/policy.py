"""Compile a repository's contribution guide into a machine-checkable policy.

The policy is always read from the *base* branch, never from the PR itself,
so a contribution cannot weaken the rules it is judged by.

Every rule keeps a citation (file:line) back to the sentence it came from, so
each finding in a review can show the contributor *why* it was raised.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Rule:
    text: str
    source: str  # "CONTRIBUTING.md:250"

    def cite(self) -> str:
        return f"{self.text} ({self.source})"


@dataclass
class Policy:
    project_roots: list[str] = field(default_factory=list)  # e.g. ["agents", "tools"]
    required_files: list[str] = field(default_factory=list)  # e.g. ["README.md", ".env.example"]
    manifest_files: list[str] = field(default_factory=list)
    banned_names: list[str] = field(default_factory=list)
    readme_sections: list[str] = field(default_factory=list)  # headings from template/README.md
    template_placeholders: list[str] = field(default_factory=list)
    index_files: list[str] = field(default_factory=list)  # files a PR may touch outside its folder
    checklist_items: list[str] = field(default_factory=list)  # from the PR template
    soft_rules: list[Rule] = field(default_factory=list)  # judged by the LLM reviewer
    rules: dict[str, Rule] = field(default_factory=dict)  # check-id -> cited rule
    kebab_case: bool = True

    def rule(self, key: str) -> Optional[str]:
        r = self.rules.get(key)
        return r.cite() if r else None


MANIFESTS = [
    "requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "package.json",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "Gemfile", "environment.yml",
]

# Fallbacks used when a repo's guide does not say otherwise.
DEFAULT_BANNED = ["my-agent", "my-tool", "final-project", "final-test", "test", "demo", "helper"]


def _find(lines: list[str], pattern: str, fname: str) -> Optional[Rule]:
    rx = re.compile(pattern, re.I)
    for i, line in enumerate(lines, 1):
        if rx.search(line):
            text = re.sub(r"[*`]", "", line).lstrip("#>- ").strip()
            return Rule(text, f"{fname}:{i}")
    return None


def compile_policy(base_root: Path) -> Policy:
    """Derive a policy from CONTRIBUTING.md, template/ and the PR template."""
    p = Policy(manifest_files=list(MANIFESTS))
    contributing = base_root / "CONTRIBUTING.md"
    lines = contributing.read_text(encoding="utf-8").splitlines() if contributing.exists() else []
    text = "\n".join(lines)
    fn = "CONTRIBUTING.md"

    # Project roots: "agents/<project-slug>/" style paths.
    roots = []
    for m in re.finditer(r"([a-z0-9_-]+)/<project-slug>", text):
        if m.group(1) not in roots and (base_root / m.group(1)).is_dir():
            roots.append(m.group(1))
    p.project_roots = roots or [d.name for d in base_root.iterdir() if d.is_dir() and not d.name.startswith(".")]

    # Required files: whatever the guide tells contributors to copy from template/.
    for m in re.finditer(r"template/([\w.\-]+)", text):
        if m.group(1) not in p.required_files and (base_root / "template" / m.group(1)).exists():
            p.required_files.append(m.group(1))

    # Banned generic names: backticked words on the "generic names like" line.
    banned_line = next((l for l in lines if re.search(r"generic names", l, re.I)), "")
    banned = re.findall(r"`([a-z0-9-]+)`", banned_line)
    p.banned_names = sorted(set(banned) | set(DEFAULT_BANNED)) if banned else list(DEFAULT_BANNED)

    # Files a PR may touch outside its own directory (the index tables).
    for root in p.project_roots:
        if re.search(rf"{root}/README\.md", text) and re.search(r"index", text, re.I):
            p.index_files.append(f"{root}/README.md")

    # Required README sections = H2 headings of the template.
    tpl = base_root / "template" / "README.md"
    if tpl.exists():
        tpl_text = tpl.read_text(encoding="utf-8")
        p.readme_sections = [h.strip() for h in re.findall(r"^##\s+(.+)$", tpl_text, re.M)]
        p.template_placeholders = [
            ph for ph in ["[Project Name]", "[One-sentence summary", "Feature 1: Brief description",
                          "[Language Runtime", "Explain what specific problem"]
            if ph in tpl_text
        ]

    # PR template checklist items (bold label of each checkbox).
    prt = base_root / ".github" / "PULL_REQUEST_TEMPLATE.md"
    if prt.exists():
        p.checklist_items = re.findall(r"- \[ \] \*\*(.+?):?\*\*", prt.read_text(encoding="utf-8"))

    # Cite the sentence behind every deterministic check.
    citations = {
        "scope.outside-project": r"modify only files within",
        "scope.multiple-projects": r"Do not put multiple unrelated projects",
        "scope.root-deps": r"Do not add dependencies to the repository root",
        "naming.kebab-case": r"lowercase kebab-case",
        "naming.generic": r"generic names",
        "structure.required-file": r"Copy the shared template files",
        "structure.manifest": r"Always include a dependency manifest",
        "secrets.leaked": r"Never commit `?\.env`? files, API keys",
        "secrets.env-file": r"Never commit `?\.env`? files",
        "hygiene.tracked-junk": r"no real API keys, credentials, local databases, or virtual environments",
        "readme.sections": r"Fill out all relevant sections",
        "readme.examples": r"Example inputs and outputs must reflect genuine runs",
        "readme.limitations": r"Known Limitations",
        "env.undocumented": r"document them in your `README.md` and provide placeholder values",
        "safety.loops": r"uncontained execution loops",
    }
    for key, pat in citations.items():
        r = _find(lines, pat, fn)
        if r:
            p.rules[key] = r

    # Soft rules the LLM reviewer judges (anything not mechanically checkable).
    for pat in [r"Honest Documentation", r"Known Limitations", r"Safety & Respect",
                r"Licensing & Attribution", r"Reproducibility\*\*:"]:
        r = _find(lines, pat, fn)
        if r:
            p.soft_rules.append(r)
    return p
