"""Data models for MergeReady validation findings, verdicts, and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Severity(str, Enum):
    """Severity levels for findings."""

    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"

    @classmethod
    def from_str(cls, val: str) -> Severity:
        upper = val.upper()
        if upper in ("WARN", "WARNING"):
            return cls.WARNING
        if upper == "INFO":
            return cls.INFO
        return cls.ERROR


class Verdict(str, Enum):
    """Evaluation verdict for individual rules and overall validation.
    
    Blocking Statuses for Overall PASS:
      - FAIL: Contribution violates repository policy. Blocks PASS (exit code 1).
      - ERROR: Validator crashed or execution could not complete. Blocks PASS (exit code 2).
      - Unexpected SKIP / NA on required rules: Blocks PASS (exit code 2).
      - WARN (under --strict): Blocks PASS (exit code 1).
    """

    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    WARN = "WARN"
    SKIP = "SKIP"
    NA = "N/A"


@dataclass
class Finding:
    """A concrete, evidence-backed issue or recommendation."""

    rule_id: str
    severity: Severity
    message: str
    path: Optional[str] = None
    line: Optional[int] = None
    evidence: Optional[str] = None
    fix: Optional[str] = None
    source_rule: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "message": self.message,
            "path": self.path,
            "line": self.line,
            "evidence": self.evidence,
            "fix": self.fix,
            "source_rule": self.source_rule,
        }


@dataclass
class RuleResult:
    """The outcome of running a specific check rule."""

    rule_id: str
    name: str
    verdict: Verdict
    reason: Optional[str] = None
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "findings": [f.to_dict() for f in self.findings],
        }


@dataclass
class ValidationReport:
    """Aggregated validation report across all evaluated rules."""

    project_path: str
    category: str
    slug: str
    base_ref: Optional[str] = None
    results: dict[str, RuleResult] = field(default_factory=dict)
    summary: dict[str, int] = field(default_factory=dict)
    execution_errors: list[str] = field(default_factory=list)

    def add_result(self, result: RuleResult) -> None:
        if result.rule_id in self.results:
            existing = self.results[result.rule_id]
            # Severity priority: ERROR > FAIL > WARN > SKIP / NA > PASS
            priority = {
                Verdict.ERROR: 4,
                Verdict.FAIL: 3,
                Verdict.WARN: 2,
                Verdict.SKIP: 1,
                Verdict.NA: 1,
                Verdict.PASS: 0,
            }
            if priority.get(existing.verdict, 0) > priority.get(result.verdict, 0):
                # Existing has higher severity; keep existing verdict and merge findings
                existing.findings.extend(result.findings)
                if not existing.reason and result.reason:
                    existing.reason = result.reason
                self.recompute_summary()
                return
            elif priority.get(result.verdict, 0) > priority.get(existing.verdict, 0):
                # New has higher severity; replace verdict and merge findings
                result.findings.extend(existing.findings)
                self.results[result.rule_id] = result
                self.recompute_summary()
                return
            else:
                existing.findings.extend(result.findings)
                self.recompute_summary()
                return

        self.results[result.rule_id] = result
        self.recompute_summary()

    def recompute_summary(self) -> None:
        counts = {
            "pass": 0,
            "fail": 0,
            "error": 0,
            "warn": 0,
            "skip": 0,
            "na": 0,
            "findings_total": 0,
            "errors": 0,
            "warnings": 0,
            "infos": 0,
        }
        for res in self.results.values():
            if res.verdict == Verdict.PASS:
                counts["pass"] += 1
            elif res.verdict == Verdict.FAIL:
                counts["fail"] += 1
            elif res.verdict == Verdict.ERROR:
                counts["error"] += 1
            elif res.verdict == Verdict.WARN:
                counts["warn"] += 1
            elif res.verdict == Verdict.SKIP:
                counts["skip"] += 1
            elif res.verdict == Verdict.NA:
                counts["na"] += 1

            for f in res.findings:
                counts["findings_total"] += 1
                if f.severity == Severity.ERROR:
                    counts["errors"] += 1
                elif f.severity == Severity.WARNING:
                    counts["warnings"] += 1
                elif f.severity == Severity.INFO:
                    counts["infos"] += 1

        self.summary = counts

    @property
    def has_execution_errors(self) -> bool:
        """True if validator crashed, rule output was malformed, or config was invalid."""
        return (
            len(self.results) == 0
            or self.summary.get("error", 0) > 0
            or len(self.execution_errors) > 0
        )

    @property
    def has_failures(self) -> bool:
        """True if any rule failed, policy error finding was emitted, or validator crashed."""
        return (
            self.summary.get("fail", 0) > 0
            or self.summary.get("errors", 0) > 0
            or self.has_execution_errors
        )

    @property
    def has_warnings(self) -> bool:
        return self.summary.get("warn", 0) > 0 or self.summary.get("warnings", 0) > 0

    @property
    def has_skips(self) -> bool:
        return self.summary.get("skip", 0) > 0

    @property
    def final_verdict(self) -> Verdict:
        """Centralized, immutable final verdict computation. No individual rule can override this."""
        if len(self.results) == 0:
            return Verdict.ERROR
        if self.has_execution_errors:
            return Verdict.ERROR
        if self.has_failures:
            return Verdict.FAIL
        if self.has_warnings:
            return Verdict.WARN
        return Verdict.PASS

    def exit_code(self, strict: bool = False) -> int:
        if self.has_execution_errors:
            return 2  # Operational / validator execution error
        if self.has_failures:
            return 1  # Policy violation failure
        if strict and (self.has_warnings or self.has_skips):
            return 1
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_path": self.project_path,
            "category": self.category,
            "slug": self.slug,
            "base_ref": self.base_ref,
            "final_verdict": self.final_verdict.value,
            "summary": self.summary,
            "execution_errors": list(self.execution_errors),
            "results": {k: v.to_dict() for k, v in self.results.items()},
        }
