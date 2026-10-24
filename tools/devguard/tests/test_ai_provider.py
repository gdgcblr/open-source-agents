"""Unit tests for DevGuard AI provider adapter."""

import pytest
from unittest.mock import MagicMock, patch
from devguard.ai_provider import GeminiProvider


def test_missing_api_key_raises_value_error(monkeypatch: pytest.MonkeyPatch):
    """When GEMINI_API_KEY is not set or has placeholder value, ValueError is raised."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
        GeminiProvider(load_dotenv=False)

    monkeypatch.setenv("GEMINI_API_KEY", "your_gemini_api_key_here")
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
        GeminiProvider(load_dotenv=False)


def test_missing_google_genai_package(monkeypatch: pytest.MonkeyPatch):
    """When google-genai is not installed, accessing client raises RuntimeError."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-12345")
    provider = GeminiProvider(load_dotenv=False)
    with patch.dict("sys.modules", {"google": None, "google.genai": None}):
        with pytest.raises(RuntimeError, match="Optional dependency 'google-genai' is not installed"):
            provider.generate("test prompt")


def test_provider_generate_success(monkeypatch: pytest.MonkeyPatch):
    """Successful generation returns text output."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-12345")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    provider = GeminiProvider(load_dotenv=False)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "feat: add secure credentials loader"
    mock_client.models.generate_content.return_value = mock_response

    provider._client = mock_client
    result = provider.generate("prompt")
    assert result == "feat: add secure credentials loader"
    mock_client.models.generate_content.assert_called_once_with(
        model="gemini-2.5-flash",
        contents="prompt",
    )


def test_provider_generate_api_error(monkeypatch: pytest.MonkeyPatch):
    """API errors are wrapped into RuntimeError."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-12345")
    provider = GeminiProvider(load_dotenv=False)

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = Exception("Connection reset")

    provider._client = mock_client
    with pytest.raises(RuntimeError, match="Gemini API request failed"):
        provider.generate("prompt")

