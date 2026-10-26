"""Unit tests for the Gemini service without real API calls."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from google.genai import types
from google.genai import errors

from backend.app.config import settings
from backend.app.models import GeminiAnswer, QueryRequest
from backend.app.service import ServiceError, _validate_model_answer, generate_answer


def test_generate_answer_uses_low_thinking_and_parses_json(monkeypatch):
    generate_content = Mock(return_value=SimpleNamespace(
        text='{"sql":"SELECT id FROM users","explanation":"Lists user IDs"}'
    ))
    monkeypatch.setattr(
        "backend.app.service.genai.Client",
        Mock(return_value=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))),
    )

    answer = generate_answer(
        QueryRequest(question="List user IDs"),
        replace(settings, gemini_api_key="test-key"),
    )

    config = generate_content.call_args.kwargs["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.thinking_config.thinking_level.value.lower() == "low"
    assert config.response_schema.type.name == "OBJECT"
    assert set(config.response_schema.properties) == {"sql", "explanation", "assumptions", "risks"}
    assert answer.sql == "SELECT id FROM users"


def test_generate_answer_validates_sdk_parsed_response(monkeypatch):
    generate_content = Mock(return_value=SimpleNamespace(
        text=None,
        parsed={"sql": "SELECT id FROM users", "explanation": "Lists user IDs"},
    ))
    monkeypatch.setattr(
        "backend.app.service.genai.Client",
        Mock(return_value=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))),
    )

    answer = generate_answer(
        QueryRequest(question="List user IDs"),
        replace(settings, gemini_api_key="test-key"),
    )

    assert answer.sql == "SELECT id FROM users"
    assert answer.unverified is True


def test_generate_answer_accepts_sdk_parsed_pydantic_model(monkeypatch):
    generate_content = Mock(return_value=SimpleNamespace(
        text=None,
        parsed=GeminiAnswer(sql="SELECT id FROM users", explanation="Lists user IDs"),
    ))
    monkeypatch.setattr(
        "backend.app.service.genai.Client",
        Mock(return_value=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))),
    )

    answer = generate_answer(
        QueryRequest(question="List user IDs"),
        replace(settings, gemini_api_key="test-key"),
    )

    assert answer.sql == "SELECT id FROM users"
    assert answer.unverified is True


def test_generate_answer_still_blocks_unsafe_sdk_parsed_response(monkeypatch):
    generate_content = Mock(return_value=SimpleNamespace(
        text=None,
        parsed={"sql": "DELETE FROM users", "explanation": "Deletes users"},
    ))
    monkeypatch.setattr(
        "backend.app.service.genai.Client",
        Mock(return_value=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))),
    )

    with pytest.raises(ServiceError) as error:
        generate_answer(
            QueryRequest(question="Delete users"),
            replace(settings, gemini_api_key="test-key"),
        )

    assert error.value.code == "unsafe_model_response"


def test_model_response_parser_tolerates_preamble_and_normalizes_optional_fields():
    answer = _validate_model_answer(
        'Here is the result:\n{"sql":"SELECT id FROM users",'
        '"explanation":"Lists user IDs","assumptions":"Table exists",'
        '"risks":null,"extra":"ignored"}'
    )

    assert answer.sql == "SELECT id FROM users"
    assert answer.assumptions == ["Table exists"]
    assert answer.risks == []


def test_generate_answer_returns_safe_timeout_message(monkeypatch):
    generate_content = Mock(side_effect=httpx.ReadTimeout("private transport detail"))
    monkeypatch.setattr(
        "backend.app.service.genai.Client",
        Mock(return_value=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))),
    )

    with pytest.raises(ServiceError) as error:
        generate_answer(
            QueryRequest(question="List user IDs"),
            replace(settings, gemini_api_key="test-key", request_timeout_seconds=120),
        )

    assert error.value.status_code == 504
    assert error.value.code == "model_request_timeout"
    assert "120 seconds" not in error.value.message
    assert "private transport detail" not in error.value.message


def test_generate_answer_retries_json_mode_if_schema_is_rejected(monkeypatch):
    generate_content = Mock(side_effect=[
        errors.APIError(400, {"status": "INVALID_ARGUMENT", "message": "private schema detail"}),
        SimpleNamespace(text='{"sql":"SELECT id FROM users","explanation":"Lists user IDs"}'),
    ])
    monkeypatch.setattr(
        "backend.app.service.genai.Client",
        Mock(return_value=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))),
    )

    answer = generate_answer(
        QueryRequest(question="List user IDs"),
        replace(settings, gemini_api_key="test-key"),
    )

    assert answer.sql == "SELECT id FROM users"
    assert generate_content.call_count == 2
    retry_config = generate_content.call_args.kwargs["config"]
    assert retry_config.response_mime_type == "application/json"
    assert retry_config.response_schema is None
