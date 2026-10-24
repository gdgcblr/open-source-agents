"""Incident Orchestrator managing dynamic lifecycle states and safety enforcement."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.agent import AgentDecision, BaseLLMClient
from src.config import AgentConfig
from src.models import (
    IncidentRecord,
    IncidentState,
    RemediationResult,
    SeverityLevel,
    ToolCallRecord,
    VerificationResult,
)
from src.safety import SafetyPolicy, execute_with_timeout
from src.severity import SeverityEvaluator
from src.simulator import ServiceSimulator
from src.tools import ToolDispatcher, ToolExecutionResult


class IncidentOrchestrator:
    """Coordinates detection, investigation, remediation, verification, and safety enforcement."""

    def __init__(
        self,
        simulator: ServiceSimulator,
        llm_client: BaseLLMClient,
        config: Optional[AgentConfig] = None,
        approval_callback: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        severity_evaluator: Optional[SeverityEvaluator] = None,
    ):
        self.simulator = simulator
        self.llm_client = llm_client
        self.config = config or AgentConfig()
        self.dispatcher = ToolDispatcher(simulator)
        self.safety = SafetyPolicy(self.config, approval_callback=approval_callback)
        self.severity_evaluator = severity_evaluator or SeverityEvaluator()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def run_incident_response(
        self,
        incident_id: str,
        title: str,
        initial_symptoms: Optional[List[str]] = None,
        alert_context: Optional[Dict[str, Any]] = None,
    ) -> IncidentRecord:
        """Run autonomous end-to-end incident response loop."""
        incident = IncidentRecord(
            incident_id=incident_id,
            title=title,
            service_name=self.simulator.service_name,
            state=IncidentState.DETECTED,
            symptoms=initial_symptoms or ["Automated alert: Service health degraded or unhealthy."],
            created_at=self._now(),
            updated_at=self._now(),
        )

        # 1. Gather initial evidence to assess impact and assign initial severity
        initial_health = self.simulator.check_health()
        initial_metrics = self.simulator.get_metrics()
        initial_logs = self.simulator.get_recent_logs(limit=10)
        initial_assessment = self.severity_evaluator.assess(
            service_name=self.simulator.service_name,
            health=initial_health,
            metrics=initial_metrics,
            logs=initial_logs,
            alert_context=alert_context,
        )
        incident.severity = initial_assessment.severity
        incident.severity_assessment = initial_assessment
        incident.severity_history.append(initial_assessment)
        incident.add_observation(
            f"Initial severity assigned: {initial_assessment.severity.value} ({initial_assessment.priority.value}). "
            f"Reasons: {'; '.join(initial_assessment.reasons)}"
        )

        # Immediate protective escalation for credible security or data-integrity risk
        if initial_assessment.is_security_or_integrity_risk:
            incident.state = IncidentState.ESCALATED
            incident.escalation_reason = (
                f"Immediate protective escalation: Credible security or data-integrity risk: "
                f"{'; '.join(initial_assessment.reasons)}"
            )
            incident.add_observation(incident.escalation_reason)
            incident.updated_at = self._now()
            return incident

        # Transition to INVESTIGATING
        incident.state = IncidentState.INVESTIGATING
        incident.add_observation(f"Incident response started for {incident.service_name}.")

        while incident.iterations < self.config.max_iterations:
            incident.iterations += 1
            incident.updated_at = self._now()

            # Safety check: iteration limit
            if not self.safety.check_iteration_limit(incident.iterations):
                incident.state = IncidentState.FAILED
                incident.escalation_reason = (
                    f"Execution terminated: reached maximum iteration limit ({self.config.max_iterations})."
                )
                break

            # Safety check: tool call limit
            if not self.safety.check_tool_call_limit():
                incident.state = IncidentState.FAILED
                incident.escalation_reason = (
                    f"Execution terminated: reached maximum tool calls limit ({self.config.max_tool_calls})."
                )
                break

            # 1. Ask LLM client to decide the next step
            try:
                decision = execute_with_timeout(
                    self.llm_client.decide_next_step,
                    args=(incident, self.dispatcher.registered_tool_names),
                    timeout_seconds=self.config.operation_timeout_seconds,
                )
            except TimeoutError as te:
                incident.add_observation(f"LLM reasoning timeout: {str(te)}")
                incident.state = IncidentState.FAILED
                incident.escalation_reason = "Model operation timed out."
                break
            except Exception as e:
                incident.add_observation(f"LLM reasoning error: {str(e)}")
                incident.state = IncidentState.FAILED
                incident.escalation_reason = f"Model exception: {str(e)}"
                break

            # 2. Process LLM decision
            if decision.decision_type == "ESCALATE":
                incident.state = IncidentState.ESCALATED
                incident.escalation_reason = decision.escalation_reason or decision.explanation
                if decision.root_cause:
                    incident.root_cause = decision.root_cause
                incident.add_observation(f"Incident escalated to humans: {incident.escalation_reason}")
                if incident.severity == SeverityLevel.SEV_1:
                    incident.add_observation("URGENT: SEV-1 incident escalated immediately to primary on-call SRE.")
                break

            elif decision.decision_type == "RESOLVE":
                # Verify whether incident can actually be marked RESOLVED
                latest_verification = (
                    incident.verification_outcomes[-1]
                    if incident.verification_outcomes
                    else None
                )
                is_sec = bool(incident.severity_assessment and incident.severity_assessment.is_security_or_integrity_risk)
                can_res, reason = self.safety.can_resolve(latest_verification, is_security_or_integrity_risk=is_sec)
                if can_res:
                    incident.state = IncidentState.RESOLVED
                    incident.root_cause = decision.root_cause or incident.root_cause
                    incident.resolution_summary = decision.explanation or "Incident successfully resolved."
                    incident.add_observation("Resolution verified and confirmed.")
                    break
                else:
                    incident.add_observation(f"Attempted early resolution blocked by safety guard: {reason}")
                    # Force a verification or continue investigating
                    continue

            elif decision.decision_type == "TOOL_CALL":
                tool_name = decision.tool_name
                tool_args = decision.tool_arguments or {}

                if not tool_name:
                    incident.add_observation("LLM proposed TOOL_CALL without tool_name.")
                    continue

                is_read_only = self.dispatcher.is_read_only(tool_name)
                is_remediation = self.dispatcher.is_remediation(tool_name)

                # Set DIAGNOSED state if a remediation tool is chosen and root cause is stated
                if is_remediation:
                    incident.state = IncidentState.DIAGNOSED
                    if decision.root_cause:
                        incident.root_cause = decision.root_cause
                        incident.add_hypothesis(decision.root_cause)

                # Safety check before tool execution
                is_sec = bool(incident.severity_assessment and incident.severity_assessment.is_security_or_integrity_risk)
                is_allowed, block_reason = self.safety.validate_tool_intent(
                    tool_name=tool_name,
                    arguments=tool_args,
                    is_read_only=is_read_only,
                    registered_tools=self.dispatcher.registered_tool_names,
                    is_security_or_integrity_risk=is_sec,
                )

                if not is_allowed:
                    incident.record_tool_call(
                        ToolCallRecord(
                            tool_name=tool_name,
                            arguments=tool_args,
                            result=None,
                            success=False,
                            error=block_reason,
                            timestamp=self._now(),
                        )
                    )
                    incident.add_observation(f"Safety violation blocked tool execution: {block_reason}")
                    # If action was blocked due to repeated failures, permission, or security risk, escalate
                    if any(k in (block_reason or "") for k in ("infinite loops", "allowlist", "High-risk action", "security or data-integrity")):
                        incident.state = IncidentState.ESCALATED
                        incident.escalation_reason = block_reason
                        if incident.severity == SeverityLevel.SEV_1:
                            incident.add_observation("URGENT: SEV-1 incident escalated immediately to primary on-call SRE.")
                        break
                    continue

                # Execute tool with timeout protection
                if is_remediation:
                    incident.state = IncidentState.REMEDIATING

                try:
                    tool_res: ToolExecutionResult = execute_with_timeout(
                        self.dispatcher.execute,
                        args=(tool_name, tool_args),
                        timeout_seconds=self.config.operation_timeout_seconds,
                    )
                except TimeoutError as te:
                    tool_res = ToolExecutionResult(
                        tool_name=tool_name,
                        success=False,
                        data=None,
                        error=f"Tool execution timed out after {self.config.operation_timeout_seconds}s",
                    )
                except Exception as e:
                    tool_res = ToolExecutionResult(
                        tool_name=tool_name,
                        success=False,
                        data=None,
                        error=f"Unhandled tool error: {str(e)}",
                    )

                # Record tool call in in-memory incident record
                incident.record_tool_call(
                    ToolCallRecord(
                        tool_name=tool_name,
                        arguments=tool_args,
                        result=tool_res.data,
                        success=tool_res.success,
                        error=tool_res.error,
                        timestamp=self._now(),
                    )
                )

                # Update safety metrics
                self.safety.record_tool_execution(
                    tool_name=tool_name,
                    success=tool_res.success,
                    is_remediation=is_remediation,
                )

                # Dynamic Severity Reassessment when material new evidence arrives
                current_health = self.simulator.check_health()
                current_metrics = self.simulator.get_metrics()
                current_deps = self.simulator.get_dependency_health()
                current_diff = self.simulator.get_config_diff()
                current_logs = self.simulator.get_recent_logs(limit=20)

                reassessed = self.severity_evaluator.assess(
                    service_name=self.simulator.service_name,
                    health=current_health,
                    metrics=current_metrics,
                    dependencies=current_deps,
                    config_diff=current_diff,
                    logs=current_logs,
                    alert_context=alert_context,
                )

                if incident.severity != reassessed.severity or reassessed.is_security_or_integrity_risk != is_sec:
                    incident.severity = reassessed.severity
                    incident.severity_assessment = reassessed
                    incident.severity_history.append(reassessed)
                    incident.add_observation(
                        f"Severity reassessed to {reassessed.severity.value} ({reassessed.priority.value}): {'; '.join(reassessed.reasons)}"
                    )

                    if reassessed.is_security_or_integrity_risk:
                        incident.state = IncidentState.ESCALATED
                        incident.escalation_reason = (
                            f"Immediate protective escalation: Material new evidence revealed security/data-integrity risk: "
                            f"{'; '.join(reassessed.reasons)}"
                        )
                        incident.add_observation(incident.escalation_reason)
                        break

                # If remediation action executed, store result and independently verify
                if is_remediation:
                    remed_result = RemediationResult(
                        action=tool_name,
                        success=tool_res.success and (tool_res.data.get("success", False) if isinstance(tool_res.data, dict) else True),
                        message=tool_res.data.get("message", "") if isinstance(tool_res.data, dict) else str(tool_res.data),
                        details=tool_res.data.get("details", {}) if isinstance(tool_res.data, dict) else {},
                        timestamp=self._now(),
                    )
                    incident.action_results.append(remed_result)

                    # State -> VERIFYING
                    incident.state = IncidentState.VERIFYING
                    verification = self.simulator.verify_recovery()
                    incident.verification_outcomes.append(verification)

                    if verification.is_healthy:
                        # Success verified independently
                        incident.state = IncidentState.RESOLVED
                        incident.resolution_summary = (
                            f"Action '{tool_name}' successfully executed and verified healthy: {verification.message}"
                        )
                        incident.add_observation(f"Independent verification PASSED: {verification.message}")
                        
                        # Reassess severity to reflect healthy recovered state (SEV-4)
                        resolved_assessment = self.severity_evaluator.assess(
                            service_name=self.simulator.service_name,
                            health=self.simulator.check_health(),
                            metrics=self.simulator.get_metrics(),
                            dependencies=self.simulator.get_dependency_health(),
                            config_diff=self.simulator.get_config_diff(),
                            logs=self.simulator.get_recent_logs(limit=10),
                            alert_context=alert_context,
                        )
                        incident.severity = resolved_assessment.severity
                        incident.severity_assessment = resolved_assessment
                        incident.severity_history.append(resolved_assessment)
                        break
                    else:
                        # Verification failed: move back to INVESTIGATING to reconsider plan
                        incident.state = IncidentState.INVESTIGATING
                        incident.add_observation(
                            f"Remediation '{tool_name}' did not restore health. Verification FAILED: {verification.message}"
                        )

                # If tool was verify_recovery directly called
                elif tool_name == "verify_recovery":
                    if tool_res.success and isinstance(tool_res.data, dict):
                        verification = VerificationResult(**tool_res.data)
                        incident.verification_outcomes.append(verification)
                        if verification.is_healthy:
                            incident.state = IncidentState.RESOLVED
                            incident.resolution_summary = "Service verified healthy."
                            resolved_assessment = self.severity_evaluator.assess(
                                service_name=self.simulator.service_name,
                                health=self.simulator.check_health(),
                                metrics=self.simulator.get_metrics(),
                                dependencies=self.simulator.get_dependency_health(),
                                config_diff=self.simulator.get_config_diff(),
                                logs=self.simulator.get_recent_logs(limit=10),
                                alert_context=alert_context,
                            )
                            incident.severity = resolved_assessment.severity
                            incident.severity_assessment = resolved_assessment
                            incident.severity_history.append(resolved_assessment)
                            break

        # If loop terminated without resolved or escalated state
        if incident.state in (IncidentState.DETECTED, IncidentState.INVESTIGATING, IncidentState.REMEDIATING, IncidentState.VERIFYING):
            incident.state = IncidentState.ESCALATED
            incident.escalation_reason = "Incident loop completed without resolving. Escalating to human on-call."
            if incident.severity == SeverityLevel.SEV_1:
                incident.add_observation("URGENT: SEV-1 incident escalated immediately to primary on-call SRE.")

        incident.updated_at = self._now()
        return incident
