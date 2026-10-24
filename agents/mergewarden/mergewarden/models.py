"""Core data types shared by every check, agent and report."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class Severity(str, Enum):
    BLOCKER = "blocker"  # PR must not be merged (e.g. leaked secret)
    MAJOR = "major"  # must be fixed before merge
    MINOR = "minor"  # should be fixed, does not block
    INFO = "info"  # observation for the maintainer

    @property
    def rank(self) -> int:
        return ["info", "minor", "major", "blocker"].index(self.value)


class Criterion(str, Enum):
    """The four review criteria every contribution is scored against."""

    REPRODUCIBILITY = "Reproducibility"
    DOCUMENTATION = "Documentation"
    SECURITY = "Security & Privacy"
    SCOPE = "Focused Scope"


class Verdict(str, Enum):
    READY = "ready"
    CHANGES_REQUESTED = "changes_requested"
    BLOCKED = "blocked"


@dataclass
class Finding:
    check: str  # stable id, e.g. "secrets.leaked-key"
    severity: Severity
    criterion: Criterion
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    fix: Optional[str] = None
    rule: Optional[str] = None  # the policy rule this enforces, with its citation
    source: str = "deterministic"  # "deterministic" or "llm"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["criterion"] = self.criterion.value
        return d


@dataclass
class Submission:
    """Everything the gatekeeper knows about one contribution."""

    root: Path  # checkout of the head of the contribution (read-only use)
    project_dir: Optional[str]  # e.g. "agents/my-agent" (repo-relative)
    changed_files: list[str]  # repo-relative paths touched by the PR
    title: str = ""
    body: str = ""  # PR description (where the checklist lives)
    url: Optional[str] = None
    author: Optional[str] = None
    number: Optional[int] = None
    # Repo-relative files git would commit. None = every file under root counts.
    tracked: Optional[set[str]] = None
    # Snapshot of the base branch (CONTRIBUTING.md, template/, existing agents/ and tools/).
    base_root: Optional[Path] = None

    @property
    def project_path(self) -> Optional[Path]:
        return self.root / self.project_dir if self.project_dir else None

    def project_files(self) -> list[Path]:
        p = self.project_path
        if not p or not p.is_dir():
            return []
        files = (f for f in p.rglob("*") if f.is_file() and ".git" not in f.parts)
        if self.tracked is not None:
            files = (f for f in files if str(f.relative_to(self.root)) in self.tracked)
        return sorted(files)

    def read(self, name: str) -> str:
        """Read a project file (relative to the project folder), '' if absent."""
        p = self.project_path / name if self.project_path else None
        try:
            return p.read_text(encoding="utf-8") if p and p.is_file() else ""
        except (UnicodeDecodeError, OSError):
            return ""


@dataclass
class Report:
    submission: Submission
    findings: list[Finding] = field(default_factory=list)
    llm_used: bool = False
    sandbox: Optional[dict] = None
    review_markdown: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> Verdict:
        worst = max((f.severity.rank for f in self.findings), default=0)
        if worst >= Severity.BLOCKER.rank:
            return Verdict.BLOCKED
        if worst >= Severity.MAJOR.rank:
            return Verdict.CHANGES_REQUESTED
        return Verdict.READY

    def scores(self) -> dict[str, int]:
        """0-100 per criterion. Deductions: blocker 60, major 25, minor 8."""
        penalty = {Severity.BLOCKER: 60, Severity.MAJOR: 25, Severity.MINOR: 8, Severity.INFO: 0}
        out = {c.value: 100 for c in Criterion}
        for f in self.findings:
            out[f.criterion.value] = max(0, out[f.criterion.value] - penalty[f.severity])
        return out

    def score(self) -> int:
        s = self.scores()
        return round(sum(s.values()) / len(s))
