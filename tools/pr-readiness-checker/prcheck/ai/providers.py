"""Model providers behind one small interface, so the review (and later the
fix-mode agent) can swap Gemini for another model or a canned test double."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_TIMEOUT_SECONDS = 30
SERVER_RETRY_DELAYS = (2, 5)  # seconds to wait before retry 1 and retry 2


class ProviderUnavailable(RuntimeError):
    """The provider can't be used here (missing package or API key). Not a crash."""


class ProviderError(RuntimeError):
    """The provider call failed (network, quota, server error)."""


@dataclass
class ProviderResponse:
    text: str
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None


class ReviewProvider(Protocol):
    name: str
    model: str

    def generate(self, *, system: str, prompt: str, schema: dict[str, Any]) -> ProviderResponse: ...


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str | None = None, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            raise ProviderUnavailable("GEMINI_API_KEY is not set (put it in .env or your environment).")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ProviderUnavailable("The AI extra is not installed: pip install -e \".[ai]\"") from exc
        self._types = types
        self.model = model or os.environ.get("MODEL_NAME") or DEFAULT_GEMINI_MODEL
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=timeout_seconds * 1000),
        )

    def generate(self, *, system: str, prompt: str, schema: dict[str, Any]) -> ProviderResponse:
        from google.genai import errors

        config = self._types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        started = time.perf_counter()
        try:
            response = self._call_with_retries(prompt, config, errors)
        except errors.ClientError as exc:
            code = getattr(exc, "code", None)
            if code == 429:
                raise ProviderError("Gemini rate limit or quota reached; try again later.") from exc
            if code in (401, 403):
                raise ProviderError("Gemini rejected the API key (check GEMINI_API_KEY).") from exc
            raise ProviderError(f"Gemini request failed ({code}): {exc}") from exc
        except errors.APIError as exc:
            raise ProviderError(f"Gemini server error: {exc}") from exc
        except Exception as exc:  # network errors, timeouts
            raise ProviderError(f"Could not reach Gemini: {type(exc).__name__}: {exc}") from exc

        usage = response.usage_metadata
        return ProviderResponse(
            text=response.text or "",
            prompt_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    def _call_with_retries(self, prompt: str, config: Any, errors: Any) -> Any:
        """Retry temporary server errors (5xx, e.g. 503 'high demand') with backoff; never retry 4xx."""
        for delay in (*SERVER_RETRY_DELAYS, None):
            try:
                return self._client.models.generate_content(model=self.model, contents=prompt, config=config)
            except errors.ServerError:
                if delay is None:
                    raise
                time.sleep(delay)
        raise AssertionError("unreachable")


class StaticProvider:
    """Returns canned responses in order. Used by tests and offline evals."""

    name = "static"

    def __init__(self, responses: list[str | Exception], model: str = "static-test-model"):
        self.model = model
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def generate(self, *, system: str, prompt: str, schema: dict[str, Any]) -> ProviderResponse:
        self.calls.append({"system": system, "prompt": prompt, "schema": schema})
        if not self._responses:
            raise ProviderError("StaticProvider ran out of responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return ProviderResponse(text=item, prompt_tokens=len(prompt) // 4, output_tokens=len(item) // 4, latency_ms=1)
