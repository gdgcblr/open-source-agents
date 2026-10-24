"""Integration test verifying the Streamlit dashboard (`app.py`) renders and interacts cleanly."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parent.parent.parent / "app.py"


def test_streamlit_app_renders_and_switches_scenarios() -> None:
    """Launch app.py via Streamlit AppTest and verify initial render, findings, and honest fallback labeling."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()

    assert not at.exception, f"Streamlit app raised an exception: {at.exception}"
    assert "active_cache_key" in at.session_state
    active_key = at.session_state["active_cache_key"]
    report = at.session_state["report_cache"][active_key]
    assert report.scenario_id == "customer_id_rename"
    assert report.overall_status == "BREAKING_FAILURE_REPRODUCED"
    assert len(report.finding_list) == 1
    assert report.finding_list[0].verification_state == "REPRODUCED_FAILURE"

    # When Ollama is offline, verify the UI explicitly reports fallback mode and does not claim Gemma ran
    if report.ai_explanation.status == "FALLBACK":
        warning_texts = [w.value for w in at.warning]
        assert any("Deterministic Fallback Mode Active" in w for w in warning_texts)
        markdown_texts = [m.value for m in at.markdown]
        assert any("Deterministic Rule-Based Assessment (Fallback" in m for m in markdown_texts)
        assert not any("Gemma AI Reasoning & Remediation (`" in m for m in markdown_texts)


def test_streamlit_app_renders_gemma_mode_when_inference_succeeds(monkeypatch) -> None:
    """Verify that when ADK + Gemma inference succeeds, the Streamlit UI displays Gemma Mode Active,
    separates deterministic findings from Gemma's reasoning, and renders trade-offs and verification plan.
    """
    import json
    from config.settings import ProviderReadiness
    from litellm.types.utils import Choices, Message, ModelResponse, Usage

    async def fake_acompletion(model, messages, tools=None, **kwargs):
        payload = {
            "summary": "orders-api renamed customer_id to customerId, breaking checkout-client.",
            "compatibility_assessment": "checkout-client reads payload['customer_id'] directly, raising KeyError.",
            "observed_facts": [
                "orders-api removed customer_id and added customerId.",
                "checkout-client client.py:12 reads payload['customer_id'].",
            ],
            "why_it_matters": "Combined deployment breaks checkout session creation despite passing isolated unit tests.",
            "severity_label": "high",
            "confidence_label": "high",
            "hypotheses": ["customer_id was renamed to camelCase customerId."],
            "suggested_fix_options": [
                "Update checkout-client to read payload.get('customerId') or payload['customer_id'].",
                "Dual-write customer_id and customerId in orders-api.",
            ],
            "remediation_tradeoffs": "Updating checkout-client migrates forward directly, while dual-writing in orders-api preserves backward compatibility.",
            "verification_plan": ["Run test_post_fix_contract.py to verify combined compatibility."],
            "suggested_test": "assert session['session_customer'] == 'cus_123'",
            "limitations": ["Scoped to Python AST dictionary accesses."],
        }
        return ModelResponse(
            id="chatcmpl-ui-test",
            choices=[
                Choices(
                    finish_reason="stop",
                    index=0,
                    message=Message(content=json.dumps(payload), role="assistant"),
                )
            ],
            model=model,
            usage=Usage(prompt_tokens=150, completion_tokens=100, total_tokens=250),
        )

    monkeypatch.setattr(
        "config.settings.check_provider_readiness",
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
    monkeypatch.setattr("google.adk.models.lite_llm.acompletion", fake_acompletion)

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()

    assert not at.exception, f"Streamlit app raised an exception: {at.exception}"
    active_key = at.session_state["active_cache_key"]
    report = at.session_state["report_cache"][active_key]
    assert report.ai_explanation.status == "SUCCESS"
    assert report.ai_explanation.model == "ollama_chat/gemma4:e4b"

    success_texts = [s.value for s in at.success]
    assert any("Gemma Mode Active (`status=SUCCESS`)" in s for s in success_texts)
    markdown_texts = [m.value for m in at.markdown]
    assert any("Gemma AI Reasoning & Remediation (`ollama_chat/gemma4:e4b`)" in m for m in markdown_texts)
    assert any("Dual-writing" in m or "dual-writing" in m for m in markdown_texts)
