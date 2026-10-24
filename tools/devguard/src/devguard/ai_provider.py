"""AI provider adapters for DevGuard.

Supported providers:
- ``GeminiProvider``  — Google Gemini via the official ``google-genai`` SDK.
- ``OllamaProvider``  — Local Ollama server via its REST API (stdlib only, no extra deps).

Use :func:`create_provider` to select a provider from environment variables or
explicit arguments without coupling call-sites to concrete classes.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol


class AIProvider(Protocol):
    """Protocol for AI text generation providers."""

    #: Human-readable provider name used in output labels (e.g. "gemini", "ollama").
    name: str

    def generate(self, prompt: str) -> str:
        ...


def _load_env_file() -> None:
    """Best-effort loader for .env files without requiring python-dotenv."""
    for candidate in [Path(".env"), Path("tools/devguard/.env"), Path(__file__).resolve().parents[2] / ".env"]:
        if candidate.exists() and candidate.is_file():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Gemini provider
# ---------------------------------------------------------------------------

class GeminiProvider:
    """Google Gemini model adapter using the official google-genai SDK."""

    name: str = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        load_dotenv: bool = True,
    ) -> None:
        if load_dotenv:
            _load_env_file()
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key or key == "your_gemini_api_key_here":
            raise ValueError(
                "GEMINI_API_KEY is not configured. Set GEMINI_API_KEY in your environment "
                "or .env file, or use --fallback for deterministic message generation."
            )

        self.api_key = key
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise RuntimeError(
                    "Optional dependency 'google-genai' is not installed. "
                    "Install it using: pip install 'devguard[ai]', or run with --fallback."
                ) from exc
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate(self, prompt: str) -> str:
        """Send prompt to Gemini model and return response text."""
        client = self._get_client()
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            return (response.text or "").strip()
        except Exception as exc:
            raise RuntimeError(f"Gemini API request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Ollama provider
# ---------------------------------------------------------------------------

_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"
_OLLAMA_DEFAULT_MODEL = "llama3.2"


class OllamaProvider:
    """Local Ollama provider that talks to the Ollama REST API.

    Requires a running ``ollama serve`` instance (default: http://localhost:11434).
    Uses only Python stdlib — no extra dependencies.

    Environment variables
    ---------------------
    OLLAMA_BASE_URL
        Base URL of the Ollama server. Defaults to ``http://localhost:11434``.
    OLLAMA_MODEL
        Model tag to use (e.g. ``llama3.2``, ``mistral``, ``codellama``).
        Defaults to ``llama3.2``.
    """

    name: str = "ollama"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        load_dotenv: bool = True,
        timeout: int = 120,
    ) -> None:
        if load_dotenv:
            _load_env_file()

        self.base_url = (
            (base_url or os.getenv("OLLAMA_BASE_URL", _OLLAMA_DEFAULT_BASE_URL)).rstrip("/")
        )
        self.model = model or os.getenv("OLLAMA_MODEL", _OLLAMA_DEFAULT_MODEL)
        self.timeout = timeout

        # Validate connectivity eagerly so callers get a clear error up-front.
        self._check_server()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_server(self) -> None:
        """Ping the Ollama server to confirm it is reachable."""
        url = f"{self.base_url}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5):
                pass
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama server is not reachable at '{self.base_url}'. "
                "Ensure 'ollama serve' is running, or set OLLAMA_BASE_URL to the correct address. "
                f"(Error: {exc.reason})"
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"Ollama server is not reachable at '{self.base_url}': {exc}"
            ) from exc

    def _list_local_models(self) -> list[str]:
        """Return a list of locally pulled model names."""
        url = f"{self.base_url}/api/tags"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, prompt: str) -> str:
        """Send *prompt* to the Ollama /api/generate endpoint and return the response text.

        Uses the non-streaming endpoint (``stream: false``) so the full response
        is returned in a single JSON payload.
        """
        url = f"{self.base_url}/api/generate"
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode())
                text = data.get("response", "").strip()
                if not text:
                    raise RuntimeError("Ollama returned an empty response.")
                return text
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            # Surface "model not found" with a helpful message
            if exc.code == 404 or "model" in body.lower():
                available = self._list_local_models()
                hint = (
                    f"Available locally: {', '.join(available)}" if available
                    else "No models pulled yet — run: ollama pull <model>"
                )
                raise RuntimeError(
                    f"Ollama model '{self.model}' not found. {hint}\n"
                    f"Pull it with: ollama pull {self.model}"
                ) from exc
            raise RuntimeError(f"Ollama API error {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Ollama request failed (server unreachable at '{self.base_url}'): {exc.reason}"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

_PROVIDER_CHOICES = ("gemini", "ollama")


def create_provider(
    provider_name: str | None = None,
    model: str | None = None,
    load_dotenv: bool = True,
) -> AIProvider:
    """Instantiate and return the requested AI provider.

    Resolution order for *provider_name*:

    1. Explicit argument passed by the caller.
    2. ``DEVGUARD_AI_PROVIDER`` environment variable.
    3. Falls back to ``"gemini"`` if ``GEMINI_API_KEY`` is set.
    4. Falls back to ``"ollama"`` if ``OLLAMA_BASE_URL`` / ``OLLAMA_MODEL`` is set.
    5. Defaults to ``"gemini"``.

    Args:
        provider_name: One of ``"gemini"`` or ``"ollama"``.
        model: Model identifier (provider-specific). Overrides env vars.
        load_dotenv: Whether to attempt loading a ``.env`` file.

    Returns:
        An :class:`AIProvider` instance.

    Raises:
        ValueError: If an unsupported provider name is given.
        RuntimeError: If the selected provider cannot be initialised.
    """
    if load_dotenv:
        _load_env_file()

    if provider_name is None:
        provider_name = os.getenv("DEVGUARD_AI_PROVIDER")

    if provider_name is None:
        # Auto-detect: prefer Gemini if its key is present, else Ollama if its
        # URL/model env vars are present, else default to Gemini (will raise a
        # clear error if the key is missing).
        gemini_key = os.getenv("GEMINI_API_KEY", "")
        ollama_url = os.getenv("OLLAMA_BASE_URL", "")
        ollama_model = os.getenv("OLLAMA_MODEL", "")
        if gemini_key and gemini_key != "your_gemini_api_key_here":
            provider_name = "gemini"
        elif ollama_url or ollama_model:
            provider_name = "ollama"
        else:
            provider_name = "gemini"

    provider_name = provider_name.lower().strip()
    if provider_name not in _PROVIDER_CHOICES:
        raise ValueError(
            f"Unknown AI provider '{provider_name}'. "
            f"Supported providers: {', '.join(_PROVIDER_CHOICES)}. "
            "Set DEVGUARD_AI_PROVIDER in your environment or pass --provider."
        )

    if provider_name == "gemini":
        return GeminiProvider(model=model, load_dotenv=False)
    else:  # ollama
        return OllamaProvider(model=model, load_dotenv=False)

