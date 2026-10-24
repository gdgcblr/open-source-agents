"""Data models for BlastRadius Change Impact Analysis."""

from dataclasses import dataclass, field
from typing import List, Set, Optional, Dict, Any


@dataclass
class DiffHunk:
    """Represents a single unified diff hunk."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str
    modified_new_lines: Set[int] = field(default_factory=set)
    lines: List[str] = field(default_factory=list)


@dataclass
class FileDiff:
    """Represents the parsed diff for a single file."""
    old_path: str
    new_path: str
    hunks: List[DiffHunk] = field(default_factory=list)

    @property
    def all_modified_lines(self) -> Set[int]:
        """Collects all modified line numbers in the new file version."""
        lines = set()
        for h in self.hunks:
            lines.update(h.modified_new_lines)
        return lines


@dataclass
class JavaMethod:
    """Represents an extracted Java method or constructor."""
    package_name: str
    class_name: str
    method_name: str
    signature: str
    return_type: str
    modifiers: List[str]
    annotations: List[str]
    start_line: int
    end_line: int
    file_path: str
    is_constructor: bool = False

    @property
    def fq_name(self) -> str:
        """Full qualified method identifier."""
        pkg = f"{self.package_name}." if self.package_name else ""
        return f"{pkg}{self.class_name}#{self.method_name}"


@dataclass
class CallerReference:
    """Represents a discovered call site invoking a target method."""
    caller_file: str
    caller_class: str
    caller_method: str
    call_line: int
    target_method_name: str
    target_class_hint: Optional[str]
    code_snippet: str
    is_test: bool = False


@dataclass
class TestRecommendation:
    """Represents a recommended test to execute."""
    test_file: str
    test_class: str
    test_method: Optional[str]
    priority: str  # HIGH, MEDIUM, LOW
    reason: str
    call_line: Optional[int] = None


@dataclass
class RiskEvaluation:
    """Risk tier and rationale."""
    tier: str  # CRITICAL, HIGH, MEDIUM, LOW
    score: int  # 0 to 100
    factors: List[str] = field(default_factory=list)


@dataclass
class ImpactReport:
    """Comprehensive change impact report."""
    target_repo: str
    diff_file_count: int
    changed_methods: List[JavaMethod] = field(default_factory=list)
    callers: List[CallerReference] = field(default_factory=list)
    recommended_tests: List[TestRecommendation] = field(default_factory=list)
    uncovered_methods: List[JavaMethod] = field(default_factory=list)
    risk: Optional[RiskEvaluation] = None
    limitations: List[str] = field(default_factory=list)
    summary_notes: List[str] = field(default_factory=list)

