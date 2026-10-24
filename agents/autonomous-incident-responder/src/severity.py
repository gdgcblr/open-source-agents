"""Deterministic Incident Severity Assessment Module.

Defines severity levels (SEV-1 to SEV-4), response priorities,
configurable thresholds, and impact-driven deterministic evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from src.models import (
    ConfigDiffResult,
    DependencyStatus,
    HealthCheckResult,
    HealthState,
    LogEntry,
    LogLevel,
    MetricSnapshot,
    ResponsePriority,
    SeverityAssessment,
    SeverityLevel,
)


@dataclass
class SeverityThresholds:
    """Configurable, documented thresholds for simulator incident classification."""
    # Error rate boundaries
    sev1_error_rate: float = 0.50          # >= 50% transaction error rate -> SEV-1
    sev2_error_rate: float = 0.20          # 20% - 49% error rate -> SEV-2
    sev3_error_rate: float = 0.05          # 5% - 19% error rate -> SEV-3

    # Latency percentiles (p95 ms)
    sev1_latency_p95_ms: float = 5000.0    # Extreme latency >= 5s
    sev2_latency_p95_ms: float = 2000.0    # High latency >= 2s
    sev3_latency_p95_ms: float = 500.0     # Moderate latency >= 500ms

    # User impact percentages
    sev1_affected_users_pct: float = 50.0  # >= 50% users affected -> SEV-1
    sev2_affected_users_pct: float = 15.0  # >= 15% users affected -> SEV-2
    sev3_affected_users_pct: float = 5.0   # >= 5% users affected -> SEV-3

    # Service tiers
    tier1_services: Set[str] = field(default_factory=lambda: {"checkout-api", "payment-service", "auth-service"})
    
    # Dependencies whose loss halts critical functions
    critical_dependencies: Set[str] = field(default_factory=lambda: {"primary_db", "payment_gateway", "auth_service"})
    
    # Dependencies with non-fatal workarounds (e.g. cache fallback)
    workaround_dependencies: Set[str] = field(default_factory=lambda: {"redis_cache"})


class SeverityEvaluator:
    """Evaluates incident evidence deterministically using structured metrics and rules."""

    SECURITY_INTEGRITY_KEYWORDS = {
        "security breach",
        "data corruption",
        "unauthorized access",
        "checksum mismatch",
        "credential leak",
        "data exfiltration",
        "tampered",
        "sql injection",
    }

    def __init__(self, thresholds: Optional[SeverityThresholds] = None):
        self.thresholds = thresholds or SeverityThresholds()

    def assess(
        self,
        service_name: str,
        health: Optional[HealthCheckResult] = None,
        metrics: Optional[MetricSnapshot] = None,
        dependencies: Optional[List[DependencyStatus]] = None,
        config_diff: Optional[ConfigDiffResult] = None,
        logs: Optional[List[LogEntry]] = None,
        alert_context: Optional[Dict[str, Any]] = None,
    ) -> SeverityAssessment:
        """Deterministically assess severity using accumulated structured evidence."""
        reasons: List[str] = []
        evidence_used: Dict[str, Any] = {"service_name": service_name}
        missing_or_uncertain: List[str] = []
        alert_ctx = alert_context or {}

        is_tier1 = service_name in self.thresholds.tier1_services
        evidence_used["is_tier1"] = is_tier1

        # ---------------------------------------------------------
        # Dimension 1: Security and Data-Integrity Risk (Override)
        # ---------------------------------------------------------
        security_risk_detected = False
        security_reason = ""

        # Check explicit alert context flags
        if alert_ctx.get("has_security_breach_risk") or alert_ctx.get("has_data_corruption_risk"):
            security_risk_detected = True
            security_reason = alert_ctx.get(
                "security_details",
                "Explicit security breach or data-integrity alert flagged in incident context."
            )

        # Check log entries for indicators of security / integrity compromise
        if logs and not security_risk_detected:
            for log in logs:
                msg_lower = log.message.lower()
                for kw in self.SECURITY_INTEGRITY_KEYWORDS:
                    if kw in msg_lower:
                        security_risk_detected = True
                        security_reason = f"Log indicator detected: '{kw}' in message: {log.message[:100]}"
                        break
                if security_risk_detected:
                    break

        if security_risk_detected:
            evidence_used["security_or_integrity_risk"] = True
            evidence_used["security_reason"] = security_reason
            reasons.append(f"CRITICAL OVERRIDE: {security_reason}")
            return SeverityAssessment(
                severity=SeverityLevel.SEV_1,
                priority=ResponsePriority.P1_CRITICAL_URGENT,
                reasons=reasons,
                evidence_used=evidence_used,
                missing_or_uncertain_evidence=missing_or_uncertain,
                recommended_action="Execute immediate protective containment and page security/data-governance leads.",
                is_security_or_integrity_risk=True,
                requires_urgent_escalation=True,
            )

        # ---------------------------------------------------------
        # Dimension 2: Check Evidence Completeness & Uncertainty
        # ---------------------------------------------------------
        if health is None:
            missing_or_uncertain.append("Health check data is missing.")
        elif health.status == HealthState.UNKNOWN:
            missing_or_uncertain.append("Service health check status is UNKNOWN.")

        if metrics is None:
            missing_or_uncertain.append("Telemetry metrics (error rate, latency) are missing.")
        
        if alert_ctx.get("affected_users_pct") is None:
            missing_or_uncertain.append("Affected user percentage measurement is not available.")

        # Check contradictory evidence
        if health and metrics:
            if health.status == HealthState.UNHEALTHY and metrics.error_rate == 0.0 and health.checks.get("process_alive", True):
                missing_or_uncertain.append(
                    "Contradictory evidence: Health reports UNHEALTHY but metrics error_rate is 0.0%."
                )

        # ---------------------------------------------------------
        # Dimension 3: Gather telemetry and operational impact
        # ---------------------------------------------------------
        error_rate = metrics.error_rate if metrics else None
        latency_p95 = metrics.latency_p95_ms if metrics else None
        health_status = health.status if health else HealthState.UNKNOWN
        affected_users_pct = alert_ctx.get("affected_users_pct")
        workaround_active = alert_ctx.get("workaround_active", False)

        evidence_used["health_status"] = health_status.value
        evidence_used["error_rate"] = error_rate
        evidence_used["latency_p95_ms"] = latency_p95
        evidence_used["affected_users_pct"] = affected_users_pct
        evidence_used["workaround_active"] = workaround_active

        # Check critical and workaround dependencies
        failing_critical_deps: List[str] = []
        failing_workaround_deps: List[str] = []

        if dependencies:
            dep_dict = {d.name: d.status for d in dependencies}
            evidence_used["dependencies"] = {k: v.value for k, v in dep_dict.items()}
            for name, status in dep_dict.items():
                if status in (HealthState.UNHEALTHY, HealthState.DEGRADED):
                    if name in self.thresholds.critical_dependencies:
                        failing_critical_deps.append(name)
                    elif name in self.thresholds.workaround_dependencies:
                        failing_workaround_deps.append(name)

        evidence_used["failing_critical_deps"] = failing_critical_deps
        evidence_used["failing_workaround_deps"] = failing_workaround_deps

        # ---------------------------------------------------------
        # Dimension 4: Impact Evaluation (SEV-1 vs SEV-2 vs SEV-3 vs SEV-4)
        # ---------------------------------------------------------
        # SEV-1 Criteria:
        # - Full outage of Tier-1 service (health UNHEALTHY / process dead)
        # - Error rate >= sev1_error_rate (>= 50%) on Tier-1 service
        # - Affected users >= 50%
        # - Critical dependency down on Tier-1 service
        is_sev1 = False
        if is_tier1:
            if health_status == HealthState.UNHEALTHY:
                is_sev1 = True
                reasons.append(f"Tier-1 service '{service_name}' health status is UNHEALTHY.")
            if error_rate is not None and error_rate >= self.thresholds.sev1_error_rate:
                is_sev1 = True
                reasons.append(
                    f"Error rate {error_rate*100:.1f}% exceeds SEV-1 threshold ({self.thresholds.sev1_error_rate*100:.1f}%)."
                )
            if affected_users_pct is not None and affected_users_pct >= self.thresholds.sev1_affected_users_pct:
                is_sev1 = True
                reasons.append(
                    f"Affected users {affected_users_pct:.1f}% exceeds SEV-1 threshold ({self.thresholds.sev1_affected_users_pct:.1f}%)."
                )
            if failing_critical_deps:
                is_sev1 = True
                reasons.append(f"Critical upstream dependencies unavailable: {failing_critical_deps}.")

        if is_sev1:
            return SeverityAssessment(
                severity=SeverityLevel.SEV_1,
                priority=ResponsePriority.P1_CRITICAL_URGENT,
                reasons=reasons,
                evidence_used=evidence_used,
                missing_or_uncertain_evidence=missing_or_uncertain,
                recommended_action="Mobilize primary on-call SRE and page tier-1 incident commanders immediately.",
                is_security_or_integrity_risk=False,
                requires_urgent_escalation=True,
            )

        # SEV-2 Criteria:
        # - Major service degradation on Tier-1 (DEGRADED, or error rate >= 20%, or latency >= 2000ms, or users >= 15%)
        # - Full outage of Tier-2 service
        is_sev2 = False
        if is_tier1:
            if health_status == HealthState.DEGRADED:
                is_sev2 = True
                reasons.append(f"Tier-1 service '{service_name}' health status is DEGRADED.")
            if error_rate is not None and error_rate >= self.thresholds.sev2_error_rate:
                is_sev2 = True
                reasons.append(
                    f"Error rate {error_rate*100:.1f}% exceeds SEV-2 threshold ({self.thresholds.sev2_error_rate*100:.1f}%)."
                )
            if latency_p95 is not None and latency_p95 >= self.thresholds.sev2_latency_p95_ms:
                is_sev2 = True
                reasons.append(
                    f"Latency p95 {latency_p95:.1f}ms exceeds SEV-2 threshold ({self.thresholds.sev2_latency_p95_ms:.1f}ms)."
                )
            if affected_users_pct is not None and affected_users_pct >= self.thresholds.sev2_affected_users_pct:
                is_sev2 = True
                reasons.append(
                    f"Affected users {affected_users_pct:.1f}% exceeds SEV-2 threshold ({self.thresholds.sev2_affected_users_pct:.1f}%)."
                )
        else:
            # Tier-2 service outage
            if health_status == HealthState.UNHEALTHY:
                is_sev2 = True
                reasons.append(f"Non-tier-1 service '{service_name}' is UNHEALTHY.")

        # Conservative policy for missing telemetry on Tier-1
        if is_tier1 and (health is None or metrics is None) and not is_sev2:
            is_sev2 = True
            reasons.append("Conservative assessment: Essential telemetry missing for Tier-1 service.")

        if is_sev2:
            return SeverityAssessment(
                severity=SeverityLevel.SEV_2,
                priority=ResponsePriority.P2_HIGH,
                reasons=reasons,
                evidence_used=evidence_used,
                missing_or_uncertain_evidence=missing_or_uncertain,
                recommended_action="High-priority response: investigate root cause and prepare remediation.",
                is_security_or_integrity_risk=False,
                requires_urgent_escalation=False,
            )

        # SEV-3 Criteria:
        # - Limited impact with workaround (e.g. failing_workaround_deps or workaround_active)
        # - Error rate between 5% and 20%
        # - Latency between 500ms and 2000ms
        is_sev3 = False
        if failing_workaround_deps or workaround_active:
            is_sev3 = True
            reasons.append(
                f"Non-critical dependency degraded ({failing_workaround_deps or 'cache'}) with functional workaround in place."
            )
        if error_rate is not None and error_rate >= self.thresholds.sev3_error_rate:
            is_sev3 = True
            reasons.append(
                f"Error rate {error_rate*100:.1f}% exceeds SEV-3 threshold ({self.thresholds.sev3_error_rate*100:.1f}%)."
            )
        if latency_p95 is not None and latency_p95 >= self.thresholds.sev3_latency_p95_ms:
            is_sev3 = True
            reasons.append(
                f"Latency p95 {latency_p95:.1f}ms exceeds SEV-3 threshold ({self.thresholds.sev3_latency_p95_ms:.1f}ms)."
            )

        if is_sev3:
            return SeverityAssessment(
                severity=SeverityLevel.SEV_3,
                priority=ResponsePriority.P3_MODERATE,
                reasons=reasons,
                evidence_used=evidence_used,
                missing_or_uncertain_evidence=missing_or_uncertain,
                recommended_action="Normal on-call queue response: investigate within SLA.",
                is_security_or_integrity_risk=False,
                requires_urgent_escalation=False,
            )

        # SEV-4 Criteria:
        # - Nominal health and metrics, minor or cosmetic errors
        reasons.append("All observed metrics and health checks are nominal (error rate < 5%, all dependencies healthy).")
        return SeverityAssessment(
            severity=SeverityLevel.SEV_4,
            priority=ResponsePriority.P4_LOW,
            reasons=reasons,
            evidence_used=evidence_used,
            missing_or_uncertain_evidence=missing_or_uncertain,
            recommended_action="Low urgency: record telemetry and schedule routine review.",
            is_security_or_integrity_risk=False,
            requires_urgent_escalation=False,
        )
