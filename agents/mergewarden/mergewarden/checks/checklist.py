"""Verify the PR template checklist against the evidence.

Ticking a box is a claim. If the contributor ticked "No secrets" and we found
one, that is called out explicitly as a contradicted claim.
"""

from __future__ import annotations

import re

from ..models import Criterion, Finding, Severity, Submission
from ..policy import Policy

# PR-template label -> finding-id prefixes that would make the claim false.
EVIDENCE = {
    "directory & naming": ("naming.", "scope.no-project"),
    "documentation": ("readme.sections", "readme.placeholders", "structure.required-file"),
    "reproducible setup": ("setup.", "env.undocumented", "structure.manifest"),
    "core functionality tested": ("sandbox.failed",),
    "example usage": ("readme.examples",),
    "dependencies declared": ("structure.manifest",),
    "secrets & security": ("secrets.", "hygiene.tracked-junk"),
    "scope limitation": ("scope.",),
}


def parse(body: str) -> dict[str, bool]:
    out = {}
    for m in re.finditer(r"^\s*[-*]\s*\[([ xX])\]\s*\*{0,2}(.+?)(?::\*\*|\*\*:|\*\*|:)", body, re.M):
        out[m.group(2).strip().lower()] = m.group(1).lower() == "x"
    return out


def check(sub: Submission, policy: Policy, prior: list[Finding]) -> list[Finding]:
    if sub.number is None:  # local pre-flight: no PR description yet
        return []
    boxes = parse(sub.body or "")
    if not boxes:
        return [Finding(
            "checklist.missing", Severity.MINOR, Criterion.DOCUMENTATION,
            "The PR description does not include the Contribution Checklist from the PR template.",
            fix="Paste .github/PULL_REQUEST_TEMPLATE.md into the PR description and tick what is true.",
        )]
    out = []
    unticked = [k for k, v in boxes.items() if not v]
    if unticked:
        out.append(Finding(
            "checklist.unticked", Severity.MINOR, Criterion.DOCUMENTATION,
            f"Checklist items not confirmed: {', '.join(unticked)}.",
        ))
    for label, ticked in boxes.items():
        prefixes = next((v for k, v in EVIDENCE.items() if k in label), ())
        if not ticked or not prefixes:
            continue
        hits = [f for f in prior if f.check.startswith(prefixes) and f.severity.rank >= Severity.MAJOR.rank]
        if hits:
            out.append(Finding(
                "checklist.contradicted", Severity.MAJOR, hits[0].criterion,
                f"Checklist claims \"{label}\" but {len(hits)} finding(s) contradict it "
                f"(e.g. {hits[0].message})",
            ))
    return out
