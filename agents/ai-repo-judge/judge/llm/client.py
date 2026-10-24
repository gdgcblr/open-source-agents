"""Provider-agnostic chat client. Every provider is reached through the OpenAI-compatible
`/chat/completions` endpoint, so switching between Groq, Gemini, OpenRouter, Ollama or any custom
endpoint is configuration, not code. Providers are tried in order; a quota error moves to the next.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field

import httpx

from judge.llm.ratelimit import RateLimiter, parse_duration

log = logging.getLogger(__name__)


@dataclass
class ProviderSpec:
    name: str
    base_url: str
    model: str
    api_key: str | None
    tpm: int
    rpm: int
    timeout: float
    extra: dict = field(default_factory=dict)


DEFAULTS = {
    "groq": dict(
        base_url="https://api.groq.com/openai/v1",
        key="GROQ_API_KEY",
        model="openai/gpt-oss-120b",
        tpm=8000,
        rpm=30,
        timeout=90,
        extra={"reasoning_effort": "low"},
    ),
    "gemini": dict(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        key="GEMINI_API_KEY",
        model="gemini-flash-latest",
        tpm=200_000,
        rpm=8,
        timeout=240,
        extra={"reasoning_effort": "low"},
    ),
    "openrouter": dict(
        base_url="https://openrouter.ai/api/v1",
        key="OPENROUTER_API_KEY",
        model="openai/gpt-oss-20b:free",
        tpm=20_000,
        rpm=15,
        timeout=120,
        extra={},
    ),
    "ollama": dict(
        base_url="http://localhost:11434/v1",
        key=None,
        model="qwen2.5:7b",
        tpm=1_000_000,
        rpm=1000,
        timeout=600,
        extra={},
    ),
    "custom": dict(base_url="", key="LLM_API_KEY", model="", tpm=50_000, rpm=60, timeout=120, extra={}),
}


class LLMError(RuntimeError):
    pass


class QuotaExhausted(LLMError):
    """The provider's quota will not recover soon (e.g. daily limit); try the next provider."""


@dataclass
class ChatResult:
    text: str
    provider: str
    model: str
    tokens: int


def provider_from_env(name: str) -> ProviderSpec | None:
    name = name.strip().lower()
    if name not in DEFAULTS:
        raise LLMError(f"unknown LLM provider {name!r}; choose from {', '.join(DEFAULTS)} or mock")
    d = DEFAULTS[name]
    up = name.upper()
    key = os.getenv(d["key"]) if d["key"] else None
    if name == "gemini":
        key = key or os.getenv("GOOGLE_API_KEY")
    base_url = os.getenv(f"{up}_BASE_URL") or (os.getenv("LLM_BASE_URL") if name == "custom" else None) or d["base_url"]
    model = os.getenv(f"{up}_MODEL") or (os.getenv("LLM_MODEL") if name == "custom" else None) or d["model"]
    if (d["key"] and not key) or not base_url or not model:
        return None
    return ProviderSpec(
        name=name,
        base_url=base_url.rstrip("/"),
        model=model,
        api_key=key,
        tpm=int(os.getenv(f"{up}_TPM", d["tpm"])),
        rpm=int(os.getenv(f"{up}_RPM", d["rpm"])),
        timeout=float(os.getenv(f"{up}_TIMEOUT", d["timeout"])),
        extra=dict(d["extra"]),
    )


