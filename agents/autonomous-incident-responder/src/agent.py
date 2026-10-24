"""Agent reasoning interfaces and LLM integrations.

Provides Gemini function calling via google-genai SDK and a deterministic
mock-model interface for offline testing and evaluation.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.config import AgentConfig
from src.models import IncidentRecord, HealthState


class AgentDecision(BaseModel):
    """Structured decision output from LLM reasoning step."""
    decision_type: str = Field(description="'TOOL_CALL', 'RESOLVE', or 'ESCALATE'")
    tool_name: Optional[str] = None
    tool_arguments: Dict[str, Any] = Field(default_factory=dict)
    explanation: str = ""
    root_cause: Optional[str] = None
    escalation_reason: Optional[str] = None


class BaseLLMClient(ABC):
    """Abstract interface for incident response reasoning."""

    @abstractmethod
    def decide_next_step(
        self,
        incident: IncidentRecord,
        available_tools: List[str],
    ) -> AgentDecision:
        """Analyze current incident state and decide the next diagnostic or remediation step."""
        pass


class MockLLMClient(BaseLLMClient):
    """Deterministic mock-model interface for repeatable testing without Gemini API key."""

    def __init__(self, scripted_decisions: Optional[List[AgentDecision]] = None):
        self.scripted_decisions: List[AgentDecision] = list(scripted_decisions or [])
        self.decision_index: int = 0

    def add_scripted_decision(self, decision: AgentDecision) -> None:
        self.scripted_decisions.append(decision)

    def decide_next_step(
        self,
        incident: IncidentRecord,
        available_tools: List[str],
    ) -> AgentDecision:
        # If scripted decisions are provided, consume them sequentially
        if self.scripted_decisions and self.decision_index < len(self.scripted_decisions):
            decision = self.scripted_decisions[self.decision_index]
            self.decision_index += 1
            return decision

        # Otherwise, execute dynamic deterministic reasoning based on accumulated evidence
        executed_tools = [tc.tool_name for tc in incident.tool_calls]

        # 1. First step: check health if not checked
        if "check_health" not in executed_tools:
            return AgentDecision(
                decision_type="TOOL_CALL",
                tool_name="check_health",
                tool_arguments={},
                explanation="Initial diagnostic: verify current health and active alerts.",
            )

        # 2. Check recent logs for error clues
        if "get_recent_logs" not in executed_tools:
            return AgentDecision(
                decision_type="TOOL_CALL",
                tool_name="get_recent_logs",
                tool_arguments={"limit": 20},
                explanation="Examine recent application logs for stack traces or error spikes.",
            )

        # 3. Check configuration diff
        if "get_config_diff" not in executed_tools:
            return AgentDecision(
                decision_type="TOOL_CALL",
                tool_name="get_config_diff",
                tool_arguments={},
                explanation="Inspect configuration drift against known-good baseline.",
            )

        # 4. Check dependencies
        if "get_dependency_health" not in executed_tools:
            return AgentDecision(
                decision_type="TOOL_CALL",
                tool_name="get_dependency_health",
                tool_arguments={},
                explanation="Check connectivity and health of upstream dependencies.",
            )

        # Synthesize collected evidence:
        has_config_drift = False
        drift_keys = []
        unavailable_deps = []
        elevated_errors = False

        for tc in incident.tool_calls:
            if tc.tool_name == "get_config_diff" and tc.success and tc.result:
                if tc.result.get("has_diff"):
                    has_config_drift = True
                    drift_keys = tc.result.get("changed_keys", [])
            elif tc.tool_name == "get_dependency_health" and tc.success and tc.result:
                for dep in tc.result:
                    if dep.get("status") in ("UNHEALTHY", "DEGRADED"):
                        unavailable_deps.append(dep.get("name"))
            elif tc.tool_name == "get_metrics" and tc.success and tc.result:
                if tc.result.get("error_rate", 0) > 0.05:
                    elevated_errors = True
            elif tc.tool_name == "check_health" and tc.success and tc.result:
                if "Elevated error rate" in tc.result.get("message", ""):
                    elevated_errors = True

        # Remediation path A: Config drift detected -> Roll back config
        if has_config_drift:
            if "rollback_config" not in executed_tools:
                return AgentDecision(
                    decision_type="TOOL_CALL",
                    tool_name="rollback_config",
                    tool_arguments={},
                    explanation=f"Identified invalid configuration in parameters {drift_keys}. Rolling back to known-good baseline.",
                    root_cause=f"Configuration drift in parameters {drift_keys}",
                )
            if "verify_recovery" not in executed_tools or executed_tools[-1] == "rollback_config":
                return AgentDecision(
                    decision_type="TOOL_CALL",
                    tool_name="verify_recovery",
                    tool_arguments={},
                    explanation="Verify that configuration rollback restored service health.",
                )
            # If verify_recovery succeeded
            last_tc = incident.tool_calls[-1]
            if last_tc.tool_name == "verify_recovery" and last_tc.result.get("is_healthy"):
                return AgentDecision(
                    decision_type="RESOLVE",
                    explanation="Service successfully recovered after configuration rollback.",
                    root_cause=f"Configuration drift in parameters {drift_keys}",
                )

        # Remediation path B: Dependency outage detected
        if unavailable_deps:
            # An external dependency outage cannot be fixed by local restart
            # Avoid repeated restarts for external outages: escalate immediately
            return AgentDecision(
                decision_type="ESCALATE",
                explanation=f"Critical upstream dependency outage detected: {unavailable_deps}. No safe local remediation available.",
                root_cause=f"Upstream dependency outage: {unavailable_deps}",
                escalation_reason=f"External dependency outage: {unavailable_deps}. Human / infrastructure intervention required.",
            )

        # Remediation path C: Elevated error rate without config drift or dependency failure
        if elevated_errors:
            if "restart_service" not in executed_tools:
                return AgentDecision(
                    decision_type="TOOL_CALL",
                    tool_name="restart_service",
                    tool_arguments={},
                    explanation="Elevated error rate caused by internal transient worker/memory leak. Initiating graceful restart.",
                    root_cause="Internal resource exhaustion / memory leak",
                )
            if "verify_recovery" not in executed_tools or executed_tools[-1] == "restart_service":
                return AgentDecision(
                    decision_type="TOOL_CALL",
                    tool_name="verify_recovery",
                    tool_arguments={},
                    explanation="Verify recovery post-restart.",
                )
            last_tc = incident.tool_calls[-1]
            if last_tc.tool_name == "verify_recovery" and last_tc.result.get("is_healthy"):
                return AgentDecision(
                    decision_type="RESOLVE",
                    explanation="Service restored to nominal health after restart.",
                    root_cause="Transient thread pool / worker leak",
                )

        # Fallback: if nothing worked, escalate
        return AgentDecision(
            decision_type="ESCALATE",
            explanation="Diagnostic data exhausted without identifying a permitted remediation.",
            escalation_reason="Root cause uncertain or remediation exhausted.",
        )


class GeminiLLMClient(BaseLLMClient):
    """Gemini-powered reasoning client using the official Google Gen AI SDK."""

    def __init__(self, config: AgentConfig):
        self.config = config
        if not config.has_valid_api_key():
            raise ValueError(
                "Gemini API key is not configured. Set GEMINI_API_KEY environment variable."
            )

        # Initialize official Gen AI SDK client
        from google import genai
        self.client = genai.Client(api_key=config.api_key)

    def _build_system_prompt(self, available_tools: List[str]) -> str:
        return f"""You are an Autonomous Site Reliability Engineer (DevOps Incident Responder).
