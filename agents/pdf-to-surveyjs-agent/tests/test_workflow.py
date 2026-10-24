from __future__ import annotations

import asyncio
import re
from types import SimpleNamespace

import pytest

from pdf_to_surveyjs_agent.workflow import (
    ConfigurationError,
    ConversionError,
    _parse_model_json,
    _require_configuration,
    _run_turn,
)


def test_missing_credentials_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="No fallback model was used"):
        _require_configuration()


def test_placeholder_credential_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "your_google_ai_studio_api_key_here")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ConfigurationError, match="real key"):
        _require_configuration()


def test_parse_model_json_accepts_fenced_output() -> None:
    parsed = _parse_model_json(
        '```json\n{"survey":{"elements":[]},"warnings":["Review required"]}\n```'
    )

    assert parsed["warnings"] == ["Review required"]


def test_parse_model_json_accepts_json_surrounded_by_prose() -> None:
    parsed = _parse_model_json(
        'Here is the draft:\n{"survey":{"elements":[]},"warnings":[]}\nPlease review it.'
    )

    assert parsed == {"survey": {"elements": []}, "warnings": []}


def test_parse_model_json_ignores_unrelated_object_before_envelope() -> None:
    parsed = _parse_model_json(
        'Metadata: {"status":"draft"}\n'
        '{"survey":{"elements":[]},"warnings":["Check labels"]}'
    )

    assert parsed["warnings"] == ["Check labels"]


def test_parse_model_json_rejects_extra_wrapper_keys() -> None:
    with pytest.raises(ConversionError, match="required SurveyJS JSON object"):
        _parse_model_json(
            '{"survey":{"elements":[]},"warnings":[],"unexpected":true}'
        )


def test_agent_uses_structured_output_schema() -> None:
    from pdf_to_surveyjs_agent.agent import AGENT_INSTRUCTION, build_agent
    from pdf_to_surveyjs_agent.schemas import SurveyDraftResponse

    agent = build_agent()
    assert agent.output_schema is SurveyDraftResponse
    assert agent.generate_content_config.temperature == 0.1
    assert agent.generate_content_config.max_output_tokens is None
    assert agent.generate_content_config.thinking_config.thinking_level.value == "MINIMAL"
    assert re.search(r"(?<![${\\])\{[^{}]+\}", AGENT_INSTRUCTION) is None


def test_run_turn_ignores_thought_parts() -> None:
    class FakeRunner:
        async def run_async(self, **_kwargs):
            yield SimpleNamespace(
                error_code=None,
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text="internal reasoning", thought=True),
                        SimpleNamespace(
                            text='{"survey":{"elements":[]},"warnings":[]}',
                            thought=False,
                        ),
                    ]
                ),
                is_final_response=lambda: True,
            )

    result = asyncio.run(_run_turn(FakeRunner(), "session", "prompt"))

    assert result == '{"survey":{"elements":[]},"warnings":[]}'


def test_run_turn_accepts_text_when_event_is_not_marked_final() -> None:
    class FakeRunner:
        async def run_async(self, **_kwargs):
            yield SimpleNamespace(
                error_code=None,
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            text='{"survey":{"elements":[]},"warnings":[]}',
                            thought=False,
                        )
                    ]
                ),
                is_final_response=lambda: False,
            )

    result = asyncio.run(_run_turn(FakeRunner(), "session", "prompt"))

    assert result == '{"survey":{"elements":[]},"warnings":[]}'


def test_run_turn_turns_quota_event_into_short_error() -> None:
    class FakeRunner:
        async def run_async(self, **_kwargs):
            yield SimpleNamespace(
                error_code="RESOURCE_EXHAUSTED",
                error_message="429 RESOURCE_EXHAUSTED",
            )

    with pytest.raises(ConversionError, match="quota was exceeded"):
        asyncio.run(_run_turn(FakeRunner(), "session", "prompt"))

