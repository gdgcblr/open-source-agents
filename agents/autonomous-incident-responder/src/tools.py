"""Diagnostic and remediation tools for the Autonomous DevOps Incident Responder.

All tools operate exclusively on the in-memory ServiceSimulator.
Input arguments and outputs are strictly validated using Pydantic.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field, ValidationError

from src.models import (
    ConfigDiffResult,
    DependencyStatus,
    DeploymentRecord,
    HealthCheckResult,
    LogEntry,
    MetricSnapshot,
    RemediationResult,
    VerificationResult,
)
from src.simulator import ServiceSimulator


# --- Structured Input Argument Models ---

class CheckHealthArgs(BaseModel):
    """Arguments for checking service health."""
    pass


class GetRecentLogsArgs(BaseModel):
    """Arguments for fetching recent application logs."""
    limit: int = Field(default=20, ge=1, le=100, description="Number of recent log lines to fetch (1-100).")
    level: Optional[str] = Field(default=None, description="Optional log level filter: INFO, WARN, ERROR, CRITICAL.")


class GetMetricsArgs(BaseModel):
    """Arguments for fetching service telemetry metrics."""
    pass


class GetDependencyHealthArgs(BaseModel):
    """Arguments for fetching upstream dependency statuses."""
    pass


class GetConfigDiffArgs(BaseModel):
    """Arguments for comparing running config with known-good baseline."""
    pass


class GetDeploymentHistoryArgs(BaseModel):
    """Arguments for fetching deployment and configuration change records."""
    limit: int = Field(default=10, ge=1, le=50, description="Number of recent deployments to fetch (1-50).")


class RestartServiceArgs(BaseModel):
    """Arguments for restarting the service process."""
    pass


class RollbackConfigArgs(BaseModel):
    """Arguments for rolling back configuration to known-good baseline."""
    pass


class VerifyRecoveryArgs(BaseModel):
    """Arguments for independently verifying system recovery."""
    pass


# --- Tool Implementation and Controlled Dispatcher ---

class ToolExecutionResult(BaseModel):
    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None


class ToolDispatcher:
    """Controlled dispatcher for executing strictly validated incident responder tools."""

    # Classifications
    READ_ONLY_TOOLS = {
        "check_health",
        "get_recent_logs",
        "get_metrics",
        "get_dependency_health",
        "get_config_diff",
        "get_deployment_history",
        "verify_recovery",
    }
    REMEDIATION_TOOLS = {
        "restart_service",
        "rollback_config",
    }

    def __init__(self, simulator: ServiceSimulator):
        self.simulator = simulator
        self._handlers: Dict[str, tuple[type[BaseModel], Callable[[Any], Any]]] = {
            "check_health": (CheckHealthArgs, self._tool_check_health),
            "get_recent_logs": (GetRecentLogsArgs, self._tool_get_recent_logs),
            "get_metrics": (GetMetricsArgs, self._tool_get_metrics),
            "get_dependency_health": (GetDependencyHealthArgs, self._tool_get_dependency_health),
            "get_config_diff": (GetConfigDiffArgs, self._tool_get_config_diff),
            "get_deployment_history": (GetDeploymentHistoryArgs, self._tool_get_deployment_history),
            "restart_service": (RestartServiceArgs, self._tool_restart_service),
            "rollback_config": (RollbackConfigArgs, self._tool_rollback_config),
            "verify_recovery": (VerifyRecoveryArgs, self._tool_verify_recovery),
        }

    @property
    def registered_tool_names(self) -> List[str]:
        return list(self._handlers.keys())

    def is_read_only(self, tool_name: str) -> bool:
        return tool_name in self.READ_ONLY_TOOLS

    def is_remediation(self, tool_name: str) -> bool:
        return tool_name in self.REMEDIATION_TOOLS

    def execute(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> ToolExecutionResult:
        """Validate tool name and arguments, then execute exclusively against the simulator."""
        if tool_name not in self._handlers:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=f"Unrecognized tool '{tool_name}'. Available tools: {self.registered_tool_names}",
            )

        args_model, handler = self._handlers[tool_name]
        raw_args = arguments or {}

        # Validate arguments against Pydantic model
        try:
            validated_args = args_model.model_validate(raw_args)
        except ValidationError as e:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=f"Invalid arguments for tool '{tool_name}': {e.errors()}",
            )

        try:
            result = handler(validated_args)
            # Serialize Pydantic result if needed
            serialized = result.model_dump() if hasattr(result, "model_dump") else result
            return ToolExecutionResult(
                tool_name=tool_name,
                success=True,
                data=serialized,
                error=None,
            )
        except Exception as e:
            return ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=f"Tool execution exception: {str(e)}",
            )

    # --- Tool Handlers ---

    def _tool_check_health(self, args: CheckHealthArgs) -> HealthCheckResult:
        return self.simulator.check_health()

    def _tool_get_recent_logs(self, args: GetRecentLogsArgs) -> List[Dict[str, Any]]:
        logs = self.simulator.get_recent_logs(limit=args.limit, level=args.level)
        return [entry.model_dump() for entry in logs]

    def _tool_get_metrics(self, args: GetMetricsArgs) -> MetricSnapshot:
        return self.simulator.get_metrics()

    def _tool_get_dependency_health(self, args: GetDependencyHealthArgs) -> List[Dict[str, Any]]:
        deps = self.simulator.get_dependency_health()
        return [dep.model_dump() for dep in deps]

    def _tool_get_config_diff(self, args: GetConfigDiffArgs) -> ConfigDiffResult:
        return self.simulator.get_config_diff()

    def _tool_get_deployment_history(self, args: GetDeploymentHistoryArgs) -> List[Dict[str, Any]]:
        deployments = self.simulator.get_deployment_history(limit=args.limit)
        return [dep.model_dump() for dep in deployments]

    def _tool_restart_service(self, args: RestartServiceArgs) -> RemediationResult:
        return self.simulator.restart_service()

    def _tool_rollback_config(self, args: RollbackConfigArgs) -> RemediationResult:
        return self.simulator.rollback_config()

    def _tool_verify_recovery(self, args: VerifyRecoveryArgs) -> VerificationResult:
        return self.simulator.verify_recovery()
