"""Deterministic Service Simulator for Autonomous DevOps Incident Response.

Maintains in-memory service state, telemetry, logs, configurations,
dependencies, and deterministic fault-injection hooks.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.models import (
    ConfigDiffResult,
    DependencyStatus,
    DeploymentRecord,
    HealthCheckResult,
    HealthState,
    LogEntry,
    LogLevel,
    MetricSnapshot,
    RemediationResult,
    VerificationResult,
)


KNOWN_GOOD_CONFIG: Dict[str, Any] = {
    "db_pool_size": 25,
    "request_timeout_ms": 3000,
    "cache_ttl_sec": 300,
    "auth_endpoint": "https://auth.internal/v1",
    "max_concurrency": 100,
    "circuit_breaker_enabled": True,
    "log_level": "INFO",
}


class ServiceSimulator:
    """A deterministic, repeatable simulator for an enterprise microservice."""

    def __init__(self, service_name: str = "checkout-api"):
        self.service_name = service_name
        self.uptime_seconds = 142000
        self.restarts_count = 0
        self.is_running = True

        # Configuration state
        self.known_good_config: Dict[str, Any] = copy.deepcopy(KNOWN_GOOD_CONFIG)
        self.current_config: Dict[str, Any] = copy.deepcopy(KNOWN_GOOD_CONFIG)
        self.deployment_history: List[DeploymentRecord] = [
            DeploymentRecord(
                deployment_id="dep-100",
                timestamp="2026-10-24T10:00:00Z",
                author="release-pipeline",
                version="v2.4.0",
                status="SUCCESS",
                summary="Stable baseline deployment",
                config_changes={},
            )
        ]

        # Dependencies state
        self.dependencies: Dict[str, DependencyStatus] = {
            "primary_db": DependencyStatus(
                name="primary_db",
                status=HealthState.HEALTHY,
                latency_ms=12.4,
                message="Connected to PostgreSQL primary (replica lag 0ms)",
                last_checked=self._now(),
            ),
            "redis_cache": DependencyStatus(
                name="redis_cache",
                status=HealthState.HEALTHY,
                latency_ms=1.8,
                message="Redis cluster OK (hit rate 94.2%)",
                last_checked=self._now(),
            ),
            "auth_service": DependencyStatus(
                name="auth_service",
                status=HealthState.HEALTHY,
                latency_ms=24.5,
                message="OAuth2 token validation service reachable",
                last_checked=self._now(),
            ),
            "payment_gateway": DependencyStatus(
                name="payment_gateway",
                status=HealthState.HEALTHY,
                latency_ms=88.0,
                message="Third-party payment gateway responding within SLA",
                last_checked=self._now(),
            ),
        }

        # Telemetry & logs
        self.logs: List[LogEntry] = []
        self._seed_initial_logs()

        # Fault state
        self.invalid_config_fault: Optional[Dict[str, Any]] = None
        self.unavailable_dependencies: Set[str] = set()
        self.elevated_error_fault: Optional[Dict[str, Any]] = None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _seed_initial_logs(self) -> None:
        self.logs = [
            LogEntry(
                timestamp=self._now(),
                level=LogLevel.INFO,
                service=self.service_name,
                message="Service started successfully on port 8080",
            ),
            LogEntry(
                timestamp=self._now(),
                level=LogLevel.INFO,
                service=self.service_name,
                message="Connected to all upstream dependencies",
            ),
        ]

    # --- Telemetry & Diagnostics ---

    def check_health(self) -> HealthCheckResult:
        """Evaluate and return service health status based on current faults."""
        if not self.is_running:
            return HealthCheckResult(
                service=self.service_name,
                status=HealthState.UNHEALTHY,
                uptime_seconds=0,
                restarts_count=self.restarts_count,
                active_incidents=1,
                message="Service process is not running",
                checks={"process_alive": False},
            )

        checks = {
            "process_alive": True,
            "configuration_valid": self.invalid_config_fault is None,
            "dependencies_healthy": len(self.unavailable_dependencies) == 0,
            "error_rate_nominal": self.elevated_error_fault is None,
        }

        if self.invalid_config_fault:
            return HealthCheckResult(
                service=self.service_name,
                status=HealthState.UNHEALTHY,
                uptime_seconds=self.uptime_seconds,
                restarts_count=self.restarts_count,
                active_incidents=1,
                message=f"Configuration error: {self.invalid_config_fault.get('reason', 'Invalid configuration detected')}",
                checks=checks,
            )

        if self.unavailable_dependencies:
            deps = ", ".join(sorted(self.unavailable_dependencies))
            return HealthCheckResult(
                service=self.service_name,
                status=HealthState.DEGRADED,
                uptime_seconds=self.uptime_seconds,
                restarts_count=self.restarts_count,
                active_incidents=1,
                message=f"Critical dependency unreachable: {deps}",
                checks=checks,
            )

        if self.elevated_error_fault:
            rate = self.elevated_error_fault.get("error_rate", 0.45) * 100
            return HealthCheckResult(
                service=self.service_name,
                status=HealthState.DEGRADED,
                uptime_seconds=self.uptime_seconds,
                restarts_count=self.restarts_count,
                active_incidents=1,
                message=f"Elevated error rate: {rate:.1f}% exceeds 5.0% SLO threshold",
                checks=checks,
            )

        return HealthCheckResult(
            service=self.service_name,
            status=HealthState.HEALTHY,
            uptime_seconds=self.uptime_seconds,
            restarts_count=self.restarts_count,
            active_incidents=0,
            message="All health checks passing nominally",
            checks=checks,
        )

    def get_recent_logs(self, limit: int = 20, level: Optional[str] = None) -> List[LogEntry]:
        """Return the most recent log entries, optionally filtered by minimum log level."""
        filtered = self.logs
        if level:
            target_level = level.upper()
            filtered = [entry for entry in self.logs if entry.level.value == target_level]
        return filtered[-limit:]

    def get_metrics(self) -> MetricSnapshot:
        """Return a snapshot of current error rate, latencies, and resource consumption."""
        if not self.is_running:
            return MetricSnapshot(
                timestamp=self._now(),
                error_rate=1.0,
                latency_p95_ms=0.0,
                latency_p50_ms=0.0,
                request_volume_rpm=0,
                cpu_utilization=0.0,
                memory_utilization=0.0,
            )

        if self.invalid_config_fault:
            return MetricSnapshot(
                timestamp=self._now(),
                error_rate=0.85,
                latency_p95_ms=4500.0,
                latency_p50_ms=2100.0,
                request_volume_rpm=120,
                cpu_utilization=0.15,
                memory_utilization=0.40,
            )

        if self.unavailable_dependencies:
            return MetricSnapshot(
                timestamp=self._now(),
                error_rate=0.62,
                latency_p95_ms=3800.0,
                latency_p50_ms=1200.0,
                request_volume_rpm=850,
                cpu_utilization=0.55,
                memory_utilization=0.60,
            )

        if self.elevated_error_fault:
            return MetricSnapshot(
                timestamp=self._now(),
                error_rate=self.elevated_error_fault.get("error_rate", 0.45),
                latency_p95_ms=2400.0,
                latency_p50_ms=850.0,
                request_volume_rpm=1150,
                cpu_utilization=0.88,
                memory_utilization=0.92,
            )

        return MetricSnapshot(
            timestamp=self._now(),
            error_rate=0.002,
            latency_p95_ms=42.0,
            latency_p50_ms=16.0,
            request_volume_rpm=1300,
            cpu_utilization=0.25,
            memory_utilization=0.38,
        )

    def get_dependency_health(self) -> List[DependencyStatus]:
        """Return the current connectivity and health status of all registered dependencies."""
        now = self._now()
        results: List[DependencyStatus] = []
        for name, dep in self.dependencies.items():
            dep_copy = dep.model_copy()
            dep_copy.last_checked = now
            results.append(dep_copy)
        return results

    def get_config_diff(self) -> ConfigDiffResult:
        """Compare current running configuration with the known-good baseline."""
        changed_keys = []
        curr_vals = {}
        good_vals = {}

        for k, v in self.current_config.items():
            if k not in self.known_good_config or self.known_good_config[k] != v:
                changed_keys.append(k)
                curr_vals[k] = v
                good_vals[k] = self.known_good_config.get(k)

        for k, v in self.known_good_config.items():
            if k not in self.current_config and k not in changed_keys:
                changed_keys.append(k)
                curr_vals[k] = None
                good_vals[k] = v

        has_diff = len(changed_keys) > 0
        summary = (
            f"Config drift detected in {len(changed_keys)} parameter(s): {', '.join(changed_keys)}"
            if has_diff
            else "Current configuration matches known-good baseline"
        )

        return ConfigDiffResult(
            has_diff=has_diff,
            changed_keys=changed_keys,
            current_values=curr_vals,
            known_good_values=good_vals,
            summary=summary,
        )

    def get_deployment_history(self, limit: int = 10) -> List[DeploymentRecord]:
        """Return recent deployment and configuration update records."""
        return self.deployment_history[-limit:]

    # --- Fault Injection ---

    def inject_invalid_config(
        self,
        bad_config_override: Dict[str, Any],
        author: str = "deploy-bot",
        reason: str = "Malformed configuration key or out-of-range value",
    ) -> None:
        """Inject an invalid configuration update into the service."""
        old_config = copy.deepcopy(self.current_config)
        self.current_config.update(bad_config_override)
        self.invalid_config_fault = {
            "override": bad_config_override,
            "reason": reason,
        }

        dep_id = f"dep-{len(self.deployment_history) + 101}"
        self.deployment_history.append(
            DeploymentRecord(
                deployment_id=dep_id,
                timestamp=self._now(),
                author=author,
                version=f"v2.4.{len(self.deployment_history)}",
                status="COMPLETED",
                summary=f"Automated config deployment applied by {author}",
                config_changes=bad_config_override,
            )
        )

        self.logs.append(
            LogEntry(
                timestamp=self._now(),
                level=LogLevel.CRITICAL,
                service=self.service_name,
                message=f"CRITICAL: Failed to validate configuration: {reason}. Overrides: {bad_config_override}",
                metadata={"config_error": True, "bad_keys": list(bad_config_override.keys())},
            )
        )

    def inject_unavailable_dependency(
        self,
        dependency_name: str,
        message: str = "Connection refused: connection to upstream endpoint failed",
    ) -> None:
        """Simulate an upstream dependency becoming unavailable."""
        if dependency_name in self.dependencies:
            self.unavailable_dependencies.add(dependency_name)
            self.dependencies[dependency_name].status = HealthState.UNHEALTHY
            self.dependencies[dependency_name].message = message
            self.dependencies[dependency_name].latency_ms = 9999.0

            self.logs.append(
                LogEntry(
                    timestamp=self._now(),
                    level=LogLevel.ERROR,
                    service=self.service_name,
                    message=f"ERROR: Upstream dependency '{dependency_name}' failed health check: {message}",
                    metadata={"dependency": dependency_name, "error": "CONNECTION_FAILURE"},
                )
            )

    def inject_elevated_error_rate(
        self,
        error_rate: float = 0.45,
        reason: str = "Thread pool exhaustion and memory leak in worker threads",
    ) -> None:
        """Simulate internal resource leak or transient thread exhaustion causing elevated 500s."""
        self.elevated_error_fault = {
            "error_rate": error_rate,
            "reason": reason,
        }

        self.logs.append(
            LogEntry(
                timestamp=self._now(),
                level=LogLevel.ERROR,
                service=self.service_name,
                message=f"ERROR: HTTP 500 Internal Server Error surge detected. Reason: {reason}",
                metadata={"error_rate": error_rate},
            )
        )

    def inject_security_incident(
        self,
        indicator: str = "Security breach: Unauthorized access and credential leak detected in auth headers",
    ) -> None:
        """Simulate a critical security incident."""
        self.logs.append(
            LogEntry(
                timestamp=self._now(),
                level=LogLevel.CRITICAL,
                service=self.service_name,
                message=f"CRITICAL SECURITY ALERT: {indicator}",
                metadata={"security_breach": True},
            )
        )

    def inject_data_integrity_risk(
        self,
        indicator: str = "Data corruption: Checksum mismatch on transaction ledger records",
    ) -> None:
        """Simulate a data corruption or transaction integrity failure."""
        self.logs.append(
            LogEntry(
                timestamp=self._now(),
                level=LogLevel.CRITICAL,
                service=self.service_name,
                message=f"CRITICAL DATA INTEGRITY ALERT: {indicator}",
                metadata={"data_corruption": True},
            )
        )

    def clear_faults(self) -> None:
        """Reset all injected faults to return to a clean baseline."""
        self.invalid_config_fault = None
        self.unavailable_dependencies.clear()
        self.elevated_error_fault = None
        self.current_config = copy.deepcopy(self.known_good_config)
        for dep in self.dependencies.values():
            dep.status = HealthState.HEALTHY
            dep.latency_ms = 15.0
            dep.message = "Service responding normally"
        self.is_running = True

    # --- Remediation Actions ---

    def restart_service(self) -> RemediationResult:
        """Restart the service process.
        
        Clears transient worker leaks and elevated error rate faults.
        DOES NOT fix invalid configuration or external dependency outages.
        """
        self.restarts_count += 1
        self.uptime_seconds = 5
        self.is_running = True

        self.logs.append(
            LogEntry(
                timestamp=self._now(),
                level=LogLevel.INFO,
                service=self.service_name,
                message=f"Service restarted gracefully (restart #{self.restarts_count}). Initializing workers...",
            )
        )

        # If fault was purely internal memory leak / thread pool exhaustion, restart clears it
        if self.elevated_error_fault and not self.invalid_config_fault and not self.unavailable_dependencies:
            cleared_reason = self.elevated_error_fault.get("reason", "")
            self.elevated_error_fault = None
            self.logs.append(
                LogEntry(
                    timestamp=self._now(),
                    level=LogLevel.INFO,
                    service=self.service_name,
                    message=f"Transient issue '{cleared_reason}' cleared by restart. Workers healthy.",
                )
            )
            return RemediationResult(
                action="restart_service",
                success=True,
                message=f"Service restarted successfully. Transient state cleared. Restart count: {self.restarts_count}",
                details={"restarts_count": self.restarts_count, "transient_cleared": True},
                timestamp=self._now(),
            )

        # If invalid config or unavailable dependency persists, restart fails to make service healthy
        if self.invalid_config_fault:
            self.logs.append(
                LogEntry(
                    timestamp=self._now(),
                    level=LogLevel.CRITICAL,
                    service=self.service_name,
                    message="Service restarted but failed configuration validation upon startup.",
                )
            )
            return RemediationResult(
                action="restart_service",
                success=False,
                message="Service restarted, but remains UNHEALTHY due to invalid configuration.",
                details={"restarts_count": self.restarts_count, "unhealthy_reason": "INVALID_CONFIG"},
                timestamp=self._now(),
            )

        if self.unavailable_dependencies:
            self.logs.append(
                LogEntry(
                    timestamp=self._now(),
                    level=LogLevel.WARN,
                    service=self.service_name,
                    message="Service restarted, but upstream dependency connection remains refused.",
                )
            )
            return RemediationResult(
                action="restart_service",
                success=False,
                message=f"Service restarted, but upstream dependencies remain unavailable: {list(self.unavailable_dependencies)}",
                details={"restarts_count": self.restarts_count, "unhealthy_reason": "DEPENDENCY_UNAVAILABLE"},
                timestamp=self._now(),
            )

        return RemediationResult(
            action="restart_service",
            success=True,
            message=f"Service restarted cleanly. Restart count: {self.restarts_count}",
            details={"restarts_count": self.restarts_count},
            timestamp=self._now(),
        )

    def rollback_config(self) -> RemediationResult:
        """Roll back current configuration to the known-good baseline."""
        diff_before = self.get_config_diff()
        if not diff_before.has_diff:
            return RemediationResult(
                action="rollback_config",
                success=False,
                message="No configuration drift detected; rollback skipped.",
                details={"has_diff": False},
                timestamp=self._now(),
            )

        self.current_config = copy.deepcopy(self.known_good_config)
        self.invalid_config_fault = None

        dep_id = f"dep-{len(self.deployment_history) + 101}"
        self.deployment_history.append(
            DeploymentRecord(
                deployment_id=dep_id,
                timestamp=self._now(),
                author="incident-responder-agent",
                version=f"v2.4.0-rollback-{dep_id}",
                status="ROLLBACK_SUCCESS",
                summary="Configuration rolled back to known-good baseline",
                config_changes={k: self.known_good_config.get(k) for k in diff_before.changed_keys},
            )
        )

        self.logs.append(
            LogEntry(
                timestamp=self._now(),
                level=LogLevel.INFO,
                service=self.service_name,
                message=f"Configuration rolled back to known-good baseline. Reverted keys: {diff_before.changed_keys}",
            )
        )

        return RemediationResult(
            action="rollback_config",
            success=True,
            message=f"Configuration successfully restored to known-good baseline. Reverted keys: {diff_before.changed_keys}",
            details={"reverted_keys": diff_before.changed_keys},
            timestamp=self._now(),
        )

    def verify_recovery(self) -> VerificationResult:
        """Independently verify whether the service and dependencies have recovered."""
        health = self.check_health()
        metrics = self.get_metrics()
        diff = self.get_config_diff()
        failing_deps = sorted(list(self.unavailable_dependencies))

        is_healthy = (
            health.status == HealthState.HEALTHY
            and metrics.error_rate < 0.05
            and len(failing_deps) == 0
            and not diff.has_diff
        )

        if is_healthy:
            msg = "Verification SUCCESS: Service is HEALTHY, error rate nominal, no config drift, all dependencies OK."
        else:
            reasons = []
            if health.status != HealthState.HEALTHY:
                reasons.append(f"health status is {health.status.value} ({health.message})")
            if metrics.error_rate >= 0.05:
                reasons.append(f"error rate {metrics.error_rate * 100:.1f}% exceeds 5%")
            if failing_deps:
                reasons.append(f"dependencies down: {failing_deps}")
            if diff.has_diff:
                reasons.append(f"config drift detected: {diff.changed_keys}")
            msg = f"Verification FAILED: {'; '.join(reasons)}"

        return VerificationResult(
            is_healthy=is_healthy,
            service_status=health.status,
            error_rate=metrics.error_rate,
            failing_dependencies=failing_deps,
            has_config_drift=diff.has_diff,
            message=msg,
        )
