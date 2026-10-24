"""Comprehensive automated tests for all 10 required agent scenarios and safety gates."""

import pytest
from src.agent import AgentDecision, MockLLMClient
from src.config import AgentConfig
from src.models import IncidentState
from src.orchestrator import IncidentOrchestrator
from src.simulator import ServiceSimulator


def test_1_invalid_configuration_diagnosed_and_corrected():
    """Scenario 1: Invalid configuration diagnosed and corrected."""
    sim = ServiceSimulator("checkout-api")
    bad_config = {"db_pool_size": -10, "request_timeout_ms": 0}
    sim.inject_invalid_config(bad_config, author="bad-release-bot", reason="Negative pool size")

    config = AgentConfig(high_risk_actions={"rollback_config"})
    # Grant approval for rollback
    orchestrator = IncidentOrchestrator(
        simulator=sim,
        llm_client=MockLLMClient(),
        config=config,
        approval_callback=lambda action, args: True,
    )

    incident = orchestrator.run_incident_response(
        incident_id="INC-001",
        title="Checkout API Unhealthy - Config Error",
    )

    assert incident.state == IncidentState.RESOLVED
    assert incident.root_cause is not None
    assert "Configuration drift" in incident.root_cause
    assert any(a.action == "rollback_config" and a.success for a in incident.action_results)
    assert any(v.is_healthy for v in incident.verification_outcomes)
    assert sim.check_health().status.value == "HEALTHY"


def test_2_unavailable_dependency_detected_without_repeatedly_restarting():
    """Scenario 2: Unavailable dependency detected without repeatedly restarting the application."""
    sim = ServiceSimulator("checkout-api")
    sim.inject_unavailable_dependency("auth_service", message="Connection refused: port 8081 unreachable")

    orchestrator = IncidentOrchestrator(
        simulator=sim,
        llm_client=MockLLMClient(),
    )

    incident = orchestrator.run_incident_response(
        incident_id="INC-002",
        title="Auth Service Outage",
    )

    # Must escalate to humans, NOT loop restart
    assert incident.state == IncidentState.ESCALATED
    assert "auth_service" in (incident.escalation_reason or "")

    # Count restart attempts: must NOT repeatedly restart
    restart_calls = [tc for tc in incident.tool_calls if tc.tool_name == "restart_service"]
    assert len(restart_calls) <= 1


def test_3_elevated_error_rate_investigated():
    """Scenario 3: Elevated error rate investigated and resolved via restart."""
    sim = ServiceSimulator("checkout-api")
    sim.inject_elevated_error_rate(error_rate=0.48, reason="Worker thread pool exhaustion")

    orchestrator = IncidentOrchestrator(
        simulator=sim,
        llm_client=MockLLMClient(),
    )

    incident = orchestrator.run_incident_response(
        incident_id="INC-003",
        title="High Error Rate Surge",
    )

    assert incident.state == IncidentState.RESOLVED
    assert any(a.action == "restart_service" and a.success for a in incident.action_results)
    assert any(v.is_healthy for v in incident.verification_outcomes)
    assert sim.check_health().status.value == "HEALTHY"


def test_4_failed_remediation_followed_by_further_investigation():
    """Scenario 4: Failed remediation followed by further investigation."""
    sim = ServiceSimulator("checkout-api")
    # Both dependency outage and elevated errors
    sim.inject_unavailable_dependency("primary_db")

    # Mock client attempts restart first, then sees it fail verification and escalates
    mock_llm = MockLLMClient(
        scripted_decisions=[
            AgentDecision(decision_type="TOOL_CALL", tool_name="check_health"),
            AgentDecision(decision_type="TOOL_CALL", tool_name="restart_service"),
            # Post-failed-restart verification fails, returns to INVESTIGATING
            AgentDecision(decision_type="TOOL_CALL", tool_name="get_dependency_health"),
            AgentDecision(
                decision_type="ESCALATE",
                explanation="Restart failed because primary_db is down. Escalating.",
                escalation_reason="Dependency primary_db connection refused; local restart failed.",
            ),
        ]
    )

    orchestrator = IncidentOrchestrator(simulator=sim, llm_client=mock_llm)
    incident = orchestrator.run_incident_response(
        incident_id="INC-004",
        title="Database Down - Failed Restart",
    )

    assert incident.state == IncidentState.ESCALATED
    assert any(a.action == "restart_service" and not a.success for a in incident.action_results)
    assert any(not v.is_healthy for v in incident.verification_outcomes)
    assert "primary_db" in (incident.escalation_reason or "")


def test_5_escalation_when_no_safe_fix_available():
    """Scenario 5: Escalation when no safe fix is available."""
    sim = ServiceSimulator("checkout-api")
    sim.inject_unavailable_dependency("payment_gateway", message="External 503 gateway unavailable")

    mock_llm = MockLLMClient(
        scripted_decisions=[
            AgentDecision(decision_type="TOOL_CALL", tool_name="check_health"),
            AgentDecision(decision_type="TOOL_CALL", tool_name="get_dependency_health"),
            AgentDecision(
                decision_type="ESCALATE",
                explanation="External payment gateway unavailable. No local remediation possible.",
                escalation_reason="Third-party payment vendor outage. Contacting vendor support.",
            ),
        ]
    )

    orchestrator = IncidentOrchestrator(simulator=sim, llm_client=mock_llm)
    incident = orchestrator.run_incident_response(
        incident_id="INC-005",
        title="Payment Gateway Outage",
    )

    assert incident.state == IncidentState.ESCALATED
    assert "payment vendor" in incident.escalation_reason.lower()
    # No risky actions taken
    assert len(incident.action_results) == 0


