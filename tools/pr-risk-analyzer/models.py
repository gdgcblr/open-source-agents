from dataclasses import asdict, dataclass, field
from typing import Literal

Severity = Literal["critical", "high", "medium", "low", "info"]


@dataclass
class DiffLine:
    """A line within a Git diff."""

    kind: Literal["added", "deleted", "context"]
    content: str
    old_line_number: int | None = None
    new_line_number: int | None = None


@dataclass
class FileChange:
    """Changes detected for one file in a unified diff."""

    old_path: str | None
    new_path: str | None
    status: str = "modified"
    lines: list[DiffLine] = field(default_factory=list)
    is_binary: bool = False

    @property
    def path(self) -> str:
        """Prefer the new path, falling back to the old path."""
        return self.new_path or self.old_path or "<unknown>"

    @property
    def added_lines(self) -> list[DiffLine]:
        return [line for line in self.lines if line.kind == "added"]

    @property
    def deleted_lines(self) -> list[DiffLine]:
        return [line for line in self.lines if line.kind == "deleted"]


@dataclass
class Finding:
    """One review signal produced by a rule."""

    rule_id: str
    title: str
    severity: Severity
    message: str
    file_path: str | None = None
    line_number: int | None = None
    evidence: str | None = None
    recommendation: str = ""
    confidence: str = "medium"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnalysisReport:
    """The complete result of analyzing a diff."""

    findings: list[Finding]
    files_changed: int
    additions: int
    deletions: int

    def to_dict(self) -> dict:
        return {
            "summary": {
                "files_changed": self.files_changed,
                "additions": self.additions,
                "deletions": self.deletions,
                "findings": len(self.findings),
                "severity_counts": {
                    severity: sum(
                        finding.severity == severity
                        for finding in self.findings
                    )
                    for severity in (
                        "critical", "high", "medium", "low", "info"
                    )
                },
            },
            "findings": [finding.to_dict() for finding in self.findings],
        }