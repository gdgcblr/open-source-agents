"""Shared data structures."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

SEVERITIES = ("critical", "high", "medium", "low", "info")
SEVERITY_RANK = {name: i for i, name in enumerate(SEVERITIES)}  # lower = worse


@dataclass
class Finding:
    file: str
    line: int
    severity: str  # one of SEVERITIES
    category: str  # security | bug | quality | testing | performance | style
    title: str
    detail: str
    suggestion: str = ""
    source: str = "rule"  # which reviewer produced it

    def key(self) -> tuple:
        return (self.file, self.line, self.title.lower())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReviewResult:
    summary: str
    verdict: str  # APPROVE | COMMENT | REQUEST_CHANGES
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)  # non-fatal problems (e.g. LLM down)

    def counts(self) -> dict:
        out = {s: 0 for s in SEVERITIES}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "verdict": self.verdict,
            "counts": self.counts(),
            "stats": self.stats,
            "notes": self.notes,
            "findings": [f.to_dict() for f in self.findings],
        }
