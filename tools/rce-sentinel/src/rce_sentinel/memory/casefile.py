"""Per-run case file and distilled handoffs.

The case file is a compact, model-agnostic summary handed to whichever model runs next.
Its stable part is sorted and byte-identical across runs of an unchanged repo, so it sits
in the cacheable prompt prefix. On escalation, the next tier gets a short handoff with
findings and open questions, not the previous transcript.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from rce_sentinel.models import Dependency, Finding, Verdict
from rce_sentinel.scanner.rules import PyModule

MAX_MAP_LINES = 120


@dataclass
class CaseFile:
    repo_map: list[str] = field(default_factory=list)
    deps: list[str] = field(default_factory=list)
    sinks: list[str] = field(default_factory=list)

    @classmethod
    def build(cls, modules: list[PyModule], other_files: list[str], deps: list[Dependency],
              findings: list[Finding]) -> CaseFile:
        repo_map = []
        for mod in sorted(modules, key=lambda m: m.path):
            defs = [n.name for n in mod.tree.body
                    if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)]
            repo_map.append(f"{mod.path}: {', '.join(defs[:12])}")
        repo_map += sorted(other_files)
        return cls(
            repo_map=repo_map[:MAX_MAP_LINES],
            deps=sorted({f"{d.ecosystem}:{d.name}=={d.version}" for d in deps if d.version}),
            sinks=sorted({f"{f.file}:{f.line} {f.rule_id}" for f in findings
                          if f.layer != "dependency"}),
        )

    def stable_text(self) -> str:
        return ("CASE FILE\nrepo map:\n" + "\n".join(self.repo_map)
                + "\ndependencies:\n" + "\n".join(self.deps[:80]) + "\n")

    def volatile_text(self) -> str:
        return "sinks this run:\n" + "\n".join(self.sinks[:40]) + "\n"


def handoff(finding: Finding, verdict: Verdict | None, reason: str, tier: str,
            caveman: bool) -> str:
    """Distilled escalation note for the next tier."""
    if verdict is None:
        got = "no valid answer"
    else:
        got = f"{verdict.verdict} conf={verdict.confidence:.2f}"
        if verdict.evidence:
            e = verdict.evidence[0]
            got += f" cited {e.file}:{e.line}"
    if caveman:
        return (f"HANDOFF {tier}: {finding.rule_id} {finding.file}:{finding.line}. "
                f"prev={got}. escalate why: {reason}. open: is data attacker-controlled? "
                "is sink reached?")
    return (f"Handoff from {tier}: {finding.rule_id} at {finding.file}:{finding.line}. "
            f"Previous answer: {got}. Escalated because: {reason}. Open questions: is the "
            "data attacker-controlled, and does it reach the sink?")
