"""Deterministic unit and integration tests for incident severity assessment."""

import pytest
from src.agent import AgentDecision, MockLLMClient
from src.config import AgentConfig
from src.models import (
    DependencyStatus,
    HealthCheckResult,
    HealthState,
    IncidentState,
    LogEntry,
    LogLevel,
    MetricSnapshot,
    ResponsePriority,
    SeverityLevel,
)
from src.orchestrator import IncidentOrchestrator
from src.severity import SeverityEvaluator, SeverityThresholds
from src.simulator import ServiceSimulator


def test_1_critical_service_outage_is_sev1():
    """Scenario 1: Critical service outage -> SEV-1."""
    evaluator = SeverityEvaluator()

    health = HealthCheckResult(
        service="checkout-api",
        status=HealthState.UNHEALTHY,
        uptime_seconds=0,
        restarts_count=3,
        active_incidents=1,
        message="Service process terminated unexpectedly",
        checks={"process_alive": False},
    )
    metrics = MetricSnapshot(
        timestamp="2026-10-24T12:00:00Z",
        error_rate=0.92,
        latency_p95_ms=6200.0,
        latency_p50_ms=3100.0,
        request_volume_rpm=50,
        cpu_utilization=0.95,
        memory_utilization=0.98,
    )

    assessment = evaluator.assess(
        service_name="checkout-api",
        health=health,
        metrics=metrics,
    )

    assert assessment.severity == SeverityLevel.SEV_1
    assert assessment.priority == ResponsePriority.P1_CRITICAL_URGENT
    assert assessment.requires_urgent_escalation is True
    assert any("UNHEALTHY" in r for r in assessment.reasons)
    assert any("exceeds SEV-1 threshold" in r for r in assessment.reasons)


def test_2_major_service_degradation_is_sev2():
    """Scenario 2: Major service degradation -> SEV-2."""
    evaluator = SeverityEvaluator()

    health = HealthCheckResult(
        service="checkout-api",
        status=HealthState.DEGRADED,
        uptime_seconds=5000,
        restarts_count=0,
        active_incidents=1,
        message="High transaction latency and error rate",
        checks={"process_alive": True},
    )
    metrics = MetricSnapshot(
        timestamp="2026-10-24T12:00:00Z",
        error_rate=0.25,  # 25% error rate: between SEV-2 (20%) and SEV-1 (50%)
        latency_p95_ms=2800.0,
        latency_p50_ms=900.0,
        request_volume_rpm=1100,
        cpu_utilization=0.75,
        memory_utilization=0.80,
    )

    assessment = evaluator.assess(
        service_name="checkout-api",
        health=health,
        metrics=metrics,
    )

    assert assessment.severity == SeverityLevel.SEV_2
    assert assessment.priority == ResponsePriority.P2_HIGH
    assert assessment.requires_urgent_escalation is False
    assert any("DEGRADED" in r for r in assessment.reasons)


def test_3_limited_impact_with_workaround_is_sev3():
    """Scenario 3: Limited impact with a workaround -> SEV-3."""
    evaluator = SeverityEvaluator()

    health = HealthCheckResult(
        service="checkout-api",
        status=HealthState.HEALTHY,
        uptime_seconds=50000,
        restarts_count=0,
        active_incidents=0,
        message="Core services healthy",
        checks={"process_alive": True},
    )
    metrics = MetricSnapshot(
        timestamp="2026-10-24T12:00:00Z",
        error_rate=0.08,  # 8% error rate: between SEV-3 (5%) and SEV-2 (20%)
        latency_p95_ms=620.0,
        latency_p50_ms=210.0,
        request_volume_rpm=1200,
        cpu_utilization=0.35,
        memory_utilization=0.45,
    )
    dependencies = [
        DependencyStatus(
            name="redis_cache",
            status=HealthState.UNHEALTHY,
            latency_ms=9999.0,
            message="Cache connection timeout",
            last_checked="2026-10-24T12:00:00Z",
        ),
        DependencyStatus(
            name="primary_db",
            status=HealthState.HEALTHY,
            latency_ms=12.0,
            message="Postgres healthy",
            last_checked="2026-10-24T12:00:00Z",
        ),
    ]

    assessment = evaluator.assess(
        service_name="checkout-api",
        health=health,
        metrics=metrics,
        dependencies=dependencies,
        alert_context={"workaround_active": True},
    )

    assert assessment.severity == SeverityLevel.SEV_3
    assert assessment.priority == ResponsePriority.P3_MODERATE
    assert any("workaround" in r.lower() for r in assessment.reasons)


