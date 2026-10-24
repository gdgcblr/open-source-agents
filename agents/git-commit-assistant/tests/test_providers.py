"""Tests for provider resolution and the mock/openai providers."""

import pytest

from commit_assistant.providers import (
    MockProvider,
    OpenAIProvider,
    ProviderError,
    get_provider,
    resolve_provider,
)


def test_resolve_explicit_flag_wins():
    # Explicit flag beats env and key presence.
    env = {"PROVIDER": "mock", "OPENAI_API_KEY": "sk-test"}
    assert resolve_provider("openai", env) == "openai"


def test_resolve_env_provider_used_when_no_flag():
    assert resolve_provider(None, {"PROVIDER": "mock"}) == "mock"


def test_resolve_auto_without_key_is_mock():
    assert resolve_provider("auto", {}) == "mock"
    assert resolve_provider(None, {}) == "mock"


def test_resolve_auto_with_key_but_no_package(monkeypatch):
    # Pretend openai is not importable; auto must fall back to mock.
    monkeypatch.setattr(
        "commit_assistant.providers._module_available",
        lambda name: False,
    )
    assert resolve_provider("auto", {"OPENAI_API_KEY": "sk-test"}) == "mock"


def test_resolve_auto_with_key_and_package(monkeypatch):
    monkeypatch.setattr(
        "commit_assistant.providers._module_available",
        lambda name: True,
    )
    assert resolve_provider("auto", {"OPENAI_API_KEY": "sk-test"}) == "openai"


def test_resolve_unknown_provider_raises():
    with pytest.raises(ProviderError):
        resolve_provider("nope", {})


def test_get_provider_mock():
    assert isinstance(get_provider("mock"), MockProvider)


def test_get_provider_openai():
    assert isinstance(get_provider("openai"), OpenAIProvider)


def test_get_provider_unknown_raises():
    with pytest.raises(ProviderError):
        get_provider("bogus")


def test_mock_provider_end_to_end(read_fixture):
    out = MockProvider().generate(read_fixture("add_module.diff"))
    assert out.startswith("feat(commit_assistant): ")
    assert "- add commit_assistant/greet.py" in out


def test_mock_provider_no_body(read_fixture):
    out = MockProvider().generate(read_fixture("add_module.diff"), no_body=True)
    assert "\n" not in out


def test_mock_provider_empty_diff_is_valid():
    out = MockProvider().generate("")
    assert out == "chore: update repository"


def test_openai_without_key_raises(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError) as exc:
        OpenAIProvider().generate("diff --git a/x b/x\n")
    assert "OPENAI_API_KEY" in str(exc.value)


def test_openai_missing_package_raises(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        "commit_assistant.providers._module_available",
        lambda name: False,
    )
    with pytest.raises(ProviderError) as exc:
        OpenAIProvider().generate("diff --git a/x b/x\n")
    assert "openai" in str(exc.value).lower()
