"""Domain enums for PatchProof contracts, evidence, verdicts, and checks."""

from enum import StrEnum


class SourceKind(StrEnum):
    FIXTURE = "fixture"
    GITHUB = "github"
    LOCAL = "local"


class ExecutionMode(StrEnum):
    STATIC_ONLY = "static_only"
    SANDBOX_IF_AVAILABLE = "sandbox_if_available"


class ModelMode(StrEnum):
    DETERMINISTIC = "deterministic"
    PROVIDER = "provider"


class Verdict(StrEnum):
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"


class RequirementOrigin(StrEnum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class RequirementStatus(StrEnum):
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    UNVERIFIED = "UNVERIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    AMBIGUOUS = "AMBIGUOUS"


class FindingCategory(StrEnum):
    FUNCTIONAL_DEFECT = "FUNCTIONAL_DEFECT"
    REQUIREMENT_GAP = "REQUIREMENT_GAP"
    TEST_GAP = "TEST_GAP"
    REGRESSION_RISK = "REGRESSION_RISK"
    SECURITY_CONCERN = "SECURITY_CONCERN"
    PERFORMANCE_CONCERN = "PERFORMANCE_CONCERN"
    MAINTAINABILITY_CONCERN = "MAINTAINABILITY_CONCERN"
    AMBIGUITY = "AMBIGUITY"
    ENVIRONMENT_BLOCKER = "ENVIRONMENT_BLOCKER"


class Severity(StrEnum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FindingStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    HYPOTHESIS = "HYPOTHESIS"
    UNVERIFIED = "UNVERIFIED"


class CheckStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_RUN = "NOT_RUN"
    REJECTED = "REJECTED"
    TIMED_OUT = "TIMED_OUT"
    ERROR = "ERROR"


class AgentStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class EvidenceKind(StrEnum):
    ISSUE_TEXT = "ISSUE_TEXT"
    PR_TEXT = "PR_TEXT"
    DIFF = "DIFF"
    SOURCE = "SOURCE"
    TEST_SOURCE = "TEST_SOURCE"
    TEST_RESULT = "TEST_RESULT"
    STATIC_RESULT = "STATIC_RESULT"
    ENVIRONMENT = "ENVIRONMENT"
    AGENT_INFERENCE = "AGENT_INFERENCE"


class TrustLevel(StrEnum):
    UNTRUSTED_REPO_DATA = "UNTRUSTED_REPO_DATA"
    TOOL_OBSERVED = "TOOL_OBSERVED"
    DETERMINISTIC_ANALYSIS = "DETERMINISTIC_ANALYSIS"
    MODEL_INFERENCE = "MODEL_INFERENCE"

