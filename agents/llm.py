"""Pluggable LLM providers. Plain HTTPS via `requests`, so there are no vendor SDKs to install.

Select with LLM_PROVIDER=mock|anthropic|openai|gemini (default: mock, which needs no API key).
"""
from __future__ import annotations

import os
import re
import time
from urllib.parse import urlsplit
import ipaddress
import socket
from abc import ABC, abstractmethod

import requests
from .guardrails import allow_remote, validate_base_url
from .guardrails import GuardrailError


class LLMError(RuntimeError):
    pass


class Provider(ABC):
    name = "base"

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str: ...


def validate_endpoint(url: str, local: bool = False) -> None:
    parsed = urlsplit(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LLMError('Endpoint URL must not contain credentials, query, or fragment')
    if parsed.scheme not in ({'http', 'https'} if local else {'https'}):
        raise LLMError('Hosted endpoints require HTTPS')
    host = parsed.hostname or ''
    if local:
        if host not in ('localhost', '127.0.0.1', '::1'):
            raise LLMError('Local model endpoint must use localhost or loopback IP')
    elif not host or host.lower() not in ('api.openai.com',):
        raise LLMError('OpenAI endpoint must be api.openai.com; other hosts are not trusted')


def _post_json(url: str, headers: dict, payload: dict, retries: int = 2) -> dict:
    # Never echo response bodies, transport exceptions or headers: may contain secrets.
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=(5, 45), allow_redirects=False)
        except requests.RequestException:
            raise LLMError('Model request failed (network/timeout)') from None
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                raise LLMError('Model returned invalid JSON') from None
        if r.status_code not in (429, 500, 502, 503, 529) or attempt == retries:
            raise LLMError(f'Model returned HTTP {r.status_code}')
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    raise LLMError('Model request failed')


class MockProvider(Provider):
    """Deterministic offline stand-in so the demo and tests run with zero setup."""

    name = "mock"

    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        if "[[TASK:SUMMARY]]" in system:
            m = re.search(r"FINDINGS_TOTAL: (\d+)", user)
            n = int(m.group(1)) if m else 0
            files = re.search(r"FILES_CHANGED: (\d+)", user)
            return (
                f"This PR touches {files.group(1) if files else '?'} file(s) and the automated "
                f"checks raised {n} finding(s). Address the highest-severity items first, then "
                f"re-run the review. (Mock provider: set LLM_PROVIDER for a real model summary.)"
            )
        m = re.search(r"ADDED_LINES: (\d+)", user)
        if m and int(m.group(1)) > 80:
            return ('[{"line": 1, "severity": "low", "category": "quality", '
                    '"title": "Large change in one file", '
                    '"detail": "Over 80 lines were added to this file.", '
                    '"suggestion": "Consider splitting into smaller modules."}]')
        return "[]"


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self) -> None:
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        allow_remote()
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            {"model": self.model, "max_tokens": max_tokens, "system": system,
             "messages": [{"role": "user", "content": user}]},
        )
        return "".join(b.get("text", "") for b in data.get("content", []))


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self) -> None:
        self.key = os.environ.get("OPENAI_API_KEY")
        if not self.key:
            raise LLMError("OPENAI_API_KEY is not set")
        allow_remote()
        self.model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.base = validate_base_url(os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        validate_endpoint(self.base)

    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        data = _post_json(
            f"{self.base}/chat/completions",
            {"Authorization": f"Bearer {self.key}"},
            {"model": self.model, "max_tokens": max_tokens,
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        )
        return data["choices"][0]["message"]["content"] or ""


class OllamaProvider(Provider):
    name = 'ollama'

    def __init__(self) -> None:
        self.model = os.getenv('OLLAMA_MODEL', 'qwen2.5-coder:7b')
        self.base = os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434/v1').rstrip('/')
        validate_endpoint(self.base, local=True)

    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        data = _post_json(f'{self.base}/chat/completions', {}, {
            'model': self.model, 'max_tokens': max_tokens,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]
        })
        return data['choices'][0]['message']['content'] or ''


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self) -> None:
        self.key = os.environ.get("GEMINI_API_KEY")
        if not self.key:
            raise LLMError("GEMINI_API_KEY is not set")
        allow_remote()
        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        data = _post_json(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            {"x-goog-api-key": self.key},
            {"systemInstruction": {"parts": [{"text": system}]},
             "contents": [{"role": "user", "parts": [{"text": user}]}],
             "generationConfig": {"maxOutputTokens": max_tokens}},
        )
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)


class OllamaProvider(Provider):
    name = "ollama"
    def __init__(self):
        self.model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
        self.base = validate_base_url(os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"), local=True)
    def complete(self, system: str, user: str, max_tokens: int = 1000) -> str:
        data = _post_json(f"{self.base}/chat/completions", {},
            {"model": self.model, "max_tokens": max_tokens,
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
        return data["choices"][0]["message"]["content"] or ""

PROVIDERS = {
    "mock": MockProvider,
    "ollama": OllamaProvider,
    "ollama": OllamaProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}


def get_provider(name: str | None = None) -> Provider:
    name = (name or os.environ.get("LLM_PROVIDER") or "mock").lower()
    if name not in PROVIDERS:
        raise LLMError(f"Unknown provider '{name}'. Choose from: {', '.join(PROVIDERS)}")
    return PROVIDERS[name]()