def test_6_maximum_iteration_limit_enforced():
    """Scenario 6: Maximum iteration limit enforced."""
    sim = ServiceSimulator("checkout-api")
    config = AgentConfig(max_iterations=3)

    # Mock client that just loops calling check_health
    mock_llm = MockLLMClient(
        scripted_decisions=[
            AgentDecision(decision_type="TOOL_CALL", tool_name="check_health"),
            AgentDecision(decision_type="TOOL_CALL", tool_name="check_health"),
            AgentDecision(decision_type="TOOL_CALL", tool_name="check_health"),
            AgentDecision(decision_type="TOOL_CALL", tool_name="check_health"),
        ]
    )

    orchestrator = IncidentOrchestrator(simulator=sim, llm_client=mock_llm, config=config)
    incident = orchestrator.run_incident_response(
        incident_id="INC-006",
        title="Infinite Diagnostic Loop",
    )

    assert incident.state == IncidentState.FAILED
    assert "maximum iteration limit" in incident.escalation_reason
    assert incident.iterations <= 3


def test_7_invalid_tool_calls_rejected():
    """Scenario 7: Invalid tool calls rejected."""
    sim = ServiceSimulator("checkout-api")

    mock_llm = MockLLMClient(
        scripted_decisions=[
            AgentDecision(decision_type="TOOL_CALL", tool_name="delete_production_database", tool_arguments={}),
            AgentDecision(decision_type="TOOL_CALL", tool_name="get_recent_logs", tool_arguments={"limit": 9999}),
            AgentDecision(decision_type="ESCALATE", explanation="Escalating after tool validation failure."),
        ]
    )

    orchestrator = IncidentOrchestrator(simulator=sim, llm_client=mock_llm)
    incident = orchestrator.run_incident_response(
        incident_id="INC-007",
        title="Invalid Tool Invocation",
    )

    # First tool was unrecognized
    assert not incident.tool_calls[0].success
    assert "Unrecognized tool" in (incident.tool_calls[0].error or "")

    # Second tool had invalid limit (> 100)
    assert not incident.tool_calls[1].success
    assert "Invalid arguments" in (incident.tool_calls[1].error or "")

    assert incident.state == IncidentState.ESCALATED


def test_8_resolution_prevented_when_health_checks_fail():
    """Scenario 8: Resolution prevented when health checks fail."""
    sim = ServiceSimulator("checkout-api")
    # Service has active fault
    sim.inject_invalid_config({"db_pool_size": -50})

    # Model tries to prematurely claim RESOLVE without fixing or verifying
    mock_llm = MockLLMClient(
        scripted_decisions=[
            AgentDecision(decision_type="RESOLVE", explanation="Everything looks fine from here!"),
            # Orchestrator blocks early resolve, continues loop
            AgentDecision(decision_type="ESCALATE", explanation="Could not resolve without verification."),
        ]
    )

    orchestrator = IncidentOrchestrator(simulator=sim, llm_client=mock_llm)
    incident = orchestrator.run_incident_response(
        incident_id="INC-008",
        title="Premature Resolution Attempt",
    )

    # Must NOT be RESOLVED
    assert incident.state != IncidentState.RESOLVED
    assert any("blocked by safety guard" in obs for obs in incident.observations)


def test_9_high_risk_actions_blocked_without_approval():
    """Scenario 9: High-risk actions blocked without approval."""
    sim = ServiceSimulator("checkout-api")
    sim.inject_invalid_config({"request_timeout_ms": -1})

    # rollback_config is high risk, and approval callback denies it
    config = AgentConfig(high_risk_actions={"rollback_config"})
    orchestrator = IncidentOrchestrator(
        simulator=sim,
        llm_client=MockLLMClient(),
        config=config,
        approval_callback=lambda action, args: False,  # Deny approval
    )

    incident = orchestrator.run_incident_response(
        incident_id="INC-009",
        title="Unauthorized Rollback Attempt",
    )

    # Action was blocked and escalated
    assert incident.state == IncidentState.ESCALATED
    assert "High-risk action" in (incident.escalation_reason or "")
    # rollback_config was NOT executed on simulator
    assert not any(a.action == "rollback_config" and a.success for a in incident.action_results)


def test_10_tool_errors_and_timeouts_handled_safely():
    """Scenario 10: Tool errors and timeouts handled safely."""
    sim = ServiceSimulator("checkout-api")

    # Set very short timeout to simulate tool timeout
    config = AgentConfig(operation_timeout_seconds=0.001)

    # Inject artificial slow handler in dispatcher
    import time
    def slow_tool(args):
        time.sleep(0.05)
        return {"done": True}

    orchestrator = IncidentOrchestrator(
        simulator=sim,
        llm_client=MockLLMClient(
            scripted_decisions=[
                AgentDecision(decision_type="TOOL_CALL", tool_name="check_health"),
                AgentDecision(decision_type="ESCALATE", explanation="Tool timed out safely."),
            ]
        ),
        config=config,
    )
    # Patch check_health handler to be slow
    from src.tools import CheckHealthArgs
    orchestrator.dispatcher._handlers["check_health"] = (CheckHealthArgs, slow_tool)

    incident = orchestrator.run_incident_response(
        incident_id="INC-010",
        title="Tool Timeout Test",
    )

    # Tool timed out without crashing the orchestrator process
    assert len(incident.tool_calls) > 0
    assert not incident.tool_calls[0].success
    assert "timed out" in (incident.tool_calls[0].error or "").lower()
    assert incident.state in (IncidentState.ESCALATED, IncidentState.FAILED)
