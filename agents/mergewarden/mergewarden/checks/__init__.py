"""Deterministic checks. No network, no LLM: same input, same findings."""

from __future__ import annotations

from ..models import Finding, Submission
from ..policy import Policy
from . import checklist, envvars, injection, readme, safety, scope, secrets, structure

STATIC_CHECKS = [scope, structure, secrets, readme, envvars, injection, safety]


def run_static(sub: Submission, policy: Policy, extra: list[Finding] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for mod in STATIC_CHECKS:
        findings += mod.check(sub, policy)
    findings += extra or []
    # The checklist is verified last, against everything found so far.
    findings += checklist.check(sub, policy, findings)
    return findings
