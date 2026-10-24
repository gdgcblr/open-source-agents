"""Docs & developer experience: README completeness against template/README.md, leftover placeholders,
examples, architecture, limitations, configuration and security notes."""

from __future__ import annotations

import re

from judge.models import AnalyzerResult, Check, Finding
from judge.workspace import Workspace

DIM = "docs"

# Sections of template/README.md and alternative words contributors commonly use.
TEMPLATE_SECTIONS: dict[str, tuple[str, ...]] = {
    "Overview": ("overview", "about", "introduction", "problem", "what it does"),
    "Technical Stack": ("technical stack", "tech stack", "stack", "technologies", "built with"),
    "Architecture & Data Flow": ("architecture", "data flow", "how it works", "design"),
    "Prerequisites": ("prerequisites", "requirements"),
    "Installation & Setup": ("installation", "setup", "getting started", "install"),
    "Configuration & Environment Variables": ("configuration", "environment variables", "env", "config"),
    "How to Run": ("how to run", "usage", "running", "run"),
    "Example Input & Output": ("example", "examples", "demo", "sample"),
    "How to Test": ("test", "testing"),
    "Known Limitations": ("limitations", "known issues", "caveats"),
    "Security & Privacy Considerations": ("security", "privacy"),
    "Future Improvements": ("future", "roadmap", "improvements", "todo"),
    "License": ("license",),
}

# Text that only appears when a template section was copied but never filled in.
PLACEHOLDERS = [
    r"\[Project Name\]",
    r"\[One-sentence summary",
    r"Feature 1: Brief description",
    r"Explain what specific problem or challenge",
    r"Who is this tool or agent built for\?",
    r"\[Language Runtime",
    r"\[Package manager",
    r"\[Required API keys",
    r"Provide the exact command\(s\)",
    r"Analyze the repository structure of gdgcblr/open-source-agents",
    r"Be honest about constraints, edge cases",
    r"Explain how another developer or reviewer can verify",
    r"How are credentials loaded and protected\?",
    r"Specify the license for this subproject",
    r"Provide a brief explanation or diagram showing",
    r"e\.g\., Rate limits on free-tier APIs may cause",
    r"Add caching for external API responses\.",
    r"\(Add any additional variables your project requires",
]
PLACEHOLDER_RE = re.compile("|".join(PLACEHOLDERS))
HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$", re.M)


def sections(readme: str) -> list[tuple[str, str, int]]:
    """(heading, body, line) for every markdown heading; a body includes its sub-sections."""
    fences = [(m.start(), m.end()) for m in re.finditer(r"```.*?```", readme, re.S)]
    matches = [m for m in HEADING.finditer(readme) if not any(a <= m.start() < b for a, b in fences)]
    out = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        nxt = next((n for n in matches[i + 1 :] if len(n.group(1)) <= level), None)
        end = nxt.start() if nxt else len(readme)
        out.append((m.group(2).strip(), readme[m.end() : end].strip(), readme[: m.start()].count("\n") + 1))
    return out


def _find(secs: list[tuple[str, str, int]], keys: tuple[str, ...]) -> tuple[str, str, int] | None:
    for heading, body, line in secs:
        h = re.sub(r"[^a-z ]", " ", heading.lower())
        if any(re.search(rf"\b{re.escape(k)}\b", h) for k in keys):
            return heading, body, line
    return None


def analyze(ws: Workspace) -> AnalyzerResult:
    r = AnalyzerResult()
    readme = ws.readme
    rel = ws.readme_path or "README.md"
    words = len(re.findall(r"\w+", readme))
    r.checks.append(
        Check(
            id="readme",
            dimension=DIM,
            label="README exists and is substantial",
            weight=2,
            status="fail" if not readme else "pass" if words >= 300 else "warn",
            score=min(1.0, words / 400) if readme else 0.0,
            detail=f"{words} words" if readme else "No README",
            fix="Write a README from template/README.md." if words < 300 else None,
        )
    )
    if not readme:
        return r

    secs = sections(readme)
    present = {name: _find(secs, keys) for name, keys in TEMPLATE_SECTIONS.items()}
    have = [n for n, s in present.items() if s and len(s[1]) > 20]
    missing = [n for n in TEMPLATE_SECTIONS if n not in have]
    cov = len(have) / len(TEMPLATE_SECTIONS)
    r.checks.append(
        Check(
            id="sections",
            dimension=DIM,
            label="Covers the template's sections",
            weight=3,
            status="pass" if cov >= 0.8 else "warn" if cov >= 0.5 else "fail",
            score=cov,
            detail=f"{len(have)}/{len(TEMPLATE_SECTIONS)} sections"
            + (f"; missing: {', '.join(missing)}" if missing else ""),
            fix=f"Add: {', '.join(missing[:4])}." if missing else None,
        )
    )

    leftovers = []
    for i, line in enumerate(readme.splitlines(), 1):
        if PLACEHOLDER_RE.search(line):
            leftovers.append(i)
            r.findings.append(
                Finding(
                    dimension=DIM,
                    severity="low",
                    title="Template placeholder left in README",
                    file=rel,
                    line=i,
                    snippet=line.strip()[:160],
                    fix="Replace the template text with details of your project.",
                )
            )
    n = len(leftovers)
    r.checks.append(
        Check(
            id="placeholders",
            dimension=DIM,
            label="No unfilled template placeholders",
            weight=3,
            status="pass" if n == 0 else "warn" if n <= 2 else "fail",
            score=max(0.0, 1 - n / 6),
            detail=f"{n} placeholder line(s)" if n else "None left",
        )
    )

    ex = present["Example Input & Output"]
    ex_ok = bool(ex and "```" in ex[1] and not PLACEHOLDER_RE.search(ex[1]))
    r.checks.append(
        Check(
            id="examples",
            dimension=DIM,
            label="Real example input and output",
            weight=2,
            status="pass" if ex_ok else "warn" if ex else "fail",
            detail="Example with code block" if ex_ok else "Missing or still the template example",
            fix=None if ex_ok else "Paste a genuine run: the exact input and the output it produced.",
        )
    )

    arch = present["Architecture & Data Flow"]
    diagram = bool(arch and ("```" in arch[1] or "mermaid" in arch[1] or "![" in arch[1]))
    r.checks.append(
        Check(
            id="architecture",
            dimension=DIM,
            label="Architecture explained (ideally with a diagram)",
            weight=1,
            status="pass" if diagram else "warn" if arch else "fail",
            score=1.0 if diagram else 0.6 if arch else 0.0,
            detail="Diagram included" if diagram else "Prose only" if arch else "Missing",
        )
    )

    lim = present["Known Limitations"]
    lim_ok = bool(lim and len(lim[1]) > 40 and not PLACEHOLDER_RE.search(lim[1]))
    r.checks.append(
        Check(
            id="limitations",
            dimension=DIM,
            label="Honest known limitations",
            weight=1,
            status="pass" if lim_ok else "warn" if lim else "fail",
            detail="Documented" if lim_ok else "Missing or template text",
        )
    )

    sec = present["Security & Privacy Considerations"]
    r.checks.append(
        Check(
            id="security_notes",
            dimension=DIM,
            label="Security & privacy notes",
            weight=1,
            status="pass" if sec and len(sec[1]) > 40 and not PLACEHOLDER_RE.search(sec[1]) else "warn",
            detail="Documented" if sec else "Missing",
        )
    )

    r.facts.update(readme_words=words, sections_present=have, sections_missing=missing, placeholders=n)
    return r