def test_4_minor_non_critical_errors_is_sev4():
    """Scenario 4: Minor non-critical errors -> SEV-4."""
    evaluator = SeverityEvaluator()

    health = HealthCheckResult(
        service="checkout-api",
        status=HealthState.HEALTHY,
        uptime_seconds=100000,
        restarts_count=0,
        active_incidents=0,
        message="All systems operational",
        checks={"process_alive": True},
    )
    metrics = MetricSnapshot(
        timestamp="2026-10-24T12:00:00Z",
        error_rate=0.003,  # 0.3% error rate (< 5%)
        latency_p95_ms=45.0,
        latency_p50_ms=18.0,
        request_volume_rpm=1300,
        cpu_utilization=0.20,
        memory_utilization=0.30,
    )

    assessment = evaluator.assess(
        service_name="checkout-api",
        health=health,
        metrics=metrics,
    )

    assert assessment.severity == SeverityLevel.SEV_4
    assert assessment.priority == ResponsePriority.P4_LOW
    assert any("nominal" in r.lower() for r in assessment.reasons)


def test_5_human_caused_config_error_severity_based_on_impact_not_cause():
    """Scenario 5: Human-caused configuration error with widespread impact -> severity based on impact, not cause."""
    sim = ServiceSimulator("checkout-api")
    # Human typo causing massive failure
    sim.inject_invalid_config(
        bad_config_override={"db_pool_size": 0, "request_timeout_ms": -1},
        author="alice-developer-typo",
        reason="Human typo in database pool configuration",
    )

    evaluator = SeverityEvaluator()
    health = sim.check_health()
    metrics = sim.get_metrics()
    diff = sim.get_config_diff()

    assessment = evaluator.assess(
        service_name=sim.service_name,
        health=health,
        metrics=metrics,
        config_diff=diff,
    )

    # Despite cause being "human typo", impact is 85% error rate & UNHEALTHY -> SEV-1
    assert assessment.severity == SeverityLevel.SEV_1
    assert assessment.priority == ResponsePriority.P1_CRITICAL_URGENT
    # Root cause in config diff is noted, but does not downgrade severity
    assert diff.has_diff is True


def test_6_security_or_data_integrity_risk_protective_escalation():
    """Scenario 6: Security or data-integrity risk -> protective escalation."""
    sim = ServiceSimulator("checkout-api")
    # Injected data integrity failure
    sim.inject_data_integrity_risk("Database transaction rollback: Checksum mismatch on order ledger")

    orchestrator = IncidentOrchestrator(
        simulator=sim,
        llm_client=MockLLMClient(),
    )

    incident = orchestrator.run_incident_response(
        incident_id="INC-SEC-01",
        title="Transaction Ledger Checksum Failure",
    )

    # Must assess as SEV-1 and trigger protective escalation
    assert incident.severity == SeverityLevel.SEV_1
    assert incident.state == IncidentState.ESCALATED
    assert incident.severity_assessment.is_security_or_integrity_risk is True
    assert "protective escalation" in incident.escalation_reason.lower()
    # No automated remediation attempted
    assert len(incident.action_results) == 0


def test_7_missing_or_contradictory_evidence_records_uncertainty():
    """Scenario 7: Missing or contradictory evidence -> uncertainty is recorded."""
    evaluator = SeverityEvaluator()

    # Contradictory evidence: Health reports UNHEALTHY, but metrics error rate is 0.0%
    health = HealthCheckResult(
        service="checkout-api",
        status=HealthState.UNHEALTHY,
        uptime_seconds=1000,
        restarts_count=0,
        active_incidents=1,
        message="Inconclusive alert",
        checks={"process_alive": True},
    )
    metrics = MetricSnapshot(
        timestamp="2026-10-24T12:00:00Z",
        error_rate=0.0,
        latency_p95_ms=30.0,
        latency_p50_ms=15.0,
        request_volume_rpm=1000,
        cpu_utilization=0.2,
        memory_utilization=0.3,
    )

    assessment = evaluator.assess(
        service_name="checkout-api",
        health=health,
        metrics=metrics,
    )

    # Contradictory evidence must be explicitly recorded
    assert len(assessment.missing_or_uncertain_evidence) > 0
    assert any("contradictory" in u.lower() for u in assessment.missing_or_uncertain_evidence)
    # Conservative policy applies SEV-1/SEV-2 for tier-1
    assert assessment.severity in (SeverityLevel.SEV_1, SeverityLevel.SEV_2)


