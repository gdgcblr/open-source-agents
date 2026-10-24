"""Local-first ADK execution workflow with schema validation and deterministic fallback."""

from __future__ import annotations

import asyncio
import json
import re
import time

from agents.factory import create_adk_agent
from agents.prompts import build_agent_context_prompt
from agents.schemas import AIExplanationSchema
from config.settings import AppSettings, check_provider_readiness
from domain.enums import AIStatus
from domain.models import (
    AIExplanation,
    ConsumerFieldAccess,
    ContractComparison,
    Finding,
    ScenarioDefinition,
    TestExecutionResult,
)


def build_deterministic_explanation(
    scenario: ScenarioDefinition,
    comparison: ContractComparison,
    consumer_accesses: list[ConsumerFieldAccess],
    findings: list[Finding],
    test_results: list[TestExecutionResult],
    status: AIStatus = "FALLBACK",
    provider_label: str = "Deterministic Rule Engine (Fallback)",
    model_id: str | None = None,
    fallback_reason: str | None = None,
    duration_ms: int = 0,
) -> AIExplanation:
    """Construct a ground-truth explanation from measured deterministic evidence."""
    combined_test = next((t for t in test_results if t.test_kind == "combined_integration"), None)
    provider_test = next((t for t in test_results if t.test_kind == "provider_isolated"), None)
    consumer_test = next((t for t in test_results if t.test_kind == "consumer_isolated"), None)

    if findings:
        f0 = findings[0]
        field_name = f0.field or "unknown_field"
        replacement = f0.replacement_candidate
        before_val = (
            comparison.before_fields[field_name].sample_value
            if field_name in comparison.before_fields
            else "sample_val"
        )

        if f0.verification_state == "REPRODUCED_FAILURE" and combined_test and combined_test.status == "FAIL":
            summary = (
                f"Reproduced cross-repository contract failure: `{scenario.provider_repo}` removed "
                f"`{field_name}`"
                + (f" (renamed to `{replacement}`)" if replacement else "")
                + f", causing `{scenario.consumer_repo}` to fail at runtime with `{combined_test.failure_summary}`."
            )
            compatibility_assessment = (
                f"Breaking contract change verified by executed test `{combined_test.file_path}` (exit code {combined_test.exit_code}). "
                f"`{scenario.provider_repo}` removed `{field_name}` in `{comparison.provider_after_path}` while `{scenario.consumer_repo}` "
                f"still performs a required access on `{field_name}` in `{scenario.consumer_source}`."
            )
        else:
            summary = f0.summary
            compatibility_assessment = (
                f"Potential breaking change detected by static contract diff and Python AST analysis (`INFERRED_RISK`). "
                f"`{scenario.provider_repo}` removed or altered `{field_name}`"
                + (f" (candidate replacement `{replacement}`)" if replacement else "")
                + f" while `{scenario.consumer_repo}` accesses `{field_name}` in `{scenario.consumer_source}`. "
                "No combined runtime integration test has been executed yet to reproduce the failure."
            )

        if provider_test and consumer_test and consumer_test.uses_stale_mock:
            why_it_matters = (
                f"Isolated CI checks in both `{scenario.provider_repo}` and `{scenario.consumer_repo}` passed "
                f"because `{scenario.consumer_repo}`'s unit test relies on a stale mock payload that still supplies "
                f"`{field_name}`. Deploying these two candidate versions together breaks `{scenario.consumer_repo}` (`{scenario.consumer_source}`)."
            )
        else:
            why_it_matters = (
                f"Downstream code in `{scenario.consumer_repo}` (`{scenario.consumer_source}`) depends directly on `{field_name}` "
                f"from `{scenario.provider_repo}`. Deploying `{scenario.provider_repo}` without coordinating `{scenario.consumer_repo}` "
                f"will raise a `KeyError` or data mismatch on `{field_name}`."
            )

        observed_facts: list[str] = [
            f"Provider before contract (`{comparison.provider_before_path}`) contained `{field_name}`.",
            f"Provider after contract (`{comparison.provider_after_path}`) removed `{field_name}`"
            + (f" and added `{replacement}`." if replacement else "."),
        ]
        for acc in consumer_accesses:
            if acc.field_path == field_name:
                observed_facts.append(
                    f"Consumer source `{acc.file_path}:{acc.line}` reads `{acc.field_path}` via `{acc.access_mode}` (`{acc.code_snippet}`)."
                )
        if provider_test and provider_test.status != "NOT_RUN" and consumer_test and consumer_test.status != "NOT_RUN":
            observed_facts.append(
                f"Isolated tests passed: `{provider_test.file_path}` ({provider_test.status}) and `{consumer_test.file_path}` ({consumer_test.status}"
                + (", using mock)." if consumer_test.uses_stale_mock else ").")
            )
        if combined_test:
            if combined_test.status == "NOT_RUN":
                observed_facts.append(
                    f"Combined test `{combined_test.file_path}` was NOT executed (`status=NOT_RUN`); assessment is static only."
                )
            else:
                observed_facts.append(
                    f"Combined test `{combined_test.file_path}` exited with code {combined_test.exit_code} ({combined_test.status}): `{combined_test.failure_summary}`."
                )
        else:
            observed_facts.append("No runtime integration test was executed; findings are static (`INFERRED_RISK`).")

        hypotheses: list[str] = []
        if replacement:
            hypotheses.append(
                f"Candidate field rename `{field_name}` -> `{replacement}` inferred from matching normalized key name and sample value (`{before_val}`)."
            )

        if replacement:
            fix_options = [
                f"Immediate Mitigation (Preferred — Provider backward-compatible dual-write): Update `{scenario.provider_source}` in `{scenario.provider_repo}` to emit both `{field_name}` and `{replacement}` during the transition so existing consumers do not break.",
                f"Long-Term Migration (Consumer dual-read & cutover): Update `{scenario.consumer_source}` in `{scenario.consumer_repo}` to read `payload.get(\"{replacement}\") or payload[\"{field_name}\"]`, refresh stale consumer unit-test mocks, and remove `{field_name}` from `{scenario.provider_repo}` only after all consumers migrate.",
            ]
        else:
            fix_options = [
                f"Immediate Mitigation (Provider contract restoration): Retain `{field_name}` in `{scenario.provider_source}` (`{scenario.provider_repo}`) to preserve backward compatibility.",
                f"Long-Term Migration (Consumer defensive read): Update `{scenario.consumer_source}` in `{scenario.consumer_repo}` to use `payload.get(\"{field_name}\")` with a safe fallback before deprecating `{field_name}`.",
            ]

        remediation_tradeoffs = (
            f"Immediate mitigation via additive dual-writing in `{scenario.provider_repo}` (emitting both `{field_name}` and `{replacement or 'the new schema'}`) "
            "preserves backward compatibility and enables zero-downtime independent rollouts across all consumers at the cost of temporary payload duplication. "
            f"Long-term migration in `{scenario.consumer_repo}` (`{scenario.consumer_source}`) completes the schema transition cleanly "
            f"but would cause a runtime `KeyError` during deployment if `{scenario.provider_repo}` drops `{field_name}` before `{scenario.consumer_repo}` is deployed."
        )
        verification_plan = [
            f"Run isolated unit tests in `{scenario.provider_repo}` and `{scenario.consumer_repo}` after updating stale mock payloads.",
            f"Execute a cross-repository integration test passing the live `{scenario.provider_repo}` payload directly into `{scenario.consumer_repo}` (`{scenario.consumer_source}`).",
        ]
        severity_label = f0.severity.lower() if f0.severity.lower() in {"critical", "high", "medium", "low"} else "high"
        suggested_test = (
            f"def test_{field_name}_contract_compatibility(provider_payload, consumer_fn):\n"
            f"    assert ('{replacement or field_name}' in provider_payload) or ('{field_name}' in provider_payload)\n"
            f"    result = consumer_fn(provider_payload)\n"
            f"    assert result is not None"
        )
    else:
        summary = (
            f"No breaking contract incompatibility detected between `{scenario.provider_repo}` and `{scenario.consumer_repo}`. "
            f"Added fields ({', '.join(comparison.added_fields) or 'none'}) are backward-compatible."
        )
        compatibility_assessment = (
            f"Compatible additive change: `{scenario.provider_repo}` retained all existing fields consumed by `{scenario.consumer_repo}` "
            f"({', '.join(a.field_path for a in consumer_accesses) or 'none'}) with unchanged types while adding "
            f"`{', '.join(comparison.added_fields) or 'no new fields'}`."
        )
        why_it_matters = (
            f"`{scenario.provider_repo}` preserved all fields consumed by `{scenario.consumer_repo}` "
            f"({', '.join(a.field_path for a in consumer_accesses) or 'none'}). Candidate changes can be merged safely with respect to this interface."
        )
        observed_facts = [
            f"Provider contract retained existing fields: {', '.join(sorted(comparison.before_fields.keys()))}.",
            f"Added fields in `{comparison.provider_after_path}`: {', '.join(comparison.added_fields) or 'none'}.",
        ]
        if combined_test and combined_test.status != "NOT_RUN":
            observed_facts.append(
                f"Combined integration test `{combined_test.file_path}` executed and exited with status {combined_test.status} (exit code {combined_test.exit_code})."
            )
        else:
            observed_facts.append(
                "No combined runtime test was executed (`NOT_RUN`); compatibility verdict is based on static contract and AST comparison."
            )
        hypotheses = [
            "Downstream consumers ignoring unknown JSON fields will remain unaffected by the optional addition."
        ]
        fix_options = [
            "No code remediation needed. Optionally update consumer mock fixtures to include the newly added optional field for completeness."
        ]
        remediation_tradeoffs = (
            "No breaking remediation is required because additive fields in JSON responses are backward-compatible with standard dictionary lookups. "
            "If the consumer later adopts the new field, use `payload.get(...)` so older provider revisions remain compatible during rollbacks."
        )
        verification_plan = [
            f"Verify existing `{scenario.consumer_repo}` unit and integration tests continue to pass with the expanded payload.",
        ]
        severity_label = "none"
        suggested_test = None

    limitations = [
        "Consumer AST analysis inspects static string dictionary accesses (`payload['key']` and `.get('key')`) in Python source files.",
        "Deterministic analyzer and executed pytest runner own the pass/fail verdict.",
    ]
    if not combined_test or combined_test.status == "NOT_RUN":
        limitations.append(
            "No combined integration test was executed; findings reflect static analysis only."
        )

    return AIExplanation(
        status=status,
        provider=provider_label,
        model=model_id,
        summary=summary,
        why_it_matters=why_it_matters,
        observed_facts=observed_facts,
        hypotheses=hypotheses,
        suggested_fix_options=fix_options,
        suggested_test=suggested_test,
        confidence_label="high",
        limitations=limitations,
        duration_ms=duration_ms,
        fallback_reason=fallback_reason,
        compatibility_assessment=compatibility_assessment,
        severity_label=severity_label,
        remediation_tradeoffs=remediation_tradeoffs,
        verification_plan=verification_plan,
    )


