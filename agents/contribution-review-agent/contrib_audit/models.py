"""Data models for the contribution audit system."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Verdict(str, Enum):
    READY = "READY"
    APPROVE_WITH_NITS = "APPROVE_WITH_NITS"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    REJECT = "REJECT"


@dataclass
class Finding:
    """A single audit finding."""
    rule_id: str
    severity: Severity
    file: Optional[Path]
    line: Optional[int]
    message: str
    evidence: Optional[str]   # always redacted
    fix_hint: str

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "file": str(self.file) if self.file else None,
            "line": self.line,
            "message": self.message,
            "evidence": self.evidence,
            "fix_hint": self.fix_hint,
        }


@dataclass
class AuditResult:
    """Aggregated result of a full audit run."""
    project_path: Path
    project_name: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def verdict(self) -> Verdict:
        severities = {f.severity for f in self.findings}
        for f in self.findings:
            if f.severity == Severity.ERROR and f.rule_id == "R07":
                return Verdict.REJECT
        if Severity.ERROR in severities:
            return Verdict.CHANGES_REQUESTED
        if Severity.WARNING in severities:
            return Verdict.APPROVE_WITH_NITS
        return Verdict.READY

    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]

    def infos(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.INFO]

    def to_dict(self) -> dict:
        return {
            "project_path": str(self.project_path),
            "project_name": self.project_name,
            "verdict": self.verdict.value,
            "findings": [f.to_dict() for f in self.findings],
        }
