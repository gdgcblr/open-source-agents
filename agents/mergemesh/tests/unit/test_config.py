"""Unit tests for configuration validation, local-only runtime enforcement, and AI fallback safety."""

from __future__ import annotations

import pytest

from agents.factory import _normalize_ollama_messages, create_adk_agent
from agents.schemas import AIExplanationSchema
from agents.workflow import _extract_json_block
from config.settings import DEFAULT_OLLAMA_MODEL, check_provider_readiness, load_settings


def test_default_ai_mode_is_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERGEMESH_AI_MODE", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    settings = load_settings()
    assert settings.ai_mode == "local"
    assert settings.ollama_model == DEFAULT_OLLAMA_MODEL == "gemma4:e4b"
    assert settings.is_gemini_configured() is False


def test_ollama_model_configurable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for candidate in ("gemma4:e4b", "gemma4:e2b", "gemma3:4b"):
        monkeypatch.setenv("OLLAMA_MODEL", candidate)
        settings = load_settings()
        assert settings.ollama_model == candidate
        descriptor = create_adk_agent(settings)
        assert descriptor.model_id == f"ollama_chat/{candidate}"
        assert descriptor.adk_agent is not None
        assert descriptor.adk_agent.tools == []
        assert descriptor.adk_agent.model._additional_args.get("api_base") == settings.ollama_base_url
        assert descriptor.adk_agent.model._additional_args.get("response_format") == {"type": "json_object"}


def test_normalize_ollama_messages_converts_developer_role() -> None:
    raw_messages = [
        {"role": "developer", "content": "System instructions"},
        {"role": "user", "content": "Analyze evidence"},
    ]
    normalized = _normalize_ollama_messages(raw_messages)
    assert normalized[0]["role"] == "system"
    assert normalized[0]["content"] == "System instructions"
    assert normalized[1]["role"] == "user"


def test_extract_json_block_strips_gemma_thinking_tags() -> None:
    raw_with_think = (
        '<think>\nLet me check {"customer_id": "123"} vs {"customerId": "123"}.\n</think>\n'
        '{\n'
        '  "summary": "Provider renamed customer_id to customerId, breaking consumer.",\n'
        '  "compatibility_assessment": "Consumer subscript access will raise KeyError.",\n'
        '  "why_it_matters": "Downstream checkout fails at runtime.",\n'
        '  "observed_facts": ["customer_id removed"],\n'
        '  "hypotheses": ["Renamed to customerId"],\n'
        '  "severity_label": "high",\n'
        '  "confidence_label": "high",\n'
        '  "suggested_fix_options": ["Use payload.get(\'customerId\') or payload[\'customer_id\']"],\n'
        '  "remediation_tradeoffs": "Dual-read in consumer vs dual-write in provider.",\n'
        '  "verification_plan": ["Run combined integration test"]\n'
        '}'
    )
    parsed = _extract_json_block(raw_with_think)
    validated = AIExplanationSchema.model_validate(parsed)
    assert "customer_id" in validated.summary
    assert validated.severity_label == "high"


def test_deterministic_ai_mode_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERGEMESH_AI_MODE", "deterministic")
    settings = load_settings()
    assert settings.ai_mode == "deterministic"


def test_non_loopback_ollama_url_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "https://external.example.com:11434")
    settings = load_settings()
    readiness = check_provider_readiness(settings)
    assert readiness.ollama_reachable is False
    assert "Blocked non-local OLLAMA_BASE_URL" in readiness.ollama_status_message
    descriptor = create_adk_agent(settings)
    assert descriptor.adk_agent is None
    assert "Blocked non-local OLLAMA_BASE_URL" in (descriptor.error_reason or "")


def test_invalid_ai_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERGEMESH_AI_MODE", "unsupported_provider")
    with pytest.raises(ValueError, match="Invalid MERGEMESH_AI_MODE"):
        load_settings()


