"""README completeness plus a "setup lint": do the commands in the README
reference files and scripts that actually exist in the submission?"""

from __future__ import annotations

import json
import re

from ..models import Criterion, Finding, Severity, Submission
from ..policy import Policy

CODE_BLOCK = re.compile(r"```[\w-]*\n(.*?)```", re.S)


def sections(md: str) -> dict[str, str]:
    """Map H2 heading -> body text."""
    out: dict[str, str] = {}
    parts = re.split(r"^##\s+(.+)$", md, flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        out[parts[i].strip()] = parts[i + 1]
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def _find_section(secs: dict[str, str], want: str) -> str | None:
    w = _norm(want)
    for k, v in secs.items():
        n = _norm(k)
        if n == w or w in n or n in w or (w[:8] and n.startswith(w[:8])):
            return v
    return None


def check(sub: Submission, policy: Policy) -> list[Finding]:
    out: list[Finding] = []
    if not sub.project_dir:
        return out
    md = sub.read("README.md")
    rf = f"{sub.project_dir}/README.md"
    if not md:
        return out  # structure check already reports the missing file
    secs = sections(md)

    missing, empty = [], []
    for want in policy.readme_sections:
        body = _find_section(secs, want)
        if body is None:
            missing.append(want)
        elif len(re.sub(r"\s|-{3,}", "", body)) < 25 and "n/a" not in body.lower():
            empty.append(want)
    if missing:
        out.append(Finding(
            "readme.sections", Severity.MAJOR if len(missing) > 2 else Severity.MINOR, Criterion.DOCUMENTATION,
            f"README is missing template sections: {', '.join(missing)}.", file=rf,
            fix="Add each section from template/README.md; write `N/A` plus a reason if one doesn't apply.",
            rule=policy.rule("readme.sections"),
        ))
    if empty:
        out.append(Finding(
            "readme.empty-sections", Severity.MINOR, Criterion.DOCUMENTATION,
            f"README sections with almost no content: {', '.join(empty)}.", file=rf,
            rule=policy.rule("readme.sections"),
        ))

    left = [ph for ph in policy.template_placeholders if ph in md]
    if left:
        out.append(Finding(
            "readme.placeholders", Severity.MAJOR, Criterion.DOCUMENTATION,
            f"README still contains template placeholder text: {', '.join(repr(p) for p in left)}.", file=rf,
            rule=policy.rule("readme.sections"),
        ))

    ex = _find_section(secs, "Example Input & Output")
    if ex is not None and not CODE_BLOCK.search(ex):
        out.append(Finding(
            "readme.examples", Severity.MINOR, Criterion.DOCUMENTATION,
            "The Example Input & Output section has no example run (no code block).", file=rf,
            rule=policy.rule("readme.examples"),
        ))
    if ex is not None and "gdgcblr/open-source-agents and list the core directories" in ex:
        out.append(Finding(
            "readme.examples", Severity.MAJOR, Criterion.DOCUMENTATION,
            "The example input/output is copied unchanged from the template, not a genuine run.", file=rf,
            rule=policy.rule("readme.examples"),
        ))

    out += _setup_lint(sub, md, rf, policy)
    return out


def _setup_lint(sub: Submission, md: str, rf: str, policy: Policy) -> list[Finding]:
    out: list[Finding] = []
    proj = sub.project_path
    slug = sub.project_dir.split("/")[-1]
    cmds = [l.strip() for b in CODE_BLOCK.findall(md) for l in b.splitlines()
            if l.strip() and not l.strip().startswith("#")]
    pkg = {}
    if (proj / "package.json").exists():
        try:
            pkg = json.loads((proj / "package.json").read_text(encoding="utf-8"))
        except ValueError:
            out.append(Finding("setup.bad-manifest", Severity.MAJOR, Criterion.REPRODUCIBILITY,
                               "package.json is not valid JSON.", file=f"{sub.project_dir}/package.json"))
    broken: list[str] = []
    for c in cmds:
        c = c.lstrip("$ ")
        m = re.search(r"\bcd\s+((?:agents|tools)/[\w.\-<>]+)", c)
        if m and m.group(1) != sub.project_dir and "<" not in m.group(1):
            broken.append(f"`{c}` (your folder is `{sub.project_dir}`)")
        for m in re.finditer(r"-r\s+([\w./\-]+\.txt)", c):
            if not (proj / m.group(1)).exists():
                broken.append(f"`{c}` ({m.group(1)} does not exist)")
        m = re.match(r"(?:python3?|uv run|poetry run python)\s+([\w./\-]+\.py)\b", c)
        if m and not (proj / m.group(1)).exists():
            broken.append(f"`{c}` ({m.group(1)} does not exist)")
        m = re.match(r"(?:python3?)\s+-m\s+([\w.]+)", c)
        if m:
            mod = m.group(1).split(".")[0]
            if mod not in {"venv", "pip", "pytest", "http", "unittest", "build"} and not (
                (proj / mod).is_dir() or (proj / f"{mod}.py").exists() or (proj / "src" / mod).is_dir()
            ):
                broken.append(f"`{c}` (module `{mod}` not found in project)")
        m = re.match(r"(?:npm|pnpm|yarn)\s+(?:run\s+)?(start|dev|test|build|[\w:-]+)$", c)
        if m and pkg is not None and m.group(1) not in {"install", "i", "ci"}:
            if not pkg:
                broken.append(f"`{c}` (no package.json)")
            elif m.group(1) not in pkg.get("scripts", {}):
                broken.append(f"`{c}` (no `{m.group(1)}` script in package.json)")
        if re.match(r"cp\s+\.env\.example", c) and not (proj / ".env.example").exists():
            broken.append(f"`{c}` (.env.example does not exist)")
    for b in dict.fromkeys(broken):
        out.append(Finding(
            "setup.broken-command", Severity.MAJOR, Criterion.REPRODUCIBILITY,
            f"README setup command will fail on a fresh clone: {b}.", file=rf,
            rule=policy.rule("readme.sections"),
        ))
    return out
