import os

import pytest

from rentrakshak.llm import resolve_agent_model, resolve_backend


def test_auto_prefers_gemini_when_api_key(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("RENTRAKSHAK_LLM_BACKEND", "auto")
    assert resolve_backend() == "gemini"
    assert isinstance(resolve_agent_model(), str)


def test_ollama_backend_requires_extensions(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("RENTRAKSHAK_LLM_BACKEND", "ollama")
    monkeypatch.setenv("RENTRAKSHAK_OLLAMA_MODEL", "gemma3:4b")
    try:
        model = resolve_agent_model()
    except ImportError:
        pytest.skip("google-adk[extensions] not installed")
    assert model is not None
    assert getattr(model, "model", "").startswith("ollama/")