def _extract_json_block(raw_text: str) -> dict:
    """Extract and parse a JSON object from model text response, stripping reasoning tags if present."""
    cleaned = raw_text.strip()
    # Strip <think>...</think> or <|thought|>... blocks emitted by reasoning models (e.g. Gemma 4)
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()
    cleaned = re.sub(r"<\|thought\|>.*?<\|thought\|>", "", cleaned, flags=re.DOTALL | re.IGNORECASE).strip()

    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    decoder = json.JSONDecoder()
    for idx, ch in enumerate(cleaned):
        if ch == "{":
            try:
                obj, _ = decoder.raw_decode(cleaned[idx:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue

    brace_start = cleaned.find("{")
    brace_end = cleaned.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        cleaned = cleaned[brace_start : brace_end + 1]
    return json.loads(cleaned)


def _enforce_grounding_guardrails(
    validated: AIExplanationSchema,
    scenario: ScenarioDefinition,
    findings: list[Finding],
    test_results: list[TestExecutionResult],
) -> AIExplanationSchema:
    """Ensure model output respects verification boundaries and populates all structured sections."""
    combined_test = next((t for t in test_results if t.test_kind == "combined_integration"), None)
    combined_ran = bool(combined_test and combined_test.status in {"PASS", "FAIL"})

    limitations = list(validated.limitations)
    if not combined_ran:
        static_note = "No combined runtime integration test was executed; findings reflect static contract and AST analysis only (INFERRED_RISK)."
        if not any("not executed" in lim.lower() or "static" in lim.lower() for lim in limitations):
            limitations.append(static_note)

    compat_assessment = validated.compatibility_assessment.strip()
    if not compat_assessment:
        compat_assessment = validated.why_it_matters

    tradeoffs = validated.remediation_tradeoffs.strip()
    if not tradeoffs:
        if findings:
            tradeoffs = (
                f"Updating `{scenario.consumer_repo}` migrates the consumer to the new contract directly, "
                f"whereas dual-writing in `{scenario.provider_repo}` preserves backward compatibility for rolling deployments."
            )
        else:
            tradeoffs = (
                "Additive optional fields preserve backward compatibility for existing consumers without requiring coordinated rollouts."
            )

    ver_plan = list(validated.verification_plan)
    if not ver_plan:
        if scenario.integration_test:
            ver_plan.append(f"Run combined integration check `{scenario.integration_test}` after applying the remediation.")
        else:
            ver_plan.append(
                f"Run unit tests in `{scenario.provider_repo}` and `{scenario.consumer_repo}`, plus a cross-repository contract test."
            )

    sev = validated.severity_label
    if not findings and sev in {"critical", "high"}:
        sev = "none"

    return validated.model_copy(
        update={
            "compatibility_assessment": compat_assessment,
            "remediation_tradeoffs": tradeoffs,
            "verification_plan": ver_plan,
            "limitations": limitations,
            "severity_label": sev,
        }
    )


async def _run_adk_agent_async(agent: object, prompt_text: str) -> str:
    """Execute the Google ADK Agent in-memory against local Ollama and collect text response."""
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=agent, app_name="mergemesh")  # type: ignore[arg-type]
    session = await runner.session_service.create_session(
        app_name="mergemesh",
        user_id="mergemesh_evaluator",
    )
    content = types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])
    collected_parts: list[str] = []
    async for event in runner.run_async(
        user_id="mergemesh_evaluator",
        session_id=session.id,
        new_message=content,
    ):
        if getattr(event, "content", None) and getattr(event.content, "parts", None):
            for part in event.content.parts:
                if getattr(part, "text", None):
                    collected_parts.append(part.text)
    return "\n".join(collected_parts).strip()