def test_gemini_mode_and_vertex_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MERGEMESH_AI_MODE", "gemini")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-gcp-project")
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    settings = load_settings()

    assert settings.ai_mode == "gemini"
    assert settings.gemini_backend == "vertex_ai"
    assert settings.is_gemini_configured() is True


def test_malformed_ai_json_rejected_by_schema() -> None:
    with pytest.raises(Exception):
        bad_dict = _extract_json_block("not valid json at all")
        AIExplanationSchema.model_validate(bad_dict)


def test_workflow_timeout_unavailable_and_invalid_response_fail_visibly(
    fixtures_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify timeout, missing model, and malformed model JSON fail visibly into FALLBACK or UNAVAILABLE
    and never disguise a failed Gemma call as status == 'SUCCESS'.
    """
    from analysis.compatibility import evaluate_compatibility
    from analysis.consumer_usage import scan_consumer_file
    from analysis.contract_extractor import compare_contract_files
    from agents.workflow import generate_ai_explanation
    from config.settings import ProviderReadiness
    from services.scenario_loader import load_scenario_definition

    scenario = load_scenario_definition("customer_id_rename", fixtures_root=fixtures_root)
    s_root = fixtures_root / scenario.id
    comparison = compare_contract_files(
        before_file=s_root / scenario.provider_before,
        after_file=s_root / scenario.provider_after,
        before_rel_path=scenario.provider_before,
        after_rel_path=scenario.provider_after,
        required_fields=scenario.required_fields,
    )
    accesses = scan_consumer_file(
        file_path=s_root / scenario.consumer_source,
        consumer_repo=scenario.consumer_repo,
        rel_file_path=scenario.consumer_source,
    )
    findings = evaluate_compatibility(
        provider_repo=scenario.provider_repo,
        consumer_repo=scenario.consumer_repo,
        contract_comparison=comparison,
        consumer_accesses=accesses,
        combined_test_result=None,
    )

    monkeypatch.setenv("MERGEMESH_AI_MODE", "local")
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:e4b")

    # 1. Missing model (Ollama running, but gemma4:e4b not pulled)
    monkeypatch.setattr(
        "agents.workflow.check_provider_readiness",
        lambda s, timeout_sec=1.5: ProviderReadiness(
            ollama_reachable=True,
            ollama_model_installed=False,
            ollama_available_models=["llama3:8b"],
            ollama_status_message="Ollama running, but model 'gemma4:e4b' is not pulled (found: llama3:8b)",
            gemini_configured=False,
            gemini_backend="developer_api",
            gemini_status_message="Not configured",
            ollama_recovery_hint="Run: ollama pull gemma4:e4b",
        ),
    )
    settings_fb = load_settings()
    exp_missing = generate_ai_explanation(settings_fb, scenario, comparison, accesses, findings, [])
    assert exp_missing.status == "FALLBACK"
    assert "not pulled" in (exp_missing.fallback_reason or "")
    assert "ollama pull gemma4:e4b" in (exp_missing.fallback_reason or "")

    # 2. Timeout during inference (with ALLOW_LOCAL_FALLBACK=false -> UNAVAILABLE, with true -> FALLBACK)
    monkeypatch.setattr(
        "agents.workflow.check_provider_readiness",
        lambda s, timeout_sec=1.5: ProviderReadiness(
            ollama_reachable=True,
            ollama_model_installed=True,
            ollama_available_models=["gemma4:e4b"],
            ollama_status_message="Ollama ready (gemma4:e4b)",
            gemini_configured=False,
            gemini_backend="developer_api",
            gemini_status_message="Not configured",
        ),
    )

    def _raise_timeout(agent, prompt_text, timeout_sec):
        raise TimeoutError(f"Ollama inference timed out after {timeout_sec}s")

    monkeypatch.setattr("agents.workflow._invoke_adk_with_timeout", _raise_timeout)
    exp_timeout_fb = generate_ai_explanation(settings_fb, scenario, comparison, accesses, findings, [])
    assert exp_timeout_fb.status == "FALLBACK"
    assert "TimeoutError" in (exp_timeout_fb.fallback_reason or "")

    monkeypatch.setenv("ALLOW_LOCAL_FALLBACK", "false")
    settings_no_fb = load_settings()
    exp_timeout_unavail = generate_ai_explanation(settings_no_fb, scenario, comparison, accesses, findings, [])
    assert exp_timeout_unavail.status == "UNAVAILABLE"
    assert "TimeoutError" in (exp_timeout_unavail.fallback_reason or "")

    # 3. Invalid / malformed JSON response from model
    monkeypatch.setenv("ALLOW_LOCAL_FALLBACK", "true")
    settings_fb2 = load_settings()
    monkeypatch.setattr(
        "agents.workflow._invoke_adk_with_timeout",
        lambda agent, prompt_text, timeout_sec: '{"summary": "too short"}',
    )
    exp_invalid = generate_ai_explanation(settings_fb2, scenario, comparison, accesses, findings, [])
    assert exp_invalid.status == "FALLBACK"
    assert "ValidationError" in (exp_invalid.fallback_reason or "")


def test_hosted_gemma_live_api_smoke_test(
    fixtures_root,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Minimal live API smoke test for hosted Google Gemma (`gemma-4-26b-a4b-it`) via ADK LiteLlm."""
    import os

    from analysis.compatibility import evaluate_compatibility
    from analysis.consumer_usage import scan_consumer_file
    from analysis.contract_extractor import compare_contract_files
    from agents.workflow import generate_ai_explanation
    from config.settings import DEFAULT_HOSTED_GEMMA_MODEL
    from services.scenario_loader import load_scenario_definition

    if not (os.environ.get("GEMINI_API_KEY", "").strip() or os.environ.get("GOOGLE_API_KEY", "").strip()):
        pytest.skip("GEMINI_API_KEY / GOOGLE_API_KEY not set in environment or .env")

    monkeypatch.setenv("MERGEMESH_AI_MODE", "gemini")
    monkeypatch.setenv("GEMINI_MODEL", DEFAULT_HOSTED_GEMMA_MODEL)
    monkeypatch.setenv("ALLOW_LOCAL_FALLBACK", "false")
    monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "90")

    settings = load_settings()
    assert settings.ai_mode == "gemini"
    assert settings.gemini_model == "gemma-4-26b-a4b-it"
    assert settings.is_gemini_configured() is True

    descriptor = create_adk_agent(settings)
    assert descriptor.adk_agent is not None
    assert descriptor.model_id == "gemini/gemma-4-26b-a4b-it"

    scenario = load_scenario_definition("customer_id_rename", fixtures_root=fixtures_root)
    s_root = fixtures_root / scenario.id
    comparison = compare_contract_files(
        before_file=s_root / scenario.provider_before,
        after_file=s_root / scenario.provider_after,
        before_rel_path=scenario.provider_before,
        after_rel_path=scenario.provider_after,
        required_fields=scenario.required_fields,
    )
    accesses = scan_consumer_file(
        file_path=s_root / scenario.consumer_source,
        consumer_repo=scenario.consumer_repo,
        rel_file_path=scenario.consumer_source,
    )
    findings = evaluate_compatibility(
        provider_repo=scenario.provider_repo,
        consumer_repo=scenario.consumer_repo,
        contract_comparison=comparison,
        consumer_accesses=accesses,
        combined_test_result=None,
    )

    explanation = generate_ai_explanation(settings, scenario, comparison, accesses, findings, [])
    assert explanation.status == "SUCCESS", f"Live call did not return SUCCESS: {explanation.fallback_reason}"
    assert explanation.model == "gemini/gemma-4-26b-a4b-it"
    assert explanation.fallback_reason is None
    assert "customer_id" in explanation.summary or "customer_id" in explanation.compatibility_assessment

