"""Data types shared across the toolkit. All are plain dataclasses that serialize to JSON."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["info", "warning", "error"]
Evidence_Status = Literal["documented", "experimentally-verified", "unverified"]
TaskType = Literal["coding", "research", "extraction", "writing", "general"]
SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}


# ----------------------------------------------------------------------------- profiles


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    url: str


@dataclass(frozen=True)
class Guideline:
    """One documented piece of model-specific guidance."""

    id: str
    kind: str  # "structure" (drives a structural patch) or "advice" (reported as a diagnostic)
    text: str
    source: Source
    section: str
    evidence: Evidence_Status
    severity: Severity = "info"
    when: dict[str, Any] = field(default_factory=dict)
    augments: str | None = None  # rule id whose diagnostic this advice is attached to


@dataclass(frozen=True)
class Capability:
    name: str
    summary: str
    source: Source
    evidence: Evidence_Status


@dataclass(frozen=True)
class Variant:
    """Model-specific overrides inside a provider profile (models of one provider differ)."""

    id: str
    match: tuple[str, ...]
    guidelines: tuple[Guideline, ...]
    capabilities: tuple[Capability, ...]


@dataclass(frozen=True)
class ModelProfile:
    id: str
    provider: str
    display_name: str
    profile_version: str
    last_verified: str
    aliases: tuple[str, ...]
    match: tuple[str, ...]
    style: str  # "xml" or "markdown"
    constraints_position: str  # "before" or "after" the request
    long_context_reminder: bool
    sources: tuple[Source, ...]
    capabilities: tuple[Capability, ...]
    guidelines: tuple[Guideline, ...]
    variants: tuple[Variant, ...] = ()
    variant: str | None = None  # set when a model-specific variant was merged in


@dataclass(frozen=True)
class HarnessProfile:
    id: str
    display_name: str
    mode: str  # "rewrite" (return a new prompt) or "augment" (return side context only)
    description: str
    default_model_profile: str | None = None
    model_env: tuple[str, ...] = ()
    max_context_chars: int | None = None


@dataclass
class Resolution:
    profile: ModelProfile
    model: str | None
    matched: bool  # False when we fell back to the generic profile
    how: str  # "exact-id", "alias", "pattern", "harness-default" or "fallback"


# ----------------------------------------------------------------------------- analysis


@dataclass
class Evidence:
    text: str
    start: int
    end: int


@dataclass
class Requirement:
    """An explicit requirement stated by the user. These are locked: enhancement must keep them verbatim."""

    id: str
    kind: str  # constraint | format | length | literal | technology | audience
    text: str
    start: int
    end: int


@dataclass
class Patch:
    """A minimal proposed edit against the original prompt's character offsets."""

    id: str
    rule_id: str
    op: str  # "insert" (start == end), "replace", or "wrap" (prefix `new` at 0, `suffix` at the end)
    start: int
    end: int
    new: str
    rationale: str
    auto: bool = False  # applied by default without being explicitly accepted
    needs_input: bool = False  # `new` contains "{answer}" which only the user can fill in
    question: str | None = None
    order: int = 0  # tie-breaker for inserts at the same offset
    suffix: str = ""  # wrap only


@dataclass
class Diagnostic:
    rule_id: str
    category: str
    severity: Severity
    message: str
    remediation: str
    confidence: float
    evidence: list[Evidence] = field(default_factory=list)
    patch_ids: list[str] = field(default_factory=list)
    source_url: str | None = None  # set for model-guidance diagnostics
    evidence_status: Evidence_Status | None = None


@dataclass
class AnalysisReport:
    prompt_chars: int
    word_count: int
    tokens: int
    token_method: str
    task_type: str
    task_scores: dict[str, int]
    intent: str
    model: str | None
    model_profile: str
    profile_version: str
    variant: str | None
    requirements: list[Requirement]
    diagnostics: list[Diagnostic]
    patches: list[Patch]
    flags: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def max_severity(self) -> Severity | None:
        if not self.diagnostics:
            return None
        return max((d.severity for d in self.diagnostics), key=lambda s: SEVERITY_ORDER[s])


@dataclass
class LockCheck:
    preserved: list[str]  # requirement ids found verbatim in the output
    missing: list[str]  # requirement ids no longer present

    @property
    def ok(self) -> bool:
        return not self.missing


@dataclass
class EnhancementResult:
    original: str
    enhanced: str
    changed: bool
    status: str  # "enhanced" | "no-change" | "skipped" | "blocked"
    reason: str | None
    harness: str
    mode: str
    additional_context: str | None
    applied: list[str]  # patch ids
    pending: list[str]  # proposed but not applied (needs acceptance or input)
    rejected: list[str]
    diff: str
    lock: LockCheck
    analysis: AnalysisReport

    @property
    def warnings(self) -> list[str]:
        return self.analysis.warnings

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["lock"]["ok"] = self.lock.ok
        return d