Your goal is to detect, investigate, and remediate simulated service incidents safely and deterministically.

Operational Principles:
1. Thorough Investigation: Always check health, recent logs, metrics, config diff, and dependency health before acting.
2. Safety First: Only invoke tools from the permitted list: {available_tools}.
3. Permitted Remediation: If invalid configuration is detected, use rollback_config. If transient resource leaks/errors, restart_service.
4. Dependency Outage Safety: If an external dependency is unavailable, do NOT repeatedly restart the service. Instead, escalate to humans.
5. Verification Prerequisite: Always execute verify_recovery after any remediation action.
6. Escalation: If no safe fix is available, cause is uncertain, or verification fails after remediation, conclude with ESCALATE.

When you want to call a tool, call the appropriate function.
If you have verified recovery and the incident is resolved, conclude with decision_type 'RESOLVE' and state the root cause.
If remediation is impossible or failed, conclude with decision_type 'ESCALATE' and state the escalation reason.
"""

    def decide_next_step(
        self,
        incident: IncidentRecord,
        available_tools: List[str],
    ) -> AgentDecision:
        """Call Gemini model with function calling declarations."""
        from google import genai
        from google.genai import types

        # Build context summary
        history_summary = []
        for tc in incident.tool_calls:
            history_summary.append({
                "tool": tc.tool_name,
                "arguments": tc.arguments,
                "success": tc.success,
                "result_snippet": str(tc.result)[:300] if tc.result else str(tc.error),
            })

        user_content = (
            f"Active Incident: {incident.incident_id} - {incident.title}\n"
            f"Service: {incident.service_name}\n"
            f"Current State: {incident.state.value}\n"
            f"Initial Symptoms: {incident.symptoms}\n"
            f"Observations So Far: {incident.observations}\n"
            f"Tool Execution History ({len(history_summary)} calls):\n"
            f"{json.dumps(history_summary, indent=2)}\n\n"
            "What is the next step to investigate, remediate, verify, or escalate?"
        )

        # Define tool function declarations for Gemini
        function_declarations = [
            types.FunctionDeclaration(
                name="check_health",
                description="Check current health status and active alerts for the service.",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
            types.FunctionDeclaration(
                name="get_recent_logs",
                description="Fetch recent application logs to inspect errors and stack traces.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "limit": types.Schema(type=types.Type.INTEGER, description="Number of logs (1-100)"),
                        "level": types.Schema(type=types.Type.STRING, description="Optional level (INFO, WARN, ERROR, CRITICAL)"),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="get_metrics",
                description="Fetch error rate, latency percentiles, and resource utilization metrics.",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
            types.FunctionDeclaration(
                name="get_dependency_health",
                description="Inspect connectivity and health of upstream dependencies (databases, auth, cache, APIs).",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
            types.FunctionDeclaration(
                name="get_config_diff",
                description="Compare running service configuration with known-good baseline.",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
            types.FunctionDeclaration(
                name="get_deployment_history",
                description="Inspect recent deployments and configuration releases.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "limit": types.Schema(type=types.Type.INTEGER, description="Number of deployments (1-50)")
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="restart_service",
                description="Gracefully restart the service process to clear transient resource leaks.",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
            types.FunctionDeclaration(
                name="rollback_config",
                description="Roll back configuration parameters to known-good baseline.",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
            types.FunctionDeclaration(
                name="verify_recovery",
                description="Independently verify whether the service and dependencies have fully recovered.",
                parameters=types.Schema(type=types.Type.OBJECT, properties={}),
            ),
        ]

        # Filter function declarations to only available tools
        active_tools = [fd for fd in function_declarations if fd.name in available_tools]
        tools_config = [types.Tool(function_declarations=active_tools)]

        config = types.GenerateContentConfig(
            system_instruction=self._build_system_prompt(available_tools),
            tools=tools_config,
            temperature=0.1,
        )

        # Call Gemini with automatic backoff for free-tier rate limits (429)
        import time
        max_retries = 3
        response = None
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.config.model_name,
                    contents=user_content,
                    config=config,
                )
                break
            except Exception as e:
                err_text = str(e)
                if ("429" in err_text or "RESOURCE_EXHAUSTED" in err_text) and attempt < max_retries - 1:
                    time.sleep(10)
                    continue
                raise

        # Check for function calls
        if response.function_calls:
            call = response.function_calls[0]
            call_args = dict(call.args) if call.args else {}
            explanation = f"Invoking tool {call.name}"
            try:
                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if hasattr(part, "text") and part.text:
                            explanation = part.text
                            break
            except Exception:
                pass

            return AgentDecision(
                decision_type="TOOL_CALL",
                tool_name=call.name,
                tool_arguments=call_args,
                explanation=explanation,
            )

        # Text response indicating resolution or escalation
        text = response.text or ""
        text_lower = text.lower()
        if "escalat" in text_lower:
            return AgentDecision(
                decision_type="ESCALATE",
                explanation=text,
                escalation_reason=text,
            )
        elif "resolv" in text_lower:
            return AgentDecision(
                decision_type="RESOLVE",
                explanation=text,
                root_cause=text,
            )

        return AgentDecision(
            decision_type="TOOL_CALL",
            tool_name="verify_recovery",
            tool_arguments={},
            explanation="Performing verification check.",
        )
