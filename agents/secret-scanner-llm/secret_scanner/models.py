"""Data models. Nothing in here ever holds a raw secret value."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

VERDICTS = ("real", "placeholder", "test_fixture", "false_positive")
# "unverified": no LLM verdict available (--no-llm or LLM error). "uncertain": LLM wanted to
# dismiss but with too little confidence. Both stay reportable.
REPORTABLE_VERDICTS = ("real", "unverified", "uncertain")
SEVERITIES = ("info", "low", "medium", "high", "critical")


@dataclass
class Candidate:
    """Stage-1 (deterministic) candidate. `redacted_value` / `context` are already redacted."""

    file: str
    line: int
    rule: str
    kind: str
    redacted_value: str
    context: list[str]
    high_confidence_format: bool = False
    in_test_path: bool = False
    base_severity: str = "medium"
    hints: list[str] = field(default_factory=list)
    injection_suspected: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TriageResult:
    verdict: str
    confidence: float
    reason: str
    remediation: str = ""
    model: str = ""
    seconds: float = 0.0


@dataclass
class Finding:
    candidate: Candidate
    verdict: str  # one of VERDICTS + unverified/uncertain
    confidence: float
    reason: str
    remediation: str
    severity: str
    decided_by: str  # "llm" | "policy" | "none"
    llm_note: str = ""
    llm_seconds: float = 0.0

    @property
    def reportable(self) -> bool:
        return self.verdict in REPORTABLE_VERDICTS

    def to_dict(self) -> dict:
        c = self.candidate
        return {
            "file": c.file,
            "line": c.line,
            "rule": c.rule,
            "kind": c.kind,
            "redacted_value": c.redacted_value,
            "context": c.context,
            "high_confidence_format": c.high_confidence_format,
            "in_test_path": c.in_test_path,
            "severity": self.severity,
            "verdict": self.verdict,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "remediation": self.remediation,
            "decided_by": self.decided_by,
            "llm_note": self.llm_note,
            "llm_seconds": round(self.llm_seconds, 3),
        }
