"""Bounded model/tool orchestration loop."""
import json
from openai import OpenAI

from .audit import AuditLogger
from .config import Settings
from .context import SYSTEM_POLICY, build_context
from .cost import CostMeter
from .decision import DecisionGate, LocalDecisionGate
from .guardrails import (
    GuardrailViolation, detect_injection_markers, validate_output,
    validate_tool_name, validate_user_input,
)
from .memory import MemoryStore
from .models import RunResult
from .tools import build_tools


class SecureAgent:
    def __init__(
        self,
        settings: Settings,
        client=None,
        decision_gate: DecisionGate | None = None,
    ):
        self.settings = settings
        if client is None:
            if not settings.api_key:
                raise ValueError("OPENAI_API_KEY is required for live model calls.")
            client = OpenAI(api_key=settings.api_key, timeout=30.0, max_retries=1)
        self.client = client
        self.memory = MemoryStore(settings.memory_db_path)
        self.audit = AuditLogger(settings.audit_log_path)
        self.tools = build_tools(self.memory, settings.user_id)
        self.decision_gate = decision_gate or LocalDecisionGate()

    def run(self, user_request: str) -> RunResult:
        request = validate_user_input(user_request, self.settings)
        injection_flag = detect_injection_markers(request)
        self.audit.event(
            "request_received",
            user_id=self.settings.user_id,
            input_chars=len(request),
            injection_marker_detected=injection_flag,
        )
        meter = CostMeter(
            max_cost_usd=self.settings.max_estimated_cost_usd,
            input_rate_per_million=self.settings.input_usd_per_million_tokens,
            output_rate_per_million=self.settings.output_usd_per_million_tokens,
        )
        context = build_context(self.memory, self.settings.user_id, request)
        messages = [
            {"role": "system", "content": SYSTEM_POLICY},
            {"role": "user", "content": context},
        ]
        tool_calls_used = 0
        names = set(self.tools)
        tool_schemas = [
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                    "strict": True,
                },
            }
            for spec in self.tools.values()
        ]

        for step in range(1, self.settings.max_steps + 1):
            meter.ensure_budget()
            response = self.client.chat.completions.create(
                model=self.settings.model,
                messages=messages,
                tools=tool_schemas,
                tool_choice="auto",
                max_tokens=self.settings.max_output_tokens,
                temperature=0.2,
            )
            choice = response.choices[0]
            message = choice.message
            raw_content = message.content or ""
            meter.record(context, raw_content)
            if message.tool_calls:
                messages.append(message.model_dump(exclude_none=True))
                for call in message.tool_calls:
                    if tool_calls_used >= self.settings.max_tool_calls:
                        raise RuntimeError("Tool-call budget reached; stopping safely.")
                    name = call.function.name
                    validate_tool_name(name, names)
                    try:
                        args = json.loads(call.function.arguments or "{}")
                    except json.JSONDecodeError as exc:
                        raise GuardrailViolation("Tool arguments were not valid JSON.") from exc
                    if not isinstance(args, dict):
                        raise GuardrailViolation("Tool arguments must be a JSON object.")
                    spec = self.tools[name]
                    decision = self.decision_gate.evaluate(name, args, spec.requires_approval)
                    self.audit.event("tool_decision", tool=name, verdict=decision.verdict, reason=decision.reason)
                    if decision.verdict != "allow":
                        result = f"Tool blocked by policy ({decision.verdict}): {decision.reason}"
                    else:
                        # Tool handlers are narrow and validate their own arguments.
                        result = spec.handler(args)
                        tool_calls_used += 1
                        self.audit.event("tool_executed", tool=name, outcome="success")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": str(result)[:2000],
                    })
                continue

            answer = validate_output(raw_content)
            self.audit.event(
                "request_completed",
                steps=step,
                tool_calls=tool_calls_used,
                estimated_cost_usd=round(meter.estimated_cost_usd, 8),
            )
            return RunResult(
                answer=answer,
                steps=step,
                tool_calls=tool_calls_used,
                estimated_cost_usd=meter.estimated_cost_usd,
                warnings=["Possible prompt-injection language detected; tools remain policy-gated."]
                if injection_flag else [],
            )

        self.audit.event("request_stopped", reason="max_steps_reached")
        return RunResult(
            answer="Stopped safely because the maximum number of agent steps was reached.",
            steps=self.settings.max_steps,
            tool_calls=tool_calls_used,
            estimated_cost_usd=meter.estimated_cost_usd,
            blocked=True,
            warnings=["Step budget reached."],
        )
