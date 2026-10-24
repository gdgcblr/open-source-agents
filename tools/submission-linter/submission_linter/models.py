"""Shared data types."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

ERROR = "error"
WARN = "warn"
INFO = "info"


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    path: str | None = None
    line: int | None = None
    hint: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    project: str
    findings: list[Finding] = field(default_factory=list)

    def add(self, *args, **kwargs) -> None:
        self.findings.append(Finding(*args, **kwargs))

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def errors(self) -> int:
        return self.count(ERROR)

    @property
    def warnings(self) -> int:
        return self.count(WARN)

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "summary": {
                "errors": self.errors,
                "warnings": self.warnings,
                "info": self.count(INFO),
            },
            "findings": [f.to_dict() for f in self.findings],
        }
