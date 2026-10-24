"""Thin LLM clients (Gemini, OpenAI-compatible, Anthropic) over plain HTTPS.

The user brings their own key: from the environment / `.env`, or typed into a hidden
prompt (kept in memory for this run only, never written to disk).
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import sys
import time
from abc import ABC, abstractmethod
from typing import Optional

import requests

from .errors import ConfigError, LLMError

log = logging.getLogger(__name__)
_sleep = time.sleep  # patched in tests

PROVIDERS = ("gemini", "openai", "anthropic")
DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-5-5",
}
KEY_ENV = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
}
OPENAI_DEFAULT_BASE = "https://api.openai.com/v1"


def _error_message(resp: requests.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error", body) if isinstance(body, dict) else body
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return (msg or resp.text)[:300]
    except ValueError:
        return resp.text[:300]


def _post_json(url: str, headers: dict, payload: dict, timeout: int = 180, max_attempts: int = 4) -> dict:
    """POST with retries on network errors, 408/429 and 5xx. Auth errors fail fast."""
    last = "unknown error"
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last = f"network error ({type(exc).__name__})"
        else:
            if resp.status_code == 200:
                try:
                    return resp.json()
                except ValueError:
                    raise LLMError("The API returned a non-JSON response.") from None
            if resp.status_code in (401, 403):
                raise LLMError(f"Authentication failed (HTTP {resp.status_code}). Check your API key. {_error_message(resp)}")
            if resp.status_code in (408, 429) or resp.status_code >= 500:
                last = f"HTTP {resp.status_code}: {_error_message(resp)}"
            else:
                raise LLMError(f"API error (HTTP {resp.status_code}): {_error_message(resp)}")
        if attempt < max_attempts:
            delay = min(2**attempt, 30)
            log.warning("LLM request failed (%s); retrying in %ss (%d/%d)", last, delay, attempt, max_attempts)
            _sleep(delay)
    raise LLMError(f"LLM request failed after {max_attempts} attempts: {last}")


class LLMClient(ABC):
    provider: str

    def __init__(self, model: str, api_key: str):
        self.model = model
        self._api_key = api_key

    @abstractmethod
    def complete_json(self, system: str, user: str) -> str:
        """Return the model's raw text reply, which is expected to be JSON."""


class GeminiClient(LLMClient):
    provider = "gemini"

    def complete_json(self, system: str, user: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "maxOutputTokens": 8192,
            },
        }
        data = _post_json(url, {"x-goog-api-key": self._api_key}, payload)
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError):
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates returned")
            raise LLMError(f"Gemini returned no usable content ({reason}).") from None


class OpenAIClient(LLMClient):
    provider = "openai"

    def complete_json(self, system: str, user: str) -> str:
        base = os.environ.get("OPENAI_BASE_URL", OPENAI_DEFAULT_BASE).rstrip("/")
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
        }
        data = _post_json(f"{base}/chat/completions", {"Authorization": f"Bearer {self._api_key}"}, payload)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError("OpenAI-compatible API returned an unexpected response shape.") from None


class AnthropicClient(LLMClient):
    provider = "anthropic"

    def complete_json(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": 8192,  # no temperature: newer Claude models reject it
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {"x-api-key": self._api_key, "anthropic-version": "2023-06-01"}
        data = _post_json("https://api.anthropic.com/v1/messages", headers, payload)
        try:
            return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")
        except (KeyError, TypeError):
            raise LLMError("Anthropic API returned an unexpected response shape.") from None


_CLIENTS = {"gemini": GeminiClient, "openai": OpenAIClient, "anthropic": AnthropicClient}


def _env_key(provider: str) -> Optional[str]:
    for var in KEY_ENV[provider]:
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return None


def _can_prompt() -> bool:
    return sys.stdin.isatty() and sys.stderr.isatty()


def resolve_provider(provider: Optional[str] = None) -> str:
    provider = (provider or os.environ.get("LLM_PROVIDER") or "").strip().lower() or None
    if provider:
        if provider not in PROVIDERS:
            raise ConfigError(f"Unknown LLM provider {provider!r}. Choose one of: {', '.join(PROVIDERS)}.")
        return provider
    detected = [p for p in PROVIDERS if _env_key(p)]
    if detected:
        return detected[0]
    if _can_prompt():
        choice = input(f"No API key found. LLM provider [{'/'.join(PROVIDERS)}]: ").strip().lower()
        if choice in PROVIDERS:
            return choice
        raise ConfigError(f"Unknown LLM provider {choice!r}.")
    raise ConfigError(
        "No LLM API key found. Set GEMINI_API_KEY, OPENAI_API_KEY or ANTHROPIC_API_KEY "
        "(in your terminal or a .env file). See README.md."
    )


def build_client(provider: Optional[str] = None, model: Optional[str] = None) -> LLMClient:
    provider = resolve_provider(provider)
    key = _env_key(provider)
    if not key and provider == "openai" and os.environ.get("OPENAI_BASE_URL"):
        key = "not-needed"  # local OpenAI-compatible servers (Ollama, vLLM) ignore the key
    if not key:
        if not _can_prompt():
            raise ConfigError(f"No API key for '{provider}'. Set {KEY_ENV[provider][0]} in your terminal or .env file.")
        key = getpass.getpass(f"Enter your {provider} API key (hidden, not saved): ").strip()
        if not key:
            raise ConfigError("No API key entered.")
    model = model or os.environ.get("MODEL_NAME") or DEFAULT_MODELS[provider]
    return _CLIENTS[provider](model, key)


def extract_json(text: str) -> dict:
    """Parse a JSON object from model text, tolerating code fences and stray prose."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])
