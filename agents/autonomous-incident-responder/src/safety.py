"""Safety policy enforcement engine for autonomous incident response.

Enforces deterministic constraints in Python code:
- Read-only diagnostics automatic approval
- Strict remediation allowlisting
- High-risk action approval gates
- Maximum model iterations and tool calls
- Prevention of repeated failed remediation loops
- Independent verification prerequisite for resolution
- Tool timeout management
"""

from __future__ import annotations

import concurrent.futures
from typing import Any, Callable, Dict, Optional, Set

from src.config import AgentConfig
from src.models import VerificationResult


class SafetyViolation(Exception):
    """Raised when an action violates safety policies."""
    pass


class SafetyPolicy:
    """Enforces operational and remediation safety constraints."""

    def __init__(
        self,
        config: AgentConfig,
        approval_callback: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
    ):
        self.config = config
        self.approval_callback = approval_callback
        self.failed_action_counts: Dict[str, int] = {}
        self.total_tool_calls: int = 0

    def check_iteration_limit(self, current_iterations: int) -> bool:
        """Return True if under iteration limit, False if exceeded."""
        return current_iterations < self.config.max_iterations

    def check_tool_call_limit(self) -> bool:
        """Return True if under tool call limit, False if exceeded."""
        return self.total_tool_calls < self.config.max_tool_calls

    def validate_tool_intent(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        is_read_only: bool,
        registered_tools: Optional[List[str]] = None,
        is_security_or_integrity_risk: bool = False,
    ) -> tuple[bool, Optional[str]]:
        """Evaluate whether a tool invocation is permitted under current safety policy."""
        # 0. Validate tool exists
        if registered_tools is not None and tool_name not in registered_tools:
            return False, f"Unrecognized tool '{tool_name}'. Available tools: {registered_tools}"

        # 1. Read-only diagnostics are permitted automatically
        if is_read_only:
            return True, None

        # 2. Block speculative/automated remediation for security or data-integrity risks
        if is_security_or_integrity_risk:
            return False, (
                "Blocked: Automated remediation is prohibited for credible security or "
                "data-integrity risks. Immediate protective escalation is required."
            )

        # 3. Remediation must be in explicit allowlist
        if tool_name not in self.config.permitted_remediations:
            return False, (
                f"Blocked: Action '{tool_name}' is not in the permitted remediation allowlist: "
                f"{sorted(list(self.config.permitted_remediations))}"
            )

        # 4. Repeated failed action prevention
        failures = self.failed_action_counts.get(tool_name, 0)
        if failures >= self.config.max_repeated_action_failures:
            return False, (
                f"Blocked: Action '{tool_name}' has repeatedly failed {failures} times. "
                "Further attempts are blocked to prevent infinite loops."
            )

        # 5. High-risk action approval check (severity alone never authorizes high-risk actions)
        if tool_name in self.config.high_risk_actions:
            if not self.approval_callback or not self.approval_callback(tool_name, arguments):
                return False, (
                    f"Blocked: High-risk action '{tool_name}' requires approval, "
                    "which was denied or not provided."
                )

        return True, None

    def record_tool_execution(self, tool_name: str, success: bool, is_remediation: bool) -> None:
        """Update metrics and safety state following tool execution."""
        self.total_tool_calls += 1
        if is_remediation:
            if not success:
                self.failed_action_counts[tool_name] = self.failed_action_counts.get(tool_name, 0) + 1
            else:
                # Reset failure counter on successful remediation
                self.failed_action_counts[tool_name] = 0

    def can_resolve(
        self,
        verification: Optional[VerificationResult],
        is_security_or_integrity_risk: bool = False,
    ) -> tuple[bool, Optional[str]]:
        """Strict verification prerequisite: never resolve without successful verification and met criteria."""
        if is_security_or_integrity_risk:
            return False, "Resolution rejected: Cannot automatically resolve an incident with an active security or data-integrity risk."

        if verification is None:
            return False, "Resolution rejected: No independent verification has been performed."

        # A successful health check is necessary, but other recovery criteria must also be met
        if not verification.is_healthy or verification.service_status.value != "HEALTHY":
            return False, f"Resolution rejected: Service health check is not HEALTHY: {verification.message}"

        if verification.error_rate >= 0.05:
            return False, f"Resolution rejected: Error rate {verification.error_rate*100:.1f}% remains above recovery threshold."

        if verification.failing_dependencies:
            return False, f"Resolution rejected: Dependencies remain unhealthy: {verification.failing_dependencies}"

        if verification.has_config_drift:
            return False, "Resolution rejected: Configuration drift remains unresolved."

        return True, None


def execute_with_timeout(func: Callable[..., Any], args: tuple = (), kwargs: dict = None, timeout_seconds: float = 10.0) -> Any:
    """Execute a callable with a strict timeout guard."""
    if kwargs is None:
        kwargs = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Operation timed out after {timeout_seconds} seconds")
