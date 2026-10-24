"""Policy layer for validating and filtering verification CheckRequests."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from patchproof.core.models import CheckRequest

ALLOWED_CHECK_PROFILES: frozenset[str] = frozenset(
    {
        "static_ast_retry_bound",
        "static_ast_syntax_check",
        "sandbox_pytest",
    }
)

_SAFE_ARG_RE = re.compile(r"^[A-Za-z0-9_./:\-=]{1,128}$")
_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "..",
    ";",
    "|",
    "&",
    "$",
    "`",
    ">",
    "<",
    "curl",
    "wget",
    "http://",
    "https://",
    "eval",
    "exec",
    "--network",
)


class PolicyDecision(BaseModel):
    """Result of policy evaluation for a single CheckRequest."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approved: bool
    reason: str


def evaluate_check_policy(request: CheckRequest) -> PolicyDecision:
    """Validate a CheckRequest against the allowlisted profile and argument grammar."""
    if request.profile not in ALLOWED_CHECK_PROFILES:
        allowed_list = sorted(ALLOWED_CHECK_PROFILES)
        return PolicyDecision(
            approved=False,
            reason=f"Profile '{request.profile}' is not in allowlist {allowed_list}",
        )

    if request.target_path:
        norm = request.target_path.replace("\\", "/")
        if norm.startswith("/") or ".." in norm.split("/") or ":" in norm:
            return PolicyDecision(
                approved=False,
                reason=f"Target path '{request.target_path}' violates workspace confinement policy",
            )

    for arg in request.args:
        lower_arg = arg.lower()
        for forbidden in _FORBIDDEN_SUBSTRINGS:
            if forbidden in lower_arg:
                return PolicyDecision(
                    approved=False,
                    reason=f"Argument '{arg}' contains forbidden token '{forbidden}'",
                )
        if not _SAFE_ARG_RE.match(arg):
            return PolicyDecision(
                approved=False,
                reason=f"Argument '{arg}' does not match fixed argument grammar",
            )

    return PolicyDecision(approved=True, reason="Approved by static/sandbox check policy")