def test_8_severity_reassessment_when_new_evidence_arrives():
    """Scenario 8: Severity reassessment when new evidence arrives."""
    sim = ServiceSimulator("checkout-api")

    # Start with moderate degradation (SEV-2)
    sim.inject_elevated_error_rate(error_rate=0.45, reason="Transient resource contention")

    # Mock client that checks health, then an unavailable dependency outage is injected mid-investigation
    def step_with_mid_investigation_outage(incident, tools):
        executed = [tc.tool_name for tc in incident.tool_calls]
        if "check_health" not in executed:
            return AgentDecision(decision_type="TOOL_CALL", tool_name="check_health")
        if "get_dependency_health" not in executed:
            # Inject critical DB outage mid-flight
            sim.inject_unavailable_dependency("primary_db")
            return AgentDecision(decision_type="TOOL_CALL", tool_name="get_dependency_health")
        return AgentDecision(decision_type="ESCALATE", explanation="Escalating after DB outage detected.")

    class DynamicOutageMockClient(MockLLMClient):
        def decide_next_step(self, incident, tools):
            return step_with_mid_investigation_outage(incident, tools)

    orchestrator = IncidentOrchestrator(simulator=sim, llm_client=DynamicOutageMockClient())
    incident = orchestrator.run_incident_response(
        incident_id="INC-REASSESS-01",
        title="Dynamic Outage Escalation",
    )

    # Verify severity was updated during the lifecycle
    assert len(incident.severity_history) >= 2
    # Initial was SEV-2
    assert incident.severity_history[0].severity == SeverityLevel.SEV_2
    # Final escalated to SEV-1 due to critical primary_db outage
    assert incident.severity == SeverityLevel.SEV_1
    assert incident.state == IncidentState.ESCALATED


def test_9_severity_changes_do_not_bypass_approval_controls():
    """Scenario 9: Severity changes do not bypass approval controls."""
    sim = ServiceSimulator("checkout-api")
    # SEV-1 critical config outage
    sim.inject_invalid_config({"db_pool_size": -50})

    config = AgentConfig(high_risk_actions={"rollback_config"})
    # Approval callback strictly denies approval
    orchestrator = IncidentOrchestrator(
        simulator=sim,
        llm_client=MockLLMClient(),
        config=config,
        approval_callback=lambda action, args: False,
    )

    incident = orchestrator.run_incident_response(
        incident_id="INC-APPROVAL-01",
        title="Unauthorized SEV-1 Rollback Attempt",
    )

    # Even though incident was SEV-1, rollback_config was blocked and incident escalated
    assert incident.severity == SeverityLevel.SEV_1
    assert incident.state == IncidentState.ESCALATED
    assert "High-risk action" in (incident.escalation_reason or "")
    assert not any(a.action == "rollback_config" and a.success for a in incident.action_results)


def test_10_existing_config_drift_scenario_with_severity_integration():
    """Scenario 10: Existing config_drift scenario continues to work and tracks severity lifecycle."""
    sim = ServiceSimulator("checkout-api")
    sim.inject_invalid_config(
        bad_config_override={"db_pool_size": -10, "request_timeout_ms": 0},
        author="cd-pipeline",
        reason="Negative database connection pool",
    )

    config = AgentConfig(high_risk_actions={"rollback_config"})
    orchestrator = IncidentOrchestrator(
        simulator=sim,
        llm_client=MockLLMClient(),
        config=config,
        approval_callback=lambda action, args: True,  # Auto-approve
    )

    incident = orchestrator.run_incident_response(
        incident_id="INC-E2E-SEV",
        title="Config Drift with Severity Verification",
    )

    # Incident successfully resolves
    assert incident.state == IncidentState.RESOLVED
    assert any(a.action == "rollback_config" and a.success for a in incident.action_results)
    assert any(v.is_healthy for v in incident.verification_outcomes)
    # Severity history shows progression from SEV-1 (initial) to SEV-4 (post-recovery nominal)
    assert len(incident.severity_history) >= 2
    assert incident.severity_history[0].severity == SeverityLevel.SEV_1
    assert incident.severity == SeverityLevel.SEV_4  # Resolved service has nominal SEV-4 severity