class ChatClient:
    """Ordered list of providers with per-provider rate limiting, retries and fallback."""

    def __init__(
        self,
        providers: list[ProviderSpec],
        max_retries: int = 4,
        sleep=time.sleep,
        transport: httpx.BaseTransport | None = None,
    ):
        if not providers:
            raise LLMError("no LLM provider configured")
        self.providers = providers
        self.max_retries = max_retries
        self._sleep = sleep
        self._limiters = {p.name: RateLimiter(p.tpm, p.rpm, sleep=sleep) for p in providers}
        self._dead: set[str] = set()
        self._http = httpx.Client(transport=transport) if transport else httpx.Client()

    @classmethod
    def from_env(cls) -> ChatClient:
        primary = os.getenv("LLM_PROVIDER", "groq")
        fallbacks = [p for p in os.getenv("LLM_FALLBACK_PROVIDERS", "").split(",") if p.strip()]
        specs = []
        for name in [primary, *fallbacks]:
            spec = provider_from_env(name)
            if spec is None:
                log.warning("LLM provider %s is not configured (missing key/model); skipping", name)
            elif spec.name not in {s.name for s in specs}:
                specs.append(spec)
        return cls(specs)

    @property
    def available(self) -> list[str]:
        return [p.name for p in self.providers if p.name not in self._dead]

    def chat_json(self, system: str, user: str, max_tokens: int = 1800) -> ChatResult:
        errors = []
        for spec in self.providers:
            if spec.name in self._dead:
                continue
            try:
                return self._call(spec, system, user, max_tokens)
            except QuotaExhausted as exc:
                log.warning("%s quota exhausted: %s; falling back", spec.name, exc)
                self._dead.add(spec.name)
                errors.append(f"{spec.name}: {exc}")
            except LLMError as exc:
                log.warning("%s failed: %s; falling back", spec.name, exc)
                errors.append(f"{spec.name}: {exc}")
        raise LLMError("; ".join(errors) or "all providers exhausted")

    def _call(self, spec: ProviderSpec, system: str, user: str, max_tokens: int) -> ChatResult:
        limiter = self._limiters[spec.name]
        estimate = (len(system) + len(user)) // 3 + max_tokens
        body = {
            "model": spec.model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            **spec.extra,
        }
        headers = {"Content-Type": "application/json"}
        if spec.api_key:
            headers["Authorization"] = f"Bearer {spec.api_key}"
        last = ""
        for attempt in range(self.max_retries + 1):
            limiter.acquire(estimate)
            try:
                resp = self._http.post(
                    f"{spec.base_url}/chat/completions", json=body, headers=headers, timeout=spec.timeout
                )
            except httpx.HTTPError as exc:
                last = f"network error: {exc}"
                self._sleep(min(30, 2**attempt * 2))
                continue
            limiter.update_from_headers(resp.headers)
            if resp.status_code == 429:
                wait = (
                    parse_duration(resp.headers.get("retry-after"))
                    or parse_duration(resp.headers.get("x-ratelimit-reset-tokens"))
                    or parse_duration(resp.headers.get("x-ratelimit-reset-requests"))
                    or 2**attempt * 5
                )
                if wait > 90 or re.search(r"per ?day|\bTPD\b|\bRPD\b", resp.text, re.I):
                    raise QuotaExhausted(f"daily quota reached (retry in {wait:.0f}s)")
                log.info("%s rate limited; waiting %.1fs", spec.name, wait)
                limiter.block_for(wait + 0.5)
                last = "429 rate limited"
                continue
            if resp.status_code in (401, 403):
                raise QuotaExhausted(f"HTTP {resp.status_code}: check the API key")
            if resp.status_code == 400 and spec.extra and "reasoning" in resp.text:
                spec.extra = {}  # model does not support reasoning_effort; retry without it
                body = {k: v for k, v in body.items() if k != "reasoning_effort"}
                continue
            if resp.status_code >= 500 or resp.status_code == 408:
                last = f"HTTP {resp.status_code}"
                self._sleep(min(30, 2**attempt * 2))
                continue
            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            try:
                text = data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError) as exc:
                raise LLMError(f"unexpected response shape: {str(data)[:200]}") from exc
            tokens = int((data.get("usage") or {}).get("total_tokens") or estimate)
            limiter.record(tokens)
            return ChatResult(text=text, provider=spec.name, model=spec.model, tokens=tokens)
        raise LLMError(f"gave up after {self.max_retries + 1} attempts ({last})")