def _invoke_adk_with_timeout(agent: object, prompt_text: str, timeout_sec: int) -> str:
    """Run the async ADK runner within a bounded timeout."""
    return asyncio.run(
        asyncio.wait_for(_run_adk_agent_async(agent, prompt_text), timeout=float(timeout_sec))
    )


def generate_ai_explanation(
    settings: AppSettings,
    scenario: ScenarioDefinition,
    comparison: ContractComparison,
    consumer_accesses: list[ConsumerFieldAccess],
    findings: list[Finding],
    test_results: list[TestExecutionResult],
) -> AIExplanation:
    """Run the local ADK model workflow with strict validation and safe deterministic fallback."""
    start_ns = time.perf_counter_ns()

    if settings.ai_mode == "deterministic":
        elapsed = int((time.perf_counter_ns() - start_ns) / 1_000_000)
        return build_deterministic_explanation(
            scenario=scenario,
            comparison=comparison,
            consumer_accesses=consumer_accesses,
            findings=findings,
            test_results=test_results,
            status="SKIPPED",
            provider_label="Deterministic Local Engine (No LLM)",
            model_id="deterministic",
            fallback_reason="Pure deterministic mode selected; no LLM called.",
            duration_ms=elapsed,
        )

    readiness = check_provider_readiness(settings, timeout_sec=1.5)
    descriptor = create_adk_agent(settings, stage="primary")

    def _handle_unavailable(reason: str) -> AIExplanation:
        elapsed = int((time.perf_counter_ns() - start_ns) / 1_000_000)
        full_reason = reason
        if (
            settings.ai_mode == "local"
            and readiness.ollama_recovery_hint
            and readiness.ollama_recovery_hint not in reason
        ):
            full_reason = f"{reason} | Recovery: {readiness.ollama_recovery_hint}"
        if settings.allow_local_fallback:
            return build_deterministic_explanation(
                scenario=scenario,
                comparison=comparison,
                consumer_accesses=consumer_accesses,
                findings=findings,
                test_results=test_results,
                status="FALLBACK",
                provider_label=f"{descriptor.provider_label} -> Deterministic Fallback",
                model_id=descriptor.model_id,
                fallback_reason=full_reason,
                duration_ms=elapsed,
            )
        return build_deterministic_explanation(
            scenario=scenario,
            comparison=comparison,
            consumer_accesses=consumer_accesses,
            findings=findings,
            test_results=test_results,
            status="UNAVAILABLE",
            provider_label=descriptor.provider_label,
            model_id=descriptor.model_id,
            fallback_reason=full_reason,
            duration_ms=elapsed,
        )

    if settings.ai_mode == "local":
        if not readiness.ollama_reachable:
            return _handle_unavailable(readiness.ollama_status_message)
        if not readiness.ollama_model_installed:
            return _handle_unavailable(readiness.ollama_status_message)
    elif settings.ai_mode == "gemini":
        if not readiness.gemini_configured:
            return _handle_unavailable(readiness.gemini_status_message)
    elif settings.ai_mode == "hybrid":
        if readiness.ollama_reachable and readiness.ollama_model_installed:
            descriptor = create_adk_agent(
                settings=AppSettings(**{**settings.__dict__, "ai_mode": "local"}),
                stage="primary",
            )
        elif not readiness.gemini_configured:
            return _handle_unavailable(
                f"Local Ollama ({readiness.ollama_status_message}) and hosted Gemma ({readiness.gemini_status_message}) are not ready."
            )

    if descriptor.adk_agent is None:
        return _handle_unavailable(descriptor.error_reason or "Local ADK agent could not be initialized.")

    prompt_text = build_agent_context_prompt(
        scenario=scenario,
        comparison=comparison,
        consumer_accesses=consumer_accesses,
        findings=findings,
        test_results=test_results,
    )

    try:
        effective_timeout = (
            max(settings.ai_request_timeout_seconds, 60)
            if settings.ai_mode in {"gemini", "hybrid"}
            else settings.ai_request_timeout_seconds
        )
        raw_output = _invoke_adk_with_timeout(
            agent=descriptor.adk_agent,
            prompt_text=prompt_text,
            timeout_sec=effective_timeout,
        )
        parsed_dict = _extract_json_block(raw_output)
        validated = AIExplanationSchema.model_validate(parsed_dict)
        validated = _enforce_grounding_guardrails(
            validated=validated,
            scenario=scenario,
            findings=findings,
            test_results=test_results,
        )
        elapsed = int((time.perf_counter_ns() - start_ns) / 1_000_000)

        return AIExplanation(
            status="SUCCESS",
            provider=descriptor.provider_label,
            model=descriptor.model_id,
            summary=validated.summary,
            why_it_matters=validated.why_it_matters,
            observed_facts=validated.observed_facts,
            hypotheses=validated.hypotheses,
            suggested_fix_options=validated.suggested_fix_options,
            suggested_test=validated.suggested_test,
            confidence_label=validated.confidence_label,
            limitations=validated.limitations
            or ["Deterministic analyzer and executed test runner retain authority over the verdict."],
            duration_ms=elapsed,
            fallback_reason=None,
            compatibility_assessment=validated.compatibility_assessment,
            severity_label=validated.severity_label,
            remediation_tradeoffs=validated.remediation_tradeoffs,
            verification_plan=validated.verification_plan,
        )
    except Exception as exc:
        return _handle_unavailable(f"Local AI invocation or schema validation failed: {type(exc).__name__}: {exc}")
