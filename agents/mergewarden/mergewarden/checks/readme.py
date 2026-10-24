"""README completeness plus a "setup lint": do the commands in the README
reference files and scripts that actually exist in the submission?"""

from __future__ import annotations

import difflib
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


# Sections where reusing the template's wording is fine (generic setup steps, license line).
TEMPLATE_OK = {"installation & setup", "license"}


def _match(heading: str, want: str) -> float:
    """How well a README heading matches a required section name (0 = no match).

    A heading must keep at least 4 letters after normalising, so `## 🚀` or
    `## 1.` can't stand in for every section.
    """
    n, w = _norm(heading), _norm(want)
    if len(n) < 4:
        return 0.0
    if n == w:
        return 1.0
    if len(w) >= 4 and w in n:  # "Installation & Setup Guide"
        return 0.95
    ratio = difflib.SequenceMatcher(None, n, w).ratio()
    return ratio if ratio >= 0.75 else 0.0


def _find_section(secs: dict[str, str], want: str, used: set[str] | None = None) -> str | None:
    """Body of the best-matching heading. With `used`, each heading is claimed at most once."""
    best, score = None, 0.0
    for k in secs:
        if used is not None and k in used:
            continue
        sc = _match(k, want)
        if sc > score:
            best, score = k, sc
    if best is None:
        return None
    if used is not None:
        used.add(best)
    return secs[best]


def _prose(line: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[*_`>#|]", "", line)).strip().lower()


def check(sub: Submission, policy: Policy) -> list[Finding]:
    out: list[Finding] = []
    if not sub.project_dir:
        return out
    md = sub.read("README.md")
    rf = f"{sub.project_dir}/README.md"
    if not md:
        return out  # structure check already reports the missing file
    secs = sections(md)

    missing, empty, copied = [], [], []
    used: set[str] = set()
    for want in policy.readme_sections:
        body = _find_section(secs, want, used)
        if body is None:
            missing.append(want)
            continue
        if len(re.sub(r"\s|-{3,}", "", body)) < 25 and "n/a" not in body.lower():
            empty.append(want)
        if want.lower() not in TEMPLATE_OK:
            mine = {_prose(l) for l in body.splitlines()}
            hit = next((t for t in policy.template_lines.get(want, []) if _prose(t) in mine), None)
            if hit:
                copied.append((want, hit))
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

    for want, line in copied:
        # Template example bullets ("- e.g., Rate limits...") pretend to be facts; an
        # instruction sentence left in place is only untidy.
        example = line.lstrip().startswith(("-", "*", "1.")) or "e.g" in line.lower()
        out.append(Finding(
            "readme.template-copied", Severity.MAJOR if example else Severity.MINOR, Criterion.DOCUMENTATION,
            f"The '{want}' section still contains text copied from the template: \"{_prose(line)[:90]}\".",
            file=rf, fix=f"Replace the template's example text in '{want}' with facts about your own project.",
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
