"""Unit tests for DevGuard AI provider adapters (Gemini + Ollama)."""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from devguard.ai_provider import GeminiProvider, OllamaProvider, create_provider


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------


def _mock_urlopen_ok(payload: dict | None = None):
    """Return a context-manager mock that yields *payload* as JSON bytes."""
    body = json.dumps(payload if payload is not None else {}).encode()
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


def test_ollama_init_checks_server(monkeypatch: pytest.MonkeyPatch):
    """OllamaProvider pings /api/tags on init and stores defaults."""
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    with patch("devguard.ai_provider.urllib.request.urlopen", return_value=_mock_urlopen_ok({"models": []})):
        provider = OllamaProvider(load_dotenv=False)

    assert provider.name == "ollama"
    assert provider.base_url == "http://localhost:11434"
    assert provider.model == "llama3.2"


def test_ollama_init_uses_env_and_args(monkeypatch: pytest.MonkeyPatch):
    """Constructor args and env vars configure base_url / model."""
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://remote:11434/")
    monkeypatch.setenv("OLLAMA_MODEL", "mistral")

    with patch("devguard.ai_provider.urllib.request.urlopen", return_value=_mock_urlopen_ok()):
        from_env = OllamaProvider(load_dotenv=False)
        override = OllamaProvider(model="codellama", base_url="http://other:9999/", load_dotenv=False)

    assert from_env.base_url == "http://remote:11434"
    assert from_env.model == "mistral"
    assert override.base_url == "http://other:9999"
    assert override.model == "codellama"


def test_ollama_server_unreachable(monkeypatch: pytest.MonkeyPatch):
    """Unreachable Ollama server raises a clear RuntimeError on init."""
    with patch(
        "devguard.ai_provider.urllib.request.urlopen",
        side_effect=URLError("Connection refused"),
    ):
        with pytest.raises(RuntimeError, match="Ollama server is not reachable"):
            OllamaProvider(load_dotenv=False)


def test_ollama_generate_success(monkeypatch: pytest.MonkeyPatch):
    """Successful /api/generate returns the response text."""
    tags_resp = _mock_urlopen_ok({"models": [{"name": "llama3.2"}]})
    gen_resp = _mock_urlopen_ok({"response": "feat: add ollama support\n"})

    with patch("devguard.ai_provider.urllib.request.urlopen", side_effect=[tags_resp, gen_resp]):
        provider = OllamaProvider(load_dotenv=False)
        result = provider.generate("write a commit message")

    assert result == "feat: add ollama support"


def test_ollama_generate_empty_response(monkeypatch: pytest.MonkeyPatch):
    """Empty model output is reported as RuntimeError."""
    tags_resp = _mock_urlopen_ok()
    gen_resp = _mock_urlopen_ok({"response": "   "})

    with patch("devguard.ai_provider.urllib.request.urlopen", side_effect=[tags_resp, gen_resp]):
        provider = OllamaProvider(load_dotenv=False)
        with pytest.raises(RuntimeError, match="empty response"):
            provider.generate("prompt")


def test_ollama_model_not_found(monkeypatch: pytest.MonkeyPatch):
    """404 / model-not-found responses list locally available models."""
    tags_resp = _mock_urlopen_ok()

    err_body = b'{"error":"model \'missing\' not found"}'
    http_err = HTTPError(
        url="http://localhost:11434/api/generate",
        code=404,
        msg="Not Found",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(err_body),
    )

    list_resp = _mock_urlopen_ok({"models": [{"name": "llama3.2:latest"}, {"name": "mistral:latest"}]})

    with patch(
        "devguard.ai_provider.urllib.request.urlopen",
        side_effect=[tags_resp, http_err, list_resp],
    ):
        provider = OllamaProvider(model="missing", load_dotenv=False)
        with pytest.raises(RuntimeError, match="Ollama model 'missing' not found"):
            provider.generate("prompt")


def test_ollama_generate_server_down_mid_request(monkeypatch: pytest.MonkeyPatch):
    """URLError during generate is wrapped with a reachability message."""
    tags_resp = _mock_urlopen_ok()

    with patch(
        "devguard.ai_provider.urllib.request.urlopen",
        side_effect=[tags_resp, URLError("timed out")],
    ):
        provider = OllamaProvider(load_dotenv=False)
        with pytest.raises(RuntimeError, match="server unreachable"):
            provider.generate("prompt")


# ---------------------------------------------------------------------------
# create_provider factory
# ---------------------------------------------------------------------------


def test_create_provider_explicit_gemini(monkeypatch: pytest.MonkeyPatch):
    """Explicit provider_name='gemini' returns GeminiProvider."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    provider = create_provider(provider_name="gemini", load_dotenv=False)
    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"


def test_create_provider_explicit_ollama(monkeypatch: pytest.MonkeyPatch):
    """Explicit provider_name='ollama' returns OllamaProvider."""
    with patch("devguard.ai_provider.urllib.request.urlopen", return_value=_mock_urlopen_ok()):
        provider = create_provider(provider_name="ollama", model="mistral", load_dotenv=False)
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "mistral"


def test_create_provider_from_env(monkeypatch: pytest.MonkeyPatch):
    """DEVGUARD_AI_PROVIDER selects the provider."""
    monkeypatch.setenv("DEVGUARD_AI_PROVIDER", "ollama")
    with patch("devguard.ai_provider.urllib.request.urlopen", return_value=_mock_urlopen_ok()):
        provider = create_provider(load_dotenv=False)
    assert isinstance(provider, OllamaProvider)


def test_create_provider_auto_detect_gemini(monkeypatch: pytest.MonkeyPatch):
    """Auto-detect prefers Gemini when GEMINI_API_KEY is set."""
    monkeypatch.delenv("DEVGUARD_AI_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "real-key")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2")
    provider = create_provider(load_dotenv=False)
    assert isinstance(provider, GeminiProvider)


def test_create_provider_auto_detect_ollama(monkeypatch: pytest.MonkeyPatch):
    """Auto-detect falls back to Ollama when only OLLAMA_* vars are set."""
    monkeypatch.delenv("DEVGUARD_AI_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "codellama")
    with patch("devguard.ai_provider.urllib.request.urlopen", return_value=_mock_urlopen_ok()):
        provider = create_provider(load_dotenv=False)
    assert isinstance(provider, OllamaProvider)
    assert provider.model == "codellama"


def test_create_provider_unknown_raises(monkeypatch: pytest.MonkeyPatch):
    """Unsupported provider names raise ValueError."""
    with pytest.raises(ValueError, match="Unknown AI provider"):
        create_provider(provider_name="chatgpt", load_dotenv=False)
