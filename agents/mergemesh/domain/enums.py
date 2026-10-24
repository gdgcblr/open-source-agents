"""Domain enumerations and literals for MergeMesh."""

from __future__ import annotations

from typing import Literal

CheckStatus = Literal["PASS", "FAIL", "ERROR", "TIMEOUT", "NOT_RUN"]
AIStatus = Literal["SUCCESS", "FALLBACK", "UNAVAILABLE", "SKIPPED"]
SeverityLevel = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]
FindingKind = Literal[
    "FIELD_REMOVED_BUT_CONSUMED",
    "MISSING_REQUIRED_FIELD",
    "FIELD_TYPE_CHANGED",
    "POTENTIAL_FIELD_RENAME",
    "COMPATIBLE_ADDITION",
    "UNKNOWN",
]
VerificationState = Literal[
    "REPRODUCED_FAILURE",
    "INFERRED_RISK",
    "VERIFIED_COMPATIBLE",
    "TEST_ERROR",
]
